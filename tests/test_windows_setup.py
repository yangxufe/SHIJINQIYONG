"""Isolated setup/account tests. No machine trust, firewall or real accounts."""
from datetime import timedelta
from contextlib import closing
from io import StringIO
import json
from pathlib import Path
import socket
import sqlite3
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, SimpleTestCase, TestCase
from django.utils import timezone

from core.forms import INVITATION_SALT
from core.models import HouseholdSettings, MemberInvitation, MemberRole
from core.management.commands.backup_household import create_private_backup
from scripts import windows_runtime as runtime


class FirstHouseholdTests(TestCase):
    def test_first_admin_validated_and_rerun_preserves_existing(self):
        with patch('builtins.input', side_effect=['合成家庭', 'family']), patch('core.management.commands.setup_household.getpass', side_effect=['Synthetic!first2026', 'Synthetic!first2026']):
            call_command('setup_household', time_zone='Asia/Shanghai', stdout=StringIO())
        user = get_user_model().objects.get()
        self.assertEqual(user.member_role.role, 'admin')
        self.assertTrue(user.check_password('Synthetic!first2026'))
        self.assertFalse(user.is_superuser)
        original = user.password
        with patch('builtins.input', side_effect=AssertionError('Must not prompt for an existing household')):
            call_command('setup_household', time_zone='UTC', stdout=StringIO())
        user.refresh_from_db()
        self.assertEqual(user.password, original)
        self.assertEqual(HouseholdSettings.objects.get().time_zone, 'Asia/Shanghai')

    def test_invalid_password_and_username_retry_without_partial_account(self):
        with patch('builtins.input', side_effect=['家庭', 'username-too-long', 'normal']), patch('core.management.commands.setup_household.getpass', side_effect=['123', '123', 'Synthet!c-retRy2026', 'Synthet!c-retRy2026']):
            call_command('setup_household', time_zone='UTC', stdout=StringIO(), stderr=StringIO())
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(get_user_model().objects.get().username, 'normal')

    def test_existing_member_cannot_be_silently_promoted_by_setup(self):
        user = get_user_model().objects.create_user('existing')
        MemberRole.objects.create(user=user, role='member')
        with self.assertRaises(CommandError):
            call_command('setup_household', time_zone='UTC')
        self.assertEqual(user.member_role.role, 'member')


class AccountLifecycleTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('member', password='Original!Test2026')
        MemberRole.objects.create(user=self.user, role='member')
        self.admin = get_user_model().objects.create_user('admin', password='Original!Admin2026')
        MemberRole.objects.create(user=self.admin, role='admin')
        self.client.force_login(self.user, backend='django.contrib.auth.backends.ModelBackend')

    def password_payload(self, old='Original!Test2026'):
        return {'old_password': old, 'new_password1': 'Updated!test2026', 'new_password2': 'Updated!test2026'}

    def test_password_change_keeps_self_and_invalidates_other_sessions(self):
        other = Client()
        other.force_login(self.user, backend='django.contrib.auth.backends.ModelBackend')
        result = self.client.post('/account/password/', self.password_payload(), secure=True)
        self.assertRedirects(result, '/settings/', fetch_redirect_response=False)
        self.assertEqual(self.client.get('/inventory/list/', secure=True).status_code, 200)
        self.assertEqual(other.get('/inventory/list/', secure=True).status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Updated!test2026'))
        self.assertTrue(self.admin.check_password('Original!Admin2026'))

    def test_old_password_weak_password_csrf_and_anonymous_rejected(self):
        self.assertEqual(Client().post('/account/password/', self.password_payload(), secure=True).status_code, 302)
        for payload in (self.password_payload('wrong'), {**self.password_payload(), 'new_password1':'123', 'new_password2':'123'}):
            response = self.client.post('/account/password/', payload, secure=True)
            self.assertTrue(response.context['form'].errors)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.user, backend='django.contrib.auth.backends.ModelBackend')
        self.assertEqual(csrf.post('/account/password/', self.password_payload(), secure=True).status_code, 403)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Original!Test2026'))

    def test_admin_can_revoke_invite_and_member_cannot(self):
        invite = MemberInvitation.objects.create(created_by=self.admin, expires_at=timezone.now()+timedelta(hours=24))
        token = signing.dumps(str(invite.pk), salt=INVITATION_SALT)
        self.assertEqual(self.client.post('/settings/', {'revoke_invitation':str(invite.pk)}, secure=True).status_code, 403)
        admin = Client()
        admin.force_login(self.admin, backend='django.contrib.auth.backends.ModelBackend')
        self.assertEqual(admin.post('/settings/', {'revoke_invitation':str(invite.pk)}, secure=True).status_code, 302)
        result = Client().post('/register/', {'username':'newmember', 'invitation':token, 'password1':'Password!safe2026', 'password2':'Password!safe2026'}, secure=True)
        self.assertEqual(result.status_code, 422)
        self.assertFalse(get_user_model().objects.filter(username='newmember').exists())

    def test_help_public_no_account_enumeration_or_open_redirect(self):
        anonymous = Client()
        response = anonymous.get('/account/help/', secure=True)
        self.assertContains(response, 'Start-Windows.cmd')
        self.assertEqual(response['Cache-Control'], 'no-store')
        response = anonymous.post('/login/', {'username':'member', 'password':'Original!Test2026', 'next':'https://evil.example/'}, secure=True)
        self.assertEqual(response.url, '/')
        self.assertEqual(anonymous.get('/logout/', secure=True).status_code, 405)


class WindowsRuntimeTests(SimpleTestCase):
    def test_profile_rerun_does_not_change_secret_ports_or_zone(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp)
            first = runtime.profile_config(path, 'Asia/Shanghai')
            self.assertEqual(runtime.profile_config(path, 'UTC'), first)
            self.assertNotEqual(first['web_port'], first['backend_port'])
            self.assertGreaterEqual(len(first['secret']), 50)

    def test_occupied_port_is_skipped_and_invalid_profile_fails_closed(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0))
            port = listener.getsockname()[1]
            self.assertNotEqual(runtime.free_port(port), port)
        with TemporaryDirectory() as tmp:
            path = Path(tmp)
            value = runtime.profile_config(path, 'UTC')
            value['backend_port'] = value['web_port']
            runtime.write_json(path/'profile.json', value)
            with self.assertRaises(ValueError): runtime.profile_config(path)

    def test_environment_isolated_and_caddy_never_receives_secret(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp)
            cfg = runtime.profile_config(path, 'UTC')
            with patch.dict('os.environ', {'SHIJIN_DATA_DIR':'old-real-data', 'SHIJIN_RECIPE_API_KEY':'old-secret', 'DJANGO_SETTINGS_MODULE':'config.settings.dev'}):
                env = runtime.environment(path, cfg)
                runtime.activate_environment(path, cfg)
                import os
                self.assertNotIn('SHIJIN_RECIPE_API_KEY', os.environ)
                self.assertEqual(os.environ['SHIJIN_DATA_DIR'], str(path/'data'))
                self.assertEqual(os.environ['DJANGO_SETTINGS_MODULE'], 'config.settings.prod')
            self.assertEqual(env['SHIJIN_DATA_DIR'], str(path/'data'))
            self.assertEqual(env['DJANGO_SETTINGS_MODULE'], 'config.settings.prod')
            self.assertNotIn('SHIJIN_RECIPE_API_KEY', env)
            content = runtime.caddy_config(path, cfg).read_text()
            self.assertNotIn(cfg['secret'], content)
            self.assertIn('bind 127.0.0.1', content)
            self.assertIn('skip_install_trust', content)
            self.assertIn('max_size 220MB', content)
            self.assertIn(f"127.0.0.1:{cfg['backend_port']}", content)

    def test_lan_exact_private_network_and_paths_validated(self):
        for ip,cidr in [('8.8.8.8','8.8.8.0/24'), ('192.168.1.2','0.0.0.0/0'), ('192.168.2.2','192.168.1.0/24')]:
            with self.assertRaises(ValueError): runtime.checked_lan(ip,cidr)
        with TemporaryDirectory() as tmp:
            path=Path(tmp)
            cfg=runtime.profile_config(path,'UTC')
            text=runtime.caddy_config(path,cfg,('192.168.1.2','192.168.1.0/24')).read_text()
            self.assertIn('bind 127.0.0.1 192.168.1.2',text)
            self.assertNotIn('{$',text)

    def test_interrupted_initial_migration_can_be_backed_up_before_retry(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp)
            source=root/'app.sqlite3'
            with closing(sqlite3.connect(source)) as db: db.execute('CREATE TABLE partial (id INTEGER)')
            target,count=create_private_backup(source, root/'media', root/'backups')
            self.assertEqual(count,0)
            with closing(sqlite3.connect(target/'app.sqlite3')) as db:
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
