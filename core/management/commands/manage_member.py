"""Interactive, local-only household account operations."""

from getpass import getpass
from ipaddress import ip_address

from axes.utils import reset as reset_axes
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.contrib.sessions.models import Session

from core.models import MemberRole


class Command(BaseCommand):
    help = "在本机交互管理家庭成员账号与登录锁定。"

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest="operation", required=True)
        create = subparsers.add_parser("create", help="创建成员或管理员")
        create.add_argument("username")
        create.add_argument("--role", choices=MemberRole.Role.values, required=True)
        password = subparsers.add_parser("password", help="交互修改密码")
        password.add_argument("username")
        for operation in ("disable", "enable"):
            subparsers.add_parser(operation).add_argument("username")
        unlock = subparsers.add_parser("unlock", help="解除指定账号或来源 IP 的登录锁定")
        unlock.add_argument("--username")
        unlock.add_argument("--ip")

    def _password(self, user):
        first = getpass("新密码（不回显）：")
        second = getpass("再次输入：")
        if first != second:
            raise CommandError("两次密码不一致。")
        try:
            validate_password(first, user=user)
        except ValidationError as exc:
            raise CommandError("密码不符合规则：" + "；".join(exc.messages)) from exc
        return first

    @staticmethod
    def _revoke_sessions(user):
        for session in Session.objects.all().iterator():
            if session.get_decoded().get("_auth_user_id") == str(user.pk):
                session.delete()

    def handle(self, *args, **options):
        operation = options["operation"]
        if operation == "unlock":
            username = options.get("username")
            client_ip = options.get("ip")
            if not username and not client_ip:
                raise CommandError("请指定 --username 或 --ip。")
            if client_ip:
                try:
                    client_ip = str(ip_address(client_ip))
                except ValueError as exc:
                    raise CommandError("IP 地址无效。") from exc
            if username:
                reset_axes(username=username)
            if client_ip:
                reset_axes(ip=client_ip)
            self.stdout.write("指定锁定记录已清除。")
            return

        User = get_user_model()
        username = options["username"]
        if operation == "create":
            user = User(username=username)
            try:
                user.full_clean(exclude=["password"])
            except ValidationError as exc:
                raise CommandError("账号无效或已存在：" + "；".join(exc.messages)) from exc
            password = self._password(user)
            with transaction.atomic():
                user.set_password(password)
                user.save()
                MemberRole.objects.create(user=user, role=options["role"])
            self.stdout.write("账号已创建。")
            return

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise CommandError("账号不存在。") from exc
        if operation == "password":
            password = self._password(user)
            with transaction.atomic():
                user.set_password(password)
                user.save(update_fields=["password"])
                self._revoke_sessions(user)
            self.stdout.write("密码已更新，旧会话将失效。")
        else:
            with transaction.atomic():
                user.is_active = operation == "enable"
                user.save(update_fields=["is_active"])
                if operation == "disable":
                    self._revoke_sessions(user)
            self.stdout.write("账号状态已更新。")
