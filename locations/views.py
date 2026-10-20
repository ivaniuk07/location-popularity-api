from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers, status, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Category, Location, Review, ReviewVote
from .pagination import StandardPagination
from .permissions import IsAdminOrReadOnly, IsAuthorOrAdminOrReadOnly
from .serializers import (
    CategorySerializer,
    LocationSerializer,
    ReviewSerializer,
    ReviewVoteSerializer,
)


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.order_by("id")
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    pagination_class = StandardPagination

    def _save_category(self, serializer):
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError:
            raise serializers.ValidationError(
                {"name": "Категорія з такою назвою вже існує."}
            )

    def perform_create(self, serializer):
        self._save_category(serializer)

    def perform_update(self, serializer):
        self._save_category(serializer)

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise serializers.ValidationError({
                "detail": (
                    "Категорію використовують локації. Спочатку перенесіть "
                    "їх до іншої категорії."
                )
            })


class LocationViewSet(viewsets.ModelViewSet):
    queryset = (
        Location.objects.active()
        .select_related("category", "author")
        .order_by("-created_at", "-id")
    )
    serializer_class = LocationSerializer
    permission_classes = [IsAuthorOrAdminOrReadOnly]
    pagination_class = StandardPagination

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    def perform_destroy(self, instance):
        instance.soft_delete()


class ReviewListCreateView(generics.ListCreateAPIView):
    serializer_class = ReviewSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    pagination_class = StandardPagination

    def get_location(self):
        if not hasattr(self, "_location"):
            self._location = get_object_or_404(
                Location.objects.active(), pk=self.kwargs["location_id"]
            )
        return self._location

    def get_queryset(self):
        return (
            Review.objects.filter(location=self.get_location())
            .select_related("author", "location")
            .annotate(
                likes_count=Count(
                    "votes", filter=Q(votes__vote=ReviewVote.VoteType.LIKE)
                ),
                dislikes_count=Count(
                    "votes", filter=Q(votes__vote=ReviewVote.VoteType.DISLIKE)
                ),
            )
            .order_by("-created_at", "-id")
        )

    def perform_create(self, serializer):
        location = self.get_location()
        if Review.objects.filter(location=location, author=self.request.user).exists():
            raise serializers.ValidationError({
                "detail": "Ви вже залишили відгук для цієї локації."
            })
        try:
            with transaction.atomic():
                serializer.save(location=location, author=self.request.user)
        except IntegrityError:
            raise serializers.ValidationError({
                "detail": "Ви вже залишили відгук для цієї локації."
            })
        except DjangoValidationError:
            raise NotFound("Локація недоступна.")


class ReviewVoteView(APIView):
    permission_classes = [IsAuthenticated]

    def get_review(self, review_id):
        return get_object_or_404(
            Review.objects.filter(location__deleted_at__isnull=True),
            pk=review_id,
        )

    def put(self, request, review_id):
        serializer = ReviewVoteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = self.get_review(review_id)
        value = serializer.validated_data["vote"]

        try:
            with transaction.atomic():
                vote, created = ReviewVote.objects.get_or_create(
                    review=review,
                    user=request.user,
                    defaults={"vote": value},
                )
                if not created and vote.vote != value:
                    vote.vote = value
                    vote.save(update_fields=["vote", "updated_at"])
        except DjangoValidationError:
            raise NotFound("Відгук недоступний.")

        counts = ReviewVote.objects.filter(review=review).aggregate(
            likes_count=Count(
                "id", filter=Q(vote=ReviewVote.VoteType.LIKE)
            ),
            dislikes_count=Count(
                "id", filter=Q(vote=ReviewVote.VoteType.DISLIKE)
            ),
        )
        return Response({"vote": vote.vote, **counts})

    def delete(self, request, review_id):
        review = self.get_review(review_id)
        ReviewVote.objects.filter(review=review, user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
