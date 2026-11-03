"""Global Pytest Fixtures and Test Environment Setup."""

import os
from collections.abc import Generator
from pathlib import Path

import pytest

from config.settings import AppSettings, get_settings


@pytest.fixture(autouse=True)
def test_env_setup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Generator[None, None, None]:
    """Ensure test runs use an isolated environment and temporary database."""
    test_db = tmp_path / "test.db"
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{test_db}")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    # Clear lru_cache for get_settings during testing
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def mock_settings() -> AppSettings:
    """Fixture providing fresh test settings."""
    return get_settings()
