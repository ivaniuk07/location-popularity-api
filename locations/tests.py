from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.test import APITransactionTestCase

from .models import Category, Location, Review, ReviewVote


User = get_user_model()


class CategoryAPITests(APITransactionTestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Parks")
        self.member = User.objects.create_user(
            username="member", password="Member-Password-482!"
        )
        self.admin = User.objects.create_user(
            username="staff", password="Staff-Password-482!", is_staff=True
        )

    def test_anyone_can_list_and_read_categories(self):
        list_response = self.client.get("/api/categories/")
        detail_response = self.client.get(f"/api/categories/{self.category.pk}/")

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.data["count"], 1)
        self.assertEqual(list_response.data["results"][0]["name"], "Parks")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.data["id"], self.category.pk)

    def test_guest_and_regular_user_cannot_change_categories(self):
        for user in (None, self.member):
            if user:
                self.client.force_login(user)
            for response in (
                self.client.post("/api/categories/", {"name": "Museums"}),
                self.client.patch(
                    f"/api/categories/{self.category.pk}/", {"name": "Gardens"}
                ),
                self.client.delete(f"/api/categories/{self.category.pk}/"),
            ):
                self.assertEqual(response.status_code, 403)
            self.client.logout()

        self.category.refresh_from_db()
        self.assertEqual(self.category.name, "Parks")
        self.assertEqual(Category.objects.count(), 1)

    def test_staff_can_create_edit_and_delete_category(self):
        self.client.force_login(self.admin)

        created = self.client.post("/api/categories/", {"name": "  Museums  "})
        self.assertEqual(created.status_code, 201)
        category_id = created.data["id"]
        self.assertEqual(created.data["name"], "Museums")

        updated = self.client.patch(
            f"/api/categories/{category_id}/", {"name": "Art museums"}
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["name"], "Art museums")

        deleted = self.client.delete(f"/api/categories/{category_id}/")
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(Category.objects.filter(pk=category_id).exists())

    def test_blank_and_case_insensitive_duplicate_names_are_rejected(self):
        self.client.force_login(self.admin)

        for name in ("", "   ", "  pArKs  "):
            response = self.client.post("/api/categories/", {"name": name})
            self.assertEqual(response.status_code, 400)

        another = Category.objects.create(name="Museums")
        duplicate_update = self.client.patch(
            f"/api/categories/{another.pk}/", {"name": "PARKS"}
        )
        self.assertEqual(duplicate_update.status_code, 400)

    def test_list_is_paginated(self):
        Category.objects.bulk_create(
            [Category(name=f"Category {number}") for number in range(11)]
        )

        response = self.client.get("/api/categories/?page=2&page_size=5")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 12)
        self.assertEqual(len(response.data["results"]), 5)
        self.assertIsNotNone(response.data["next"])

    def test_category_with_location_cannot_be_deleted(self):
        Location.objects.create(
            name="City park",
            description="A park",
            category=self.category,
            address="Main street",
            latitude=50.450001,
            longitude=30.523333,
            author=self.member,
        )
        self.client.force_login(self.admin)

        response = self.client.delete(f"/api/categories/{self.category.pk}/")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Спочатку перенесіть", str(response.data["detail"]))
        self.assertTrue(Category.objects.filter(pk=self.category.pk).exists())


class LocationAPITests(APITransactionTestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Parks")
        self.author = User.objects.create_user(
            username="author", password="Author-Password-482!"
        )
        self.other_user = User.objects.create_user(
            username="other", password="Other-Password-482!"
        )
        self.admin = User.objects.create_user(
            username="admin", password="Admin-Password-482!", is_staff=True
        )
        self.payload = {
            "name": "City park",
            "description": "A large park",
            "category": self.category.pk,
            "address": "Main street",
            "latitude": "50.450001",
            "longitude": "30.523333",
        }
        self.location = Location.objects.create(
            name=self.payload["name"],
            description=self.payload["description"],
            category=self.category,
            address=self.payload["address"],
            latitude=self.payload["latitude"],
            longitude=self.payload["longitude"],
            author=self.author,
        )

    def test_guest_can_list_and_read_but_cannot_create(self):
        listed = self.client.get("/api/locations/")
        detail = self.client.get(f"/api/locations/{self.location.pk}/")
        denied = self.client.post("/api/locations/", self.payload)

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.data["count"], 1)
        self.assertEqual(listed.data["results"][0]["id"], self.location.pk)
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["author"], self.author.pk)
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(Location.objects.count(), 1)

    def test_creation_sets_author_and_ignores_protected_fields(self):
        self.client.force_login(self.other_user)
        payload = {
            **self.payload,
            "name": "Museum square",
            "author": self.author.pk,
            "created_at": "2000-01-01T00:00:00Z",
            "deleted_at": "2000-01-01T00:00:00Z",
            "rating": 5,
            "popularity": 999,
        }

        response = self.client.post("/api/locations/", payload)

        self.assertEqual(response.status_code, 201)
        created = Location.objects.get(pk=response.data["id"])
        self.assertEqual(created.author_id, self.other_user.pk)
        self.assertIsNone(created.deleted_at)
        self.assertNotEqual(created.created_at.year, 2000)
        self.assertEqual(response.data["rating"], 0)
        self.assertEqual(response.data["popularity"], 0)

    def test_only_author_or_admin_can_edit_and_delete(self):
        url = f"/api/locations/{self.location.pk}/"
        self.client.force_login(self.other_user)
        self.assertEqual(self.client.patch(url, {"name": "Changed"}).status_code, 403)
        self.assertEqual(self.client.delete(url).status_code, 403)

        self.client.force_login(self.author)
        updated = self.client.patch(
            url,
            {"name": "Renamed", "author": self.other_user.pk, "deleted_at": "2000-01-01T00:00:00Z"},
        )
        self.assertEqual(updated.status_code, 200)
        self.location.refresh_from_db()
        self.assertEqual(self.location.name, "Renamed")
        self.assertEqual(self.location.author_id, self.author.pk)
        self.assertIsNone(self.location.deleted_at)

        replaced = self.client.put(url, {**self.payload, "name": "Fully updated"})
        self.assertEqual(replaced.status_code, 200)
        self.location.refresh_from_db()
        self.assertEqual(self.location.name, "Fully updated")

        self.client.force_login(self.admin)
        self.assertEqual(self.client.patch(url, {"name": "Admin edit"}).status_code, 200)
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.location.refresh_from_db()
        self.assertIsNotNone(self.location.deleted_at)

    def test_soft_delete_hides_location_and_blocks_new_reviews_and_votes(self):
        existing_review = Review.objects.create(
            location=self.location,
            author=self.author,
            rating=5,
            comment="Nice place",
        )
        self.client.force_login(self.author)
        url = f"/api/locations/{self.location.pk}/"

        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertTrue(Location.objects.filter(pk=self.location.pk).exists())
        self.assertFalse(Location.objects.active().filter(pk=self.location.pk).exists())
        self.assertEqual(self.client.get("/api/locations/").data["count"], 0)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.patch(url, {"name": "Hidden"}).status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)

        with self.assertRaises(DjangoValidationError):
            Review.objects.create(
                location=self.location,
                author=self.other_user,
                rating=4,
                comment="Another review",
            )
        with self.assertRaises(DjangoValidationError):
            ReviewVote.objects.create(
                review=existing_review,
                user=self.other_user,
                vote=ReviewVote.VoteType.LIKE,
            )

    def test_invalid_coordinates_and_category_are_rejected(self):
        self.client.force_login(self.author)
        for changes in (
            {"latitude": "91"},
            {"longitude": "181"},
            {"category": 999999},
        ):
            response = self.client.post("/api/locations/", {**self.payload, **changes})
            self.assertEqual(response.status_code, 400)


class ReviewAPITests(APITransactionTestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Parks")
        self.location = Location.objects.create(
            name="City park",
            description="A park",
            category=self.category,
            address="Main street",
            latitude="50.450001",
            longitude="30.523333",
        )
        self.author = User.objects.create_user(
            username="review-author", password="Author-Password-482!"
        )
        self.voter = User.objects.create_user(
            username="voter", password="Voter-Password-482!"
        )
        self.list_url = f"/api/locations/{self.location.pk}/reviews/"

    def test_guest_can_read_but_cannot_create_review_or_vote(self):
        review = Review.objects.create(
            location=self.location, author=self.author, rating=5, comment="Great"
        )

        listed = self.client.get(self.list_url)
        denied_create = self.client.post(
            self.list_url, {"rating": 4, "comment": "Nice"}
        )
        denied_vote = self.client.put(
            f"/api/reviews/{review.pk}/vote/", {"vote": 1}
        )

        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.data["count"], 1)
        self.assertEqual(listed.data["results"][0]["likes_count"], 0)
        self.assertEqual(listed.data["results"][0]["dislikes_count"], 0)
        self.assertEqual(denied_create.status_code, 403)
        self.assertEqual(denied_vote.status_code, 403)

    def test_create_sets_author_and_rejects_duplicate(self):
        self.client.force_login(self.author)
        response = self.client.post(
            self.list_url,
            {
                "rating": 5,
                "comment": "Great place",
                "author": self.voter.pk,
                "location": 999999,
            },
        )

        self.assertEqual(response.status_code, 201)
        review = Review.objects.get(pk=response.data["id"])
        self.assertEqual(review.author_id, self.author.pk)
        self.assertEqual(review.location_id, self.location.pk)
        self.assertEqual(response.data["likes_count"], 0)

        duplicate = self.client.post(
            self.list_url, {"rating": 4, "comment": "Another review"}
        )
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn("вже залишили", str(duplicate.data["detail"]))
        self.assertEqual(Review.objects.count(), 1)

    def test_rating_and_comment_validation(self):
        self.client.force_login(self.author)
        for payload in (
            {"rating": 0, "comment": "Bad"},
            {"rating": 6, "comment": "Great"},
            {"rating": 4, "comment": "   "},
        ):
            response = self.client.post(self.list_url, payload)
            self.assertEqual(response.status_code, 400)
        self.assertEqual(Review.objects.count(), 0)

    def test_reviews_are_paginated(self):
        Review.objects.create(
            location=self.location, author=self.author, rating=5, comment="First"
        )
        for number in range(11):
            user = User.objects.create_user(username=f"reviewer-{number}")
            Review.objects.create(
                location=self.location,
                author=user,
                rating=4,
                comment=f"Review {number}",
            )

        response = self.client.get(f"{self.list_url}?page=2&page_size=5")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 12)
        self.assertEqual(len(response.data["results"]), 5)

    def test_vote_create_repeat_change_and_delete(self):
        review = Review.objects.create(
            location=self.location, author=self.author, rating=5, comment="Great"
        )
        vote_url = f"/api/reviews/{review.pk}/vote/"
        self.client.force_login(self.voter)

        first = self.client.put(vote_url, {"vote": 1})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["likes_count"], 1)
        self.assertEqual(first.data["dislikes_count"], 0)
        saved_vote = ReviewVote.objects.get(review=review, user=self.voter)
        first_updated_at = saved_vote.updated_at

        repeated = self.client.put(vote_url, {"vote": 1})
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(ReviewVote.objects.filter(review=review, user=self.voter).count(), 1)
        saved_vote.refresh_from_db()
        self.assertEqual(saved_vote.updated_at, first_updated_at)

        changed = self.client.put(vote_url, {"vote": -1})
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.data["likes_count"], 0)
        self.assertEqual(changed.data["dislikes_count"], 1)
        listed = self.client.get(self.list_url)
        self.assertEqual(listed.data["results"][0]["likes_count"], 0)
        self.assertEqual(listed.data["results"][0]["dislikes_count"], 1)

        self.assertEqual(self.client.delete(vote_url).status_code, 204)
        self.assertFalse(ReviewVote.objects.filter(review=review, user=self.voter).exists())
        self.assertEqual(self.client.delete(vote_url).status_code, 204)

    def test_invalid_vote_is_rejected(self):
        review = Review.objects.create(
            location=self.location, author=self.author, rating=5, comment="Great"
        )
        self.client.force_login(self.voter)
        vote_url = f"/api/reviews/{review.pk}/vote/"

        for value in (0, 2):
            response = self.client.put(vote_url, {"vote": value})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(ReviewVote.objects.count(), 0)

    def test_deleted_location_hides_reviews_and_rejects_votes(self):
        review = Review.objects.create(
            location=self.location, author=self.author, rating=5, comment="Great"
        )
        self.location.soft_delete()
        self.client.force_login(self.voter)

        self.assertEqual(self.client.get(self.list_url).status_code, 404)
        self.assertEqual(
            self.client.post(self.list_url, {"rating": 4, "comment": "Nice"}).status_code,
            404,
        )
        self.assertEqual(
            self.client.put(f"/api/reviews/{review.pk}/vote/", {"vote": 1}).status_code,
            404,
        )
