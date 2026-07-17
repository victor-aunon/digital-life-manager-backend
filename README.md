# Local Ingestion Worker & Streaming API

A modular, secure, and resilient local background worker (daemon) and streaming API written in Python. This service monitors local staging and Signal attachments directories, encrypts files using AES-256 (chunk-by-chunk Fernet), splits and vectorizes document text using local Ollama, stores metadata and vector embeddings in a remote PostgreSQL instance with pgvector, routes hot/cold storage (Cloudflare R2 vs O2 Cloud), and implements OS-level eviction to 0 bytes for cold files.

## Project Structure

```text
├── .env.example
├── README.md
├── requirements.txt
├── src/
│   ├── __init__.py
│   ├── main.py                 # FastAPI Application + Lifecycle/GC Background Task
│   ├── core/
│   │   ├── config.py           # Strictly typed settings using pydantic-settings
│   │   └── orchestrator.py     # Main ingestion pipeline (Analyze -> Encrypt -> Route)
│   ├── domain/
│   │   └── storage_base.py     # Protocol StorageProvider
│   ├── infrastructure/
│   │   ├── db_repository.py    # Database transactions with PostgreSQL & pgvector
│   │   ├── signal_receiver.py  # Watchdog listeners for staging & Signal attachments
│   │   └── storage/
│   │       ├── r2_provider.py  # Cloudflare R2 boto3 client
│   │       └── o2_provider.py  # O2 Cloud local synced folder + Eviction
│   └── services/
│       ├── crypto_service.py   # Chunk-by-chunk Fernet AES-256 encryption/decryption
│       └── ai_service.py       # Langchain character splitting & Ollama embeddings
└── tests/
    ├── unit/
    │   ├── test_crypto_service.py
    │   ├── test_ai_service.py
    │   └── test_storage_router.py
    └── integration/
        ├── test_r2_provider_with_moto.py
        └── test_api_streaming.py
```

## Setup & Installation

1. **Create and Activate a Virtual Environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables:**
   Copy the example environment file and fill in your credentials:
   ```bash
   cp .env.example .env
   ```
   Generate a secure encryption key using Python:
   ```python
   python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
   Paste the generated key as `ENCRYPTION_KEY` inside your `.env` file.

## Running the Tests

To execute the unit and integration test suite, run:
```bash
pytest -v
```

The test suite includes:
- **Unit Tests:** Confirming identical bit-by-bit chunked encryption/decryption, document text chunking limits, and storage routing logic.
- **Integration Tests:** Verifying Cloudflare R2 uploads with AWS S3 mocks (`moto`) and FastAPI on-the-fly decryption streams using `TestClient`.

## Executing the Service

To run the worker daemon along with the FastAPI streaming server, run:
```bash
uvicorn src.main:app --host 127.0.0.1 --port 8000
```

The service will:
1. Initialize/migrate database tables on startup.
2. Spin up separate filesystem observers (`watchdog`) monitoring your configured `STAGING_DIR` and `SIGNAL_ATTACHMENTS_DIR`.
3. Start a background garbage collector task that polls the database for files marked as `pending_deletion` and purges them every 5 minutes.
4. Expose `GET /api/download/{file_id}` to let the Next.js Dashboard download and stream decrypted content directly in RAM.
