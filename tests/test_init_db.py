"""init_db.py 스크립트 함수 테스트."""

import pandas as pd

import init_db
from models import DataRecord, Dataset, User


def test_init_database_creates_tables(flask_app, capsys):
    from models import db

    init_db.init_database()

    with flask_app.app_context():
        assert User.query.count() == 0
        assert Dataset.query.count() == 0
        db.session.remove()

    assert '데이터베이스 테이블이 생성되었습니다' in capsys.readouterr().out


def test_create_sample_user_creates_once(db_session, capsys):
    init_db.create_sample_user()
    capsys.readouterr()
    init_db.create_sample_user()

    assert '이미 존재합니다' in capsys.readouterr().out
    user = User.query.filter_by(email='test@example.com').one()
    assert user.check_password('test1234')


def test_create_sample_data_requires_sample_user(db_session, capsys):
    init_db.create_sample_data()

    assert '먼저 샘플 사용자를 생성하세요' in capsys.readouterr().out
    assert Dataset.query.count() == 0


def test_create_sample_data_inserts_datasets_and_records(db_session):
    init_db.create_sample_user()
    init_db.create_sample_data()

    datasets = Dataset.query.all()
    assert len(datasets) == 4
    assert all(dataset.is_template for dataset in datasets)
    assert all(dataset.row_count == len(dataset.records) for dataset in datasets)
    assert DataRecord.query.count() > 0


def test_create_sample_data_skips_existing_datasets(db_session, capsys):
    init_db.create_sample_user()
    init_db.create_sample_data()
    record_count = DataRecord.query.count()
    capsys.readouterr()

    init_db.create_sample_data()

    assert '이미 존재' in capsys.readouterr().out
    assert Dataset.query.count() == 4
    assert DataRecord.query.count() == record_count


def test_create_sample_data_reports_missing_template_files(db_session, monkeypatch, capsys):
    init_db.create_sample_user()
    monkeypatch.setattr(init_db.os.path, 'exists', lambda path: False)

    init_db.create_sample_data()

    assert '파일 없음' in capsys.readouterr().out
    assert Dataset.query.count() == 0


def test_create_sample_data_converts_nan_to_none(db_session, monkeypatch):
    init_db.create_sample_user()
    df = pd.DataFrame({'A': [1, 2], 'B': [float('nan'), 2.5]})
    monkeypatch.setattr(init_db.pd, 'read_csv', lambda path: df)

    init_db.create_sample_data()

    values = [record.data['B'] for record in DataRecord.query.all()]
    assert None in values
    assert 2.5 in values


def test_check_database_prints_counts(db_session, capsys):
    init_db.create_sample_user()

    init_db.check_database()
    output = capsys.readouterr().out

    assert '사용자 수 / Total Users: 1' in output
    assert '데이터셋 수 / Total Datasets: 0' in output
