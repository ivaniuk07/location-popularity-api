from django.contrib import admin
from .models import Category, Location, Review, ReviewVote, LocationView

admin.site.register(Category)
admin.site.register(Location)
admin.site.register(Review)
admin.site.register(ReviewVote)
admin.site.register(LocationView)