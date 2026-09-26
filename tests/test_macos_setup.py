"""Portable checks for the configuration a new Mac would create."""

import tempfile
from pathlib import Path
from unittest import TestCase

from scripts.macos_setup import checked_network, configure
from scripts.macos_runtime import environment_for


class MacSetupTests(TestCase):
    def test_private_network_and_existing_secret_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = configure(root, "192.168.4.12", "192.168.4.0/24", time_zone="UTC")
            original = runtime.read_text(encoding="utf-8")
            self.assertIn("SHIJIN_ALLOWED_HOSTS=192.168.4.12\n", original)
            self.assertIn("SHIJIN_RECIPE_PROVIDER=off\n", original)
            with self.assertRaises(ValueError):
                configure(root, "192.168.4.12", "192.168.4.0/24")
            configure(root, "192.168.5.12", "192.168.5.0/24", update_ip=True)
            changed = runtime.read_text(encoding="utf-8")
            self.assertIn("SHIJIN_ALLOWED_HOSTS=192.168.5.12\n", changed)
            self.assertIn("SHIJIN_CSRF_TRUSTED_ORIGINS=https://192.168.5.12:8443\n", changed)
            self.assertEqual(original.split("SHIJIN_SECRET_KEY=", 1)[1].splitlines()[0],
                             changed.split("SHIJIN_SECRET_KEY=", 1)[1].splitlines()[0])

    def test_public_or_wrong_subnet_rejected(self):
        for ip, cidr in (("8.8.8.8", "8.8.8.0/24"),
                         ("192.168.1.50", "192.168.2.0/24"),
                         ("192.168.1.50", "192.168.0.0/15")):
            with self.subTest(ip=ip, cidr=cidr), self.assertRaises(ValueError):
                checked_network(ip, cidr)

    def test_caddy_process_does_not_receive_django_secret(self):
        values = {"SHIJIN_SECRET_KEY": "private-value", "SHIJIN_LAN_IP": "192.168.1.5",
                  "SHIJIN_ALLOWED_CIDR": "192.168.1.0/24", "SHIJIN_STATIC_ROOT": "/tmp/static",
                  "SHIJIN_CADDY_STORAGE": "/tmp/caddy"}
        env = environment_for("caddy", values, {"PATH": "/bin", "SHIJIN_SECRET_KEY": "stale"})
        self.assertNotIn("SHIJIN_SECRET_KEY", env)
        self.assertEqual(env["SHIJIN_LAN_IP"], "192.168.1.5")
