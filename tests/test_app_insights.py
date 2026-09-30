"""app.generate_insights 및 템플릿별 인사이트 함수 테스트."""

import pandas as pd
from flask import session as flask_session

import app as app_module


def test_generate_insights_sales(sales_df):
    insights = app_module.generate_insights(sales_df)

    assert set(insights) >= {
        'daily_sales', 'region_sales', 'product_distribution',
        'category_sales', 'quantity_revenue', 'daily_quantity',
    }
    assert '2024-02' in insights['daily_sales']  # 최고 매출 월
    assert '부산' in insights['region_sales']  # 매출 1위 지역
    assert all(isinstance(text, str) and text for text in insights.values())


def test_sales_insight_month_growth_and_top_region(sales_df):
    ins = app_module._insights_sales(sales_df)

    # 1월 3000원 → 2월 7000원 = +133.3%
    assert '+133.3%' in ins['daily_sales']
    # 서울 4000 vs 부산 6000 → 부산 60.0%
    assert '60.0%' in ins['region_sales']


def test_sales_insight_skips_sections_for_missing_columns():
    df = pd.DataFrame({'Date': ['2024-01-01', '2024-02-01'], 'Revenue': [100, 200]})

    ins = app_module._insights_sales(df)

    assert 'daily_sales' in ins
    assert 'region_sales' not in ins
    assert 'product_distribution' not in ins
    assert 'quantity_revenue' not in ins


def test_sales_insight_single_month_has_zero_growth():
    df = pd.DataFrame({'Date': ['2024-01-01', '2024-01-15'], 'Revenue': [100, 300]})

    ins = app_module._insights_sales(df)

    assert '+0.0%' in ins['daily_sales']


def test_sales_insight_does_not_mutate_input():
    df = pd.DataFrame({'Date': ['2024-01-01'], 'Revenue': [100]})
    original_columns = df.columns.tolist()

    app_module._insights_sales(df)

    assert df.columns.tolist() == original_columns
    assert df['Date'].tolist() == ['2024-01-01']


def test_generate_insights_crop(crop_df):
    insights = app_module.generate_insights(crop_df)

    assert '쌀' in insights['daily_sales']
    assert '온대' in insights['region_sales']
    assert insights['region_sales'].count('<strong>') >= 2


def test_generate_insights_marketing(marketing_df):
    insights = app_module.generate_insights(marketing_df)

    assert set(insights) >= {
        'daily_sales', 'region_sales', 'product_distribution',
        'category_sales', 'quantity_revenue', 'daily_quantity',
    }
    # 검색 채널 ROI(7000/2200) > SNS 채널 ROI(5100/4200)
    assert '검색' in insights['region_sales']


def test_marketing_insight_budget_concentration(marketing_df):
    ins = app_module._insights_marketing(marketing_df)

    # SNS 예산 4200 / 총 6400 = 65.6%
    assert 'SNS' in ins['product_distribution']
    assert '65.6%' in ins['product_distribution']


def test_generate_insights_customer(customer_df):
    insights = app_module.generate_insights(customer_df)

    assert set(insights) >= {
        'daily_sales', 'region_sales', 'product_distribution',
        'category_sales', 'quantity_revenue', 'daily_quantity',
    }
    assert 'VIP' in insights['region_sales']
    assert '90+ days' in insights['daily_quantity']


def test_generate_insights_customer_korean(customer_df):
    with app_module.app.test_request_context():
        flask_session['language'] = 'ko'
        insights = app_module.generate_insights(customer_df)

    assert '90일' in insights['daily_quantity']


def test_customer_insight_falls_back_to_age_purchase_correlation(customer_df):
    df = customer_df.drop(columns=['Last_Purchase_Days'])

    with app_module.app.test_request_context():
        flask_session['language'] = 'ko'
        ins = app_module._insights_customer(df)

    assert '연령-구매횟수 상관계수' in ins['daily_quantity']


def test_generate_insights_generic_template_is_empty():
    df = pd.DataFrame({'Foo': [1, 2], 'Bar': ['a', 'b']})

    assert app_module.generate_insights(df) == {}


def test_generate_insights_swallows_errors():
    df = pd.DataFrame({'Revenue': ['x', 'y'], 'Region': ['서울', '부산']})

    assert app_module.generate_insights(df) == {}
