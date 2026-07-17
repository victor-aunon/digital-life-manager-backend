import os
import tempfile
import boto3
import pytest
from moto import mock_aws
from src.core.config import settings
from src.infrastructure.storage.r2_provider import CloudflareR2Provider

@mock_aws
def test_r2_provider_upload_delete_lifecycle():
    # 1. Setup mock S3 bucket
    s3_client = boto3.client("s3", region_name="us-east-1")
    s3_client.create_bucket(Bucket=settings.R2_BUCKET_NAME)

    # 2. Instantiate provider (which connects to mocked s3 endpoint)
    provider = CloudflareR2Provider()

    # 3. Create a temporary local file to upload
    with tempfile.TemporaryDirectory() as tmpdir:
        local_file = os.path.join(tmpdir, "test_file.enc")
        file_content = b"Mock Encrypted Payload"
        with open(local_file, "wb") as f:
            f.write(file_content)

        file_id = "test-uuid-r2-lifecycle"

        # Upload
        success = provider.upload(file_id, local_file)
        assert success is True

        # Verify object exists in bucket
        response = s3_client.get_object(Bucket=settings.R2_BUCKET_NAME, Key=f"{file_id}.enc")
        uploaded_data = response["Body"].read()
        assert uploaded_data == file_content

        # Stream download check
        downloaded_chunks = list(provider.download_stream(file_id))
        assert b"".join(downloaded_chunks) == file_content

        # Delete check
        del_success = provider.delete(file_id)
        assert del_success is True

        # Verify object is gone
        with pytest.raises(Exception):
            s3_client.get_object(Bucket=settings.R2_BUCKET_NAME, Key=f"{file_id}.enc")
