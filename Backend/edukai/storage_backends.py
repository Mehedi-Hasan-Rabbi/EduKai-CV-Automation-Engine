from storages.backends.s3boto3 import S3Boto3Storage


class OriginalCVStorage(S3Boto3Storage):
    """Storage backend for original candidate CVs."""
    bucket_name = None          # inherits from AWS_STORAGE_BUCKET_NAME in settings
    location = "candidates/original"
    file_overwrite = False


class EnhancedCVStorage(S3Boto3Storage):
    """Storage backend for AI-enhanced candidate CV PDFs."""
    bucket_name = None
    location = "candidates/enhanced"
    file_overwrite = False