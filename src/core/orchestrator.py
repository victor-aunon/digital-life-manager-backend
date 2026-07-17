import os
import uuid
import hashlib
import mimetypes
import logging
from typing import Optional
from src.core.config import settings
from src.infrastructure.db_repository import DBRepository
from src.services.crypto_service import CryptoService
from src.services.ai_service import AIService
from src.infrastructure.storage.r2_provider import CloudflareR2Provider
from src.infrastructure.storage.o2_provider import LocalSyncProvider

logger = logging.getLogger(__name__)

# Register common mime types just in case
mimetypes.add_type("application/pdf", ".pdf")
mimetypes.add_type("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx")

class Orchestrator:
    def __init__(
        self,
        db_repo: Optional[DBRepository] = None,
        crypto_service: Optional[CryptoService] = None,
        ai_service: Optional[AIService] = None,
        r2_provider: Optional[CloudflareR2Provider] = None,
        o2_provider: Optional[LocalSyncProvider] = None,
    ):
        self.db_repo = db_repo if db_repo is not None else DBRepository()
        self.crypto_service = crypto_service if crypto_service is not None else CryptoService()
        self.ai_service = ai_service if ai_service is not None else AIService()
        self.r2_provider = r2_provider if r2_provider is not None else CloudflareR2Provider()
        self.o2_provider = o2_provider if o2_provider is not None else LocalSyncProvider()

    def calculate_sha256(self, file_path: str) -> str:
        """Calculates SHA-256 hash of a file using chunked reading to protect RAM."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(64 * 1024)
                if not chunk:
                    break
                sha256.update(chunk)
        return sha256.hexdigest()

    def get_mime_type(self, file_path: str) -> str:
        """Determines the MIME type of a file."""
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            # Check file extension manually for common types
            ext = os.path.splitext(file_path)[1].lower()
            if ext == ".docx":
                return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            elif ext == ".pdf":
                return "application/pdf"
            return "application/octet-stream"
        return mime_type

    def is_hot_file(self, mime_type: str, file_size: int) -> bool:
        """Determines if the file should go to hot storage (Cloudflare R2).
        Rules:
        - Text, Office documents, PDFs, or Images AND size < MAX_HOT_SIZE_MB (configured via environment)
        """
        max_hot_size = settings.MAX_HOT_SIZE_MB * 1024 * 1024
        if file_size >= max_hot_size:
            return False

        hot_mime_prefixes = ["text/", "image/"]
        hot_mimes = [
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-powerpoint",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "application/json",
            "application/xml"
        ]

        is_matching_prefix = any(mime_type.startswith(prefix) for prefix in hot_mime_prefixes)
        is_matching_mime = mime_type in hot_mimes

        return is_matching_prefix or is_matching_mime

    def process_file(self, file_path: str, is_signal_attachment: bool = False) -> Optional[str]:
        """Main pipeline orchestration:
        1. Extracted metadata.
        2. Vectorized if text/doc.
        3. Saved metadata + chunks to Postgres.
        4. Encrypted to a temporary [UUID].enc file.
        5. Uploaded/moved to proper storage provider (R2 / O2 Sync).
        6. Performed cleanup & eviction.
        """
        if not os.path.exists(file_path):
            logger.error(f"Cannot process file. Path does not exist: {file_path}")
            return None

        file_size = os.path.getsize(file_path)
        if file_size == 0:
            logger.warning(f"Ignoring empty file: {file_path}")
            return None

        file_id = str(uuid.uuid4())
        logger.info(f"Starting ingestion pipeline for {file_path} (Assigned UUID: {file_id})")

        try:
            # Fase 1: Extracción de Metadatos
            hash_sha256 = self.calculate_sha256(file_path)
            mime_type = self.get_mime_type(file_path)
            logger.info(f"Metadata - Size: {file_size} bytes, MIME: {mime_type}, SHA256: {hash_sha256}")

            # Check if file has already been processed by comparing hash (deduplication)
            # In some cases, we might want to skip. Let's log it.
            
            # Fase 2: Vectorización AI
            chunks = []
            should_vectorize = (
                mime_type.startswith("text/") or 
                mime_type in [
                    "application/pdf",
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "application/msword"
                ]
            )
            if should_vectorize:
                logger.info("Extracting and vectorizing text...")
                chunks = self.ai_service.process_document(file_path, mime_type)
                logger.info(f"Document processed into {len(chunks)} chunks.")

            # Fase 3: Persistencia en VPS (Database)
            storage_status = "cloud_r2" if self.is_hot_file(mime_type, file_size) else "local_sync"
            logger.info(f"Routing Decision: file is {'HOT' if storage_status == 'cloud_r2' else 'COLD'}. Status: {storage_status}")
            
            # Save metadata and chunks within a single transaction
            self.db_repo.insert_file_and_chunks(
                file_id=file_id,
                hash_sha256=hash_sha256,
                file_size=file_size,
                mime_type=mime_type,
                storage_status=storage_status,
                chunks=chunks
            )

            # Fase 4: Cifrado Simétrico
            temp_enc_path = os.path.join(settings.STAGING_DIR, f"{file_id}.enc")
            # Ensure the directory for temp file exists
            os.makedirs(os.path.dirname(temp_enc_path), exist_ok=True)
            
            logger.info(f"Encrypting file {file_path} to {temp_enc_path}...")
            self.crypto_service.encrypt_file(file_path, temp_enc_path)
            logger.info("Encryption completed.")

            # Fase 5: Enrutamiento e Inmutabilidad
            upload_success = False
            if storage_status == "cloud_r2":
                upload_success = self.r2_provider.upload(file_id, temp_enc_path)
            else:
                upload_success = self.o2_provider.upload(file_id, temp_enc_path)

            if not upload_success:
                raise RuntimeError(f"Storage upload/move failed for provider: {storage_status}")

            # Fase 6: Evicción y Limpieza Absoluta
            if storage_status == "cloud_r2":
                # Clear original and temporary encrypted file
                logger.info("Cleaning up hot storage local files...")
                if os.path.exists(temp_enc_path):
                    os.remove(temp_enc_path)
                # Delete original file
                if os.path.exists(file_path):
                    os.remove(file_path)
                logger.info("Hot file local cleanup finished.")
            else:
                # Cold storage: Eviction to 0 bytes
                logger.info("Initiating eviction to 0 bytes on O2 sync folder...")
                # Clear temporary encrypted file from staging
                if os.path.exists(temp_enc_path):
                    os.remove(temp_enc_path)
                # Evict the synchronized O2 file
                self.o2_provider.evict_file(file_id)
                # Delete original file
                if os.path.exists(file_path):
                    os.remove(file_path)
                logger.info("Cold file eviction and cleanup finished.")

            # Signal-specific cleanup: If it was loaded from Signal attachment, verify it's deleted.
            if is_signal_attachment and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    logger.info("Signal temporary plain attachment deleted.")
                except Exception as e:
                    logger.warning(f"Could not delete Signal original attachment {file_path}: {e}")

            logger.info(f"Successfully processed file: {file_id}")
            return file_id

        except Exception as e:
            logger.error(f"Pipeline failed for file {file_path}: {e}")
            # Ensure database is clean if we failed before commit (handled by db transactions),
            # but if we failed halfway, we should try to clean up the temporary files.
            temp_enc_path = os.path.join(settings.STAGING_DIR, f"{file_id}.enc")
            if os.path.exists(temp_enc_path):
                try:
                    os.remove(temp_enc_path)
                except Exception:
                    pass
            raise e
