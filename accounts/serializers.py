import binascii

from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
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


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(
        write_only=True,
        trim_whitespace=False,
    )

    def validate(self, attrs):
        invalid_token_message = "Посилання для скидання пароля недійсне або прострочене."

        try:
            user_id = force_str(urlsafe_base64_decode(attrs["uid"]))
            user = User.objects.get(pk=user_id, is_active=True)
        except (
            TypeError,
            ValueError,
            OverflowError,
            UnicodeDecodeError,
            binascii.Error,
            DjangoValidationError,
            User.DoesNotExist,
        ):
            raise serializers.ValidationError({"token": invalid_token_message})

        if not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError({"token": invalid_token_message})

        try:
            password_validation.validate_password(attrs["new_password"], user=user)
        except DjangoValidationError as error:
            raise serializers.ValidationError({"new_password": list(error.messages)})

        attrs["user"] = user
        return attrs

    def create(self, validated_data):
        user = validated_data["user"]
        user.set_password(validated_data["new_password"])
        user.save(update_fields=["password"])
        return user
