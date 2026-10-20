from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient


class SessionAuthenticationTests(TestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

    def csrf_headers(self):
        response = self.client.get("/api/auth/csrf/")
        self.assertEqual(response.status_code, 200)
        return {"HTTP_X_CSRFTOKEN": response.json()["csrfToken"]}

    def test_registration_login_me_logout_and_csrf(self):
        payload = {
            "username": "new-member",
            "email": "new-member@example.com",
            "password": "River-Stone-284!",
        }
        self.assertEqual(
            self.client.post("/api/auth/register/", payload, format="json").status_code,
            403,
        )
        headers = self.csrf_headers()
        registered = self.client.post(
            "/api/auth/register/", payload, format="json", **headers
        )
        self.assertEqual(registered.status_code, 201)
        self.assertNotIn("password", registered.data)
        user = get_user_model().objects.get(username=payload["username"])
        self.assertTrue(user.check_password(payload["password"]))
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 403)

        self.assertEqual(
            self.client.post(
                "/api/auth/login/",
                {"username": payload["username"], "password": "wrong"},
                format="json",
                **headers,
            ).status_code,
            401,
        )
        logged_in = self.client.post(
            "/api/auth/login/",
            {"username": payload["username"], "password": payload["password"]},
            format="json",
            **headers,
        )
        self.assertEqual(logged_in.status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me/").data["id"], user.pk)

        self.assertEqual(self.client.post("/api/auth/logout/").status_code, 403)
        self.assertEqual(
            self.client.post("/api/auth/logout/", **self.csrf_headers()).status_code,
            200,
        )
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 403)
