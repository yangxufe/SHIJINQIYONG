from django.test import SimpleTestCase


class Stage01SmokeTests(SimpleTestCase):
    def test_health_is_minimal_and_uncached(self):
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_login_page_is_local_and_has_browser_policy(self):
        response = self.client.get("/login/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "食尽其用")
        self.assertContains(response, 'lang="zh-Hans"')
        self.assertIn("object-src 'none'", response["Content-Security-Policy"])
        self.assertEqual(response["X-Frame-Options"], "DENY")

    def test_no_admin_route_and_health_is_read_only(self):
        from django.urls import Resolver404, resolve

        with self.assertRaises(Resolver404):
            resolve("/admin/")
        self.assertEqual(self.client.post("/health/").status_code, 405)
