"""인사이트/지표 계산 공용 유틸리티.

"그룹별 합계 → 1위 · 점유율 · 상관계수 · 비율(%)" 처럼 인사이트 문장마다
반복되던 집계 계산을 모았다. 0 나눗셈은 0.0 으로 처리한다.
"""

import pandas as pd


def group_agg(df, group_col, value_col, how='sum', ascending=False):
    """그룹별 집계 후 정렬된 Series 를 반환한다."""
    grouped = df.groupby(group_col)[value_col].agg(how)
    return grouped.sort_values(ascending=ascending)


def share_pct(series, position=0):
    """전체 합계에서 특정 순위가 차지하는 비중(%)."""
    total = series.sum()
    return series.iloc[position] / total * 100 if total else 0.0


def top_share(df, group_col, value_col, how='sum'):
    """(1위 라벨, 1위 점유율(%), 정렬된 Series) 를 반환한다."""
    grouped = group_agg(df, group_col, value_col, how=how)
    return grouped.index[0], share_pct(grouped), grouped


def correlation(df, col_a, col_b, numeric=False):
    """두 컬럼의 상관계수. `numeric=True` 면 문자열도 숫자로 강제 변환한다."""
    if numeric:
        series_a = pd.to_numeric(df[col_a], errors='coerce')
        series_b = pd.to_numeric(df[col_b], errors='coerce')
        return series_a.corr(series_b)
    return df[[col_a, col_b]].corr().iloc[0, 1]


def ratio_pct(numerator, denominator):
    """numerator / denominator × 100 (분모 0 이면 0.0)."""
    return numerator / denominator * 100 if denominator else 0.0


def gain_pct(value, base):
    """기준값 대비 증감률(%) (기준 0 이면 0.0)."""
    return (value - base) / base * 100 if base else 0.0


def add_ratio_column(data, name, numerator_col, denominator_col,
                     mode='ratio', digits=1):
    """집계 DataFrame 에 비율 컬럼을 추가한다.

    mode='ratio'  → 분자/분모 × 100 (예: 전환율)
    mode='gain'   → (분자-분모)/분모 × 100 (예: ROI)
    mode='margin' → (분자-분모)/분자 × 100 (예: 이익률)
    """
    numerator = data[numerator_col]
    denominator = data[denominator_col]
    if mode == 'gain':
        values = (numerator - denominator) / denominator * 100
    elif mode == 'margin':
        values = (numerator - denominator) / numerator * 100
    else:
        values = numerator / denominator * 100
    data[name] = values.round(digits)
    return data
