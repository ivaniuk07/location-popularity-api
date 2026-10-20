from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    CategoryViewSet,
    LocationViewSet,
    ReviewListCreateView,
    ReviewVoteView,
)


router = SimpleRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("locations", LocationViewSet, basename="location")

urlpatterns = [
    path(
        "locations/<int:location_id>/reviews/",
        ReviewListCreateView.as_view(),
        name="location-reviews",
    ),
    path(
        "reviews/<int:review_id>/vote/",
        ReviewVoteView.as_view(),
        name="review-vote",
    ),
] + router.urls
