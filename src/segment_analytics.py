"""세그먼트 · 검정 분석 유틸리티 (RFM / 파레토(ABC) / 코호트 / A/B 검정).

`advanced_analytics` 와 같은 규칙을 따른다 — 순수 계산 + Plotly Figure 생성만 하고,
현지화 문구와 HTTP 처리는 호출부(app.py)에서 담당한다.
"""

import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src.advanced_analytics import FREQ_RULES, _datetime_series, _layout, _numeric_series
from src.chart_utils import QUALITATIVE_COLORS

# RFM 세그먼트 라벨 (R 점수, FM 점수 조건 순서대로 평가)
RFM_SEGMENTS = (
    ('champions', lambda r, fm: r >= 4 and fm >= 4),
    ('loyal', lambda r, fm: r >= 3 and fm >= 3),
    ('potential', lambda r, fm: r >= 4 and fm <= 2),
    ('at_risk', lambda r, fm: r <= 2 and fm >= 3),
    ('hibernating', lambda r, fm: r <= 2 and fm <= 2),
)
ABC_THRESHOLDS = ((80.0, 'A'), (95.0, 'B'))
AB_METRICS = ('mean', 'conversion')


# ---------------------------------------------------------------- 통계 보조


def _normal_cdf(value):
    return 0.5 * (1.0 + math.erf(value / math.sqrt(2.0)))


def _beta_continued_fraction(a, b, x):
    """Lentz 알고리즘 연분수 전개 (Numerical Recipes betacf)."""
    tiny, epsilon = 1e-300, 1e-15
    c, d = 1.0, 1.0 - (a + b) * x / (a + 1.0)
    d = tiny if abs(d) < tiny else d
    d = 1.0 / d
    result = d
    for m in range(1, 200):
        m2 = 2 * m
        for numerator in (m * (b - m) * x / ((a + m2 - 1.0) * (a + m2)),
                          -(a + m) * (a + b + m) * x / ((a + m2) * (a + m2 + 1.0))):
            d = 1.0 + numerator * d
            d = tiny if abs(d) < tiny else d
            c = 1.0 + numerator / c
            c = tiny if abs(c) < tiny else c
            d = 1.0 / d
            delta = c * d
            result *= delta
        if abs(delta - 1.0) < epsilon:
            break
    return result


def _incomplete_beta(a, b, x):
    """정규화 불완전 베타 함수 — t 분포 누적확률에 사용."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0

    factor = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                      + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return factor * _beta_continued_fraction(a, b, x) / a
    return 1.0 - factor * _beta_continued_fraction(b, a, 1.0 - x) / b


def two_sided_p_value(statistic, df=None):
    """양측 p-value. df 가 없으면 정규분포, 있으면 t 분포를 쓴다."""
    statistic = abs(float(statistic))
    if df is None or df <= 0:
        return float(2.0 * (1.0 - _normal_cdf(statistic)))
    return float(_incomplete_beta(df / 2.0, 0.5, df / (df + statistic ** 2)))


# ---------------------------------------------------------------- RFM


def _score_labels(series, ascending=True):
    """5분위 점수(1~5). 값 종류가 적으면 가능한 만큼만 나눈다."""
    bins = min(5, series.nunique())
    if bins < 2:
        return pd.Series(3, index=series.index, dtype='int64')
    ranked = series.rank(method='first', ascending=ascending)
    scores = pd.qcut(ranked, bins, labels=range(1, bins + 1)).astype('int64')
    return scores if bins == 5 else (scores * 5 // bins).clip(lower=1)


def rfm_analysis(df, customer_col, date_col, value_col, top_n=20):
    """고객별 Recency / Frequency / Monetary 점수와 세그먼트를 계산한다."""
    frame = pd.DataFrame({
        'customer': df[customer_col],
        'date': _datetime_series(df[date_col]),
        'value': _numeric_series(df, value_col),
    }).dropna()
    if frame['customer'].nunique() < 3:
        return None

    reference = frame['date'].max() + pd.Timedelta(days=1)
    rfm = frame.groupby('customer').agg(
        recency=('date', lambda dates: int((reference - dates.max()).days)),
        frequency=('date', 'count'),
        monetary=('value', 'sum'),
    )

    rfm['r_score'] = _score_labels(rfm['recency'], ascending=False)
    rfm['f_score'] = _score_labels(rfm['frequency'])
    rfm['m_score'] = _score_labels(rfm['monetary'])
    fm = ((rfm['f_score'] + rfm['m_score']) / 2).round().astype('int64')
    rfm['segment'] = [
        next((name for name, rule in RFM_SEGMENTS if rule(r, f)), 'others')
        for r, f in zip(rfm['r_score'], fm)
    ]

    counts = rfm['segment'].value_counts()
    revenue = rfm.groupby('segment')['monetary'].sum().reindex(counts.index)
    count_fig = _layout(go.Figure([go.Bar(
        x=counts.index.tolist(), y=counts.to_numpy(),
        marker_color=QUALITATIVE_COLORS[:len(counts)]
    )]), '세그먼트별 고객 수 / Customers per segment', yaxis_title='고객 수 / Customers')
    revenue_fig = _layout(go.Figure([go.Bar(
        x=revenue.index.tolist(), y=revenue.to_numpy(),
        marker_color=QUALITATIVE_COLORS[:len(revenue)]
    )]), f'세그먼트별 {value_col} / {value_col} per segment', yaxis_title=value_col)

    ordered = rfm.sort_values('monetary', ascending=False)
    return {
        'table': ordered.head(top_n).reset_index(),
        'segments': counts.to_dict(),
        'stats': {
            'customers': int(len(rfm)),
            'reference_date': reference.strftime('%Y-%m-%d'),
            'avg_recency': float(rfm['recency'].mean()),
            'avg_frequency': float(rfm['frequency'].mean()),
            'avg_monetary': float(rfm['monetary'].mean()),
            'top_segment': str(counts.index[0]),
        },
        'figures': {'rfm_segments': count_fig, 'rfm_revenue': revenue_fig},
    }


# ---------------------------------------------------------------- 파레토 / ABC


def pareto_analysis(df, category_col, value_col, top_n=30):
    """카테고리별 누적 기여도와 ABC 등급을 계산한다."""
    frame = pd.DataFrame({
        'category': df[category_col].astype(str),
        'value': _numeric_series(df, value_col),
    }).dropna()
    if frame['category'].nunique() < 2:
        return None

    totals = frame.groupby('category')['value'].sum().sort_values(ascending=False)
    total = float(totals.sum())
    if total <= 0:
        return None

    cumulative = totals.cumsum() / total * 100
    classes = [next((label for limit, label in ABC_THRESHOLDS if value <= limit), 'C')
               for value in cumulative]

    table = pd.DataFrame({
        'category': totals.index,
        'value': totals.to_numpy(),
        'share_pct': (totals / total * 100).to_numpy(),
        'cumulative_pct': cumulative.to_numpy(),
        'abc': classes,
    })

    visible = table.head(top_n)
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=visible['category'].tolist(), y=visible['value'].to_numpy(),
        name=value_col, marker_color=QUALITATIVE_COLORS[0]
    ))
    fig.add_trace(go.Scatter(
        x=visible['category'].tolist(), y=visible['cumulative_pct'].to_numpy(),
        name='누적 비율 / Cumulative %', yaxis='y2', mode='lines+markers',
        line=dict(color='#dc3545', width=2)
    ))
    fig.add_hline(y=80, yref='y2', line_dash='dash', line_color='#adb5bd',
                  annotation_text='80%', annotation_position='right')
    _layout(fig, f'{category_col} 파레토 분석 / Pareto analysis', yaxis_title=value_col,
            yaxis2=dict(title='%', overlaying='y', side='right', range=[0, 105]))

    class_counts = table['abc'].value_counts()
    top_share = int(max(1, round(len(table) * 0.2)))
    return {
        'table': table,
        'stats': {
            'categories': int(len(table)),
            'total': total,
            'a_count': int(class_counts.get('A', 0)),
            'b_count': int(class_counts.get('B', 0)),
            'c_count': int(class_counts.get('C', 0)),
            'top20_pct': float(table['share_pct'].head(top_share).sum()),
            'top_category': str(table['category'].iloc[0]),
            'top_category_pct': float(table['share_pct'].iloc[0]),
        },
        'figures': {'pareto': fig},
    }


# ---------------------------------------------------------------- 코호트


def cohort_analysis(df, customer_col, date_col, freq='M', max_periods=12):
    """첫 거래 시점 기준 코호트 리텐션 행렬을 계산한다."""
    if freq not in FREQ_RULES:
        raise ValueError(f'지원하지 않는 주기입니다: {freq}')

    frame = pd.DataFrame({
        'customer': df[customer_col],
        'date': _datetime_series(df[date_col]),
    }).dropna()
    if frame['customer'].nunique() < 3:
        return None

    frame['period'] = frame['date'].dt.to_period(freq)
    frame['cohort'] = frame.groupby('customer')['period'].transform('min')
    frame['offset'] = [period.ordinal - cohort.ordinal
                       for period, cohort in zip(frame['period'], frame['cohort'])]
    frame = frame[(frame['offset'] >= 0) & (frame['offset'] < max_periods)]

    counts = (frame.groupby(['cohort', 'offset'])['customer'].nunique()
              .unstack(fill_value=0).sort_index())
    if counts.empty or 0 not in counts.columns:
        return None

    sizes = counts[0].replace(0, np.nan)
    retention = counts.div(sizes, axis=0) * 100

    # 아직 도래하지 않은 기간은 0% 가 아니라 '측정 불가'(NaN) 로 둔다.
    last_ordinal = frame['period'].max().ordinal
    for cohort in retention.index:
        observable = last_ordinal - cohort.ordinal
        retention.loc[cohort, [column for column in retention.columns
                               if column > observable]] = np.nan
    labels = [str(value) for value in retention.index]

    values = retention.to_numpy()
    # 측정 불가 칸은 셀 라벨도 비워 둔다 ('NaN%' 가 찍히지 않도록)
    cell_text = [['' if np.isnan(value) else f'{value:.0f}%' for value in row]
                 for row in values]
    fig = go.Figure(go.Heatmap(
        z=values.round(1),
        x=[f'+{int(column)}' for column in retention.columns],
        y=labels, colorscale='Blues', zmin=0, zmax=100,
        text=cell_text, texttemplate='%{text}',
        hoverongaps=False, colorbar=dict(title='%')
    ))
    _layout(fig, '코호트 리텐션 / Cohort retention', height=max(360, 60 * len(labels)),
            xaxis_title='경과 기간 / Periods since first activity')

    repeat = retention[1].dropna() if 1 in retention.columns else pd.Series(dtype='float64')
    table = retention.round(1).reset_index()
    table['cohort'] = labels
    table.columns = ['cohort'] + [f'+{int(column)}' for column in retention.columns]
    return {
        'table': table,
        'stats': {
            'cohorts': int(len(retention)),
            'customers': int(frame['customer'].nunique()),
            'avg_repeat_pct': float(repeat.mean()) if len(repeat) else None,
            'best_cohort': str(repeat.idxmax()) if len(repeat) else None,
            'best_cohort_pct': float(repeat.max()) if len(repeat) else None,
        },
        'figures': {'cohort': fig},
    }


# ---------------------------------------------------------------- A/B 검정


def _welch_test(first, second):
    mean_a, mean_b = float(first.mean()), float(second.mean())
    var_a, var_b = float(first.var(ddof=1)), float(second.var(ddof=1))
    n_a, n_b = len(first), len(second)
    standard_error = math.sqrt(var_a / n_a + var_b / n_b)
    if not standard_error:
        return mean_a, mean_b, 0.0, 1.0, standard_error
    statistic = (mean_b - mean_a) / standard_error
    numerator = (var_a / n_a + var_b / n_b) ** 2
    denominator = ((var_a / n_a) ** 2 / (n_a - 1)) + ((var_b / n_b) ** 2 / (n_b - 1))
    degrees = numerator / denominator if denominator else float(n_a + n_b - 2)
    return mean_a, mean_b, statistic, two_sided_p_value(statistic, degrees), standard_error


def _proportion_test(first, second):
    rate_a, rate_b = float(first.mean()), float(second.mean())
    n_a, n_b = len(first), len(second)
    pooled = float((first.sum() + second.sum()) / (n_a + n_b))
    standard_error = math.sqrt(pooled * (1 - pooled) * (1 / n_a + 1 / n_b))
    if not standard_error:
        return rate_a, rate_b, 0.0, 1.0, standard_error
    statistic = (rate_b - rate_a) / standard_error
    return rate_a, rate_b, statistic, two_sided_p_value(statistic), standard_error


def ab_test_analysis(df, group_col, value_col, metric='mean', groups=None, alpha=0.05):
    """두 그룹의 평균(t 검정) 또는 전환율(비율 z 검정) 차이를 검정한다."""
    if metric not in AB_METRICS:
        raise ValueError(f'지원하지 않는 지표입니다: {metric}')

    frame = pd.DataFrame({
        'group': df[group_col].astype(str),
        'value': _numeric_series(df, value_col),
    }).dropna()
    available = frame['group'].value_counts()
    available = available[available >= 2]
    if len(available) < 2:
        return None

    selected = [group for group in (groups or []) if group in available.index][:2]
    if len(selected) < 2:
        selected = available.index[:2].tolist()

    first = frame.loc[frame['group'] == selected[0], 'value']
    second = frame.loc[frame['group'] == selected[1], 'value']
    if metric == 'conversion':
        binary_first = (first > 0).astype('float64')
        binary_second = (second > 0).astype('float64')
        value_a, value_b, statistic, p_value, standard_error = _proportion_test(
            binary_first, binary_second)
        test_name = 'z-test (proportions)'
    else:
        value_a, value_b, statistic, p_value, standard_error = _welch_test(first, second)
        test_name = "Welch's t-test"

    difference = value_b - value_a
    margin = 1.96 * standard_error
    fig = _layout(go.Figure([go.Bar(
        x=selected, y=[value_a, value_b],
        error_y=dict(type='data', array=[margin, margin], visible=bool(standard_error)),
        marker_color=QUALITATIVE_COLORS[:2]
    )]), f'{group_col} A/B 비교 / A/B comparison',
        yaxis_title='전환율 / Conversion rate' if metric == 'conversion' else value_col)

    return {
        'metric': metric,
        'test': test_name,
        'groups': selected,
        'sizes': [int(len(first)), int(len(second))],
        'values': [float(value_a), float(value_b)],
        'difference': float(difference),
        'lift_pct': float(difference / value_a * 100) if value_a else None,
        'confidence_interval': (float(difference - margin), float(difference + margin)),
        'statistic': float(statistic),
        'p_value': float(p_value),
        'significant': bool(p_value < alpha),
        'alpha': float(alpha),
        'available_groups': available.index.tolist(),
        'figures': {'ab_test': fig},
    }
