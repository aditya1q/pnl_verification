"""Login, roles, access / refresh tokens (uses a throwaway database)."""
import unittest
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from pymongo import MongoClient

from app import auth
from app.config import MONGODB_URI
from app.main import app

PASSWORD = "Str0ng-pass"


class AuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mongo = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=2500)
        try:
            cls.mongo.admin.command("ping")
        except Exception as exc:  # pragma: no cover
            raise unittest.SkipTest(f"MongoDB not reachable: {exc}")
        cls._iterations, auth.PBKDF2_ITERATIONS = auth.PBKDF2_ITERATIONS, 1000  # fast hashes in tests

    @classmethod
    def tearDownClass(cls):
        auth.PBKDF2_ITERATIONS = cls._iterations
        cls.mongo.close()

    def setUp(self):
        self.db = self.mongo[f"auth_test_{uuid.uuid4().hex[:10]}"]
        self._get_db, self._grace = auth.get_db, auth.REUSE_GRACE_SECONDS
        auth.get_db = lambda: self.db
        auth.REUSE_GRACE_SECONDS = 0
        auth._failures.clear()
        for name, role in (("boss", "admin"), ("ops", "operator"), ("view", "viewer")):
            auth.create_user(self.db, name, PASSWORD, role)

    def tearDown(self):
        auth.get_db, auth.REUSE_GRACE_SECONDS = self._get_db, self._grace
        self.mongo.drop_database(self.db.name)

    def login(self, username, password=PASSWORD):
        client = TestClient(app)
        response = client.post("/api/auth/login", json={"username": username, "password": password})
        return client, response

    def bearer(self, response):
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    def test_routes_need_a_token(self):
        client = TestClient(app)
        self.assertEqual(client.get("/api/health").status_code, 200)
        self.assertEqual(client.get("/api/backoffice/summary").status_code, 401)
        self.assertEqual(client.get("/api/users", headers={"Authorization": "Bearer junk"}).status_code, 401)

    def test_login(self):
        _, bad = self.login("boss", "wrong-password")
        self.assertEqual(bad.status_code, 401)
        client, ok = self.login("BOSS")  # usernames are case-insensitive
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["user"]["role"], "admin")
        self.assertIn(auth.REFRESH_COOKIE, client.cookies)
        cookie = ok.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=strict", cookie)
        self.assertNotIn("refresh_token", ok.json())  # never readable by page scripts
        self.assertEqual(client.get("/api/auth/me", headers=self.bearer(ok)).json()["username"], "boss")

    def test_roles(self):
        ltp = {"exchange": "NSE", "symbol": "X", "date": "2026-11-02", "ltp": 1}
        viewer, v = self.login("view")
        self.assertEqual(viewer.put("/api/backoffice/ltp", json=ltp, headers=self.bearer(v)).status_code, 403)
        self.assertEqual(viewer.get("/api/users", headers=self.bearer(v)).status_code, 403)
        operator, o = self.login("ops")
        self.assertEqual(operator.get("/api/users", headers=self.bearer(o)).status_code, 403)
        admin, a = self.login("boss")
        self.assertEqual(len(admin.get("/api/users", headers=self.bearer(a)).json()), 3)

    def test_expired_access_token(self):
        user = auth.find_user(self.db, "boss")
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        token = auth._encode({"sub": "boss", "role": "admin", "ver": user["token_version"], "type": "access",
                              "iat": past, "exp": past + timedelta(minutes=1)})
        response = TestClient(app).get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual((response.status_code, response.json()["detail"]), (401, "Session expired."))

    def test_refresh_token_cannot_be_used_as_access_token(self):
        client, _ = self.login("boss")
        refresh = client.cookies.get(auth.REFRESH_COOKIE)
        self.assertEqual(client.get("/api/auth/me", headers={"Authorization": f"Bearer {refresh}"}).status_code, 401)

    def test_refresh_rotates_and_reuse_ends_the_session(self):
        client, _ = self.login("boss")
        first = client.cookies.get(auth.REFRESH_COOKIE)
        renewed = client.post("/api/auth/refresh")
        self.assertEqual(renewed.status_code, 200)
        second = client.cookies.get(auth.REFRESH_COOKIE)
        self.assertNotEqual(first, second)
        # The old (rotated) token comes back: rejected, and the newer one is revoked too.
        thief = TestClient(app)
        thief.cookies.set(auth.REFRESH_COOKIE, first)
        self.assertEqual(thief.post("/api/auth/refresh").status_code, 401)
        self.assertEqual(client.post("/api/auth/refresh").status_code, 401)

    def test_logout_revokes_refresh_token(self):
        client, _ = self.login("boss")
        token = client.cookies.get(auth.REFRESH_COOKIE)
        self.assertEqual(client.post("/api/auth/logout").status_code, 200)
        again = TestClient(app)
        again.cookies.set(auth.REFRESH_COOKIE, token)
        self.assertEqual(again.post("/api/auth/refresh").status_code, 401)

    def test_password_change_ends_old_tokens(self):
        client, old = self.login("view")
        changed = client.post("/api/auth/change-password", headers=self.bearer(old),
                              json={"current_password": PASSWORD, "new_password": "An0ther-pass"})
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(client.get("/api/auth/me", headers=self.bearer(old)).status_code, 401)
        self.assertEqual(client.get("/api/auth/me", headers=self.bearer(changed)).status_code, 200)
        self.assertEqual(self.login("view")[1].status_code, 401)
        self.assertEqual(self.login("view", "An0ther-pass")[1].status_code, 200)

    def test_admin_manages_users(self):
        admin, a = self.login("boss")
        headers = self.bearer(a)
        created = admin.post("/api/users", headers=headers, json={"username": "new.user", "password": "short", "role": "viewer"})
        self.assertEqual(created.status_code, 400)  # password too short
        created = admin.post("/api/users", headers=headers, json={"username": "new.user", "password": PASSWORD, "role": "viewer"})
        self.assertEqual(created.status_code, 201)
        self.assertEqual(admin.post("/api/users", headers=headers,
                                    json={"username": "NEW.user", "password": PASSWORD}).status_code, 409)
        # Disabling a user stops their current token at once.
        viewer, v = self.login("view")
        self.assertEqual(admin.patch("/api/users/view", headers=headers, json={"active": False}).status_code, 200)
        self.assertEqual(viewer.get("/api/auth/me", headers=self.bearer(v)).status_code, 401)
        self.assertEqual(self.login("view")[1].status_code, 401)
        # The last active admin cannot be demoted or disabled.
        self.assertEqual(admin.patch("/api/users/boss", headers=headers, json={"role": "viewer"}).status_code, 400)
        self.assertEqual(admin.patch("/api/users/boss", headers=headers, json={"active": False}).status_code, 400)

    def test_login_throttle(self):
        for _ in range(auth.LOGIN_MAX_FAILURES):
            self.assertEqual(self.login("ops", "nope-nope")[1].status_code, 401)
        self.assertEqual(self.login("ops")[1].status_code, 429)  # even with the right password


if __name__ == "__main__":
    unittest.main()
