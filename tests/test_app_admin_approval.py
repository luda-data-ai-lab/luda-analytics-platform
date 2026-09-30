"""가입 승인 라우트 테스트 (사용 목적 필수, 승인 대기 로그인 차단, 관리자 승인/반려)."""

import pytest

from models import User

PURPOSE = '월별 매출 데이터를 업로드해 지점별 실적을 분석하려고 합니다.'


@pytest.fixture
def client(flask_app, db_session):
    with flask_app.test_client() as test_client:
        yield test_client


@pytest.fixture
def admin(db_session):
    admin = User(
        email='admin@luda.example', name='관리자', company='LUDA',
        is_admin=True, approval_status='approved',
    )
    admin.set_password('Luda-admin-7')
    db_session.session.add(admin)
    db_session.session.commit()
    return admin


@pytest.fixture
def applicant(db_session):
    applicant = User(
        email='pending@luda.example', name='신청자', company='LUDA',
        purpose=PURPOSE, approval_status='pending',
    )
    applicant.set_password('Luda-pending-7')
    db_session.session.add(applicant)
    db_session.session.commit()
    return applicant


def _register(client, **overrides):
    data = {
        'email': 'new@luda.example', 'name': '신규', 'company': 'LUDA',
        'purpose': PURPOSE,
        'password': 'Luda-analyze-7', 'password_confirm': 'Luda-analyze-7',
    }
    data.update(overrides)
    return client.post('/register', data=data)


def _login(client, email, password):
    return client.post('/login', data={'email': email, 'password': password})


def test_register_requires_purpose(client):
    response = _register(client, purpose='짧음')

    assert '/register' in response.headers['Location']
    assert User.query.filter_by(email='new@luda.example').count() == 0


def test_register_stores_purpose_and_pending_status(client):
    response = _register(client)

    assert '/login' in response.headers['Location']
    user = User.query.filter_by(email='new@luda.example').one()
    assert user.purpose == PURPOSE
    assert user.approval_status == 'pending'
    assert user.is_admin is False


def test_register_auto_approves_configured_admin(client, flask_app):
    flask_app.config['ADMIN_EMAILS'] = ['boss@luda.example']
    try:
        _register(client, email='boss@luda.example')
    finally:
        flask_app.config['ADMIN_EMAILS'] = []

    user = User.query.filter_by(email='boss@luda.example').one()
    assert user.is_admin is True
    assert user.approval_status == 'approved'
    assert user.approval_decided_at is not None


def test_register_skips_approval_when_disabled(client, flask_app):
    flask_app.config['REQUIRE_ADMIN_APPROVAL'] = False
    try:
        _register(client)
    finally:
        flask_app.config['REQUIRE_ADMIN_APPROVAL'] = True

    user = User.query.filter_by(email='new@luda.example').one()
    assert user.approval_status == 'approved'
    assert user.is_admin is False


def test_pending_user_cannot_log_in(client, applicant):
    body = _login(client, 'pending@luda.example', 'Luda-pending-7').get_data(as_text=True)

    assert '승인 대기' in body
    assert client.get('/dashboard').headers['Location'].startswith('/login')


def test_rejected_user_sees_reason(client, db_session, applicant):
    applicant.approval_status = 'rejected'
    applicant.rejection_reason = '사용 목적이 불충분합니다.'
    db_session.session.commit()

    body = _login(client, 'pending@luda.example', 'Luda-pending-7').get_data(as_text=True)

    assert '사용 목적이 불충분합니다.' in body


def test_login_syncs_configured_admin_account(client, flask_app, applicant):
    flask_app.config['ADMIN_EMAILS'] = ['pending@luda.example']
    try:
        response = _login(client, 'pending@luda.example', 'Luda-pending-7')
    finally:
        flask_app.config['ADMIN_EMAILS'] = []

    assert '/dashboard' in response.headers['Location']
    assert applicant.is_admin is True
    assert applicant.approval_status == 'approved'


def test_admin_page_requires_admin(client, db_session, applicant):
    applicant.approval_status = 'approved'
    db_session.session.commit()
    _login(client, 'pending@luda.example', 'Luda-pending-7')

    response = client.get('/admin/users')

    assert '/dashboard' in response.headers['Location']


def test_admin_page_lists_pending_purpose(client, admin, applicant):
    _login(client, 'admin@luda.example', 'Luda-admin-7')

    body = client.get('/admin/users').get_data(as_text=True)

    assert 'pending@luda.example' in body
    assert PURPOSE in body


def test_admin_can_approve_and_user_can_log_in(client, admin, applicant):
    _login(client, 'admin@luda.example', 'Luda-admin-7')
    client.post(f'/admin/users/{applicant.id}/approve')
    client.get('/logout')

    assert applicant.approval_status == 'approved'
    assert applicant.approved_by_id == admin.id
    response = _login(client, 'pending@luda.example', 'Luda-pending-7')
    assert '/dashboard' in response.headers['Location']


def test_admin_can_reject_with_reason(client, admin, applicant):
    _login(client, 'admin@luda.example', 'Luda-admin-7')

    client.post(f'/admin/users/{applicant.id}/reject', data={'reason': '목적 불충분'})

    assert applicant.approval_status == 'rejected'
    assert applicant.rejection_reason == '목적 불충분'


def test_approving_already_decided_user_is_ignored(client, admin, db_session, applicant):
    applicant.approval_status = 'rejected'
    db_session.session.commit()
    _login(client, 'admin@luda.example', 'Luda-admin-7')

    client.post(f'/admin/users/{applicant.id}/approve')

    assert applicant.approval_status == 'rejected'


def test_non_admin_cannot_approve(client, db_session, admin, applicant):
    other = User(email='member@luda.example', name='일반', approval_status='approved')
    other.set_password('Luda-member-7')
    db_session.session.add(other)
    db_session.session.commit()
    _login(client, 'member@luda.example', 'Luda-member-7')

    response = client.post(f'/admin/users/{applicant.id}/approve')

    assert '/dashboard' in response.headers['Location']
    assert applicant.approval_status == 'pending'
