"""
Run with: python create_minio_bucket.py
Or via Django shell: python manage.py shell < create_minio_bucket.py
"""
import boto3
from botocore.exceptions import ClientError

s3 = boto3.client(
    "s3",
    endpoint_url="http://minio:9000",
    aws_access_key_id="minioadmin",
    aws_secret_access_key="minioadmin123",
    region_name="us-east-1",
)

BUCKET_NAME = "edukai"

try:
    s3.head_bucket(Bucket=BUCKET_NAME)
    print(f"✅ Bucket '{BUCKET_NAME}' already exists.")
except ClientError as e:
    error_code = e.response["Error"]["Code"]
    if error_code == "404":
        s3.create_bucket(Bucket=BUCKET_NAME)
        print(f"✅ Bucket '{BUCKET_NAME}' created.")
    else:
        print(f"❌ Error: {e}")
        raise

# Set bucket policy to PUBLIC READ
# This allows the AI service to access CV URLs directly
import json

policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"AWS": ["*"]},
            "Action": ["s3:GetObject"],
            "Resource": [f"arn:aws:s3:::{BUCKET_NAME}/*"],
        }
    ],
}

s3.put_bucket_policy(Bucket=BUCKET_NAME, Policy=json.dumps(policy))
print(f"✅ Public read policy applied to '{BUCKET_NAME}'.")
print(f"✅ Files accessible at: http://minio:9000/{BUCKET_NAME}/<file-path>")