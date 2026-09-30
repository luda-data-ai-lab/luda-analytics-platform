import os
import secrets
from datetime import timedelta

from dotenv import load_dotenv

from src.account_security import parse_domain_list, parse_email_list

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# 프로젝트 루트의 .env 를 환경변수로 읽어온다 (이미 설정된 셸 변수가 우선).
load_dotenv(os.path.join(BASE_DIR, '.env'))


def _env_int(name, default):
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value.strip())
    except ValueError:
        return default


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


def _normalize_database_uri(uri):
    """드라이버가 생략된 Postgres URL 을 psycopg2 로 고정한다.

    SQLAlchemy 2.1 부터 `postgresql://` 의 기본 드라이버가 psycopg(3) 로 바뀌어,
    requirements 의 psycopg2-binary 만 설치된 환경에서 `No module named 'psycopg'`
    로 기동이 실패한다.
    """
    for prefix in ('postgresql://', 'postgres://'):
        if uri.startswith(prefix):
            return 'postgresql+psycopg2://' + uri[len(prefix):]
    return uri


def _database_uri():
    uri = os.environ.get('DATABASE_URL')
    if uri:
        return _normalize_database_uri(uri.strip())
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

    REMEMBER_COOKIE_DURATION = timedelta(days=7)

    # 계정 보안 설정
    # 가입 허용 이메일 도메인 (비우면 전체 허용). 예: REGISTRATION_ALLOWED_DOMAINS=ludaresearch.org
    REGISTRATION_ALLOWED_DOMAINS = parse_domain_list(os.environ.get('REGISTRATION_ALLOWED_DOMAINS'))
    # 가입 초대 코드 (비우면 코드 없이 가입 가능)
    REGISTRATION_INVITE_CODE = (os.environ.get('REGISTRATION_INVITE_CODE') or '').strip()
    # 로그인 실패 임계치와 잠금 시간 (0 이면 잠금 비활성화)
    LOGIN_MAX_FAILED_ATTEMPTS = _env_int('LOGIN_MAX_FAILED_ATTEMPTS', 10)
    LOGIN_LOCKOUT_MINUTES = _env_int('LOGIN_LOCKOUT_MINUTES', 15)
    # 가입 후 관리자 승인 필요 여부 (false 면 가입 즉시 로그인 가능)
    REQUIRE_ADMIN_APPROVAL = _env_flag('REQUIRE_ADMIN_APPROVAL', True)
    # 관리자 계정 이메일 목록. 예: ADMIN_EMAILS=admin@ludaresearch.org,ops@ludaresearch.org
    ADMIN_EMAILS = parse_email_list(os.environ.get('ADMIN_EMAILS'))

    # 언어 설정
    LANGUAGES = ['ko', 'en']
    DEFAULT_LANGUAGE = 'ko'
