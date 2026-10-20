import csv
import io
import json

from django.contrib.auth import get_user_model
from rest_framework.test import APITransactionTestCase

from .export import EXPORT_COLUMNS
from .models import Category, Location, LocationView, Review


class LocationExportTests(APITransactionTestCase):
    def setUp(self):
        self.parks = Category.objects.create(name="Парки")
        self.museums = Category.objects.create(name="Музеї")
        self.owner = get_user_model().objects.create_user(username="owner")
        self.other_owner = get_user_model().objects.create_user(username="other-owner")
        self.reviewer = get_user_model().objects.create_user(username="reviewer")

    def location(self, name, *, description="", category=None, author=None, rating=None, views=0):
        location = Location.objects.create(
            name=name,
            description=description,
            category=category or self.parks,
            address='Київ, вулиця "Садова", 1',
            latitude="50.450001",
            longitude="30.523333",
            author=author or self.owner,
        )
        if rating is not None:
            Review.objects.create(
                location=location,
                author=self.reviewer,
                rating=rating,
                comment="Гарне місце",
            )
        for number in range(views):
            LocationView.objects.create(location=location, visitor_key=f"guest-{number}")
        return location

    def test_json_and_csv_share_filters_sort_and_export_all_results(self):
        most_popular = self.location(
            'Парк "Дружба", Київ',
            description="Рядок один\nРядок два, з комою",
            rating=5,
            views=3,
        )
        second = self.location("Парк Шевченка", rating=4, views=2)
        third = self.location("Парк на пагорбі", rating=4)
        self.location("Парк-музей", category=self.museums, rating=5, views=10)
        self.location("Парк іншого автора", author=self.other_owner, rating=5)
        self.location("Ліс", rating=5)
        deleted = self.location("Парк видалений", rating=5)
        deleted.soft_delete()
        view_count = LocationView.objects.count()

        params = (
            f"search=парк&category={self.parks.pk}&author={self.owner.pk}"
            "&rating_min=4&ordering=-popularity&page=2&page_size=1"
        )
        json_response = self.client.get(f"/api/locations/export/?{params}&format=json")
        csv_response = self.client.get(f"/api/locations/export/?{params}&format=csv")

        self.assertEqual(json_response.status_code, 200)
        self.assertTrue(json_response["Content-Type"].startswith("application/json"))
        self.assertIn("locations.json", json_response["Content-Disposition"])
        data = json.loads(json_response.content)
        self.assertEqual([row["id"] for row in data], [most_popular.pk, second.pk, third.pk])
        self.assertEqual(data[0]["popularity"], 8)
        self.assertEqual(data[0]["category_name"], "Парки")
        self.assertEqual(data[0]["author_username"], "owner")

        self.assertEqual(csv_response.status_code, 200)
        self.assertTrue(csv_response["Content-Type"].startswith("text/csv"))
        self.assertIn("locations.csv", csv_response["Content-Disposition"])
        decoded = csv_response.content.decode("utf-8-sig")
        csv_rows = list(csv.DictReader(io.StringIO(decoded)))
        self.assertEqual(tuple(csv_rows[0]), EXPORT_COLUMNS)
        self.assertEqual([int(row["id"]) for row in csv_rows], [
            most_popular.pk, second.pk, third.pk,
        ])
        self.assertEqual(csv_rows[0]["name"], most_popular.name)
        self.assertEqual(csv_rows[0]["description"], most_popular.description)
        self.assertEqual(csv_rows[0]["address"], most_popular.address)
        self.assertEqual(LocationView.objects.count(), view_count)

    def test_empty_export_and_invalid_format(self):
        json_response = self.client.get("/api/locations/export/?format=json")
        csv_response = self.client.get("/api/locations/export/?format=csv")
        invalid = self.client.get("/api/locations/export/?format=xml")

        self.assertEqual(json.loads(json_response.content), [])
        self.assertEqual(
            csv_response.content.decode("utf-8-sig").strip(),
            ",".join(EXPORT_COLUMNS),
        )
        self.assertEqual(invalid.status_code, 400)
