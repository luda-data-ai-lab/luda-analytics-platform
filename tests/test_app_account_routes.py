"""계정 보안 라우트 테스트 (가입 제한, 로그인 잠금, 비밀번호 변경, 회사 범위, 보안 헤더)."""

from datetime import datetime, timedelta

import pytest

from models import Dataset, User


@pytest.fixture
def client(flask_app, db_session, tmp_path):
    flask_app.config['UPLOAD_FOLDER'] = str(tmp_path)
    with flask_app.test_client() as test_client:
        yield test_client


@pytest.fixture
def user(db_session):
    user = User(email='owner@luda.example', name='소유자', company='LUDA')
    user.set_password('Luda-owner-7')
    db_session.session.add(user)
    db_session.session.commit()
    return user


def _register(client, **overrides):
    data = {
        'email': 'new@luda.example', 'name': '신규', 'company': 'LUDA',
        'password': 'Luda-analyze-7', 'password_confirm': 'Luda-analyze-7',
    }
    data.update(overrides)
    return client.post('/register', data=data)


def _login(client, email='owner@luda.example', password='Luda-owner-7'):
    return client.post('/login', data={'email': email, 'password': password})


def _make_dataset(db, owner, name):
    dataset = Dataset(
        name=name, filename='f.csv', file_path='/tmp/does-not-exist.csv',
        user_id=owner.id, columns=['Revenue'], row_count=0, column_count=1,
    )
    db.session.add(dataset)
    db.session.commit()
    return dataset


def test_register_rejects_disallowed_domain(client, flask_app, db_session):
    flask_app.config['REGISTRATION_ALLOWED_DOMAINS'] = ['luda.example']
    try:
        response = _register(client, email='outsider@other.example')
    finally:
        flask_app.config['REGISTRATION_ALLOWED_DOMAINS'] = []

    assert '/register' in response.headers['Location']
    assert User.query.filter_by(email='outsider@other.example').count() == 0


def test_register_accepts_allowed_domain(client, flask_app, db_session):
    flask_app.config['REGISTRATION_ALLOWED_DOMAINS'] = ['luda.example']
    try:
        response = _register(client)
    finally:
        flask_app.config['REGISTRATION_ALLOWED_DOMAINS'] = []

    assert '/login' in response.headers['Location']
    assert User.query.filter_by(email='new@luda.example').count() == 1


def test_register_requires_invite_code_when_configured(client, flask_app, db_session):
    flask_app.config['REGISTRATION_INVITE_CODE'] = 'let-me-in'
    try:
        rejected = _register(client)
        assert User.query.filter_by(email='new@luda.example').count() == 0
        assert '/register' in rejected.headers['Location']

        accepted = _register(client, invite_code='let-me-in')
    finally:
        flask_app.config['REGISTRATION_INVITE_CODE'] = ''

    assert '/login' in accepted.headers['Location']
    assert User.query.filter_by(email='new@luda.example').count() == 1


def test_register_rejects_password_mismatch(client, db_session):
    response = _register(client, password_confirm='Luda-analyze-8')

    assert '/register' in response.headers['Location']
    assert User.query.filter_by(email='new@luda.example').count() == 0


def test_register_rejects_common_password(client, db_session):
    response = _register(client, password='password123', password_confirm='password123')

    assert '/register' in response.headers['Location']
    assert User.query.filter_by(email='new@luda.example').count() == 0


def test_failed_login_increments_and_locks_account(client, flask_app, user, db_session):
    flask_app.config['LOGIN_MAX_FAILED_ATTEMPTS'] = 3
    try:
        for _ in range(2):
            _login(client, password='wrong')
        assert User.query.get(user.id).failed_login_count == 2

        _login(client, password='wrong')
        locked = User.query.get(user.id)
        assert locked.locked_until is not None

        # 잠긴 동안에는 올바른 비밀번호로도 로그인되지 않는다.
        response = _login(client)
        assert response.status_code == 200
        assert client.get('/dashboard').status_code == 302
    finally:
        flask_app.config['LOGIN_MAX_FAILED_ATTEMPTS'] = 10


def test_successful_login_clears_lockout_state(client, user, db_session):
    user.failed_login_count = 4
    user.locked_until = datetime.utcnow() - timedelta(minutes=1)
    db_session.session.commit()

    response = _login(client)

    assert '/dashboard' in response.headers['Location']
    refreshed = User.query.get(user.id)
    assert refreshed.failed_login_count == 0
    assert refreshed.locked_until is None
    assert refreshed.last_login_at is not None


def test_change_password_requires_current_password(client, user, db_session):
    _login(client)

    response = client.post('/account/password', data={
        'current_password': 'wrong', 'new_password': 'Luda-fresh-9',
        'confirm_password': 'Luda-fresh-9',
    })

    assert '/account/password' in response.headers['Location']
    assert User.query.get(user.id).check_password('Luda-owner-7')


def test_change_password_rejects_mismatch(client, user, db_session):
    _login(client)

    response = client.post('/account/password', data={
        'current_password': 'Luda-owner-7', 'new_password': 'Luda-fresh-9',
        'confirm_password': 'Luda-fresh-8',
    })

    assert '/account/password' in response.headers['Location']
    assert User.query.get(user.id).check_password('Luda-owner-7')


def test_change_password_succeeds(client, user, db_session):
    _login(client)

    response = client.post('/account/password', data={
        'current_password': 'Luda-owner-7', 'new_password': 'Luda-fresh-9',
        'confirm_password': 'Luda-fresh-9',
    })

    assert '/dashboard' in response.headers['Location']
    assert User.query.get(user.id).check_password('Luda-fresh-9')


def test_change_password_page_renders(client, user, db_session):
    _login(client)

    assert client.get('/account/password').status_code == 200


def test_change_password_requires_login(client):
    assert client.get('/account/password').status_code == 302


def test_company_view_excludes_other_email_domains(client, user, db_session):
    same = User(email='mate@luda.example', name='동료', company='LUDA')
    same.set_password('Luda-mate-7')
    outsider = User(email='spy@other.example', name='외부인', company='LUDA')
    outsider.set_password('Luda-spy-7')
    db_session.session.add_all([same, outsider])
    db_session.session.commit()
    _make_dataset(db_session, same, '동료 데이터')
    _make_dataset(db_session, outsider, '외부 데이터')
    _login(client)

    body = client.get('/dashboard?view=company').get_data(as_text=True)

    assert '동료 데이터' in body
    assert '외부 데이터' not in body


def test_company_view_blocked_for_public_webmail_accounts(client, db_session):
    webmail = User(email='someone@gmail.com', name='웹메일', company='LUDA')
    webmail.set_password('Luda-webmail-7')
    peer = User(email='mate@luda.example', name='동료', company='LUDA')
    peer.set_password('Luda-mate-7')
    db_session.session.add_all([webmail, peer])
    db_session.session.commit()
    _make_dataset(db_session, peer, '동료 데이터')
    _login(client, email='someone@gmail.com', password='Luda-webmail-7')

    body = client.get('/dashboard?view=company').get_data(as_text=True)

    assert '동료 데이터' not in body


def test_security_headers_present_on_responses(client):
    response = client.get('/')

    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert response.headers['X-Frame-Options'] == 'DENY'
    assert 'Content-Security-Policy' in response.headers
    assert 'Referrer-Policy' in response.headers
    assert 'Strict-Transport-Security' not in response.headers


def test_hsts_header_added_in_production(client, flask_app):
    flask_app.config['IS_PRODUCTION'] = True
    try:
        response = client.get('/')
    finally:
        flask_app.config['IS_PRODUCTION'] = False

    assert response.headers['Strict-Transport-Security'].startswith('max-age=')
