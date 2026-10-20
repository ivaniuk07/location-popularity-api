from django.contrib import admin
from .models import (
    Category,
    Location,
    LocationSubscription,
    LocationView,
    Review,
    ReviewVote,
)

admin.site.register(Category)
admin.site.register(Location)
admin.site.register(Review)
admin.site.register(ReviewVote)
admin.site.register(LocationView)
admin.site.register(LocationSubscription)
