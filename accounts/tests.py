from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase, override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient


User = get_user_model()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordResetTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="reset-user",
            email="reset-user@example.com",
            password="Old-Password-482!",
        )

    def test_request_sends_reset_instructions_for_existing_email(self):
        response = self.client.post(
            "/api/auth/password-reset/",
            {"email": self.user.email},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("uid", mail.outbox[0].body)
        self.assertIn("token", mail.outbox[0].body)

    def test_unknown_email_gets_same_response_without_sending_email(self):
        response = self.client.post(
            "/api/auth/password-reset/",
            {"email": "unknown@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["detail"],
            "Якщо обліковий запис із такою адресою існує, інструкції надіслано.",
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_valid_token_changes_password_and_cannot_be_reused(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        payload = {
            "uid": uid,
            "token": token,
            "new_password": "New-Password-739!River",
        }

        response = self.client.post(
            "/api/auth/password-reset/confirm/",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(payload["new_password"]))

        reused_response = self.client.post(
            "/api/auth/password-reset/confirm/",
            payload,
            format="json",
        )
        self.assertEqual(reused_response.status_code, 400)

    def test_invalid_token_does_not_change_password(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        response = self.client.post(
            "/api/auth/password-reset/confirm/",
            {
                "uid": uid,
                "token": "invalid-token",
                "new_password": "New-Password-739!River",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Old-Password-482!"))

    @override_settings(PASSWORD_RESET_TIMEOUT=-1)
    def test_expired_token_is_rejected(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        response = self.client.post(
            "/api/auth/password-reset/confirm/",
            {
                "uid": uid,
                "token": token,
                "new_password": "New-Password-739!River",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
