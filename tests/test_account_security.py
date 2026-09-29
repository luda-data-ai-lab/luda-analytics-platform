"""계정 보안 정책 단위 테스트 (도메인 검증, 비밀번호 정책, 로그인 잠금, 보안 헤더)."""

from datetime import datetime, timedelta

from src.account_security import (
    email_domain, email_local_part, is_corporate_domain, lockout_remaining_minutes,
    parse_domain_list, password_policy_error, register_failed_login,
    register_successful_login, registration_domain_allowed, security_headers
)


class FakeUser:
    def __init__(self, failed_login_count=0, locked_until=None):
        self.failed_login_count = failed_login_count
        self.locked_until = locked_until
        self.last_login_at = None


def test_email_domain_and_local_part():
    assert email_domain('Kim@Example.COM') == 'example.com'
    assert email_domain('broken') == ''
    assert email_local_part('Kim@example.com') == 'kim'


def test_public_webmail_is_not_corporate():
    assert is_corporate_domain('ceo@ludaresearch.org')
    assert not is_corporate_domain('someone@gmail.com')
    assert not is_corporate_domain('someone@naver.com')
    assert not is_corporate_domain('no-at-sign')


def test_parse_domain_list_normalizes_separators():
    assert parse_domain_list('@LUDA.org, example.com; foo.co.kr') == [
        'luda.org', 'example.com', 'foo.co.kr'
    ]
    assert parse_domain_list(None) == []


def test_registration_domain_allowed():
    assert registration_domain_allowed('a@gmail.com', [])
    assert registration_domain_allowed('a@luda.org', ['luda.org'])
    assert not registration_domain_allowed('a@gmail.com', ['luda.org'])


def test_password_policy_rejects_weak_passwords():
    assert password_policy_error('short1') is not None
    assert password_policy_error('password123') is not None  # 흔한 비밀번호
    assert password_policy_error('onlyletters') is not None  # 숫자/기호 없음
    assert password_policy_error('jamesyeon1', email='jamesyeon@luda.org') is not None
    assert password_policy_error('hongildong9', name='hongildong') is not None


def test_password_policy_accepts_reasonable_password():
    assert password_policy_error('Luda-analyze-7', email='kim@luda.org', name='김분석') is None


def test_lockout_counts_up_then_locks():
    user = FakeUser()
    now = datetime(2026, 1, 1, 12, 0, 0)

    for _ in range(4):
        assert register_failed_login(user, 5, 15, now=now) is False
    assert user.failed_login_count == 4
    assert lockout_remaining_minutes(user, now=now) == 0

    assert register_failed_login(user, 5, 15, now=now) is True
    assert user.locked_until == now + timedelta(minutes=15)
    assert lockout_remaining_minutes(user, now=now) == 16  # 15분 + 올림 1분


def test_lockout_expires_and_success_resets_state():
    now = datetime(2026, 1, 1, 12, 0, 0)
    user = FakeUser(failed_login_count=3, locked_until=now - timedelta(minutes=1))

    assert lockout_remaining_minutes(user, now=now) == 0

    register_successful_login(user, now=now)
    assert user.failed_login_count == 0
    assert user.locked_until is None
    assert user.last_login_at == now


def test_lockout_disabled_when_max_attempts_is_zero():
    user = FakeUser()
    for _ in range(20):
        assert register_failed_login(user, 0, 15) is False
    assert user.locked_until is None


def test_security_headers_add_hsts_only_in_production():
    dev = security_headers(False)
    prod = security_headers(True)

    assert 'Strict-Transport-Security' not in dev
    assert prod['Strict-Transport-Security'].startswith('max-age=')
    assert dev['X-Frame-Options'] == 'DENY'
    assert dev['X-Content-Type-Options'] == 'nosniff'
    assert "frame-ancestors 'none'" in dev['Content-Security-Policy']
    assert 'https://cdn.plot.ly' in dev['Content-Security-Policy']
