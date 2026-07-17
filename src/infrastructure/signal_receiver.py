import os
import time
import logging
from typing import Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent
from src.core.config import settings
from src.core.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

class StagingHandler(FileSystemEventHandler):
    def __init__(self, orchestrator: Orchestrator):
        super().__init__()
        self.orchestrator = orchestrator

    def on_created(self, event):
        if event.is_directory:
            return

        file_path = event.src_path
        # Ignore encrypted files and temporary files
        if file_path.endswith(".enc") or file_path.endswith(".tmp"):
            return

        logger.info(f"[Watchdog Staging] New file detected: {file_path}")
        # Give a small delay to ensure file write is completed by the OS
        time.sleep(1.0)
        
        try:
            self.orchestrator.process_file(file_path, is_signal_attachment=False)
        except Exception as e:
            logger.error(f"[Watchdog Staging] Failed to process {file_path}: {e}")


class SignalAttachmentHandler(FileSystemEventHandler):
    def __init__(self, orchestrator: Orchestrator):
        super().__init__()
        self.orchestrator = orchestrator

    def on_created(self, event):
        if event.is_directory:
            return

        file_path = event.src_path
        logger.info(f"[Watchdog Signal] New attachment detected: {file_path}")
        # Give a small delay to ensure signal-cli has finished downloading the attachment
        time.sleep(1.0)

        try:
            self.orchestrator.process_file(file_path, is_signal_attachment=True)
        except Exception as e:
            logger.error(f"[Watchdog Signal] Failed to process attachment {file_path}: {e}")


class WatchdogService:
    def __init__(self, orchestrator: Optional[Orchestrator] = None):
        self.orchestrator = orchestrator or Orchestrator()
        self.observer = Observer()

    def start(self) -> None:
        """Starts monitoring /staging and Signal attachments folder."""
        # Ensure staging dir exists
        if not os.path.exists(settings.STAGING_DIR):
            os.makedirs(settings.STAGING_DIR, exist_ok=True)
            logger.info(f"Created staging directory: {settings.STAGING_DIR}")
            
        # Ensure signal attachments dir exists
        if not os.path.exists(settings.SIGNAL_ATTACHMENTS_DIR):
            os.makedirs(settings.SIGNAL_ATTACHMENTS_DIR, exist_ok=True)
            logger.info(f"Created Signal attachments directory: {settings.SIGNAL_ATTACHMENTS_DIR}")

        # Schedule staging monitoring
        staging_handler = StagingHandler(self.orchestrator)
        self.observer.schedule(staging_handler, path=settings.STAGING_DIR, recursive=False)
        logger.info(f"Scheduled watchdog observer for staging: {settings.STAGING_DIR}")

        # Schedule signal attachments monitoring
        signal_handler = SignalAttachmentHandler(self.orchestrator)
        self.observer.schedule(signal_handler, path=settings.SIGNAL_ATTACHMENTS_DIR, recursive=True)
        logger.info(f"Scheduled watchdog observer for Signal attachments: {settings.SIGNAL_ATTACHMENTS_DIR}")

        self.observer.start()
        logger.info("Watchdog services started successfully.")

    def stop(self) -> None:
        """Stops the observer."""
        self.observer.stop()
        self.observer.join()
        logger.info("Watchdog services stopped cleanly.")
