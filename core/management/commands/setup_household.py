"""First administrator is created only from the host console, before serving."""
from getpass import getpass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, UsernameField
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from core.models import HouseholdSettings, MemberRole


class FirstAdminForm(UserCreationForm):
    username = UsernameField(max_length=10, label="管理员账号")


class Command(BaseCommand):
    help = "空数据库首次创建家庭与管理员；已有用户永不重置。"

    def add_arguments(self, parser):
        parser.add_argument("--time-zone", required=True)

    def handle(self, *args, **options):
        User = get_user_model()
        if User.objects.exists():
            if not MemberRole.objects.filter(role="admin", user__is_active=True).exists():
                raise CommandError("已有账号但没有可用管理员；请用 manage_member 在本机维护，不会重新初始化。")
            self.stdout.write("已有管理员，账号和家庭资料保持不变。")
            return
        try:
            ZoneInfo(options["time_zone"])
        except ZoneInfoNotFoundError as exc:
            raise CommandError("时区无效。") from exc
        name = input("家庭名称（回车使用“我的家庭”）：").strip() or "我的家庭"
        if len(name) > 80 or any(ord(c) < 32 for c in name):
            raise CommandError("家庭名称无效。")
        while True:
            form = FirstAdminForm({"username": input("创建管理员账号（最多 10 个字符）：").strip(),
                "password1": getpass("密码（不回显，至少 8 个字符）："),
                "password2": getpass("再次输入密码：")})
            if form.is_valid():
                break
            for field, errors in form.errors.items():
                self.stderr.write(f"{form.fields[field].label if field in form.fields else '账号'}：{'；'.join(errors)}")
        user = form.save(commit=False)  # Django hashes before acquiring the write transaction.
        with transaction.atomic():
            if User.objects.exists():
                raise CommandError("已有其他初始化完成，本次未写入。")
            user.save()
            MemberRole.objects.create(user=user, role="admin")
            HouseholdSettings.objects.get_or_create(id=1, defaults={"display_name": name, "time_zone": options["time_zone"]})
        self.stdout.write("家庭管理员已创建。登录后可在家庭设置邀请其他成员。")
