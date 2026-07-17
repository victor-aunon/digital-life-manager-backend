import logging
from typing import List, Dict, Any, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from src.core.config import settings

logger = logging.getLogger(__name__)

class DBRepository:
    def __init__(self, dsn: Optional[str] = None):
        self.dsn = dsn or settings.DATABASE_URL

    def _get_connection(self):
        return psycopg2.connect(self.dsn)

    def create_tables(self) -> None:
        """Creates the necessary tables if they do not exist.
        Ensures pgvector extension is enabled.
        """
        create_files_table = """
        CREATE TABLE IF NOT EXISTS files (
            file_id UUID PRIMARY KEY,
            hash_sha256 VARCHAR(64) NOT NULL UNIQUE,
            file_size BIGINT NOT NULL,
            mime_type VARCHAR(255) NOT NULL,
            storage_status VARCHAR(50) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        create_chunks_table = """
        CREATE TABLE IF NOT EXISTS document_chunks (
            chunk_id SERIAL PRIMARY KEY,
            file_id UUID NOT NULL REFERENCES files(file_id) ON DELETE CASCADE,
            chunk_text TEXT NOT NULL,
            embedding VECTOR NOT NULL
        );
        """
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                # Enable vector extension
                cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                cursor.execute(create_files_table)
                cursor.execute(create_chunks_table)
            conn.commit()
            logger.info("Database tables initialized successfully.")
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Failed to initialize tables: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def insert_file_and_chunks(
        self, 
        file_id: str, 
        hash_sha256: str, 
        file_size: int, 
        mime_type: str, 
        storage_status: str, 
        chunks: List[Dict[str, Any]]
    ) -> None:
        """Inserts a file metadata and its associated vector chunks in a single transaction."""
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                # Insert File
                cursor.execute(
                    """
                    INSERT INTO files (file_id, hash_sha256, file_size, mime_type, storage_status)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (hash_sha256) DO NOTHING;
                    """,
                    (file_id, hash_sha256, file_size, mime_type, storage_status)
                )
                
                # Check if insert actually happened (it might conflict and do nothing)
                # If doing nothing, we shouldn't insert chunks as file wasn't added now, or we can handle it
                # For safety, let's make sure we insert chunks if file exists or was created.
                for chunk in chunks:
                    cursor.execute(
                        """
                        INSERT INTO document_chunks (file_id, chunk_text, embedding)
                        VALUES (%s, %s, %s::vector);
                        """,
                        (file_id, chunk["text"], chunk["embedding"])
                    )
            conn.commit()
            logger.info(f"Successfully saved file {file_id} with {len(chunks)} chunks.")
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Failed to insert file and chunks: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def get_file(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single file's metadata."""
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    "SELECT file_id, hash_sha256, file_size, mime_type, storage_status, created_at FROM files WHERE file_id = %s;",
                    (file_id,)
                )
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"Error fetching file {file_id}: {e}")
            return None
        finally:
            if conn:
                conn.close()

    def update_storage_status(self, file_id: str, status: str) -> bool:
        """Updates the storage status of a file."""
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE files SET storage_status = %s WHERE file_id = %s;",
                    (status, file_id)
                )
            conn.commit()
            return True
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Failed to update storage status for {file_id}: {e}")
            return False
        finally:
            if conn:
                conn.close()

    def get_pending_deletions(self) -> List[Dict[str, Any]]:
        """Retrieves all files marked as pending_deletion."""
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    "SELECT file_id, hash_sha256, file_size, mime_type, storage_status FROM files WHERE storage_status = 'pending_deletion';"
                )
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error fetching pending deletions: {e}")
            return []
        finally:
            if conn:
                conn.close()

    def delete_file(self, file_id: str) -> bool:
        """Deletes a file from the database. Foreign keys cascade deletes on document_chunks."""
        conn = None
        try:
            conn = self._get_connection()
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM files WHERE file_id = %s;", (file_id,))
            conn.commit()
            return True
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Failed to delete file {file_id}: {e}")
            return False
        finally:
            if conn:
                conn.close()
