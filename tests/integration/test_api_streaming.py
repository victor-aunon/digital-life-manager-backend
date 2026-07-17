import io
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from src.main import app, AppState

client = TestClient(app)

@pytest.fixture(autouse=True)
def mock_app_state(mocker):
    """Autouse fixture to mock AppState classmethods.
    Prevents instantiating real databases/boto3 client objects during test imports and runs.
    """
    mock_db = MagicMock()
    mock_r2 = MagicMock()
    mock_o2 = MagicMock()
    mock_crypto = MagicMock()
    
    # Setup mock returns
    mocker.patch("src.main.AppState.get_db_repo", return_value=mock_db)
    mocker.patch("src.main.AppState.get_r2_provider", return_value=mock_r2)
    mocker.patch("src.main.AppState.get_o2_provider", return_value=mock_o2)
    mocker.patch("src.main.AppState.get_crypto_service", return_value=mock_crypto)
    
    # Mock dependency functions
    mocker.patch("src.main.dep_db_repo", return_value=mock_db)
    mocker.patch("src.main.dep_r2_provider", return_value=mock_r2)
    mocker.patch("src.main.dep_o2_provider", return_value=mock_o2)
    mocker.patch("src.main.dep_crypto_service", return_value=mock_crypto)
    
    return {
        "db": mock_db,
        "r2": mock_r2,
        "o2": mock_o2,
        "crypto": mock_crypto
    }


def test_api_download_r2_success(mock_app_state):
    db_repo = mock_app_state["db"]
    r2_provider = mock_app_state["r2"]
    crypto_service = mock_app_state["crypto"]
    
    file_id = "test-uuid-r2-download"
    mime_type = "application/pdf"
    
    # 1. Mock DB call to return hot storage metadata
    db_repo.get_file.return_value = {
        "file_id": file_id,
        "hash_sha256": "some-hash",
        "file_size": 1000,
        "mime_type": mime_type,
        "storage_status": "cloud_r2"
    }

    # 2. Mock R2 Provider open_encrypted_stream and crypto_service decrypt_stream
    plain_content = b"PDF Plain Content Payload"
    crypto_service.decrypt_stream.return_value = [plain_content]

    mock_stream = MagicMock()
    r2_provider.open_encrypted_stream.return_value = mock_stream

    # 3. Call endpoint
    response = client.get(f"/api/download/{file_id}")
    
    assert response.status_code == 200
    assert response.headers["content-type"] == mime_type
    assert response.headers["content-disposition"] == f'attachment; filename="{file_id}"'
    assert response.content == plain_content
    
    # Verify that stream was closed in finally block
    mock_stream.close.assert_called_once()


def test_api_download_local_sync_success(mock_app_state):
    db_repo = mock_app_state["db"]
    o2_provider = mock_app_state["o2"]
    crypto_service = mock_app_state["crypto"]
    
    file_id = "test-uuid-local-download"
    mime_type = "video/mp4"
    
    # 1. Mock DB call to return cold storage metadata
    db_repo.get_file.return_value = {
        "file_id": file_id,
        "hash_sha256": "some-hash",
        "file_size": 100000,
        "mime_type": mime_type,
        "storage_status": "local_sync"
    }

    # 2. Mock O2 Provider and Crypto
    plain_content = b"Video Plain Content Payload"
    crypto_service.decrypt_stream.return_value = [plain_content]

    mock_stream = MagicMock()
    o2_provider.open_encrypted_stream.return_value = mock_stream

    # 3. Call endpoint
    response = client.get(f"/api/download/{file_id}")
    
    assert response.status_code == 200
    assert response.headers["content-type"] == mime_type
    assert response.content == plain_content
    mock_stream.close.assert_called_once()


def test_api_download_not_found(mock_app_state):
    db_repo = mock_app_state["db"]
    file_id = "non-existent-uuid"
    
    # Mock DB return None
    db_repo.get_file.return_value = None

    response = client.get(f"/api/download/{file_id}")
    assert response.status_code == 404
    assert response.json()["detail"] == "File not found"


def test_api_download_deleted_status(mock_app_state):
    db_repo = mock_app_state["db"]
    file_id = "deleted-uuid"
    
    # Mock DB return deleted status
    db_repo.get_file.return_value = {
        "file_id": file_id,
        "hash_sha256": "some-hash",
        "file_size": 1000,
        "mime_type": "text/plain",
        "storage_status": "pending_deletion"
    }

    response = client.get(f"/api/download/{file_id}")
    assert response.status_code == 410
    assert response.json()["detail"] == "File has been deleted or is pending deletion"
