import pytest
from unittest.mock import MagicMock
from src.services.ai_service import AIService

def test_text_chunking():
    service = AIService()
    # Create text that is long enough to trigger chunking
    # 1500 chars should yield at least 2 chunks (since chunk_size=1000 and overlap=200)
    long_text = "A" * 1500
    chunks = service.chunk_text(long_text)
    
    assert len(chunks) >= 2
    assert all(len(c) <= 1000 for c in chunks)
    # Check that overlap is correct: first chunk should end with "A"s, second starts with "A"s
    assert chunks[1].startswith("A")


def test_get_embedding_success(mocker):
    # Mock httpx.post
    mock_post = mocker.patch("httpx.post")
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"embedding": [0.1, 0.2, 0.3]}
    mock_post.return_value = mock_response

    service = AIService()
    embedding = service.get_embedding("Hello test")
    
    assert embedding == [0.1, 0.2, 0.3]
    mock_post.assert_called_once_with(
        service.ollama_url,
        json={"model": service.model_name, "prompt": "Hello test"},
        timeout=30.0
    )


def test_get_embedding_failure(mocker):
    # Mock httpx.post to raise an exception or fail
    mock_post = mocker.patch("httpx.post", side_effect=Exception("Connection refused"))
    
    service = AIService()
    # Should handle error gracefully and return a fallback vector
    embedding = service.get_embedding("Hello test")
    
    assert isinstance(embedding, list)
    assert len(embedding) == 384
    assert all(val == 0.0 for val in embedding)
