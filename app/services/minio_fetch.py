"""Fetch PDF bytes from MinIO / S3-compatible storage when BE sends an object key."""

from __future__ import annotations

from pathlib import Path

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError

from app.core.config import settings


def minio_download_configured() -> bool:
    return bool(
        settings.minio_endpoint
        and settings.minio_access_key
        and settings.minio_secret_key
    )


def download_template_bucket_object(object_key: str, dest: Path) -> None:
    """Download `object_key` from the template bucket (same as BE book PDF uploads)."""
    key = object_key.strip().lstrip("/")
    if not key:
        raise FileNotFoundError("Empty MinIO object key.")

    dest.parent.mkdir(parents=True, exist_ok=True)
    endpoint = (settings.minio_endpoint or "").rstrip("/")
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.minio_access_key,
        aws_secret_access_key=settings.minio_secret_key,
        config=BotoConfig(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
        region_name="us-east-1",
    )
    bucket = settings.minio_template_bucket
    try:
        client.download_file(bucket, key, str(dest))
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey", "NotFound"):
            raise FileNotFoundError(
                f"MinIO object missing: bucket={bucket} key={key} "
                f"(check MINIO_* env matches Spring Boot)"
            ) from e
        raise
