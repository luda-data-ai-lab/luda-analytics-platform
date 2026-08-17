"""인사이트 계산 공통 유틸 / Shared aggregation helpers for insights & metrics."""

import pandas as pd


def group_agg(df, group_col, value_col, how='sum', ascending=False):
    """그룹별 집계 후 정렬된 Series 반환"""
    grouped = df.groupby(group_col)[value_col].agg(how)
    return grouped.sort_values(ascending=ascending)


def share_pct(series, position=0):
    """전체 합계 대비 특정 순위 항목의 비중(%)"""
    total = series.sum()
    return series.iloc[position] / total * 100 if total else 0.0


def top_share(df, group_col, value_col, how='sum'):
    """상위 항목명과 전체 대비 비중(%), 정렬된 Series를 함께 반환"""
    grouped = group_agg(df, group_col, value_col, how=how)
    return grouped.index[0], share_pct(grouped), grouped


def correlation(df, col_a, col_b):
    """숫자 변환 후 두 컬럼의 상관계수"""
    a = pd.to_numeric(df[col_a], errors='coerce')
    b = pd.to_numeric(df[col_b], errors='coerce')
    return a.corr(b)


def ratio_pct(numerator, denominator):
    """비율(%) — 0 나눗셈 방지"""
    return numerator / denominator * 100 if denominator else 0.0


def gain_pct(value, base):
    """증감률(%) — ROI, 이익률, 성장률 계산에 공통 사용"""
    return (value - base) / base * 100 if base else 0.0


def group_ratio(df, group_col, numerator_col, denominator_col, out_col,
                mode='ratio', decimals=1, sort=True):
    """그룹별 합계로 비율/증감률 컬럼을 추가한 DataFrame 반환

    mode='ratio'  → numerator / denominator * 100              (예: 전환율)
    mode='gain'   → (numerator - denominator) / denominator * 100  (예: ROI)
    mode='margin' → (numerator - denominator) / numerator * 100    (예: 이익률)
    """
    agg = df.groupby(group_col)[[numerator_col, denominator_col]].sum().reset_index()
    numerator, denominator = agg[numerator_col], agg[denominator_col]
    if mode == 'gain':
        values = (numerator - denominator) / denominator
    elif mode == 'margin':
        values = (numerator - denominator) / numerator
    else:
        values = numerator / denominator
    agg[out_col] = (values * 100).round(decimals)
    return agg.sort_values(out_col) if sort else agg
