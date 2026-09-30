"""계정 보안 관련 정책 (회사 범위 검증, 비밀번호 정책, 로그인 실패 잠금, 보안 헤더)."""

from datetime import datetime, timedelta

# 무료 웹메일 도메인은 회사 소속의 증거가 될 수 없으므로 회사 공유에서 제외한다.
PUBLIC_EMAIL_DOMAINS = frozenset({
    'gmail.com', 'googlemail.com', 'naver.com', 'hanmail.net', 'daum.net', 'nate.com',
    'kakao.com', 'hotmail.com', 'outlook.com', 'live.com', 'yahoo.com', 'yahoo.co.jp',
    'icloud.com', 'me.com', 'aol.com', 'proton.me', 'protonmail.com', 'zoho.com',
    'yandex.com', 'mail.com', 'gmx.com', 'qq.com', '163.com',
})

# 유출 목록 상위에 항상 등장하는 비밀번호 (길이 정책만으로는 막히지 않는다)
COMMON_PASSWORDS = frozenset({
    '12345678', '123456789', '1234567890', 'password', 'password1', 'password123',
    'qwerty123', 'qwertyuiop', 'asdfghjkl', '1q2w3e4r', '1q2w3e4r5t', 'qwer1234',
    'abcd1234', 'a1234567', 'iloveyou', 'admin123', 'administrator', 'letmein123',
    'welcome1', 'welcome123', 'test1234', 'testtest', 'changeme', 'passw0rd',
    'p@ssw0rd', 'football1', 'baseball1', 'dragon123', 'monkey123', 'sunshine1',
    'princess1', 'starwars1', 'zaq12wsx', 'qazwsxedc', 'master123', 'login123',
    'company123', 'analytics123', 'samsung123', 'korea1234',
})

MIN_PASSWORD_LENGTH = 8

# 가입 시 입력하는 사용 목적 길이 제한
MIN_PURPOSE_LENGTH = 10
MAX_PURPOSE_LENGTH = 500

# 관리자 승인 상태
APPROVAL_PENDING = 'pending'
APPROVAL_APPROVED = 'approved'
APPROVAL_REJECTED = 'rejected'
MAX_REJECTION_REASON_LENGTH = 500


def email_domain(email):
    """이메일의 도메인을 소문자로 반환 (없으면 빈 문자열)."""
    if not email or '@' not in email:
        return ''
    return email.rsplit('@', 1)[1].strip().lower()


def email_local_part(email):
    if not email or '@' not in email:
        return (email or '').strip().lower()
    return email.rsplit('@', 1)[0].strip().lower()


def is_corporate_domain(email):
    """회사 범위 공유에 사용할 수 있는(웹메일이 아닌) 도메인인지 여부."""
    domain = email_domain(email)
    return bool(domain) and domain not in PUBLIC_EMAIL_DOMAINS


def registration_domain_allowed(email, allowed_domains):
    """가입 허용 도메인 목록이 설정된 경우 해당 도메인만 허용한다."""
    if not allowed_domains:
        return True
    return email_domain(email) in {d.strip().lower().lstrip('@') for d in allowed_domains if d.strip()}


def parse_domain_list(raw):
    """쉼표/공백으로 구분된 도메인 목록 문자열을 정규화한다."""
    if not raw:
        return []
    parts = [p.strip().lower().lstrip('@') for p in raw.replace(';', ',').replace(' ', ',').split(',')]
    return [p for p in parts if p]


def parse_email_list(raw):
    """쉼표/공백으로 구분된 이메일 목록 문자열을 소문자로 정규화한다."""
    if not raw:
        return []
    parts = [p.strip().lower() for p in raw.replace(';', ',').replace(' ', ',').split(',')]
    return [p for p in parts if p]


def is_bootstrap_admin(email, admin_emails):
    """설정(ADMIN_EMAILS)에 등록된 관리자 계정인지 여부."""
    return bool(email) and email.strip().lower() in set(admin_emails or ())


def purpose_error(purpose):
    """사용 목적 입력이 부적절하면 (한국어, 영어) 메시지를 반환한다."""
    text = (purpose or '').strip()
    if len(text) < MIN_PURPOSE_LENGTH:
        return (
            f'사용 목적을 {MIN_PURPOSE_LENGTH}자 이상 구체적으로 입력해주세요.',
            f'Please describe your intended use in at least {MIN_PURPOSE_LENGTH} characters.',
        )
    if len(text) > MAX_PURPOSE_LENGTH:
        return (
            f'사용 목적은 {MAX_PURPOSE_LENGTH}자 이내로 입력해주세요.',
            f'Intended use must be {MAX_PURPOSE_LENGTH} characters or fewer.',
        )
    return None


def approve_user(user, approver, now=None):
    """가입 신청을 승인 상태로 바꾼다."""
    user.approval_status = APPROVAL_APPROVED
    user.rejection_reason = None
    user.approval_decided_at = now or datetime.utcnow()
    user.approved_by_id = approver.id if approver else None


def reject_user(user, approver, reason='', now=None):
    """가입 신청을 거절 상태로 바꾸고 사유를 남긴다."""
    user.approval_status = APPROVAL_REJECTED
    user.rejection_reason = (reason or '').strip()[:MAX_REJECTION_REASON_LENGTH] or None
    user.approval_decided_at = now or datetime.utcnow()
    user.approved_by_id = approver.id if approver else None


def approval_block_message(user):
    """로그인을 막아야 하는 승인 상태면 (한국어, 영어) 안내 문구를 반환한다."""
    status = user.approval_status
    if status == APPROVAL_APPROVED:
        return None
    if status == APPROVAL_REJECTED:
        reason = (user.rejection_reason or '').strip()
        if reason:
            return (
                f'가입 신청이 반려되었습니다. (사유: {reason})',
                f'Your registration was rejected. (reason: {reason})',
            )
        return (
            '가입 신청이 반려되었습니다. 관리자에게 문의해주세요.',
            'Your registration was rejected. Please contact an administrator.',
        )
    return (
        '관리자 승인 대기 중입니다. 승인 후 로그인할 수 있습니다.',
        'Your account is awaiting administrator approval.',
    )


def password_policy_error(password, email='', name=''):
    """비밀번호 정책 위반 시 (한국어, 영어) 메시지를 반환하고, 통과하면 None."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return (
            f'비밀번호는 최소 {MIN_PASSWORD_LENGTH}자 이상이어야 합니다.',
            f'Password must be at least {MIN_PASSWORD_LENGTH} characters long.',
        )

    lowered = password.lower()
    if lowered in COMMON_PASSWORDS:
        return (
            '너무 흔한 비밀번호입니다. 다른 비밀번호를 사용해주세요.',
            'This password is too common. Please choose a different one.',
        )

    has_letter = any(c.isalpha() for c in password)
    has_other = any(not c.isalpha() for c in password)
    if not (has_letter and has_other):
        return (
            '비밀번호에는 문자와 숫자(또는 기호)를 함께 포함해주세요.',
            'Password must contain both letters and numbers (or symbols).',
        )

    local = email_local_part(email)
    if local and len(local) >= 4 and local in lowered:
        return (
            '비밀번호에 이메일 아이디를 포함할 수 없습니다.',
            'Password must not contain your email address.',
        )

    simple_name = (name or '').strip().lower()
    if simple_name and len(simple_name) >= 4 and simple_name in lowered:
        return (
            '비밀번호에 이름을 포함할 수 없습니다.',
            'Password must not contain your name.',
        )

    return None


def lockout_remaining_minutes(user, now=None):
    """계정이 잠겨 있으면 남은 분(최소 1), 아니면 0을 반환한다."""
    locked_until = user.locked_until
    if not locked_until:
        return 0
    now = now or datetime.utcnow()
    if locked_until <= now:
        return 0
    return max(1, int((locked_until - now).total_seconds() // 60) + 1)


def register_failed_login(user, max_attempts, lockout_minutes, now=None):
    """로그인 실패를 누적하고 임계치를 넘으면 잠금 시각을 설정한다."""
    now = now or datetime.utcnow()
    user.failed_login_count = (user.failed_login_count or 0) + 1
    if max_attempts > 0 and user.failed_login_count >= max_attempts:
        user.locked_until = now + timedelta(minutes=lockout_minutes)
        user.failed_login_count = 0
        return True
    return False


def register_successful_login(user, now=None):
    """로그인 성공 시 실패 누적/잠금을 초기화하고 마지막 로그인 시각을 기록한다."""
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now or datetime.utcnow()


def security_headers(is_production):
    """모든 응답에 붙일 보안 헤더."""
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.plot.ly; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
        "font-src 'self' data: https://fonts.gstatic.com https://cdn.jsdelivr.net; "
        "img-src 'self' data: blob:; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "object-src 'none'"
    )
    headers = {
        'Content-Security-Policy': csp,
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'Referrer-Policy': 'strict-origin-when-cross-origin',
        'Permissions-Policy': 'geolocation=(), microphone=(), camera=()',
        'Cross-Origin-Opener-Policy': 'same-origin',
    }
    if is_production:
        headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return headers
