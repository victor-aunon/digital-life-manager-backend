import os
import pytest

# Configure mock environment variables before any part of the application imports config
os.environ["DATABASE_URL"] = "postgresql://test_user:test_password@localhost:5432/test_db"
os.environ["ENCRYPTION_KEY"] = "gK4_G-F8U78v3Mh93z_K9VbA4H1ZpXzD6b9w7y7v7X0="
os.environ["STAGING_DIR"] = "/tmp/staging"
os.environ["O2_SYNC_DIR"] = "/tmp/o2_sync"
os.environ["R2_ACCESS_KEY_ID"] = "mock_key_id"
os.environ["R2_SECRET_ACCESS_KEY"] = "mock_secret_key"
os.environ["R2_ENDPOINT_URL"] = "http://s3.amazonaws.com"
os.environ["R2_BUCKET_NAME"] = "mock-bucket-name"
os.environ["SIGNAL_ATTACHMENTS_DIR"] = "/tmp/signal"
