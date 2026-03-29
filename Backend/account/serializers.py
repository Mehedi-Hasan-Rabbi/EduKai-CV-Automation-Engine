from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------
class RegisterSerializer(serializers.ModelSerializer):
    """Serializer for user registration."""

    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        style={"input_type": "password"},
    )
    password_confirm = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
    )

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "gender",
            "country",
            "profile_pic",
            "password",
            "password_confirm",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
class LoginSerializer(serializers.Serializer):
    """Serializer for email + password login. Returns JWT token pair."""

    email = serializers.EmailField(required=True)
    password = serializers.CharField(
        required=True,
        write_only=True,
        style={"input_type": "password"},
    )

    def validate(self, attrs):
        from django.contrib.auth import authenticate

        email = attrs.get("email").lower().strip()
        password = attrs.get("password")

        user = authenticate(request=self.context.get("request"), email=email, password=password)

        if not user:
            raise AuthenticationFailed("Invalid email or password.")
        if not user.is_active:
            raise AuthenticationFailed("This account has been deactivated.")

        # Generate JWT token pair
        refresh = RefreshToken.for_user(user)

        return {
            "user": user,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }


# ---------------------------------------------------------------------------
# Token Refresh
# ---------------------------------------------------------------------------
class CookieTokenRefreshSerializer(serializers.Serializer):
    """
    Custom refresh serializer that reads the refresh token from the HttpOnly cookie
    instead of the request body.
    """

    def validate(self, attrs):
        from django.conf import settings
        from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

        refresh_cookie_name = settings.SIMPLE_JWT.get("REFRESH_COOKIE_NAME", "refresh_token")
        refresh_token = self.context["request"].COOKIES.get(refresh_cookie_name)

        if not refresh_token:
            raise serializers.ValidationError(
                {"refresh_token": "Refresh token cookie not found. Please log in again."}
            )

        try:
            refresh = RefreshToken(refresh_token)
            data = {"access": str(refresh.access_token)}

            # If ROTATE_REFRESH_TOKENS is True, issue a new refresh token too
            from django.conf import settings as django_settings
            if django_settings.SIMPLE_JWT.get("ROTATE_REFRESH_TOKENS"):
                refresh.blacklist()
                refresh.set_jti()
                refresh.set_exp()
                data["refresh"] = str(refresh)

            return data
        except TokenError as e:
            raise InvalidToken(e.args[0])


# ---------------------------------------------------------------------------
# User Profile (Read)
# ---------------------------------------------------------------------------
class UserProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    profile_pic_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "gender",
            "country",
            "profile_pic_url",
            "role",
            "date_joined",
            "updated_at",
        ]
        read_only_fields = fields

    def get_profile_pic_url(self, obj) -> str | None:
        from candidate.utils.minio_utils import resolve_file_url
        return resolve_file_url(obj.profile_pic)


# ---------------------------------------------------------------------------
# User Profile Update (Write)
# ---------------------------------------------------------------------------
class ProfileUpdateSerializer(serializers.ModelSerializer):
    """
    Allows authenticated users to update their profile information.
    Email & role cannot be changed.
    """
    
    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "gender",
            "country",
            "profile_pic",
        ]

    def update(self, instance, validated_data):
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance


# ---------------------------------------------------------------------------
# Password Update
# ---------------------------------------------------------------------------
class PasswordUpdateSerializer(serializers.Serializer):
    """
    Allows authenticated users to change their password.
    """

    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(
        required=True,
        write_only=True,
        validators=[validate_password],
    )
    new_password_confirm = serializers.CharField(required=True, write_only=True)

    def validate(self, attrs):
        user = self.context["request"].user

        # Check old password
        if not user.check_password(attrs["old_password"]):
            raise serializers.ValidationError(
                {"old_password": "Old password is incorrect."}
            )

        # Match new passwords
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password": "New passwords do not match."}
            )

        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save()
        return user
    

# ---------------------------------------------------------------------------
# Forgot Password / OTP / Reset
# ---------------------------------------------------------------------------
class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)

    def validate_email(self, value):
        return value.lower().strip()


class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    otp = serializers.CharField(required=True, min_length=4, max_length=10)

    def validate_email(self, value):
        return value.lower().strip()

    def validate_otp(self, value):
        return value.strip()


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    new_password = serializers.CharField(
        required=True,
        write_only=True,
        validators=[validate_password],
    )
    new_password_confirm = serializers.CharField(required=True, write_only=True)

    def validate_email(self, value):
        return value.lower().strip()

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError({"new_password": "Passwords do not match."})
        return attrs