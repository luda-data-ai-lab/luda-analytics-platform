"""config.Config 테스트."""

import importlib
import os
from datetime import timedelta

import pytest

import config


def _reload_config():
    return importlib.reload(config).Config


@pytest.fixture(autouse=True)
def _restore_config():
    """환경변수 조작 후 원래 config 모듈 상태로 복원."""
    yield
    importlib.reload(config)


def test_defaults_when_env_missing(monkeypatch):
    monkeypatch.delenv('SECRET_KEY', raising=False)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    cfg = _reload_config()

    assert cfg.SECRET_KEY == 'dev-secret-key-change-in-production'
    assert cfg.SQLALCHEMY_DATABASE_URI.startswith('postgresql+psycopg2://')


def test_env_overrides(monkeypatch):
    monkeypatch.setenv('SECRET_KEY', 'from-env')
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///env.db')
    cfg = _reload_config()

    assert cfg.SECRET_KEY == 'from-env'
    assert cfg.SQLALCHEMY_DATABASE_URI == 'sqlite:///env.db'


def test_upload_and_language_settings():
    cfg = config.Config

    assert cfg.MAX_CONTENT_LENGTH == 16 * 1024 * 1024
    assert cfg.ALLOWED_EXTENSIONS == {'xlsx', 'xls', 'csv'}
    assert cfg.UPLOAD_FOLDER.endswith(os.path.join('static', 'uploads'))
    assert os.path.isabs(cfg.UPLOAD_FOLDER)
    assert cfg.PERMANENT_SESSION_LIFETIME == timedelta(hours=24)
    assert cfg.LANGUAGES == ['ko', 'en']
    assert cfg.DEFAULT_LANGUAGE in cfg.LANGUAGES
