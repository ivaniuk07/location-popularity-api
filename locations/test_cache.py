from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APITransactionTestCase

from .cache import LOCATION_LIST_VERSION_KEY
from .models import Category, Location, LocationView


class FakeRedis:
    def __init__(self):
        self.now = 0
        self.values = {}
        self.set_calls = []

    def get(self, key):
        item = self.values.get(key)
        if item is None:
            return None
        value, expires_at = item
        if expires_at is not None and expires_at <= self.now:
            del self.values[key]
            return None
        return value

    def set(self, key, value, *, ex=None, nx=False):
        if nx and self.get(key) is not None:
            return False
        if isinstance(value, str):
            value = value.encode("utf-8")
        self.values[key] = (value, self.now + ex if ex else None)
        self.set_calls.append((key, ex))
        return True

    def incr(self, key):
        value = int(self.get(key) or b"0") + 1
        self.values[key] = (str(value).encode(), None)
        return value

    def eval(self, script, number_of_keys, key, claim):
        value = self.get(key)
        if value == claim.encode("utf-8"):
            del self.values[key]
            return 1
        return 0

    def advance(self, seconds):
        self.now += seconds


class LocationListCacheTests(APITransactionTestCase):
    def setUp(self):
        self.redis = FakeRedis()
        for target in (
            "locations.cache.get_redis_connection",
            "locations.services.get_redis_connection",
        ):
            redis_patch = patch(target, return_value=self.redis)
            redis_patch.start()
            self.addCleanup(redis_patch.stop)
        self.category = Category.objects.create(name="Parks")
        self.author = get_user_model().objects.create_user(username="owner")
        self.location = self.make_location("City park")

    def make_location(self, name):
        return Location.objects.create(
            name=name,
            description="Park",
            category=self.category,
            address="Main street",
            latitude="50.450001",
            longitude="30.523333",
            author=self.author,
        )

    def version(self):
        return int(self.redis.get(LOCATION_LIST_VERSION_KEY) or b"0")

    def cached_keys(self):
        return [key for key, ex in self.redis.set_calls if ex == 60]

    def test_repeat_uses_cache_and_expires_after_60_seconds(self):
        with CaptureQueriesContext(connection) as first_queries:
            first = self.client.get("/api/locations/")
        with CaptureQueriesContext(connection) as repeat_queries:
            repeated = self.client.get("/api/locations/")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(repeated.data, first.data)
        self.assertLess(len(repeat_queries), len(first_queries))
        self.assertEqual(len(self.cached_keys()), 1)

        self.redis.advance(60)
        self.assertEqual(self.client.get("/api/locations/").status_code, 200)
        self.assertEqual(len(self.cached_keys()), 2)

    def test_selection_page_and_page_size_have_distinct_keys(self):
        self.make_location("Second park")
        queries = (
            "",
            "?search=City",
            "?search=Second",
            f"?category={self.category.pk}",
            "?category=999999",
            f"?author={self.author.pk}",
            "?author=999999",
            "?rating_min=4",
            "?rating_min=5",
            "?rating_max=4",
            "?rating_max=5",
            "?ordering=rating",
            "?ordering=-rating",
            "?page_size=1",
            "?page_size=1&page=2",
        )
        for query in queries:
            self.assertEqual(self.client.get(f"/api/locations/{query}").status_code, 200)

        self.assertEqual(len(self.cached_keys()), len(queries))
        self.assertEqual(len(set(self.cached_keys())), len(queries))

    def test_create_update_delete_invalidate_after_commit(self):
        self.client.force_login(self.author)
        self.assertEqual(self.client.get("/api/locations/").data["count"], 1)
        initial_version = self.version()

        created = self.client.post(
            "/api/locations/",
            {
                "name": "New park",
                "description": "New",
                "category": self.category.pk,
                "address": "Other street",
                "latitude": "50.450001",
                "longitude": "30.523333",
            },
        )
        self.assertEqual(created.status_code, 201)
        self.assertGreater(self.version(), initial_version)
        self.assertEqual(self.client.get("/api/locations/").data["count"], 2)

        updated = self.client.patch(
            f"/api/locations/{self.location.pk}/", {"name": "Renamed park"}
        )
        self.assertEqual(updated.status_code, 200)
        names = [item["name"] for item in self.client.get("/api/locations/").data["results"]]
        self.assertIn("Renamed park", names)

        deleted = self.client.delete(f"/api/locations/{self.location.pk}/")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get("/api/locations/").data["count"], 1)

    def test_review_view_and_category_change_invalidate_without_flushing_locks(self):
        reviewer = get_user_model().objects.create_user(username="reviewer")
        self.client.force_login(reviewer)
        self.client.get("/api/locations/")
        before_review = self.version()

        review = self.client.post(
            f"/api/locations/{self.location.pk}/reviews/",
            {"rating": 5, "comment": "Great"},
        )
        self.assertEqual(review.status_code, 201)
        self.assertGreater(self.version(), before_review)
        self.assertEqual(self.client.get("/api/locations/").data["results"][0]["rating"], 5)

        before_view = self.version()
        self.assertEqual(
            self.client.get(f"/api/locations/{self.location.pk}/").status_code, 200
        )
        self.assertGreater(self.version(), before_view)
        self.assertEqual(LocationView.objects.count(), 1)
        self.assertEqual(
            self.client.get("/api/locations/").data["results"][0]["views_last_7_days"],
            1,
        )
        lock_keys = [key for key in self.redis.values if key.startswith("location:view:")]
        self.assertEqual(len(lock_keys), 1)

        before_category = self.version()
        self.category.name = "Gardens"
        self.category.save(update_fields=["name"])
        self.assertGreater(self.version(), before_category)
        self.assertIsNotNone(self.redis.get(lock_keys[0]))

    def test_rollback_keeps_existing_cache_version(self):
        self.client.get("/api/locations/")
        version = self.version()

        with self.assertRaisesMessage(RuntimeError, "rollback"):
            with transaction.atomic():
                self.make_location("Rolled back")
                self.assertEqual(self.version(), version)
                raise RuntimeError("rollback")

        self.assertEqual(self.version(), version)
        self.assertEqual(self.client.get("/api/locations/").data["count"], 1)
