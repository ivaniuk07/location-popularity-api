from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


class Category(models.Model):
    name = models.CharField(max_length=100)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(name=""),
                name="category_name_not_empty",
            ),
            models.UniqueConstraint(
                Lower("name"),
                name="category_name_ci_unique",
            ),
        ]

    def __str__(self):
        return self.name


class LocationQuerySet(models.QuerySet):
    def active(self):
        return self.filter(deleted_at__isnull=True)


class Location(models.Model):
    objects = LocationQuerySet.as_manager()

    name = models.CharField(max_length=200)
    description = models.TextField()
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="locations",
    )
    address = models.CharField(max_length=300)

    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="locations",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(latitude__gte=-90, latitude__lte=90),
                name="location_latitude_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(longitude__gte=-180, longitude__lte=180),
                name="location_longitude_valid",
            ),
        ]

    def __str__(self):
        return self.name

    def soft_delete(self):
        if self.deleted_at is None:
            self.deleted_at = timezone.now()
            self.save(update_fields=["deleted_at", "updated_at"])


class Review(models.Model):
    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["location", "author"],
                name="one_review_per_user_per_location",
            ),
            models.CheckConstraint(
                condition=models.Q(rating__gte=1, rating__lte=5),
                name="review_rating_1_5",
            ),
        ]

    def clean(self):
        super().clean()
        if self.location_id and Location.objects.filter(
            pk=self.location_id, deleted_at__isnull=False
        ).exists():
            raise ValidationError({
                "location": "Не можна додати відгук до видаленої локації."
            })

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.rating}/5 — {self.location.name}"


class ReviewVote(models.Model):
    class VoteType(models.IntegerChoices):
        LIKE = 1, "Like"
        DISLIKE = -1, "Dislike"

    review = models.ForeignKey(
        Review,
        on_delete=models.CASCADE,
        related_name="votes",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="review_votes",
    )
    vote = models.SmallIntegerField(choices=VoteType.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["review", "user"],
                name="one_vote_per_user_per_review",
            ),
            models.CheckConstraint(
                condition=models.Q(vote__in=[1, -1]),
                name="review_vote_value_valid",
            ),
        ]

    def clean(self):
        super().clean()
        if self.review_id and Review.objects.filter(
            pk=self.review_id, location__deleted_at__isnull=False
        ).exists():
            raise ValidationError({
                "review": "Не можна голосувати за відгук видаленої локації."
            })

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user} — {self.get_vote_display()} — {self.review}"


class LocationView(models.Model):
    location = models.ForeignKey(
        Location,
        on_delete=models.CASCADE,
        related_name="views",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="location_views",
    )
    visitor_key = models.CharField(max_length=64, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["location", "created_at"],
                name="loc_view_loc_time_idx",
            ),
        ]

    def __str__(self):
        return f"Перегляд {self.location.name} — {self.created_at}"
