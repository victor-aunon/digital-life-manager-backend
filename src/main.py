import asyncio
import logging
from typing import Optional, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse

from src.core.config import settings
from src.infrastructure.db_repository import DBRepository
from src.services.crypto_service import CryptoService
from src.infrastructure.storage.r2_provider import CloudflareR2Provider
from src.infrastructure.storage.o2_provider import LocalSyncProvider
from src.infrastructure.signal_receiver import WatchdogService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("main")

# AppState Container for Lazy-Loading services to prevent import-time side-effects (e.g. boto3 constructors)
class AppState:
    _db_repo: Optional[DBRepository] = None
    _crypto_service: Optional[CryptoService] = None
    _r2_provider: Optional[CloudflareR2Provider] = None
    _o2_provider: Optional[LocalSyncProvider] = None
    _watchdog_service: Optional[WatchdogService] = None

    @classmethod
    def get_db_repo(cls) -> DBRepository:
        if cls._db_repo is None:
            cls._db_repo = DBRepository()
        return cls._db_repo

    @classmethod
    def get_crypto_service(cls) -> CryptoService:
        if cls._crypto_service is None:
            cls._crypto_service = CryptoService()
        return cls._crypto_service

    @classmethod
    def get_r2_provider(cls) -> CloudflareR2Provider:
        if cls._r2_provider is None:
            cls._r2_provider = CloudflareR2Provider()
        return cls._r2_provider

    @classmethod
    def get_o2_provider(cls) -> LocalSyncProvider:
        if cls._o2_provider is None:
            cls._o2_provider = LocalSyncProvider()
        return cls._o2_provider

    @classmethod
    def get_watchdog_service(cls) -> WatchdogService:
        if cls._watchdog_service is None:
            from src.core.orchestrator import Orchestrator
            orchestrator = Orchestrator(
                db_repo=cls.get_db_repo(),
                crypto_service=cls.get_crypto_service(),
                r2_provider=cls.get_r2_provider(),
                o2_provider=cls.get_o2_provider()
            )
            cls._watchdog_service = WatchdogService(orchestrator=orchestrator)
        return cls._watchdog_service


# FastAPI Dependencies
def dep_db_repo() -> DBRepository:
    return AppState.get_db_repo()

def dep_crypto_service() -> CryptoService:
    return AppState.get_crypto_service()

def dep_r2_provider() -> CloudflareR2Provider:
    return AppState.get_r2_provider()

def dep_o2_provider() -> LocalSyncProvider:
    return AppState.get_o2_provider()


# Garbage collection settings
GC_INTERVAL_SECONDS = 300  # Check every 5 minutes
gc_task: Optional[asyncio.Task] = None

async def run_garbage_collector():
    """Background task that runs periodically to clean up files marked as 'pending_deletion'."""
    while True:
        try:
            logger.info("Running garbage collection cycle...")
            db_repo = AppState.get_db_repo()
            r2_provider = AppState.get_r2_provider()
            o2_provider = AppState.get_o2_provider()

            pending_files = db_repo.get_pending_deletions()
            if pending_files:
                logger.info(f"Found {len(pending_files)} files marked for deletion.")
                from src.core.orchestrator import Orchestrator
                
                # Instantiate orchestrator to reuse is_hot_file routing rules
                orchestrator = Orchestrator(
                    db_repo=db_repo,
                    crypto_service=None,
                    ai_service=None,
                    r2_provider=r2_provider,
                    o2_provider=o2_provider
                )

                for file_info in pending_files:
                    file_id = str(file_info["file_id"])
                    mime_type = file_info["mime_type"]
                    file_size = file_info["file_size"]
                    logger.info(f"Processing deletion for file: {file_id} (MIME: {mime_type}, Size: {file_size})")
                    
                    # Determine which provider stored the file using deterministic routing rules
                    is_hot = orchestrator.is_hot_file(mime_type, file_size)
                    
                    if is_hot:
                        logger.info(f"File {file_id} is HOT. Deleting from Cloudflare R2...")
                        success = r2_provider.delete(file_id)
                    else:
                        logger.info(f"File {file_id} is COLD. Deleting from O2 Cloud...")
                        success = o2_provider.delete(file_id)
                    
                    if success:
                        # Perform cascade delete from DB
                        db_success = db_repo.delete_file(file_id)
                        if db_success:
                            logger.info(f"Successfully purged file {file_id} from database.")
                        else:
                            logger.error(f"Failed to delete file {file_id} from database.")
                    else:
                        logger.error(f"Failed to completely remove storage object for {file_id} from its provider.")
            else:
                logger.info("No pending deletions found.")
        except Exception as e:
            logger.error(f"Error in garbage collection loop: {e}")
        
        await asyncio.sleep(GC_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup:
    global gc_task
    logger.info("Starting up Local Ingestion Worker...")
    
    # 1. Initialize DB tables
    try:
        AppState.get_db_repo().create_tables()
    except Exception as e:
        logger.error(f"Could not connect or setup DB tables on startup: {e}")
        # We don't crash the server, but log it clearly
    
    # 2. Start Watchdog observer
    try:
        AppState.get_watchdog_service().start()
    except Exception as e:
        logger.error(f"Could not start Watchdog Service on startup: {e}")

    # 3. Start GC background task
    gc_task = asyncio.create_task(run_garbage_collector())
    
    yield
    
    # Shutdown:
    logger.info("Shutting down Local Ingestion Worker...")
    
    # 1. Stop GC background task
    if gc_task:
        gc_task.cancel()
        try:
            await gc_task
        except asyncio.CancelledError:
            pass
            
    # 2. Stop Watchdog observer
    try:
        AppState.get_watchdog_service().stop()
    except Exception as e:
        logger.error(f"Error stopping Watchdog: {e}")


app = FastAPI(
    title="Local Ingestion Worker & Streaming API",
    description="Python daemon and secure streaming API for local file ingestion and storage eviction.",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/api/download/{file_id}")
async def download_file(
    file_id: str,
    db_repo: DBRepository = Depends(dep_db_repo),
    crypto_service: CryptoService = Depends(dep_crypto_service),
    r2_provider: CloudflareR2Provider = Depends(dep_r2_provider),
    o2_provider: LocalSyncProvider = Depends(dep_o2_provider)
):
    """Endpoint serving decryped file stream directly in RAM without writing to local disk.
    Auto-detects backend storage provider (R2 / O2 Sync) and streams back decrypted payload.
    """
    logger.info(f"Received download request for file: {file_id}")
    
    # 1. Consult database for file metadata
    file_info = db_repo.get_file(file_id)
    if not file_info:
        logger.warning(f"File {file_id} not found in database.")
        raise HTTPException(status_code=404, detail="File not found")

    mime_type = file_info["mime_type"]
    storage_status = file_info["storage_status"]
    logger.info(f"File metadata - MIME: {mime_type}, Storage Status: {storage_status}")

    if storage_status == "pending_deletion":
        raise HTTPException(status_code=410, detail="File has been deleted or is pending deletion")

    # 2. Select appropriate storage provider
    if storage_status == "cloud_r2":
        provider = r2_provider
    elif storage_status == "local_sync":
        provider = o2_provider
    else:
        logger.error(f"Unknown storage status '{storage_status}' for file {file_id}")
        raise HTTPException(status_code=500, detail="Internal storage configuration error")

    # 3. Securely stream and decrypt on-the-fly
    def decrypted_stream_generator():
        try:
            logger.info(f"Opening encrypted stream for {file_id}...")
            encrypted_stream = provider.open_encrypted_stream(file_id)
        except Exception as e:
            logger.error(f"Failed to open source storage stream: {e}")
            raise HTTPException(status_code=503, detail="Storage provider unavailable")

        try:
            logger.info(f"Streaming decrypted chunks for {file_id}...")
            for decrypted_chunk in crypto_service.decrypt_stream(encrypted_stream):
                yield decrypted_chunk
            logger.info(f"Finished streaming file {file_id}.")
        except Exception as e:
            logger.error(f"Error occurred during streaming decryption of {file_id}: {e}")
            # FastAPI handles exceptions during streaming response internally, but let's log it
            raise
        finally:
            try:
                encrypted_stream.close()
                logger.info(f"Closed storage stream for {file_id}")
            except Exception as e:
                logger.warning(f"Failed to close source stream for {file_id}: {e}")

    # Return FastAPI StreamingResponse with proper MIME type
    return StreamingResponse(
        decrypted_stream_generator(),
        media_type=mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{file_id}"'
        }
    )


@app.get("/health")
async def health_check():
    """Simple health endpoint."""
    return {"status": "healthy", "service": "local-ingestion-worker"}
