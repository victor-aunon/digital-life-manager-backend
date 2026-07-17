from typing import Protocol, Generator, Any

class StorageProvider(Protocol):
    def upload(self, file_id: str, local_path: str) -> bool:
        """Uploads/moves an encrypted file to the storage backend."""
        ...

    def delete(self, file_id: str) -> bool:
        """Deletes an encrypted file from the storage backend."""
        ...

    def download_stream(self, file_id: str) -> Generator[bytes, None, None]:
        """Downloads/reads an encrypted file as a byte stream in chunks."""
        ...

    def open_encrypted_stream(self, file_id: str) -> Any:
        """Opens and returns a file-like stream of the encrypted file.
        The returned object must implement `read(size)`.
        """
        ...
