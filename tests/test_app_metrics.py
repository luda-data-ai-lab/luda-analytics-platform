"""app.calculate_metrics 테스트 (템플릿 4종 + 예외 처리)."""

import pandas as pd

import app as app_module


def test_sales_metrics(sales_df):
    metrics = app_module.calculate_metrics(sales_df)

    assert metrics['total_records'] == 4
    assert metrics['total_revenue'] == 10000
    assert metrics['avg_revenue'] == 2500
    assert metrics['total_quantity'] == 100
    assert metrics['avg_quantity'] == 25.0
    assert metrics['total_profit'] == 10000 - 4900
    assert metrics['profit_margin'] == 51.0
    assert metrics['unique_products'] == 2


def test_sales_metrics_without_optional_columns():
    df = pd.DataFrame({'Date': ['2024-01-01'], 'Revenue': [500]})
    metrics = app_module.calculate_metrics(df)

    assert metrics['total_revenue'] == 500
    assert 'total_quantity' not in metrics
    assert 'total_profit' not in metrics
    assert 'unique_products' not in metrics


def test_crop_metrics(crop_df):
    metrics = app_module.calculate_metrics(crop_df)

    assert metrics['total_records'] == 4
    assert metrics['total_revenue'] == 4200
    assert metrics['avg_revenue'] == 1050
    assert metrics['total_quantity'] == 440
    assert metrics['avg_quantity'] == 110.0
    assert metrics['unique_products'] == 2


def test_marketing_metrics(marketing_df):
    metrics = app_module.calculate_metrics(marketing_df)

    assert metrics['total_records'] == 4
    assert metrics['total_revenue'] == 12100
    assert metrics['total_profit'] == 12100 - 6400
    assert metrics['profit_margin'] == round((12100 - 6400) / 6400 * 100, 1)
    assert metrics['total_quantity'] == 205
    assert metrics['avg_quantity'] == 51.2


def test_customer_metrics(customer_df):
    metrics = app_module.calculate_metrics(customer_df)

    assert metrics['total_records'] == 5
    assert metrics['total_revenue'] == 800
    assert metrics['avg_revenue'] == 160
    assert metrics['total_quantity'] == 39
    assert metrics['avg_quantity'] == 7.8
    assert metrics['unique_products'] == 3


def test_generic_template_only_reports_record_count():
    df = pd.DataFrame({'Foo': [1, 2, 3], 'Bar': ['a', 'b', 'c']})
    assert app_module.calculate_metrics(df) == {'total_records': 3}


def test_metrics_swallow_errors_on_non_numeric_columns():
    df = pd.DataFrame({'Revenue': ['a', 'b'], 'Region': ['서울', '부산']})

    metrics = app_module.calculate_metrics(df)

    assert metrics['total_records'] == 2
    assert 'avg_revenue' not in metrics


def test_metrics_on_empty_sales_frame():
    """빈 데이터프레임은 평균 계산에서 실패해도 예외 없이 부분 결과를 반환한다."""
    df = pd.DataFrame(columns=['Date', 'Revenue', 'Quantity'])

    metrics = app_module.calculate_metrics(df)

    assert metrics['total_records'] == 0
    assert metrics['total_revenue'] == 0
    assert 'avg_revenue' not in metrics
