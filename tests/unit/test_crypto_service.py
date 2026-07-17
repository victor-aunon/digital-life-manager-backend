import os
import tempfile
import pytest
from src.services.crypto_service import CryptoService

def test_crypto_service_encrypt_decrypt_lifecycle():
    # 1. Generate a valid Fernet Key
    key = CryptoService.generate_key()
    service = CryptoService(key=key)

    # 2. Create a temporary source file with repeatable content (larger than 64KB to test chunking)
    source_content = b"A" * (150 * 1024)  # 150 KB
    
    with tempfile.TemporaryDirectory() as tmpdir:
        source_path = os.path.join(tmpdir, "source.txt")
        encrypted_path = os.path.join(tmpdir, "source.txt.enc")
        decrypted_path = os.path.join(tmpdir, "decrypted.txt")

        with open(source_path, "wb") as f:
            f.write(source_content)

        # 3. Encrypt the file
        service.encrypt_file(source_path, encrypted_path)
        assert os.path.exists(encrypted_path)
        assert os.path.getsize(encrypted_path) > 0

        # Verify that encrypted file doesn't just contain plaintext "A"s
        with open(encrypted_path, "rb") as f:
            enc_data = f.read()
            assert b"A" * 100 not in enc_data

        # 4. Decrypt the file
        service.decrypt_file(encrypted_path, decrypted_path)
        assert os.path.exists(decrypted_path)

        # Verify exact match
        with open(decrypted_path, "rb") as f:
            dec_data = f.read()
            assert dec_data == source_content


def test_crypto_service_invalid_file():
    key = CryptoService.generate_key()
    service = CryptoService(key=key)
    
    with pytest.raises(FileNotFoundError):
        service.encrypt_file("non_existent_file.xyz", "dest.enc")
