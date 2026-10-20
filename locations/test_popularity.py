from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from .models import Category, Location, LocationView, Review
from .services import with_location_stats


class LocationPopularityTests(APITestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Parks")
        self.location = self.make_location("City park")

    def make_location(self, name):
        return Location.objects.create(
            name=name,
            description="A park",
            category=self.category,
            address="Main street",
            latitude="50.450001",
            longitude="30.523333",
        )

    def test_empty_location_has_zero_stats(self):
        location = with_location_stats(Location.objects.all()).get(pk=self.location.pk)
        self.assertEqual(location.rating, 0)
        self.assertEqual(location.review_count, 0)
        self.assertEqual(location.views_last_7_days, 0)
        self.assertEqual(location.popularity, 0)

        response = self.client.get("/api/locations/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["popularity"], 0)

    def test_multiple_reviews_and_views_do_not_multiply_each_other(self):
        for number, rating in enumerate((5, 3)):
            user = get_user_model().objects.create_user(username=f"reviewer-{number}")
            Review.objects.create(
                location=self.location,
                author=user,
                rating=rating,
                comment="Nice",
            )

        now = timezone.now()
        for number in range(3):
            view = LocationView.objects.create(
                location=self.location, visitor_key=f"guest-{number}"
            )
            LocationView.objects.filter(pk=view.pk).update(
                created_at=now - timedelta(hours=number + 1)
            )
        old_view = LocationView.objects.create(
            location=self.location, visitor_key="old-guest"
        )
        LocationView.objects.filter(pk=old_view.pk).update(
            created_at=now - timedelta(hours=169)
        )

        response = self.client.get("/api/locations/")
        stats = response.data["results"][0]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(stats["rating"], 4.0)
        self.assertEqual(stats["review_count"], 2)
        self.assertEqual(stats["views_last_7_days"], 3)
        self.assertEqual(stats["popularity"], 11.0)

        empty_location = self.make_location("Empty park")
        ordered = list(
            with_location_stats(Location.objects.all())
            .order_by("-popularity")
            .values_list("pk", flat=True)
        )
        self.assertEqual(ordered, [self.location.pk, empty_location.pk])
        high_rated = list(
            with_location_stats(Location.objects.all())
            .filter(rating__gte=4)
            .values_list("pk", flat=True)
        )
        self.assertEqual(high_rated, [self.location.pk])

    def test_list_uses_bounded_queries_and_stats_can_be_sorted_before_pagination(self):
        with CaptureQueriesContext(connection) as one_location_queries:
            one = self.client.get("/api/locations/")
        self.assertEqual(one.status_code, 200)

        for number in range(6):
            self.make_location(f"Extra park {number}")
        with CaptureQueriesContext(connection) as many_location_queries:
            many = self.client.get("/api/locations/")

        self.assertEqual(many.status_code, 200)
        self.assertEqual(len(many_location_queries), len(one_location_queries))
        self.assertEqual(many.data["count"], 7)

    def test_stats_cannot_be_changed_through_location_update(self):
        author = get_user_model().objects.create_user(username="owner")
        self.location.author = author
        self.location.save(update_fields=["author"])
        self.client.force_login(author)

        response = self.client.patch(
            f"/api/locations/{self.location.pk}/",
            {"rating": 5, "review_count": 20, "views_last_7_days": 30,
             "popularity": 999, "name": "Renamed"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], "Renamed")
        self.assertEqual(response.data["popularity"], 0)
        self.assertEqual(response.data["rating"], 0)
