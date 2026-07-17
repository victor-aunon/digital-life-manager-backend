import logging
from typing import Generator, Any
import boto3
from botocore.config import Config
from src.domain.storage_base import StorageProvider
from src.core.config import settings

logger = logging.getLogger(__name__)

class CloudflareR2Provider(StorageProvider):
    def __init__(self):
        self.bucket_name = settings.R2_BUCKET_NAME
        # Use custom config for Cloudflare R2 compatibilities if needed
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=settings.R2_ACCESS_KEY_ID,
            aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
            endpoint_url=settings.R2_ENDPOINT_URL,
            config=Config(signature_version="s3v4"),
        )

    def upload(self, file_id: str, local_path: str) -> bool:
        """Uploads the local encrypted file to Cloudflare R2."""
        key = f"{file_id}.enc"
        try:
            logger.info(f"Uploading {local_path} to R2 bucket {self.bucket_name} as {key}...")
            # Perform upload using put_object stream to prevent Moto recursion limit exceptions
            with open(local_path, "rb") as f:
                self.s3_client.put_object(
                    Bucket=self.bucket_name,
                    Key=key,
                    Body=f
                )
            logger.info(f"Uploaded {key} to R2 successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to upload {key} to R2: {e}")
            return False

    def delete(self, file_id: str) -> bool:
        """Deletes the encrypted file from Cloudflare R2."""
        key = f"{file_id}.enc"
        try:
            logger.info(f"Deleting {key} from R2 bucket {self.bucket_name}...")
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
            logger.info(f"Deleted {key} from R2 successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to delete {key} from R2: {e}")
            return False

    def download_stream(self, file_id: str) -> Generator[bytes, None, None]:
        """Downloads the encrypted file from R2 as a chunked stream of bytes."""
        key = f"{file_id}.enc"
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
            body = response["Body"]
            chunk_size = 64 * 1024  # 64 KB chunks
            while True:
                chunk = body.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        except Exception as e:
            logger.error(f"Failed to stream download {key} from R2: {e}")
            raise

    def open_encrypted_stream(self, file_id: str) -> Any:
        """Opens and returns the R2 object StreamingBody directly."""
        key = f"{file_id}.enc"
        try:
            response = self.s3_client.get_object(Bucket=self.bucket_name, Key=key)
            return response["Body"]
        except Exception as e:
            logger.error(f"Failed to open R2 object stream for {key}: {e}")
            raise

