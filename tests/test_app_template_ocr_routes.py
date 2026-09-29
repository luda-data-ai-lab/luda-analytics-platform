"""app.py 템플릿 분석 / OCR 라우트 테스트."""

import io
import json
import os

import pandas as pd
import pytest

import app as app_module
from models import DataRecord, Dataset, OCRSession, User


@pytest.fixture
def client(flask_app, db_session, tmp_path):
    flask_app.config['UPLOAD_FOLDER'] = str(tmp_path)
    with flask_app.test_client() as test_client:
        yield test_client


@pytest.fixture
def user(db_session):
    user = User(email='tmpl@example.com', name='템플릿', company='LUDA')
    user.set_password('pw1234')
    db_session.session.add(user)
    db_session.session.commit()
    return user


@pytest.fixture
def logged_in_client(client, user):
    client.post('/login', data={'email': user.email, 'password': 'pw1234'})
    return client


def _excel_bytes(df):
    buffer = io.BytesIO()
    df.to_excel(buffer, index=False)
    buffer.seek(0)
    return buffer


def test_download_sample_template_returns_xlsx(logged_in_client):
    response = logged_in_client.get('/template/download_sample')

    assert response.status_code == 200
    assert response.headers['Content-Disposition'].endswith('sales_template_sample.xlsx')
    assert response.data[:2] == b'PK'  # xlsx = zip 컨테이너


def test_template_analysis_lists_only_template_datasets(logged_in_client, user, db_session):
    db_session.session.add_all([
        Dataset(name='템플릿 셋', filename='t.xlsx', file_path='/tmp/t.xlsx',
                user_id=user.id, is_template=True, row_count=1, column_count=1),
        Dataset(name='일반 셋', filename='n.csv', file_path='/tmp/n.csv',
                user_id=user.id, row_count=1, column_count=1),
    ])
    db_session.session.commit()

    body = logged_in_client.get('/template_analysis').get_data(as_text=True)

    assert '템플릿 셋' in body
    assert '일반 셋' not in body


def test_legacy_template_path_redirects_to_template_analysis(logged_in_client):
    response = logged_in_client.get('/template')

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/template_analysis')


def test_upload_template_creates_template_dataset(logged_in_client, db_session):
    df = pd.DataFrame({'Date': ['2024-01-01'], 'Revenue': [100], 'Region': ['서울']})

    response = logged_in_client.post('/template/upload', data={
        'file': (_excel_bytes(df), 'template.xlsx'),
    }, content_type='multipart/form-data')

    dataset = Dataset.query.one()
    assert dataset.is_template is True
    assert dataset.row_count == 1
    assert f'/template/analysis/{dataset.id}' in response.headers['Location']


def test_upload_template_without_file_redirects(logged_in_client, db_session):
    response = logged_in_client.post('/template/upload', data={})

    assert '/template' in response.headers['Location']
    assert Dataset.query.count() == 0


def test_upload_template_rejects_empty_filename(logged_in_client, db_session):
    response = logged_in_client.post('/template/upload', data={
        'file': (io.BytesIO(b''), ''),
    }, content_type='multipart/form-data')

    assert '/template' in response.headers['Location']
    assert Dataset.query.count() == 0


def test_upload_template_rejects_disallowed_extension(logged_in_client, db_session):
    response = logged_in_client.post('/template/upload', data={
        'file': (io.BytesIO(b'x'), 'notes.txt'),
    }, content_type='multipart/form-data')

    assert '/template' in response.headers['Location']
    assert Dataset.query.count() == 0


def test_upload_template_cleans_up_unparsable_file(logged_in_client, db_session, tmp_path):
    response = logged_in_client.post('/template/upload', data={
        'file': (io.BytesIO(b'not-an-excel-file'), 'broken.xlsx'),
    }, content_type='multipart/form-data')

    assert '/template' in response.headers['Location']
    assert Dataset.query.count() == 0
    assert os.listdir(tmp_path) == []


def test_view_template_analysis_renders_charts(logged_in_client, user, db_session):
    dataset = Dataset(name='템플릿 셋', filename='t.xlsx', file_path='/tmp/t.xlsx',
                      user_id=user.id, is_template=True)
    db_session.session.add(dataset)
    db_session.session.flush()
    for month, revenue in (('2024-01-01', 100), ('2024-02-01', 300)):
        db_session.session.add(DataRecord(
            dataset_id=dataset.id,
            data={'Date': month, 'Revenue': revenue, 'Region': '서울', 'Quantity': 3},
        ))
    db_session.session.commit()

    response = logged_in_client.get(f'/template/analysis/{dataset.id}')

    assert response.status_code == 200


def test_view_template_analysis_denies_other_users(logged_in_client, db_session):
    other = User(email='someone@example.com', name='타인')
    other.set_password('pw')
    db_session.session.add(other)
    db_session.session.flush()
    dataset = Dataset(name='남의 셋', filename='t.xlsx', file_path='/tmp/t.xlsx',
                      user_id=other.id, is_template=True)
    db_session.session.add(dataset)
    db_session.session.commit()

    response = logged_in_client.get(f'/template/analysis/{dataset.id}')

    assert response.status_code == 302
    assert '/template' in response.headers['Location']


def test_template_analyze_saves_and_redirects_to_analysis(logged_in_client, db_session):
    csv_bytes = b'Date,Revenue,Region\n2024-01-01,100,\xec\x84\x9c\xec\x9a\xb8\n'

    response = logged_in_client.post('/template_analyze', data={
        'file': (io.BytesIO(csv_bytes), 'sales.csv'),
        'template_type': 'sales_data',
        'auto_analysis': 'true',
    }, content_type='multipart/form-data')

    dataset = Dataset.query.one()
    assert dataset.is_template is True
    assert DataRecord.query.filter_by(dataset_id=dataset.id).count() == 1
    assert f'/template/analysis/{dataset.id}' in response.headers['Location']


def test_template_analyze_save_only_returns_to_form(logged_in_client, db_session):
    csv_bytes = b'Date,Revenue\n2024-01-01,100\n'

    response = logged_in_client.post('/template_analyze', data={
        'file': (io.BytesIO(csv_bytes), 'sales.csv'),
        'template_type': 'sales_data',
        'save_dataset': 'true',
    }, content_type='multipart/form-data')

    assert Dataset.query.count() == 1
    assert '/template_analysis' in response.headers['Location']


def test_template_analyze_converts_nan_to_none(logged_in_client, db_session):
    csv_bytes = b'Date,Revenue\n2024-01-01,\n'

    logged_in_client.post('/template_analyze', data={
        'file': (io.BytesIO(csv_bytes), 'sales.csv'),
        'template_type': 'sales_data',
        'save_dataset': 'true',
    }, content_type='multipart/form-data')

    assert DataRecord.query.one().data['Revenue'] is None


@pytest.mark.parametrize('form, filename', [
    ({'template_type': 'sales_data'}, 'sales.csv'),  # 파일 필드 없음은 아래에서 별도 처리
])
def test_template_analyze_requires_file_field(logged_in_client, db_session, form, filename):
    response = logged_in_client.post('/template_analyze', data=form)

    assert '/template_analysis' in response.headers['Location']
    assert Dataset.query.count() == 0


def test_template_analyze_rejects_empty_filename(logged_in_client, db_session):
    response = logged_in_client.post('/template_analyze', data={
        'file': (io.BytesIO(b''), ''), 'template_type': 'sales_data',
    }, content_type='multipart/form-data')

    assert '/template_analysis' in response.headers['Location']
    assert Dataset.query.count() == 0


def test_template_analyze_rejects_unknown_template_type(logged_in_client, db_session):
    response = logged_in_client.post('/template_analyze', data={
        'file': (io.BytesIO(b'Date,Revenue\n2024-01-01,1\n'), 'sales.csv'),
        'template_type': 'nope',
    }, content_type='multipart/form-data')

    assert '/template_analysis' in response.headers['Location']
    assert Dataset.query.count() == 0


def test_template_analyze_rejects_unreadable_excel(logged_in_client, db_session):
    response = logged_in_client.post('/template_analyze', data={
        'file': (io.BytesIO(b'x'), 'sales.xlsx'), 'template_type': 'sales_data',
    }, content_type='multipart/form-data')

    assert '/template_analysis' in response.headers['Location']
    assert Dataset.query.count() == 0


def test_template_analyze_accepts_excel(logged_in_client, db_session):
    df = pd.DataFrame({'Date': ['2024-01-01'], 'Revenue': [100]})

    response = logged_in_client.post('/template_analyze', data={
        'file': (_excel_bytes(df), 'sales.xlsx'), 'template_type': 'sales_data',
        'analysis_options': '1', 'auto_analysis': 'true',
    }, content_type='multipart/form-data')

    dataset = Dataset.query.one()
    assert f'/template/analysis/{dataset.id}' in response.headers['Location']


def test_template_analyze_detects_type_when_not_selected(logged_in_client, db_session):
    response = logged_in_client.post('/template_analyze', data={
        'file': (io.BytesIO(b'Date,Revenue\n2024-01-01,100\n'), 'sales.csv'),
    }, content_type='multipart/form-data')

    dataset = Dataset.query.one()
    assert dataset.name.startswith('판매 데이터 분석')
    assert f'/template/analysis/{dataset.id}' in response.headers['Location']


def test_ocr_upload_stores_extracted_table(logged_in_client, db_session, monkeypatch):
    import src.ocr_utils as ocr_utils

    extracted = pd.DataFrame({'이름': ['사과'], '수량': [3]})
    monkeypatch.setattr(ocr_utils, 'process_ocr_document', lambda *a, **kw: {
        'success': True, 'data': extracted, 'error': None, 'method': 'img2table',
    })

    response = logged_in_client.post('/ocr/upload', data={
        'file': (io.BytesIO(b'fake-image'), 'scan.png'),
    }, content_type='multipart/form-data')

    ocr_session = OCRSession.query.one()
    assert ocr_session.status == 'completed'
    assert ocr_session.extracted_data['columns'] == ['이름', '수량']
    assert f'/ocr/verify/{ocr_session.id}' in response.headers['Location']


def test_ocr_upload_marks_session_failed_on_error(logged_in_client, db_session, monkeypatch):
    import src.ocr_utils as ocr_utils

    def _boom(*args, **kwargs):
        raise RuntimeError('OCR 실패')

    monkeypatch.setattr(ocr_utils, 'process_ocr_document', _boom)

    response = logged_in_client.post('/ocr/upload', data={
        'file': (io.BytesIO(b'fake-image'), 'scan.png'),
    }, content_type='multipart/form-data')

    ocr_session = OCRSession.query.one()
    assert ocr_session.status == 'failed'
    assert 'OCR 실패' in ocr_session.error_message
    assert response.status_code == 302


def test_ocr_upload_without_file_redirects(logged_in_client, db_session):
    response = logged_in_client.post('/ocr/upload', data={})

    assert '/ocr/scan' in response.headers['Location']
    assert OCRSession.query.count() == 0


def test_ocr_upload_rejects_empty_filename(logged_in_client, db_session):
    response = logged_in_client.post('/ocr/upload', data={
        'file': (io.BytesIO(b''), ''),
    }, content_type='multipart/form-data')

    assert '/ocr/scan' in response.headers['Location']
    assert OCRSession.query.count() == 0


def _make_ocr_session(db, user, **kwargs):
    ocr_session = OCRSession(
        user_id=user.id, filename='scan.png', file_path='/tmp/scan.png', **kwargs
    )
    db.session.add(ocr_session)
    db.session.commit()
    return ocr_session


def test_ocr_verify_renders_extracted_rows(logged_in_client, user, db_session):
    ocr_session = _make_ocr_session(db_session, user, status='completed', extracted_data={
        'columns': ['이름', '수량'], 'data': [['사과', '3']],
    })

    response = logged_in_client.get(f'/ocr/verify/{ocr_session.id}')

    assert response.status_code == 200
    assert '사과' in response.get_data(as_text=True)


def test_ocr_verify_redirects_when_no_data(logged_in_client, user, db_session):
    ocr_session = _make_ocr_session(db_session, user)

    response = logged_in_client.get(f'/ocr/verify/{ocr_session.id}')

    assert '/ocr/scan' in response.headers['Location']


def test_ocr_verify_denies_other_users(logged_in_client, db_session):
    other = User(email='ocrother@example.com', name='타인')
    other.set_password('pw')
    db_session.session.add(other)
    db_session.session.flush()
    ocr_session = _make_ocr_session(db_session, other, extracted_data={'data': [['x']]})

    response = logged_in_client.get(f'/ocr/verify/{ocr_session.id}')

    assert '/dashboard' in response.headers['Location']


def test_ocr_save_creates_dataset_from_edited_table(logged_in_client, user, db_session, tmp_path):
    ocr_session = _make_ocr_session(db_session, user, extracted_data={'data': [['사과', '3']]})
    payload = json.dumps({'headers': ['이름', '수량'], 'rows': [['사과', '3'], ['배', '5']]})

    response = logged_in_client.post(f'/ocr/save/{ocr_session.id}', data={
        'dataset_name': 'OCR 데이터', 'description': '스캔', 'data': payload,
    })

    dataset = Dataset.query.one()
    assert dataset.is_ocr is True
    assert dataset.row_count == 2
    assert DataRecord.query.count() == 2
    assert os.path.exists(dataset.file_path)
    assert '/dashboard' in response.headers['Location']


def test_ocr_save_requires_name_and_data(logged_in_client, user, db_session):
    ocr_session = _make_ocr_session(db_session, user, extracted_data={'data': [['x']]})

    response = logged_in_client.post(f'/ocr/save/{ocr_session.id}', data={'dataset_name': ''})

    assert f'/ocr/verify/{ocr_session.id}' in response.headers['Location']
    assert Dataset.query.count() == 0


def test_ocr_save_handles_invalid_json(logged_in_client, user, db_session):
    ocr_session = _make_ocr_session(db_session, user, extracted_data={'data': [['x']]})

    response = logged_in_client.post(f'/ocr/save/{ocr_session.id}', data={
        'dataset_name': 'x', 'data': 'not-json',
    })

    assert f'/ocr/verify/{ocr_session.id}' in response.headers['Location']
    assert Dataset.query.count() == 0


def test_ocr_save_denies_other_users(logged_in_client, db_session):
    other = User(email='ocrother2@example.com', name='타인')
    other.set_password('pw')
    db_session.session.add(other)
    db_session.session.flush()
    ocr_session = _make_ocr_session(db_session, other, extracted_data={'data': [['x']]})

    response = logged_in_client.post(f'/ocr/save/{ocr_session.id}', data={
        'dataset_name': 'x', 'data': json.dumps({'headers': ['a'], 'rows': [['1']]}),
    })

    assert '/dashboard' in response.headers['Location']
    assert Dataset.query.count() == 0


def test_uploaded_file_serves_own_file(logged_in_client, user, db_session, tmp_path):
    (tmp_path / 'scan.png').write_bytes(b'image-bytes')
    _make_ocr_session(db_session, user)

    response = logged_in_client.get('/uploads/scan.png')

    assert response.status_code == 200
    assert response.data == b'image-bytes'


def test_uploaded_file_denies_other_users_file(logged_in_client, db_session, tmp_path):
    (tmp_path / 'scan.png').write_bytes(b'image-bytes')
    other = User(email='other-upload@example.com', name='다른 사용자')
    other.set_password('pw')
    db_session.session.add(other)
    db_session.session.flush()
    _make_ocr_session(db_session, other)

    response = logged_in_client.get('/uploads/scan.png')

    assert '/dashboard' in response.headers['Location']
