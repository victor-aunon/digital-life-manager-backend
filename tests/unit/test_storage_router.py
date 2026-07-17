import pytest
from src.core.orchestrator import Orchestrator

def test_storage_router_rules():
    # Instantiate the orchestrator with mocked components
    orchestrator = Orchestrator(
        db_repo=None,
        crypto_service=None,
        ai_service=None,
        r2_provider=None,
        o2_provider=None
    )

    # 1. Hot combinations: Text, office docs, pdfs, images AND size < 50MB
    assert orchestrator.is_hot_file("application/pdf", 40 * 1024 * 1024) is True
    assert orchestrator.is_hot_file("text/plain", 10 * 1024 * 1024) is True
    assert orchestrator.is_hot_file("image/png", 5 * 1024 * 1024) is True
    assert orchestrator.is_hot_file("application/vnd.openxmlformats-officedocument.wordprocessingml.document", 2 * 1024 * 1024) is True

    # 2. Cold combinations: Multimedia (video/*, audio/*), compressed, or size >= 50MB
    # Larger than 50MB (even if PDF)
    assert orchestrator.is_hot_file("application/pdf", 51 * 1024 * 1024) is False
    assert orchestrator.is_hot_file("text/plain", 50 * 1024 * 1024) is False
    
    # Video/Audio (even if small)
    assert orchestrator.is_hot_file("video/mp4", 10 * 1024 * 1024) is False
    assert orchestrator.is_hot_file("audio/mpeg", 2 * 1024 * 1024) is False
    
    # Compressed / Archive formats (which are octet-stream or compressed)
    assert orchestrator.is_hot_file("application/zip", 4 * 1024 * 1024) is False
    assert orchestrator.is_hot_file("application/x-rar-compressed", 4 * 1024 * 1024) is False
    assert orchestrator.is_hot_file("application/octet-stream", 4 * 1024 * 1024) is False


def test_storage_router_configurable_limit(mocker):
    # Mock settings.MAX_HOT_SIZE_MB to be 10MB
    mocker.patch("src.core.orchestrator.settings.MAX_HOT_SIZE_MB", 10)

    orchestrator = Orchestrator(
        db_repo=None,
        crypto_service=None,
        ai_service=None,
        r2_provider=None,
        o2_provider=None
    )

    # 8MB PDF should go to R2 (Hot)
    assert orchestrator.is_hot_file("application/pdf", 8 * 1024 * 1024) is True
    # 12MB PDF should go to O2 (Cold, because it exceeds 10MB)
    assert orchestrator.is_hot_file("application/pdf", 12 * 1024 * 1024) is False

