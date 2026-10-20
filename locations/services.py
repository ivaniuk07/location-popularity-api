import logging
from datetime import timedelta
from uuid import uuid4

from django.db.models import (
    Avg,
    Count,
    ExpressionWrapper,
    F,
    FloatField,
    IntegerField,
    OuterRef,
    Subquery,
    Value,
)
from django.db.models.functions import Coalesce
from django.utils import timezone
from django_redis import get_redis_connection
from redis.exceptions import RedisError

from .models import LocationView, Review


logger = logging.getLogger(__name__)
VIEW_TTL_SECONDS = 3600
GUEST_SESSION_KEY = "location_visitor_key"

_DELETE_OWN_CLAIM = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
"""


def with_location_stats(queryset):
    now = timezone.now()
    seven_days_ago = now - timedelta(hours=168)
    review_stats = (
        Review.objects.filter(location_id=OuterRef("pk"))
        .values("location_id")
        .annotate(average=Avg("rating", output_field=FloatField()), total=Count("pk"))
    )
    view_stats = (
        LocationView.objects.filter(
            location_id=OuterRef("pk"),
            created_at__gte=seven_days_ago,
            created_at__lte=now,
        )
        .values("location_id")
        .annotate(total=Count("pk"))
    )
    return queryset.annotate(
        rating=Coalesce(
            Subquery(review_stats.values("average")[:1], output_field=FloatField()),
            Value(0.0),
            output_field=FloatField(),
        ),
        review_count=Coalesce(
            Subquery(review_stats.values("total")[:1], output_field=IntegerField()),
            Value(0),
            output_field=IntegerField(),
        ),
        views_last_7_days=Coalesce(
            Subquery(view_stats.values("total")[:1], output_field=IntegerField()),
            Value(0),
            output_field=IntegerField(),
        ),
    ).annotate(
        popularity=ExpressionWrapper(
            F("rating") * F("review_count") + F("views_last_7_days"),
            output_field=FloatField(),
        )
    )


def record_location_view(location, request):
    if request.user.is_authenticated:
        user = request.user
        visitor_key = None
        identity = f"user:{user.pk}"
    else:
        user = None
        visitor_key = request.session.get(GUEST_SESSION_KEY)
        if not visitor_key:
            visitor_key = uuid4().hex
            request.session[GUEST_SESSION_KEY] = visitor_key
        identity = f"guest:{visitor_key}"

    redis_key = f"location:view:{location.pk}:{identity}"
    claim = uuid4().hex
    try:
        redis = get_redis_connection("default")
        claimed = redis.set(redis_key, claim, nx=True, ex=VIEW_TTL_SECONDS)
    except RedisError:
        logger.exception(
            "Не вдалося перевірити обмеження переглядів у Redis"
        )
        return False

    if not claimed:
        return False

    try:
        LocationView.objects.create(
            location=location,
            user=user,
            visitor_key=visitor_key,
        )
    except Exception:
        try:
            redis.eval(_DELETE_OWN_CLAIM, 1, redis_key, claim)
        except RedisError:
            logger.exception(
                "Не вдалося прибрати ключ перегляду після збою бази"
            )
        raise

    return True
