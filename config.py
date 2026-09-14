import os
import secrets
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _env_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


IS_PRODUCTION = os.environ.get('FLASK_ENV', 'development').strip().lower() == 'production'


def _secret_key():
    key = os.environ.get('SECRET_KEY')
    if key:
        return key
    if IS_PRODUCTION:
        raise RuntimeError(
            'SECRET_KEY 환경변수가 설정되지 않았습니다. / SECRET_KEY must be set when FLASK_ENV=production.'
        )
    # 개발 환경: 프로세스마다 임의 키 생성 (재시작 시 세션 만료)
    return secrets.token_hex(32)


def _database_uri():
    uri = os.environ.get('DATABASE_URL')
    if uri:
        return uri
    if IS_PRODUCTION:
        raise RuntimeError(
            'DATABASE_URL 환경변수가 설정되지 않았습니다. / DATABASE_URL must be set when FLASK_ENV=production.'
        )
    return 'sqlite:///' + os.path.join(BASE_DIR, 'analytics.db')


class Config:
    # 기본 설정
    IS_PRODUCTION = IS_PRODUCTION
    SECRET_KEY = _secret_key()

    # 데이터베이스 설정 (자격증명은 DATABASE_URL 환경변수로만 주입)
    SQLALCHEMY_DATABASE_URI = _database_uri()

    # 파일 업로드 설정
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}

    # 세션 설정
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = _env_flag('SESSION_COOKIE_SECURE', IS_PRODUCTION)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = 'Lax'
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE

    # 언어 설정
    LANGUAGES = ['ko', 'en']
    DEFAULT_LANGUAGE = 'ko'
