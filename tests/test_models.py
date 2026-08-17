"""models.py (User, Dataset, DataRecord, DataView, OCRSession) 테스트."""

import pytest
from sqlalchemy.exc import IntegrityError

from models import DataRecord, DataView, Dataset, OCRSession, User


def _make_user(db, email='user@example.com', password='pw1234', **kwargs):
    user = User(email=email, name=kwargs.pop('name', '홍길동'), **kwargs)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def test_set_password_hashes_and_check_password(db_session):
    user = _make_user(db_session, password='secret123')

    assert user.password_hash != 'secret123'
    assert user.check_password('secret123') is True
    assert user.check_password('wrong') is False


def test_set_password_generates_distinct_hashes(db_session):
    a = User(email='a@example.com', name='A')
    b = User(email='b@example.com', name='B')
    a.set_password('samepassword')
    b.set_password('samepassword')

    assert a.password_hash != b.password_hash


def test_user_defaults_and_flask_login_interface(db_session):
    user = _make_user(db_session, company='LUDA')

    assert user.id is not None
    assert user.company == 'LUDA'
    assert user.created_at is not None
    assert user.is_authenticated is True
    assert user.is_active is True
    assert user.is_anonymous is False
    assert user.get_id() == str(user.id)


def test_user_email_must_be_unique(db_session):
    _make_user(db_session, email='dup@example.com')

    duplicate = User(email='dup@example.com', name='중복')
    duplicate.set_password('pw')
    db_session.session.add(duplicate)

    with pytest.raises(IntegrityError):
        db_session.session.commit()
    db_session.session.rollback()


def test_dataset_defaults_and_user_backref(db_session):
    user = _make_user(db_session)
    dataset = Dataset(
        name='매출 데이터',
        filename='sales.csv',
        file_path='/tmp/sales.csv',
        user_id=user.id,
        columns=['Date', 'Revenue'],
    )
    db_session.session.add(dataset)
    db_session.session.commit()

    assert dataset.is_template is False
    assert dataset.is_ocr is False
    assert dataset.uploaded_at is not None
    assert dataset.columns == ['Date', 'Revenue']
    assert dataset.user is user
    assert user.datasets == [dataset]


def test_data_record_json_roundtrip(db_session):
    user = _make_user(db_session)
    dataset = Dataset(name='d', filename='f.csv', file_path='/tmp/f.csv', user_id=user.id)
    db_session.session.add(dataset)
    db_session.session.flush()

    payload = {'Date': '2024-01-01', 'Revenue': 1000, 'Note': None}
    db_session.session.add(DataRecord(dataset_id=dataset.id, data=payload))
    db_session.session.commit()

    record = DataRecord.query.one()
    assert record.data == payload
    assert record.dataset is dataset
    assert dataset.records == [record]


def test_deleting_dataset_cascades_to_records_and_views(db_session):
    user = _make_user(db_session)
    dataset = Dataset(name='d', filename='f.csv', file_path='/tmp/f.csv', user_id=user.id)
    db_session.session.add(dataset)
    db_session.session.flush()
    db_session.session.add(DataRecord(dataset_id=dataset.id, data={'a': 1}))
    db_session.session.add(DataView(
        dataset_id=dataset.id, name='막대 차트', chart_type='bar',
        x_column='Date', y_column='Revenue', config={'stacked': True},
    ))
    db_session.session.commit()

    db_session.session.delete(dataset)
    db_session.session.commit()

    assert DataRecord.query.count() == 0
    assert DataView.query.count() == 0


def test_deleting_user_cascades_to_datasets(db_session):
    user = _make_user(db_session)
    db_session.session.add(
        Dataset(name='d', filename='f.csv', file_path='/tmp/f.csv', user_id=user.id)
    )
    db_session.session.commit()

    db_session.session.delete(user)
    db_session.session.commit()

    assert Dataset.query.count() == 0


def test_data_view_persists_chart_settings(db_session):
    user = _make_user(db_session)
    dataset = Dataset(name='d', filename='f.csv', file_path='/tmp/f.csv', user_id=user.id)
    db_session.session.add(dataset)
    db_session.session.flush()

    view = DataView(dataset_id=dataset.id, name='추이', chart_type='line', x_column='Date')
    db_session.session.add(view)
    db_session.session.commit()

    assert view.y_column is None
    assert view.config is None
    assert view.created_at is not None
    assert view.dataset is dataset


def test_ocr_session_defaults_and_user_backref(db_session):
    user = _make_user(db_session)
    ocr = OCRSession(user_id=user.id, filename='scan.png', file_path='/tmp/scan.png')
    db_session.session.add(ocr)
    db_session.session.commit()

    assert ocr.status == 'pending'
    assert ocr.extracted_data is None
    assert ocr.error_message is None
    assert ocr.created_at is not None
    assert ocr.user is user
    assert user.ocr_sessions == [ocr]


def test_ocr_session_stores_extracted_table(db_session):
    user = _make_user(db_session)
    extracted = {'columns': ['A', 'B'], 'data': [[1, 2], [3, 4]]}
    ocr = OCRSession(
        user_id=user.id, filename='scan.png', file_path='/tmp/scan.png',
        extracted_data=extracted, status='completed',
    )
    db_session.session.add(ocr)
    db_session.session.commit()

    stored = OCRSession.query.one()
    assert stored.extracted_data == extracted
    assert stored.status == 'completed'


def test_table_names():
    assert User.__tablename__ == 'users'
    assert Dataset.__tablename__ == 'datasets'
    assert DataRecord.__tablename__ == 'data_records'
    assert DataView.__tablename__ == 'data_views'
    assert OCRSession.__tablename__ == 'ocr_sessions'
