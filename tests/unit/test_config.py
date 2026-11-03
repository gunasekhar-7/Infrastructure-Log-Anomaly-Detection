"""Unit tests for configuration loading and validation."""

from config.settings import AppSettings, get_settings


def test_settings_defaults(mock_settings: AppSettings) -> None:
    """Verify default configuration attributes are appropriately set."""
    assert mock_settings.APP_NAME == "LogPulse AnomalyGuard"
    assert mock_settings.APP_ENV == "testing"
    assert mock_settings.API_PORT == 8000
    assert mock_settings.DRAIN3_SIM_TH == 0.5
    assert mock_settings.DRAIN3_DEPTH == 4
    assert mock_settings.DEEPLOG_TOP_K == 9
    assert mock_settings.ALERT_COOLDOWN_SECONDS == 300


def test_settings_custom_env(monkeypatch) -> None:
    """Verify settings pick up overridden environment variables."""
    monkeypatch.setenv("APP_NAME", "CustomLogPulse")
    monkeypatch.setenv("DRAIN3_SIM_TH", "0.75")
    monkeypatch.setenv("ALERT_COOLDOWN_SECONDS", "60")
    get_settings.cache_clear()

    custom_settings = get_settings()
    assert custom_settings.APP_NAME == "CustomLogPulse"
    assert custom_settings.DRAIN3_SIM_TH == 0.75
    assert custom_settings.ALERT_COOLDOWN_SECONDS == 60

