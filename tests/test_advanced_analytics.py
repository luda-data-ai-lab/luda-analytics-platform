"""고급 분석 유틸리티 테스트 (시계열 / 이상치 / 상관·기여도)."""

import numpy as np
import pandas as pd
import pytest

from src.advanced_analytics import (
    categorical_columns, contribution_analysis, correlation_analysis, datetime_columns,
    numeric_columns, outlier_analysis, resample_series, timeseries_analysis
)


@pytest.fixture
def monthly_df():
    """24개월간 추세가 있는 매출 데이터."""
    dates = pd.date_range('2023-01-01', periods=24, freq='MS')
    return pd.DataFrame({
        'Date': dates.strftime('%Y-%m-%d'),
        'Revenue': [100 + 10 * i for i in range(24)],
        'Region': ['서울', '부산'] * 12,
    })


def test_numeric_columns_includes_numeric_strings():
    df = pd.DataFrame({'a': ['1', '2', '3', '4'], 'b': ['x', 'y', 'z', 'w']})

    assert numeric_columns(df) == ['a']


def test_datetime_columns_skips_numeric_and_text(monthly_df):
    assert datetime_columns(monthly_df) == ['Date']


def test_categorical_columns_excludes_constant_and_high_cardinality():
    df = pd.DataFrame({
        'const': ['a'] * 5,
        'group': ['a', 'b', 'a', 'b', 'a'],
        'unique': list(range(5)),
    })

    assert categorical_columns(df, max_unique=3) == ['group']


def test_resample_series_aggregates_by_month(monthly_df):
    series = resample_series(monthly_df, 'Date', 'Revenue', freq='M', agg='sum')

    assert len(series) == 24
    assert series.iloc[0] == 100
    assert series.iloc[-1] == 330


def test_resample_series_rejects_unknown_agg(monthly_df):
    with pytest.raises(ValueError):
        resample_series(monthly_df, 'Date', 'Revenue', agg='median')


def test_timeseries_analysis_computes_change_yoy_and_forecast(monthly_df):
    result = timeseries_analysis(monthly_df, 'Date', 'Revenue', freq='M', window=3, horizon=3)

    table = result['table']
    assert list(table.columns) == ['value', 'moving_avg', 'change_pct', 'yoy_pct']
    assert table['change_pct'].iloc[1] == pytest.approx(10.0)
    assert table['yoy_pct'].notna().any()

    stats = result['stats']
    assert stats['periods'] == 24
    assert stats['slope'] == pytest.approx(10.0)
    # 선형 추세이므로 다음 기간 예측은 다음 값(340)에 가깝다
    assert stats['forecast_next'] == pytest.approx(340, rel=0.05)
    assert len(result['forecast']) == 3
    assert (result['forecast']['upper'] >= result['forecast']['lower']).all()
    assert set(result['figures']) == {'trend', 'change'}


def test_timeseries_analysis_returns_none_for_short_series():
    df = pd.DataFrame({'Date': ['2024-01-01', '2024-02-01'], 'Revenue': [1, 2]})

    assert timeseries_analysis(df, 'Date', 'Revenue') is None


def test_timeseries_analysis_without_forecast(monthly_df):
    result = timeseries_analysis(monthly_df, 'Date', 'Revenue', horizon=0)

    assert result['forecast'] is None
    assert result['stats']['forecast_next'] is None


def test_outlier_analysis_iqr_flags_extreme_value():
    df = pd.DataFrame({'v': [10, 11, 12, 13, 11, 12, 500], 'g': list('aaaaaab')})

    result = outlier_analysis(df, 'v', method='iqr', threshold=1.5, group_col='g')

    assert result['method'] == 'iqr'
    assert result['count'] == 1
    assert result['total'] == 7
    assert result['rows']['v'].tolist() == [500]
    assert result['bounds'][1] < 500
    assert result['figures']['by_group'] is not None


def test_outlier_analysis_zscore_respects_threshold():
    values = [10] * 20 + [80]
    df = pd.DataFrame({'v': values})

    strict = outlier_analysis(df, 'v', method='zscore', threshold=2)
    loose = outlier_analysis(df, 'v', method='zscore', threshold=5)

    assert strict['count'] == 1
    assert loose['count'] == 0
    assert strict['pct'] == pytest.approx(100 / 21)


def test_outlier_analysis_returns_none_for_tiny_sample():
    assert outlier_analysis(pd.DataFrame({'v': [1, 2, 3]}), 'v') is None


def test_outlier_analysis_without_group_has_no_group_figure():
    df = pd.DataFrame({'v': [1, 2, 3, 4, 100]})

    result = outlier_analysis(df, 'v')

    assert result['figures']['by_group'] is None


def test_correlation_analysis_ranks_strongest_pairs():
    df = pd.DataFrame({
        'a': [1, 2, 3, 4, 5],
        'b': [2, 4, 6, 8, 10],
        'c': [5, 3, 4, 1, 2],
    })

    result = correlation_analysis(df)

    assert result['sample_size'] == 5
    first, second, value = result['pairs'][0]
    assert {first, second} == {'a', 'b'}
    assert value == pytest.approx(1.0)
    assert result['matrix'].shape == (3, 3)


def test_correlation_analysis_requires_two_numeric_columns():
    df = pd.DataFrame({'a': [1, 2, 3, 4], 'b': list('wxyz')})

    assert correlation_analysis(df) is None


def test_contribution_analysis_returns_standardized_coefficients():
    rng = np.random.default_rng(42)
    driver = rng.normal(size=60)
    noise = rng.normal(size=60)
    df = pd.DataFrame({
        'target': 3 * driver + 0.1 * noise,
        'driver': driver,
        'noise': noise,
    })

    result = contribution_analysis(df, 'target')

    assert result['target'] == 'target'
    assert result['r_squared'] > 0.95
    assert result['coefficients'].index[0] == 'driver'
    assert result['coefficients']['driver'] > abs(result['coefficients']['noise'])


def test_contribution_analysis_requires_features_and_variance():
    single = pd.DataFrame({'target': [1, 2, 3, 4]})
    constant = pd.DataFrame({'target': [1, 1, 1, 1, 1], 'x': [1, 2, 3, 4, 5]})

    assert contribution_analysis(single, 'target') is None
    assert contribution_analysis(constant, 'target') is None
