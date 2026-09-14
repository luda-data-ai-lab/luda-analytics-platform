"""app.py 유틸리티 함수 테스트 (언어/파일확장자/컬럼 매핑/템플릿 유형 감지)."""

import pandas as pd
import pytest
from flask import session

import app as app_module
from models import DataRecord, Dataset, User


@pytest.mark.parametrize('filename, expected', [
    ('data.csv', True),
    ('data.xlsx', True),
    ('data.xls', True),
    ('DATA.CSV', True),
    ('archive.tar.csv', True),
    ('data.txt', False),
    ('data.pdf', False),
    ('csv', False),
    ('', False),
    ('.csv', True),
])
def test_allowed_file(app_context, filename, expected):
    assert app_module.allowed_file(filename) is expected


def test_get_message_defaults_to_english_without_session(request_context):
    assert app_module.get_message('한국어', 'English') == 'English'


def test_get_message_returns_korean_when_language_is_ko(request_context):
    session['language'] = 'ko'
    assert app_module.get_message('한국어', 'English') == '한국어'


def test_get_message_returns_english_for_other_language(request_context):
    session['language'] = 'en'
    assert app_module.get_message('한국어', 'English') == 'English'


def test_before_request_sets_default_language(flask_app):
    with flask_app.test_request_context('/'):
        app_module.before_request()
        assert session['language'] == flask_app.config['DEFAULT_LANGUAGE']


def test_before_request_keeps_existing_language(flask_app):
    with flask_app.test_request_context('/'):
        session['language'] = 'en'
        app_module.before_request()
        assert session['language'] == 'en'


def test_inject_language_exposes_current_language(flask_app):
    with flask_app.test_request_context('/'):
        session['language'] = 'en'
        assert app_module.inject_language() == {'current_language': 'en'}

    with flask_app.test_request_context('/'):
        assert app_module.inject_language() == {'current_language': 'ko'}


def test_set_language_accepts_supported_language(flask_app):
    with flask_app.test_request_context('/set_language/en'):
        response = app_module.set_language('en')
        assert session['language'] == 'en'
        assert response.status_code == 302


def test_set_language_ignores_unsupported_language(flask_app):
    with flask_app.test_request_context('/set_language/fr'):
        session['language'] = 'ko'
        app_module.set_language('fr')
        assert session['language'] == 'ko'


def test_set_language_redirects_to_referrer(flask_app):
    with flask_app.test_request_context('/set_language/en', headers={'Referer': '/dashboard'}):
        response = app_module.set_language('en')
        assert response.headers['Location'] == '/dashboard'


@pytest.mark.parametrize('key, columns, expected', [
    ('매출액', ['Revenue'], 'Revenue'),
    ('매출액', ['매출액'], '매출액'),
    ('매출액', ['Total_Sales'], 'Total_Sales'),
    ('매출액', ['nope'], None),
    ('날짜', ['Start_Date'], 'Start_Date'),
    ('작물', ['Crop_Type'], 'Crop_Type'),
    ('세그먼트', ['Customer_Segment'], 'Customer_Segment'),
])
def test_resolve_column_uses_column_map(key, columns, expected):
    df = pd.DataFrame(columns=columns)
    assert app_module.resolve_column(df, key) == expected


def test_resolve_column_prefers_first_candidate():
    df = pd.DataFrame(columns=['Revenue', '매출액'])
    assert app_module.resolve_column(df, '매출액') == '매출액'


def test_resolve_column_falls_back_to_key_for_unmapped_names():
    df = pd.DataFrame(columns=['Custom'])
    assert app_module.resolve_column(df, 'Custom') == 'Custom'
    assert app_module.resolve_column(df, 'Missing') is None


@pytest.mark.parametrize('columns, expected', [
    (['Crop_Type', 'Revenue'], 'crop'),
    (['Crop_Yield_kg'], 'crop'),
    (['Channel', 'Impressions'], 'marketing'),
    (['Segment', 'Age'], 'customer'),
    (['Revenue', 'Region'], 'sales'),
    (['Date'], 'sales'),
    (['Foo', 'Bar'], 'generic'),
    (['Channel'], 'generic'),
    (['Segment'], 'generic'),
])
def test_detect_template_type(columns, expected):
    df = pd.DataFrame(columns=columns)
    assert app_module._detect_template_type(df) == expected


def test_detect_template_type_precedence_crop_over_marketing():
    df = pd.DataFrame(columns=['Crop_Type', 'Channel', 'Impressions'])
    assert app_module._detect_template_type(df) == 'crop'


def test_fix_dataset_meta_recovers_missing_metadata(db_session):
    user = User(email='meta@example.com', name='메타')
    user.set_password('pw')
    db_session.session.add(user)
    db_session.session.flush()

    dataset = Dataset(name='d', filename='f.csv', file_path='/tmp/f.csv', user_id=user.id)
    db_session.session.add(dataset)
    db_session.session.flush()
    db_session.session.add_all([
        DataRecord(dataset_id=dataset.id, data={'A': 1, 'B': 2}),
        DataRecord(dataset_id=dataset.id, data={'A': 3, 'B': 4}),
    ])
    db_session.session.commit()

    app_module._fix_dataset_meta(dataset)

    assert dataset.columns == ['A', 'B']
    assert dataset.row_count == 2
    assert dataset.column_count == 2


def test_fix_dataset_meta_is_noop_when_columns_present(db_session):
    user = User(email='meta2@example.com', name='메타')
    user.set_password('pw')
    db_session.session.add(user)
    db_session.session.flush()

    dataset = Dataset(
        name='d', filename='f.csv', file_path='/tmp/f.csv', user_id=user.id,
        columns=['X'], row_count=99, column_count=1,
    )
    db_session.session.add(dataset)
    db_session.session.commit()

    app_module._fix_dataset_meta(dataset)

    assert dataset.columns == ['X']
    assert dataset.row_count == 99


def test_fix_dataset_meta_without_records_leaves_metadata_empty(db_session):
    user = User(email='meta3@example.com', name='메타')
    user.set_password('pw')
    db_session.session.add(user)
    db_session.session.flush()

    dataset = Dataset(name='d', filename='f.csv', file_path='/tmp/f.csv', user_id=user.id)
    db_session.session.add(dataset)
    db_session.session.commit()

    app_module._fix_dataset_meta(dataset)

    assert dataset.columns is None
    assert dataset.row_count is None


def test_load_user_returns_matching_user(db_session):
    user = User(email='loader@example.com', name='로더')
    user.set_password('pw')
    db_session.session.add(user)
    db_session.session.commit()

    assert app_module.load_user(str(user.id)) is user
    assert app_module.load_user('9999') is None
