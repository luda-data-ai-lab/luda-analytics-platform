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

    # 개발 환경 기본값: 하드코딩 키 대신 임의 키, SQLite 폴백
    assert len(cfg.SECRET_KEY) >= 32
    assert cfg.SECRET_KEY != _reload_config().SECRET_KEY
    assert cfg.SQLALCHEMY_DATABASE_URI.startswith('sqlite:///')


def test_production_requires_secret_key_and_database_url(monkeypatch):
    monkeypatch.setenv('FLASK_ENV', 'production')
    monkeypatch.delenv('SECRET_KEY', raising=False)
    with pytest.raises(RuntimeError, match='SECRET_KEY'):
        _reload_config()

    monkeypatch.setenv('SECRET_KEY', 'from-env')
    monkeypatch.delenv('DATABASE_URL', raising=False)
    with pytest.raises(RuntimeError, match='DATABASE_URL'):
        _reload_config()


def test_dotenv_file_is_loaded_without_overriding_shell(monkeypatch, tmp_path):
    env_file = tmp_path / '.env'
    env_file.write_text('SECRET_KEY=from-dotenv\nDATABASE_URL=sqlite:///dotenv.db\n')
    monkeypatch.delenv('SECRET_KEY', raising=False)
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///shell.db')

    config.load_dotenv(str(env_file))

    assert os.environ['SECRET_KEY'] == 'from-dotenv'
    assert os.environ['DATABASE_URL'] == 'sqlite:///shell.db'


def test_env_overrides(monkeypatch):
    monkeypatch.setenv('SECRET_KEY', 'from-env')
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///env.db')
    cfg = _reload_config()

    assert cfg.SECRET_KEY == 'from-env'
    assert cfg.SQLALCHEMY_DATABASE_URI == 'sqlite:///env.db'


@pytest.mark.parametrize('given', [
    'postgresql://luda_user:pw@db.internal:5432/luda_analytics',
    'postgres://luda_user:pw@db.internal:5432/luda_analytics',
])
def test_postgres_url_without_driver_is_pinned_to_psycopg2(monkeypatch, given):
    monkeypatch.setenv('SECRET_KEY', 'from-env')
    monkeypatch.setenv('DATABASE_URL', f'  {given}  ')
    cfg = _reload_config()

    assert cfg.SQLALCHEMY_DATABASE_URI == (
        'postgresql+psycopg2://luda_user:pw@db.internal:5432/luda_analytics'
    )


def test_explicit_database_driver_is_kept(monkeypatch):
    monkeypatch.setenv('SECRET_KEY', 'from-env')
    monkeypatch.setenv('DATABASE_URL', 'postgresql+psycopg://user:pw@host/db')
    cfg = _reload_config()

    assert cfg.SQLALCHEMY_DATABASE_URI == 'postgresql+psycopg://user:pw@host/db'


def test_upload_and_language_settings():
    cfg = config.Config

    assert cfg.MAX_CONTENT_LENGTH == 16 * 1024 * 1024
    assert cfg.ALLOWED_EXTENSIONS == {'xlsx', 'xls', 'csv'}
    assert cfg.UPLOAD_FOLDER.endswith(os.path.join('static', 'uploads'))
    assert os.path.isabs(cfg.UPLOAD_FOLDER)
    assert cfg.PERMANENT_SESSION_LIFETIME == timedelta(hours=24)
    assert cfg.LANGUAGES == ['ko', 'en']
    assert cfg.DEFAULT_LANGUAGE in cfg.LANGUAGES
