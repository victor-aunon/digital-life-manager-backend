import os
import struct
from typing import Generator
from cryptography.fernet import Fernet
from src.core.config import settings

CHUNK_SIZE = 64 * 1024  # 64 KB

class CryptoService:
    def __init__(self, key: str = settings.ENCRYPTION_KEY):
        """Initializes the CryptoService with a Fernet key."""
        self.fernet = Fernet(key.encode() if isinstance(key, str) else key)

    @staticmethod
    def generate_key() -> str:
        """Helper to generate a new Fernet key."""
        return Fernet.generate_key().decode()

    def encrypt_file(self, source_path: str, dest_path: str) -> None:
        """Encrypts a file in 64KB chunks to protect RAM.
        Each chunk is encrypted individually using Fernet, and written with a 4-byte length prefix.
        """
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Source file not found: {source_path}")
            
        with open(source_path, "rb") as f_in, open(dest_path, "wb") as f_out:
            while True:
                chunk = f_in.read(CHUNK_SIZE)
                if not chunk:
                    break
                # Encrypt chunk
                encrypted_chunk = self.fernet.encrypt(chunk)
                # Write length of encrypted chunk as a 4-byte big-endian integer
                f_out.write(struct.pack(">I", len(encrypted_chunk)))
                # Write the actual encrypted chunk
                f_out.write(encrypted_chunk)

    def decrypt_file(self, source_path: str, dest_path: str) -> None:
        """Decrypts a file in chunks to protect RAM."""
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Encrypted source file not found: {source_path}")

        with open(source_path, "rb") as f_in, open(dest_path, "wb") as f_out:
            for decrypted_chunk in self.decrypt_stream(f_in):
                f_out.write(decrypted_chunk)

    def decrypt_stream(self, file_like_object) -> Generator[bytes, None, None]:
        """Generator that reads an encrypted file-like stream and yields decrypted chunks.
        Protects RAM by reading and yielding one chunk at a time.
        """
        while True:
            # Read 4-byte length prefix
            len_bytes = file_like_object.read(4)
            if not len_bytes:
                break
            if len(len_bytes) < 4:
                raise ValueError("Malformed encrypted stream: truncated length prefix")
                
            chunk_len = struct.unpack(">I", len_bytes)[0]
            encrypted_chunk = file_like_object.read(chunk_len)
            if len(encrypted_chunk) < chunk_len:
                raise ValueError("Malformed encrypted stream: truncated chunk payload")
                
            # Decrypt chunk and yield
            yield self.fernet.decrypt(encrypted_chunk)
