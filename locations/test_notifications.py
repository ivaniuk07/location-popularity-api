from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import override_settings
from rest_framework.test import APITransactionTestCase

from .models import Category, Location, LocationSubscription, Review
from .notifications import send_review_notification


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class LocationNotificationTests(APITransactionTestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Parks")
        self.author = get_user_model().objects.create_user(
            username="owner", email="owner@example.com"
        )
        self.reviewer = get_user_model().objects.create_user(
            username="reviewer", email="reviewer@example.com"
        )
        self.subscriber = get_user_model().objects.create_user(
            username="subscriber", email="subscriber@example.com"
        )
        self.location = Location.objects.create(
            name="City park",
            description="Park",
            category=self.category,
            address="Main street",
            latitude="50.450001",
            longitude="30.523333",
            author=self.author,
        )
        self.subscription_url = f"/api/locations/{self.location.pk}/subscription/"
        self.reviews_url = f"/api/locations/{self.location.pk}/reviews/"
        mail.outbox.clear()

    def test_subscription_requires_login_is_idempotent_and_can_be_removed(self):
        self.assertEqual(self.client.put(self.subscription_url).status_code, 403)
        self.client.force_login(self.subscriber)

        self.assertEqual(self.client.put(self.subscription_url).status_code, 200)
        self.assertEqual(self.client.put(self.subscription_url).status_code, 200)
        self.assertEqual(LocationSubscription.objects.count(), 1)

        self.assertEqual(self.client.delete(self.subscription_url).status_code, 204)
        self.assertEqual(self.client.delete(self.subscription_url).status_code, 204)
        self.assertEqual(LocationSubscription.objects.count(), 0)

    def test_deleted_location_rejects_new_subscription(self):
        self.client.force_login(self.subscriber)
        self.assertEqual(self.client.put(self.subscription_url).status_code, 200)
        self.location.soft_delete()

        self.assertEqual(self.client.put(self.subscription_url).status_code, 404)
        self.assertEqual(self.client.delete(self.subscription_url).status_code, 204)
        self.assertEqual(LocationSubscription.objects.count(), 0)
        with self.assertRaises(ValidationError):
            LocationSubscription.objects.create(
                location=self.location, user=self.subscriber
            )

    def test_new_review_emails_author_and_subscriber_once_each(self):
        self.client.force_login(self.author)
        self.client.put(self.subscription_url)
        self.client.force_login(self.subscriber)
        self.client.put(self.subscription_url)
        self.client.put(self.subscription_url)
        self.client.force_login(self.reviewer)

        response = self.client.post(
            self.reviews_url, {"rating": 5, "comment": "Wonderful park"}
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(
            {message.to[0] for message in mail.outbox},
            {self.author.email, self.subscriber.email},
        )
        self.assertTrue(all("City park" in message.body for message in mail.outbox))
        self.assertTrue(all("5/5" in message.body for message in mail.outbox))
        self.assertTrue(all("Wonderful park" in message.body for message in mail.outbox))

    def test_unsubscribed_user_stops_getting_email(self):
        self.client.force_login(self.subscriber)
        self.client.put(self.subscription_url)
        self.client.delete(self.subscription_url)
        self.client.force_login(self.reviewer)

        self.assertEqual(
            self.client.post(self.reviews_url, {"rating": 4, "comment": "Nice"}).status_code,
            201,
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.author.email])

    def test_mail_failure_does_not_make_saved_review_look_failed(self):
        self.client.force_login(self.reviewer)
        with patch(
            "locations.notifications.send_mail", side_effect=RuntimeError("smtp down")
        ), patch("locations.notifications.logger.exception") as logged_error:
            response = self.client.post(
                self.reviews_url, {"rating": 5, "comment": "Nice"}
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Review.objects.count(), 1)
        logged_error.assert_called_once()

    def test_rollback_and_deleted_location_do_not_send_email(self):
        with self.assertRaisesMessage(RuntimeError, "rollback"):
            with transaction.atomic():
                Review.objects.create(
                    location=self.location,
                    author=self.reviewer,
                    rating=5,
                    comment="Rolled back",
                )
                raise RuntimeError("rollback")
        self.assertEqual(mail.outbox, [])

        review = Review.objects.create(
            location=self.location,
            author=self.reviewer,
            rating=5,
            comment="Saved",
        )
        mail.outbox.clear()
        self.location.soft_delete()
        send_review_notification(review.pk)
        self.assertEqual(mail.outbox, [])
