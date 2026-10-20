from rest_framework import serializers

from .models import Category, Location, Review, ReviewVote


class CategorySerializer(serializers.ModelSerializer):
    name = serializers.CharField(max_length=100, trim_whitespace=True)

    class Meta:
        model = Category
        fields = ("id", "name")
        read_only_fields = ("id",)

    def validate_name(self, value):
        categories = Category.objects.filter(name__iexact=value)
        if self.instance is not None:
            categories = categories.exclude(pk=self.instance.pk)
        if categories.exists():
            raise serializers.ValidationError("Категорія з такою назвою вже існує.")
        return value


class LocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = (
            "id",
            "name",
            "description",
            "category",
            "address",
            "latitude",
            "longitude",
            "author",
            "created_at",
            "updated_at",
            "deleted_at",
        )
        read_only_fields = (
            "id",
            "author",
            "created_at",
            "updated_at",
            "deleted_at",
        )


class ReviewSerializer(serializers.ModelSerializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(trim_whitespace=True, allow_blank=False)
    likes_count = serializers.IntegerField(read_only=True, default=0)
    dislikes_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Review
        fields = (
            "id",
            "location",
            "author",
            "rating",
            "comment",
            "likes_count",
            "dislikes_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "location",
            "author",
            "created_at",
            "updated_at",
        )


class ReviewVoteSerializer(serializers.Serializer):
    vote = serializers.ChoiceField(choices=ReviewVote.VoteType.choices)
