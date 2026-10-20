from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework.test import APIClient, APITransactionTestCase

from .models import Category, Location, LocationView
from .services import GUEST_SESSION_KEY, record_location_view


class FakeRedis:
    def __init__(self):
        self.now = 0
        self.values = {}
        self.set_calls = []

    def set(self, key, value, *, nx, ex):
        self.set_calls.append((key, nx, ex))
        current = self.values.get(key)
        if current is not None and current[1] > self.now:
            return False
        self.values[key] = (value, self.now + ex)
        return True

    def eval(self, script, number_of_keys, key, claim):
        if number_of_keys == 1 and self.values.get(key, (None,))[0] == claim:
            del self.values[key]
            return 1
        return 0

    def advance(self, seconds):
        self.now += seconds


class LocationViewCountingTests(APITransactionTestCase):
    def setUp(self):
        self.redis = FakeRedis()
        redis_patch = patch(
            "locations.services.get_redis_connection", return_value=self.redis
        )
        redis_patch.start()
        self.addCleanup(redis_patch.stop)
        self.category = Category.objects.create(name="Parks")
        self.location = Location.objects.create(
            name="City park",
            description="A park",
            category=self.category,
            address="Main street",
            latitude="50.450001",
            longitude="30.523333",
        )
        self.url = f"/api/locations/{self.location.pk}/"

    def test_guest_repeat_is_ignored_until_redis_ttl_expires(self):
        first = self.client.get(self.url)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["views_last_7_days"], 1)
        self.assertEqual(first.data["popularity"], 1)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(LocationView.objects.count(), 1)
        visitor_key = self.client.session[GUEST_SESSION_KEY]
        self.assertEqual(LocationView.objects.get().visitor_key, visitor_key)
        self.assertEqual(self.redis.set_calls[0][1:], (True, 3600))

        self.redis.advance(3600)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(LocationView.objects.count(), 2)

    def test_only_successful_detail_get_counts(self):
        self.assertEqual(self.client.get("/api/locations/").status_code, 200)
        self.assertEqual(self.client.head(self.url).status_code, 200)
        self.assertEqual(self.client.get("/api/locations/999999/").status_code, 404)
        self.assertEqual(LocationView.objects.count(), 0)

        self.location.soft_delete()
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(LocationView.objects.count(), 0)

    def test_visitors_have_independent_hourly_limits(self):
        second_guest = APIClient()
        user = get_user_model().objects.create_user(username="viewer")
        logged_in = APIClient()
        logged_in.force_login(user)

        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(second_guest.get(self.url).status_code, 200)
        self.assertEqual(logged_in.get(self.url).status_code, 200)
        self.assertEqual(logged_in.get(self.url).status_code, 200)

        self.assertEqual(LocationView.objects.count(), 3)
        self.assertEqual(LocationView.objects.filter(user=user).count(), 1)
        self.assertEqual(LocationView.objects.filter(user__isnull=True).count(), 2)
        self.assertEqual(len(self.redis.values), 3)

    def test_login_after_guest_visit_has_separate_limit(self):
        user = get_user_model().objects.create_user(username="member")
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(LocationView.objects.count(), 2)
        self.assertEqual(LocationView.objects.filter(user=user).count(), 1)

    def test_same_guest_can_view_another_location(self):
        another = Location.objects.create(
            name="Another park",
            description="A second park",
            category=self.category,
            address="Second street",
            latitude="50.450001",
            longitude="30.523333",
        )

        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(
            self.client.get(f"/api/locations/{another.pk}/").status_code, 200
        )
        self.assertEqual(LocationView.objects.count(), 2)

    def test_database_failure_releases_only_its_redis_claim(self):
        request = SimpleNamespace(user=AnonymousUser(), session={})
        with patch.object(LocationView.objects, "create", side_effect=RuntimeError("db failed")):
            with self.assertRaisesMessage(RuntimeError, "db failed"):
                record_location_view(self.location, request)

        self.assertEqual(self.redis.values, {})
        self.assertEqual(LocationView.objects.count(), 0)
        self.assertTrue(record_location_view(self.location, request))
        self.assertEqual(LocationView.objects.count(), 1)
