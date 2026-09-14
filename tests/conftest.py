"""공용 테스트 픽스처 / Shared test fixtures."""

import os
import sys
import tempfile

import pandas as pd
import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, 'src')

# app/config 임포트 전에 테스트용 SQLite DB로 교체
_TEST_DB_FD, _TEST_DB_PATH = tempfile.mkstemp(suffix='.sqlite')
os.close(_TEST_DB_FD)
os.environ['DATABASE_URL'] = f'sqlite:///{_TEST_DB_PATH}'
os.environ.setdefault('SECRET_KEY', 'test-secret-key')

for path in (ROOT_DIR, SRC_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)


@pytest.fixture(scope='session', autouse=True)
def _cleanup_test_db():
    yield
    if os.path.exists(_TEST_DB_PATH):
        os.remove(_TEST_DB_PATH)


@pytest.fixture(scope='session')
def flask_app():
    """테스트 설정이 적용된 Flask 앱."""
    import app as app_module

    app_module.app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SERVER_NAME='localhost',
    )
    return app_module.app


@pytest.fixture
def app_context(flask_app):
    with flask_app.app_context():
        yield flask_app


@pytest.fixture
def request_context(flask_app):
    with flask_app.test_request_context('/'):
        yield flask_app


@pytest.fixture
def db_session(flask_app):
    """빈 테이블을 가진 DB 세션 (테스트마다 초기화)."""
    from models import db

    with flask_app.app_context():
        db.drop_all()
        db.create_all()
        yield db
        db.session.remove()
        db.drop_all()


@pytest.fixture
def sales_df():
    return pd.DataFrame({
        'Date': ['2024-01-05', '2024-01-20', '2024-02-10', '2024-02-25'],
        'Revenue': [1000, 2000, 3000, 4000],
        'Cost': [500, 900, 1500, 2000],
        'Region': ['서울', '부산', '서울', '부산'],
        'Product': ['A', 'B', 'A', 'B'],
        'Category': ['가전', '가구', '가전', '가구'],
        'Quantity': [10, 20, 30, 40],
    })


@pytest.fixture
def crop_df():
    return pd.DataFrame({
        'Crop_Type': ['쌀', '보리', '쌀', '보리'],
        'Crop_Yield_kg': [1200, 800, 1500, 700],
        'Rainfall_mm': [100, 120, 90, 130],
        'Temperature_C': [21.5, 19.0, 23.0, 18.5],
        'Fertilizer_kg': [50, 40, 55, 35],
        'Soil_Type': ['점토', '사질', '점토', '사질'],
        'Climate': ['온대', '냉대', '온대', '냉대'],
        'Irrigation_hours': [5, 3, 6, 2],
    })


@pytest.fixture
def marketing_df():
    return pd.DataFrame({
        'Date': ['2024-01-05', '2024-01-20', '2024-02-10', '2024-02-25'],
        'Channel': ['검색', 'SNS', '검색', 'SNS'],
        'Campaign_Name': ['C1', 'C2', 'C3', 'C4'],
        'Impressions': [10000, 20000, 15000, 25000],
        'Clicks': [500, 800, 700, 900],
        'Conversions': [50, 40, 70, 45],
        'Budget': [1000, 2000, 1200, 2200],
        'Revenue': [3000, 2500, 4000, 2600],
    })


@pytest.fixture
def customer_df():
    return pd.DataFrame({
        'Segment': ['VIP', '일반', 'VIP', '일반', '신규'],
        'Age': [25, 35, 45, 55, 19],
        'Gender': ['남', '여', '남', '여', '여'],
        'Income': [3000, 4000, 5000, 6000, 2000],
        'Total_Purchases': [10, 5, 20, 3, 1],
        'Avg_Purchase_Value': [100, 200, 300, 150, 50],
        'Last_Purchase_Days': [10, 120, 30, 200, 5],
    })
