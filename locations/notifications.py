import logging

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction

from .models import LocationSubscription, Review


logger = logging.getLogger(__name__)


def send_review_notification(review_id):
    try:
        review = Review.objects.select_related("location__author").get(pk=review_id)
        location = review.location
        if location.deleted_at is not None:
            return

        recipients = {}
        if location.author and location.author.email:
            address = location.author.email.strip()
            if address:
                recipients[address.casefold()] = address
        subscriber_emails = LocationSubscription.objects.filter(
            location=location, location__deleted_at__isnull=True
        ).values_list("user__email", flat=True)
        for email in subscriber_emails:
            address = email.strip()
            if address:
                recipients.setdefault(address.casefold(), address)
    except Exception:
        logger.exception("Не вдалося підготувати повідомлення про відгук")
        return

    subject = f"Новий відгук про {location.name}"
    message = (
        f"Локація: {location.name}\n"
        f"Оцінка: {review.rating}/5\n"
        f"Відгук: {review.comment}\n"
    )
    for address in recipients.values():
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[address],
                fail_silently=False,
            )
        except Exception:
            logger.exception("Не вдалося надіслати повідомлення про відгук")


def notify_review_after_commit(review_id, using=None):
    transaction.on_commit(lambda: send_review_notification(review_id), using=using)
