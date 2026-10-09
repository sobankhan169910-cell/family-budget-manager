import json
import os
import re
import struct
import tempfile
import unittest
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from app import create_app


class PwaAndSecurityTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(self.temp_dir.name, "test.sqlite3")
        self.app = create_app(
            {
                "TESTING": True,
                "DATABASE": self.database_path,
                "AUTH_REQUIRED": False,
                "WTF_CSRF_ENABLED": False,
            }
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_manifest_is_well_formed_and_icon_files_are_available(self):
        response = self.client.get("/static/manifest.webmanifest")
        manifest = json.loads(response.data)
        response.close()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(manifest["name"], "Family Budget Manager")
        self.assertEqual(manifest["short_name"], "Family Budget")
        self.assertEqual(manifest["display"], "standalone")
        self.assertEqual(manifest["theme_color"], "#256d5a")
        self.assertEqual(manifest["background_color"], "#f5f7fa")
        self.assertEqual(
            {icon["sizes"] for icon in manifest["icons"]},
            {"192x192", "512x512"},
        )
        for icon in manifest["icons"]:
            icon_response = self.client.get(icon["src"])
            self.assertEqual(icon_response.status_code, 200)
            self.assertTrue(icon_response.data.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(
                struct.unpack(">II", icon_response.data[16:24]),
                tuple(int(value) for value in icon["sizes"].split("x")),
            )
            icon_response.close()

    def test_service_worker_is_root_scoped_and_does_not_cache_private_pages(self):
        response = self.client.get("/service-worker.js")
        service_worker = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Service-Worker-Allowed"], "/")
        self.assertIn('event.request.mode === "navigate"', service_worker)
        self.assertIn('fetch(event.request, {cache: "no-store"})', service_worker)
        self.assertIn('caches.match("/static/offline.html")', service_worker)
        self.assertNotIn("caches.put", service_worker)
        self.assertNotIn('"/expenses"', service_worker)
        self.assertNotIn('"/"', service_worker)
        response.close()

    def test_private_html_responses_are_not_stored_and_have_security_headers(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])

    def test_csrf_rejects_state_change_without_token_and_accepts_valid_token(self):
        csrf_app = create_app(
            {
                "TESTING": True,
                "DATABASE": os.path.join(self.temp_dir.name, "csrf.sqlite3"),
                "AUTH_REQUIRED": False,
                "WTF_CSRF_ENABLED": True,
                "SECRET_KEY": "test-only-secret",
            }
        )
        client = csrf_app.test_client()
        rejected = client.post(
            "/expenses/add",
            data={
                "amount": "5.00",
                "expense_date": "2026-10-09",
                "category": "Groceries",
            },
        )

        self.assertEqual(rejected.status_code, 400)
        form_page = client.get("/expenses/add")
        token_match = re.search(
            rb'name="csrf_token" value="([^"]+)"',
            form_page.data,
        )
        self.assertIsNotNone(token_match)
        accepted = client.post(
            "/expenses/add",
            data={
                "csrf_token": token_match.group(1).decode(),
                "amount": "5.00",
                "expense_date": "2026-10-09",
                "category": "Groceries",
            },
        )
        self.assertEqual(accepted.status_code, 302)

    def test_authentication_protects_expense_pages_and_supports_logout(self):
        auth_app = create_app(
            {
                "TESTING": True,
                "DATABASE": os.path.join(self.temp_dir.name, "auth.sqlite3"),
                "AUTH_REQUIRED": True,
                "WTF_CSRF_ENABLED": True,
                "SECRET_KEY": "test-only-secret",
                "APP_USERNAME": "family",
                "APP_PASSWORD_HASH": generate_password_hash("test-only-password"),
                "SESSION_COOKIE_SECURE": True,
            }
        )
        client = auth_app.test_client()
        restricted = client.get("/expenses")
        self.assertEqual(restricted.status_code, 302)
        self.assertEqual(restricted.headers["Location"], "/login")

        login_page = client.get("/login", base_url="https://localhost")
        token_match = re.search(
            rb'name="csrf_token" value="([^"]+)"',
            login_page.data,
        )
        self.assertIsNotNone(token_match)
        logged_in = client.post(
            "/login",
            base_url="https://localhost",
            headers={"Referer": "https://localhost/login"},
            data={
                "csrf_token": token_match.group(1).decode(),
                "username": "family",
                "password": "test-only-password",
            },
        )
        self.assertEqual(logged_in.status_code, 302)
        self.assertIn("Secure", logged_in.headers.get("Set-Cookie", ""))
        self.assertIn("HttpOnly", logged_in.headers.get("Set-Cookie", ""))
        self.assertEqual(
            client.get("/expenses", base_url="https://localhost").status_code,
            200,
        )
        login_page.close()

        logout_page = client.get("/expenses", base_url="https://localhost")
        token_match = re.search(
            rb'name="csrf_token" value="([^"]+)"',
            logout_page.data,
        )
        self.assertIsNotNone(token_match)
        logged_out = client.post(
            "/logout",
            base_url="https://localhost",
            headers={"Referer": "https://localhost/expenses"},
            data={"csrf_token": token_match.group(1).decode()},
        )
        self.assertEqual(logged_out.status_code, 302)
        self.assertEqual(
            client.get("/expenses", base_url="https://localhost").status_code,
            302,
        )

    def test_sign_in_attempts_are_rate_limited(self):
        auth_app = create_app(
            {
                "TESTING": True,
                "DATABASE": os.path.join(self.temp_dir.name, "limit.sqlite3"),
                "AUTH_REQUIRED": True,
                "WTF_CSRF_ENABLED": True,
                "SECRET_KEY": "test-only-secret",
                "APP_USERNAME": "family",
                "APP_PASSWORD_HASH": generate_password_hash("test-only-password"),
            }
        )
        client = auth_app.test_client()
        login_page = client.get("/login")
        token_match = re.search(
            rb'name="csrf_token" value="([^"]+)"',
            login_page.data,
        )
        self.assertIsNotNone(token_match)
        for _ in range(4):
            failed_login = client.post(
                "/login",
                data={
                    "csrf_token": token_match.group(1).decode(),
                    "username": "family",
                    "password": "wrong-password",
                },
            )
            self.assertEqual(failed_login.status_code, 401)

        limited = client.post(
            "/login",
            data={
                "csrf_token": token_match.group(1).decode(),
                "username": "family",
                "password": "wrong-password",
            },
        )
        self.assertEqual(limited.status_code, 429)
        login_page.close()

    def test_production_database_and_backups_must_live_under_persistent_mount(self):
        persistent_directory = os.path.join(self.temp_dir.name, "mounted")
        database_path = os.path.join(persistent_directory, "family.sqlite3")
        os.makedirs(persistent_directory)
        production_app = create_app(
            {
                "APP_ENV": "production",
                "TESTING": True,
                "SECRET_KEY": "test-only-production-secret",
                "AUTH_REQUIRED": True,
                "APP_USERNAME": "family",
                "APP_PASSWORD_HASH": generate_password_hash("test-only-password"),
                "SESSION_COOKIE_SECURE": True,
                "PERSISTENT_DATA_DIR": persistent_directory,
                "DATABASE": database_path,
                "WTF_CSRF_ENABLED": False,
                "REQUIRE_PERSISTENT_MOUNT": False,
            }
        )
        self.assertEqual(production_app.config["DATABASE"], database_path)
        self.assertEqual(
            production_app.config["BACKUP_DIRECTORY"],
            os.path.join(persistent_directory, "backups"),
        )
        self.assertFalse(production_app.config["DEBUG"])
        production_client = production_app.test_client()
        health_response = production_client.get(
            "/healthz",
            headers={"X-Forwarded-Proto": "https"},
        )
        self.assertEqual(health_response.status_code, 200)
        self.assertEqual(
            health_response.headers["Strict-Transport-Security"],
            "max-age=31536000; includeSubDomains",
        )

        with patch("app.os.path.ismount", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "mounted persistent disk"):
                create_app(
                    {
                        "APP_ENV": "production",
                        "SECRET_KEY": "test-only-production-secret",
                        "AUTH_REQUIRED": True,
                        "APP_USERNAME": "family",
                        "APP_PASSWORD_HASH": generate_password_hash("test-only-password"),
                        "SESSION_COOKIE_SECURE": True,
                        "PERSISTENT_DATA_DIR": persistent_directory,
                        "DATABASE": database_path,
                    }
                )

        with self.assertRaisesRegex(RuntimeError, "PERSISTENT_DATA_DIR"):
            create_app(
                {
                    "APP_ENV": "production",
                    "SECRET_KEY": "test-only-production-secret",
                    "AUTH_REQUIRED": True,
                    "APP_USERNAME": "family",
                    "APP_PASSWORD_HASH": generate_password_hash("test-only-password"),
                    "SESSION_COOKIE_SECURE": True,
                    "PERSISTENT_DATA_DIR": persistent_directory,
                    "DATABASE": os.path.join(self.temp_dir.name, "outside.sqlite3"),
                }
            )


if __name__ == "__main__":
    unittest.main()
