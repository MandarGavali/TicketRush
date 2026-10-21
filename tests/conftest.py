"""Runs before any test module is imported: point the app at the test database and Redis db 1."""

import os

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://ticketrush:ticketrush@localhost:5432/ticketrush_test",
)
os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", "redis://localhost:6379/1")
os.environ["ENABLE_SWEEPER"] = "false"
os.environ["JWT_SECRET"] = "test-secret-that-is-long-enough-for-hs256"
