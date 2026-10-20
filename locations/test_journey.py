import json

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings
from rest_framework.test import APIClient, APITransactionTestCase

from .models import Category, Location, LocationView, ReviewVote


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class LocationJourneyTests(APITransactionTestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)
        self.category = Category.objects.create(name="Парки")
        self.owner = get_user_model().objects.create_user(
            username="owner", email="owner@example.com", password="Owner-River-284!"
        )
        self.reviewer = get_user_model().objects.create_user(
            username="reviewer", email="reviewer@example.com", password="Review-River-284!"
        )
        mail.outbox.clear()

    def log_in(self, username, password):
        csrf = self.client.get("/api/auth/csrf/").json()["csrfToken"]
        response = self.client.post(
            "/api/auth/login/",
            {"username": username, "password": password},
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(response.status_code, 200)
        return self.client.get("/api/auth/csrf/").json()["csrfToken"]

    def test_location_review_vote_views_export_and_soft_delete(self):
        csrf = self.log_in("owner", "Owner-River-284!")
        created = self.client.post(
            "/api/locations/",
            {
                "name": "Парк біля річки",
                "description": "Затишний парк",
                "category": self.category.pk,
                "address": "Київ, Набережна, 1",
                "latitude": "50.450001",
                "longitude": "30.523333",
            },
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(created.status_code, 201)
        location_id = created.data["id"]
        self.assertEqual(created.data["author"], self.owner.pk)
        subscription_url = f"/api/locations/{location_id}/subscription/"
        self.assertEqual(
            self.client.put(subscription_url, HTTP_X_CSRFTOKEN=csrf).status_code,
            200,
        )

        self.client.post("/api/auth/logout/", HTTP_X_CSRFTOKEN=csrf)
        csrf = self.log_in("reviewer", "Review-River-284!")
        review = self.client.post(
            f"/api/locations/{location_id}/reviews/",
            {"rating": 5, "comment": "Чудове місце"},
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(review.status_code, 201)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.owner.email])
        vote = self.client.put(
            f"/api/reviews/{review.data['id']}/vote/",
            {"vote": 1},
            format="json",
            HTTP_X_CSRFTOKEN=csrf,
        )
        self.assertEqual(vote.status_code, 200)
        self.assertEqual(ReviewVote.objects.count(), 1)

        self.assertEqual(
            self.client.post("/api/auth/logout/", HTTP_X_CSRFTOKEN=csrf).status_code,
            200,
        )
        detail_url = f"/api/locations/{location_id}/"
        self.assertEqual(self.client.get(detail_url).status_code, 200)
        self.assertEqual(self.client.get(detail_url).status_code, 200)
        self.assertEqual(LocationView.objects.filter(location_id=location_id).count(), 1)

        params = f"search=річки&category={self.category.pk}&rating_min=5&ordering=-popularity"
        listed = self.client.get(f"/api/locations/?{params}&page_size=1")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.data["count"], 1)
        self.assertEqual(listed.data["results"][0]["popularity"], 6)
        exported = self.client.get(f"/api/locations/export/?{params}&format=json")
        self.assertEqual([item["id"] for item in json.loads(exported.content)], [location_id])

        csrf = self.log_in("owner", "Owner-River-284!")
        self.assertEqual(
            self.client.delete(detail_url, HTTP_X_CSRFTOKEN=csrf).status_code,
            204,
        )
        self.assertTrue(Location.objects.filter(pk=location_id, deleted_at__isnull=False).exists())
        self.assertEqual(self.client.get(detail_url).status_code, 404)
        self.assertEqual(self.client.get(f"/api/locations/?{params}").data["count"], 0)
        self.assertEqual(json.loads(self.client.get(f"/api/locations/export/?{params}").content), [])
