from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
    )

    class Meta:
        model = User
        fields = ("id", "username", "email", "password")
        read_only_fields = ("id",)

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                "Користувач із такою електронною поштою вже існує."
            )
        return value

    def validate(self, attrs):
        user = User(
            username=attrs.get("username"),
            email=attrs.get("email"),
        )

        try:
            password_validation.validate_password(
                attrs["password"],
                user=user,
            )
        except DjangoValidationError as error:
            raise serializers.ValidationError(
                {"password": list(error.messages)}
            )

        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)