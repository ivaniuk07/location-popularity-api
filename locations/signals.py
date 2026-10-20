from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .cache import invalidate_location_list_after_commit
from .models import Category, Location, LocationView, Review


@receiver(post_save, sender=Category)
@receiver(post_save, sender=Location)
@receiver(post_save, sender=Review)
@receiver(post_save, sender=LocationView)
@receiver(post_delete, sender=Category)
@receiver(post_delete, sender=Location)
@receiver(post_delete, sender=Review)
@receiver(post_delete, sender=LocationView)
def invalidate_list_for_data_change(sender, using, **kwargs):
    invalidate_location_list_after_commit(using=using)
