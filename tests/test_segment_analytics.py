"""세그먼트·검정 분석 테스트 (RFM / 파레토(ABC) / 코호트 / A/B)."""

import numpy as np
import pandas as pd
import pytest

from src.segment_analytics import (
    ab_test_analysis, cohort_analysis, pareto_analysis, rfm_analysis, two_sided_p_value
)


@pytest.fixture
def transactions_df():
    """고객 5명 × 월별 거래 (VIP 고객일수록 최근·다빈도·고액)."""
    rows = []
    for index, customer in enumerate(['C1', 'C2', 'C3', 'C4', 'C5']):
        for month in range(1, 6 + index):
            rows.append({
                'Customer': customer,
                'Date': f'2024-{month:02d}-05',
                'Revenue': 100 * (index + 1),
                'Category': f'Cat{index % 3}',
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 통계 보조


@pytest.mark.parametrize('statistic, df, expected', [
    (1.96, None, 0.05),
    (2.0, 30, 0.0546),
    (2.228, 10, 0.05),
    (1.0, 5, 0.3632),
    (3.5, 100, 0.00069),
])
def test_two_sided_p_value_matches_reference_tables(statistic, df, expected):
    assert two_sided_p_value(statistic, df) == pytest.approx(expected, abs=1e-4)


def test_two_sided_p_value_is_symmetric_and_bounded():
    assert two_sided_p_value(-2.0, 30) == pytest.approx(two_sided_p_value(2.0, 30))
    assert 0.0 <= two_sided_p_value(0.0, 5) <= 1.0


# ---------------------------------------------------------------- RFM


def test_rfm_scores_and_segments(transactions_df):
    result = rfm_analysis(transactions_df, 'Customer', 'Date', 'Revenue')

    assert result['stats']['customers'] == 5
    table = result['table'].set_index('Customer')
    # C5 는 거래 횟수·금액이 가장 크므로 최고 F/M 점수를 받는다.
    assert table.loc['C5', 'f_score'] == 5
    assert table.loc['C5', 'm_score'] == 5
    assert table.loc['C5', 'frequency'] == 9
    assert set(result['segments']) <= {
        'champions', 'loyal', 'potential', 'at_risk', 'hibernating', 'others'}
    assert set(result['figures']) == {'rfm_segments', 'rfm_revenue'}


def test_rfm_table_keeps_selected_customer_column_name(transactions_df):
    renamed = transactions_df.rename(columns={'Customer': 'customer_id'})

    table = rfm_analysis(renamed, 'customer_id', 'Date', 'Revenue')['table']

    assert table.columns[0] == 'customer_id'
    assert set(table['customer_id']) == set(renamed['customer_id'])


def test_rfm_requires_three_customers():
    df = pd.DataFrame({
        'Customer': ['A', 'B', 'A'],
        'Date': ['2024-01-01', '2024-01-02', '2024-02-01'],
        'Revenue': [10, 20, 30],
    })

    assert rfm_analysis(df, 'Customer', 'Date', 'Revenue') is None


# ---------------------------------------------------------------- 파레토 / ABC


def test_pareto_cumulative_share_and_abc_classes():
    df = pd.DataFrame({
        'Category': ['A', 'B', 'C', 'D'],
        'Revenue': [800, 100, 60, 40],
    })

    result = pareto_analysis(df, 'Category', 'Revenue')

    table = result['table']
    assert table['category'].tolist() == ['A', 'B', 'C', 'D']
    assert table['share_pct'].tolist() == pytest.approx([80.0, 10.0, 6.0, 4.0])
    assert table['cumulative_pct'].tolist() == pytest.approx([80.0, 90.0, 96.0, 100.0])
    assert table['abc'].tolist() == ['A', 'B', 'C', 'C']
    assert result['stats']['total'] == pytest.approx(1000.0)
    assert result['stats']['top_category'] == 'A'


def test_pareto_returns_none_for_single_category_or_zero_total():
    single = pd.DataFrame({'Category': ['A', 'A'], 'Revenue': [1, 2]})
    zeros = pd.DataFrame({'Category': ['A', 'B'], 'Revenue': [0, 0]})

    assert pareto_analysis(single, 'Category', 'Revenue') is None
    assert pareto_analysis(zeros, 'Category', 'Revenue') is None


# ---------------------------------------------------------------- 코호트


def test_cohort_retention_matrix():
    rows = [
        # 1월 코호트 3명 중 2명이 2월에도 활동
        ('A', '2024-01-10'), ('B', '2024-01-11'), ('C', '2024-01-12'),
        ('A', '2024-02-10'), ('B', '2024-02-11'),
        # 2월 코호트 1명
        ('D', '2024-02-15'),
    ]
    df = pd.DataFrame(rows, columns=['Customer', 'Date'])

    result = cohort_analysis(df, 'Customer', 'Date', freq='M')

    assert result['stats']['cohorts'] == 2
    assert result['stats']['customers'] == 4
    first_cohort = result['table'].iloc[0]
    assert first_cohort['cohort'] == '2024-01'
    assert first_cohort['+0'] == pytest.approx(100.0)
    assert first_cohort['+1'] == pytest.approx(66.7, abs=0.1)
    # 아직 +1 기간이 지나지 않은 2월 코호트는 평균에서 제외된다.
    assert result['stats']['avg_repeat_pct'] == pytest.approx(66.7, abs=0.1)
    assert pd.isna(result['table'].iloc[1]['+1'])


def test_cohort_rejects_unknown_frequency(transactions_df):
    with pytest.raises(ValueError):
        cohort_analysis(transactions_df, 'Customer', 'Date', freq='X')


def test_cohort_requires_three_customers():
    df = pd.DataFrame({'Customer': ['A', 'B'], 'Date': ['2024-01-01', '2024-02-01']})

    assert cohort_analysis(df, 'Customer', 'Date') is None


# ---------------------------------------------------------------- A/B 검정


def test_ab_mean_detects_clear_difference():
    rng = np.random.default_rng(7)
    df = pd.DataFrame({
        'Group': ['A'] * 60 + ['B'] * 60,
        'Revenue': np.concatenate([rng.normal(100, 5, 60), rng.normal(120, 5, 60)]),
    })

    result = ab_test_analysis(df, 'Group', 'Revenue', metric='mean')

    assert result['test'] == "Welch's t-test"
    assert result['groups'] == ['A', 'B']
    assert result['difference'] > 0
    assert 0.0 <= result['p_value'] <= 1.0
    assert result['p_value'] < 0.01
    assert result['significant'] is True
    low, high = result['confidence_interval']
    assert low < result['difference'] < high


def test_ab_mean_not_significant_for_identical_groups():
    df = pd.DataFrame({
        'Group': ['A'] * 20 + ['B'] * 20,
        'Revenue': list(range(20)) * 2,
    })

    result = ab_test_analysis(df, 'Group', 'Revenue', metric='mean')

    assert result['p_value'] == pytest.approx(1.0)
    assert result['significant'] is False


def test_ab_conversion_uses_proportion_test():
    df = pd.DataFrame({
        'Group': ['A'] * 100 + ['B'] * 100,
        'Converted': [1] * 20 + [0] * 80 + [1] * 50 + [0] * 50,
    })

    result = ab_test_analysis(df, 'Group', 'Converted', metric='conversion')

    assert result['test'] == 'z-test (proportions)'
    assert result['values'] == pytest.approx([0.2, 0.5])
    assert result['lift_pct'] == pytest.approx(150.0)
    assert result['p_value'] < 0.001
    assert result['significant'] is True


def test_ab_rejects_unknown_metric_and_single_group():
    df = pd.DataFrame({'Group': ['A'] * 5, 'Revenue': [1, 2, 3, 4, 5]})

    with pytest.raises(ValueError):
        ab_test_analysis(df, 'Group', 'Revenue', metric='median')
    assert ab_test_analysis(df, 'Group', 'Revenue') is None


def test_cohort_heatmap_blanks_unobservable_cells():
    frame = pd.DataFrame([
        {'customer': 'C1', 'date': '2024-01-05'},
        {'customer': 'C1', 'date': '2024-02-05'},
        {'customer': 'C2', 'date': '2024-01-07'},
        {'customer': 'C3', 'date': '2024-01-09'},
        {'customer': 'C4', 'date': '2024-02-09'},
    ])

    result = cohort_analysis(frame, 'customer', 'date', freq='M')
    cell_text = result['figures']['cohort'].data[0].text

    assert cell_text[0][0] == '100%'
    # 2월 코호트의 +1 기간은 아직 도래하지 않아 라벨이 비어야 한다
    assert cell_text[1][1] == ''
    assert not any('nan' in str(value).lower() for row in cell_text for value in row)
