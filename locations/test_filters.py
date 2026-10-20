from django.contrib.auth import get_user_model
from rest_framework.test import APITransactionTestCase

from .models import Category, Location, LocationView, Review


class LocationFilterTests(APITransactionTestCase):
    def setUp(self):
        self.parks = Category.objects.create(name="Parks")
        self.museums = Category.objects.create(name="Museums")
        self.author = get_user_model().objects.create_user(username="author")
        self.other_author = get_user_model().objects.create_user(
            username="other-author"
        )
        self.reviewer = get_user_model().objects.create_user(username="reviewer")

    def add_location(
        self, name, rating, views=0, *, category=None, author=None, description=""
    ):
        location = Location.objects.create(
            name=name,
            description=description,
            category=category or self.parks,
            address="Main street",
            latitude="50.450001",
            longitude="30.523333",
            author=author or self.author,
        )
        if rating is not None:
            Review.objects.create(
                location=location,
                author=self.reviewer,
                rating=rating,
                comment="Nice place",
            )
        for number in range(views):
            LocationView.objects.create(
                location=location, visitor_key=f"guest-{number}"
            )
        return location

    def test_filters_search_order_and_second_page_work_together(self):
        first = self.add_location("Kyiv Park 1", 5, views=1)
        second = self.add_location(
            "Green area", 4, views=5, description="A park in KYIV"
        )
        third = self.add_location("Kyiv River", 5, views=3)
        fourth = self.add_location("Kyiv Square", 4, views=3)
        fifth = self.add_location("Kyiv Hill", 4)
        self.add_location("Kyiv Museum", 5, views=8, category=self.museums)
        self.add_location("Kyiv Other", 5, views=8, author=self.other_author)
        self.add_location("Kyiv Low", 3, views=8)
        self.add_location("Lviv Park", 5, views=8)

        query = (
            f"/api/locations/?search=kyiv&category={self.parks.pk}"
            f"&author={self.author.pk}&rating_min=4&rating_max=5"
            "&ordering=-popularity&page_size=2"
        )
        first_page = self.client.get(query)
        second_page = self.client.get(query + "&page=2")
        third_page = self.client.get(query + "&page=3")

        self.assertEqual(first_page.status_code, 200)
        self.assertEqual(first_page.data["count"], 5)
        self.assertEqual(
            [item["id"] for item in first_page.data["results"]],
            [second.pk, third.pk],
        )
        self.assertEqual(second_page.status_code, 200)
        self.assertEqual(
            [item["id"] for item in second_page.data["results"]],
            [fourth.pk, first.pk],
        )
        self.assertEqual(third_page.data["results"][0]["id"], fifth.pk)

    def test_rating_sorting_and_id_tie_breaker(self):
        low = self.add_location("Low", 2)
        first_high = self.add_location("High 1", 5)
        second_high = self.add_location("High 2", 5)

        ascending = self.client.get("/api/locations/?ordering=rating")
        descending = self.client.get("/api/locations/?ordering=-rating")
        self.assertEqual(
            [item["id"] for item in ascending.data["results"]],
            [low.pk, second_high.pk, first_high.pk],
        )
        self.assertEqual(
            [item["id"] for item in descending.data["results"]],
            [second_high.pk, first_high.pk, low.pk],
        )

    def test_invalid_number_and_page_size_cap(self):
        invalid = self.client.get("/api/locations/?rating_min=not-a-number")
        self.assertEqual(invalid.status_code, 400)

        Location.objects.bulk_create(
            [
                Location(
                    name=f"Park {number}",
                    description="Park",
                    category=self.parks,
                    address="Main street",
                    latitude="50.450001",
                    longitude="30.523333",
                )
                for number in range(101)
            ]
        )
        response = self.client.get("/api/locations/?page_size=500")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 101)
        self.assertEqual(len(response.data["results"]), 100)
