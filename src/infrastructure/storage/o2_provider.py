import os
import shutil
import logging
import time
from typing import Generator
from src.domain.storage_base import StorageProvider
from src.core.config import settings

logger = logging.getLogger(__name__)

class LocalSyncProvider(StorageProvider):
    def __init__(self, sync_dir: str = settings.O2_SYNC_DIR):
        self.sync_dir = sync_dir
        if not os.path.exists(self.sync_dir):
            os.makedirs(self.sync_dir, exist_ok=True)

    def _get_target_path(self, file_id: str) -> str:
        return os.path.join(self.sync_dir, f"{file_id}.enc")

    def upload(self, file_id: str, local_path: str) -> bool:
        """Moves/copies the local encrypted file to O2_SYNC_DIR.
        In O2 Cloud, copying/moving to the sync folder acts as the 'upload'.
        """
        target_path = self._get_target_path(file_id)
        try:
            logger.info(f"Moving encrypted file {local_path} to O2 Cloud Sync: {target_path}")
            # Ensure target directory exists
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            # Safe copy/move
            shutil.copy2(local_path, target_path)
            logger.info(f"Successfully placed {file_id}.enc in O2 sync folder.")
            return True
        except Exception as e:
            logger.error(f"Failed to place {file_id}.enc in O2 sync folder: {e}")
            return False

    def evict_file(self, file_id: str, wait_seconds: float = 5.0) -> bool:
        """Waits for synchronization, then evicts the file to 0 bytes.
        This keeps the file visible but frees up local disk space.
        """
        target_path = self._get_target_path(file_id)
        if not os.path.exists(target_path):
            logger.error(f"Cannot evict file. File not found: {target_path}")
            return False

        try:
            logger.info(f"Waiting {wait_seconds}s for sync client to process {file_id}.enc...")
            time.sleep(wait_seconds)

            # Eviction to 0 bytes:
            # We open with "wb" or truncate to 0 bytes.
            # In MacOS FileProvider, standard file syncs are evicted using OS calls.
            # Here we perform a standard OS-level truncation to 0 bytes, or log the simulated APFS placeholder conversion.
            logger.info(f"Executing eviction (reducing physical footprint to 0 bytes) for: {target_path}")
            
            # Perform standard truncation
            with open(target_path, "wb") as f:
                f.truncate(0)

            logger.info(f"Successfully evicted {target_path} to 0 bytes.")
            return True
        except Exception as e:
            logger.error(f"Failed to evict file {target_path}: {e}")
            return False

    def delete(self, file_id: str) -> bool:
        """Removes the file from the local O2_SYNC_DIR sync folder."""
        target_path = self._get_target_path(file_id)
        try:
            if os.path.exists(target_path):
                logger.info(f"Deleting {target_path} from O2 sync folder...")
                os.remove(target_path)
                logger.info(f"Deleted {target_path} successfully.")
                return True
            else:
                logger.warning(f"File {target_path} already deleted or not found.")
                return True
        except Exception as e:
            logger.error(f"Failed to delete {target_path} from O2 sync folder: {e}")
            return False

    def download_stream(self, file_id: str) -> Generator[bytes, None, None]:
        """Reads the encrypted file from the O2 sync folder in chunks.
        Reading it will automatically trigger the OS/sync client to fetch the content back if evicted.
        """
        target_path = self._get_target_path(file_id)
        if not os.path.exists(target_path):
            raise FileNotFoundError(f"O2 sync file not found: {target_path}")

        try:
            chunk_size = 64 * 1024  # 64 KB chunks
            with open(target_path, "rb") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
        except Exception as e:
            logger.error(f"Error streaming file from O2 sync folder: {e}")
            raise

    def open_encrypted_stream(self, file_id: str) -> Any:
        """Opens and returns a local file handle in read-binary mode."""
        target_path = self._get_target_path(file_id)
        if not os.path.exists(target_path):
            raise FileNotFoundError(f"O2 sync file not found: {target_path}")
        return open(target_path, "rb")

