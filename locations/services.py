from datetime import timedelta

from django.utils import timezone

from .models import LocationView


def count_views_last_hour(location):
    now = timezone.now()
    return LocationView.objects.filter(
        location=location,
        created_at__gte=now - timedelta(hours=1),
        created_at__lte=now,
    ).count()


def count_views_last_7_days(location):
    now = timezone.now()
    return LocationView.objects.filter(
        location=location,
        created_at__gte=now - timedelta(days=7),
        created_at__lte=now,
    ).count()