import uuid
import boto3
from botocore.client import Config
from django.conf import settings


# ---------------------------------------------------------------------------
# TWO separate clients:
#   _get_s3_client()        → internal URL — for upload/download operations
#   _get_s3_signing_client()→ PUBLIC URL  — for generating pre-signed URLs
# ---------------------------------------------------------------------------

def _get_s3_client():
    """
    Internal client — used for actual file operations (upload, download).
    Uses fast internal URL (127.0.0.1:9000).
    DO NOT use this for pre-signed URLs — signatures won't match public host.
    """
    return boto3.client(
        "s3",
        endpoint_url=settings.AWS_S3_ENDPOINT_URL,       # http://127.0.0.1:9000
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
        region_name=settings.AWS_S3_REGION_NAME,
    )


def _get_s3_signing_client():
    """
    Signing client — used ONLY for generating pre-signed URLs.
    Uses the PUBLIC URL so the host in the signature matches what
    the browser sends → no SignatureDoesNotMatch error.

    In local dev:  PUBLIC URL = http://127.0.0.1:9000  (same as internal)
    In production: PUBLIC URL = http://test3.fireai.agency:9000
    """
    public_url = getattr(settings, "MINIO_PUBLIC_URL", settings.AWS_S3_ENDPOINT_URL)

    return boto3.client(
        "s3",
        endpoint_url=public_url,                         # ✅ PUBLIC URL for signing
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
        region_name=settings.AWS_S3_REGION_NAME,
    )


def _get_s3_internal_signing_client():
    """
    Signing client for server-to-server presigned URLs.
    Used when the URL consumer is another container (AI worker),
    NOT the browser. Uses internal Docker service name.
    """
    internal_url = getattr(settings, "MINIO_INTERNAL_URL", settings.AWS_S3_ENDPOINT_URL)

    return boto3.client(
        "s3",
        endpoint_url=internal_url,                   # http://minio:9000
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
        region_name=settings.AWS_S3_REGION_NAME,
    )


def get_presigned_url_for_ai(file_field, expires_in: int | None = None) -> str | None:
    """
    Generate a pre-signed GET URL for server-to-server use (AI worker).
    Signed with INTERNAL URL → AI worker can reach minio:9000 directly.
    """
    if expires_in is None:
        expires_in = getattr(settings, "PRESIGNED_URL_EXPIRE_SECONDS", 3600)

    if not file_field or not file_field.name:
        return None

    return _get_s3_internal_signing_client().generate_presigned_url(
        ClientMethod="get_object",
        Params={
            "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
            "Key":    file_field.name,
        },
        ExpiresIn=expires_in,
    )


# ---------------------------------------------------------------------------
# GET — Pre-signed download URL
# ---------------------------------------------------------------------------
def get_presigned_url(file_field, expires_in: int | None = None) -> str | None:
    """
    Generate a pre-signed GET URL for any FileField / ImageField.
    Signed with the PUBLIC URL → works in browser directly.
    """
    if expires_in is None:
        expires_in = getattr(settings, "PRESIGNED_URL_EXPIRE_SECONDS", 3600)

    if not file_field or not file_field.name:
        return None

    # ✅ Use signing client (public URL) — no host swap needed
    return _get_s3_signing_client().generate_presigned_url(
        ClientMethod="get_object",
        Params={
            "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
            "Key":    file_field.name,
        },
        ExpiresIn=expires_in,
    )


# ---------------------------------------------------------------------------
# PUT — Pre-signed upload URL
# ---------------------------------------------------------------------------
def get_presigned_upload_url(
    object_key: str,
    content_type: str = "application/pdf",
    expires_in: int = 900,
) -> dict:
    """
    Generate a pre-signed PUT URL for direct browser → MinIO uploads.
    Signed with the PUBLIC URL → browser can PUT directly to MinIO.
    """
    # ✅ Use signing client (public URL)
    upload_url = _get_s3_signing_client().generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket":      settings.AWS_STORAGE_BUCKET_NAME,
            "Key":         object_key,
            "ContentType": content_type,
        },
        ExpiresIn=expires_in,
    )

    return {
        "upload_url": upload_url,
        "object_key": object_key,
        "expires_in": expires_in,
    }


# ---------------------------------------------------------------------------
# Smart resolver — used in serializers
# ---------------------------------------------------------------------------
def resolve_file_url(file_field, expires_in: int | None = None) -> str | None:
    """
    Works for ANY FileField or ImageField — CVs, profile pics, anything.
    - USE_S3=True  → pre-signed public MinIO URL
    - USE_S3=False → plain local Django URL
    """
    if expires_in is None:
        expires_in = getattr(settings, "PRESIGNED_URL_EXPIRE_SECONDS", 3600)

    if not file_field or not file_field.name:
        return None

    if getattr(settings, "USE_S3", False):
        return get_presigned_url(file_field, expires_in=expires_in)
    else:
        try:
            return file_field.url
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Object key builders
# ---------------------------------------------------------------------------
def build_cv_object_key(candidate_id: str, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()
    return f"candidates/original/{candidate_id}/{uuid.uuid4().hex}.{ext}"


def build_enhanced_cv_object_key(candidate_id: str, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()
    return f"candidates/enhanced/{candidate_id}/{uuid.uuid4().hex}.{ext}"


def build_profile_photo_object_key(candidate_id: str, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()
    return f"candidates/photos/{candidate_id}/{uuid.uuid4().hex}.{ext}"