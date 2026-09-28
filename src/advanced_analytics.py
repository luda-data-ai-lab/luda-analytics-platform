"""고급 분석 계산 유틸리티 (시계열 / 이상치 / 상관·기여도).

표준 분석 방법론을 데이터셋 컬럼 선택만으로 실행할 수 있도록 모아둔 모듈이다.
모든 함수는 순수 계산 + Plotly Figure 생성만 담당하고, 현지화 문구는 호출부에서 붙인다.
"""

import warnings

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src.chart_utils import BASE_LAYOUT, QUALITATIVE_COLORS

# 리샘플링 주기 (pandas 2.2 에서 M/Q/Y 별칭이 ME/QE/YE 로 변경됨)
_PANDAS_VERSION = tuple(int(part) for part in pd.__version__.split('.')[:2] if part.isdigit())
_LEGACY_FREQ_ALIASES = _PANDAS_VERSION < (2, 2)
FREQ_RULES = {
    'D': 'D',
    'W': 'W',
    'M': 'M' if _LEGACY_FREQ_ALIASES else 'ME',
    'Q': 'Q' if _LEGACY_FREQ_ALIASES else 'QE',
    'Y': 'A' if _LEGACY_FREQ_ALIASES else 'YE',
}
# 계절 주기(연간 기간 수) — YoY 및 계절 성분 계산에 사용
PERIODS_PER_YEAR = {'D': 365, 'W': 52, 'M': 12, 'Q': 4, 'Y': 1}
AGG_FUNCS = ('sum', 'mean', 'count', 'max', 'min')


def _layout(fig, title, **extra):
    layout = dict(BASE_LAYOUT, title=title)
    layout.update(extra)
    fig.update_layout(**layout)
    return fig


def numeric_columns(df):
    """숫자로 해석 가능한 컬럼 (문자열로 저장된 숫자 포함)."""
    columns = []
    for column in df.columns:
        series = pd.to_numeric(df[column], errors='coerce')
        if series.notna().sum() >= max(3, int(len(df) * 0.5)):
            columns.append(column)
    return columns


def datetime_columns(df):
    """날짜로 해석 가능한 컬럼."""
    columns = []
    for column in df.columns:
        if pd.api.types.is_numeric_dtype(df[column]):
            continue
        parsed = _datetime_series(df[column])
        if parsed.notna().sum() >= max(3, int(len(df) * 0.5)):
            columns.append(column)
    return columns


def categorical_columns(df, max_unique=50):
    """그룹 기준으로 쓸 만한 범주형 컬럼."""
    return [
        column for column in df.columns
        if 1 < df[column].nunique(dropna=True) <= max_unique
    ]


def _numeric_series(df, column):
    return pd.to_numeric(df[column], errors='coerce')


def _datetime_series(series):
    """형식을 모르는 업로드 데이터라 추론 경고는 무시하고 파싱한다."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        return pd.to_datetime(series, errors='coerce')


# ---------------------------------------------------------------- 시계열


def resample_series(df, date_col, value_col, freq='M', agg='sum'):
    """날짜 컬럼 기준으로 리샘플링한 시계열을 반환한다."""
    if agg not in AGG_FUNCS:
        raise ValueError(f'지원하지 않는 집계 방식입니다: {agg}')
    if freq not in FREQ_RULES:
        raise ValueError(f'지원하지 않는 주기입니다: {freq}')

    frame = pd.DataFrame({
        'date': _datetime_series(df[date_col]),
        'value': _numeric_series(df, value_col),
    }).dropna()
    if frame.empty:
        return pd.Series(dtype='float64')

    series = frame.set_index('date')['value'].resample(FREQ_RULES[freq]).agg(agg)
    return series.dropna()


def _linear_forecast(series, horizon, freq):
    """선형 추세 + 계절 성분으로 향후 `horizon` 기간을 예측한다."""
    values = series.to_numpy(dtype='float64')
    x = np.arange(len(values), dtype='float64')
    slope, intercept = np.polyfit(x, values, 1)
    trend = slope * x + intercept
    residual = values - trend

    season_length = PERIODS_PER_YEAR.get(freq, 12)
    seasonal = np.zeros(season_length)
    if season_length > 1 and len(values) >= season_length * 2:
        for position in range(season_length):
            seasonal[position] = residual[position::season_length].mean()
        residual = residual - np.tile(seasonal, len(values) // season_length + 1)[:len(values)]

    future_x = np.arange(len(values), len(values) + horizon, dtype='float64')
    predicted = slope * future_x + intercept
    if season_length > 1 and len(values) >= season_length * 2:
        predicted = predicted + seasonal[[int(i) % season_length for i in future_x]]

    error = float(np.std(residual, ddof=1)) if len(residual) > 1 else 0.0
    index = pd.date_range(series.index[-1], periods=horizon + 1, freq=series.index.freq
                          or FREQ_RULES.get(freq, 'ME'))[1:]
    return pd.DataFrame({
        'value': predicted,
        'lower': predicted - 1.96 * error,
        'upper': predicted + 1.96 * error,
    }, index=index), slope


def timeseries_analysis(df, date_col, value_col, freq='M', agg='sum', window=3, horizon=3):
    """이동평균·MoM/YoY 증감·간단 예측을 한 번에 계산한다."""
    series = resample_series(df, date_col, value_col, freq=freq, agg=agg)
    if len(series) < 3:
        return None

    table = pd.DataFrame({'value': series})
    table['moving_avg'] = series.rolling(window=window, min_periods=1).mean()
    table['change_pct'] = series.pct_change() * 100
    lag = PERIODS_PER_YEAR.get(freq, 12)
    table['yoy_pct'] = series.pct_change(periods=lag) * 100 if len(series) > lag else np.nan

    forecast, slope = (None, 0.0)
    if horizon > 0 and len(series) >= 4:
        forecast, slope = _linear_forecast(series, horizon, freq)

    trend_fig = go.Figure()
    trend_fig.add_trace(go.Scatter(
        x=series.index, y=series.to_numpy(), mode='lines+markers', name='실측 / Actual',
        line=dict(color=QUALITATIVE_COLORS[0], width=3)
    ))
    trend_fig.add_trace(go.Scatter(
        x=table.index, y=table['moving_avg'].to_numpy(), mode='lines',
        name=f'{window}기간 이동평균 / MA({window})',
        line=dict(color=QUALITATIVE_COLORS[1], width=2, dash='dash')
    ))
    if forecast is not None:
        trend_fig.add_trace(go.Scatter(
            x=list(forecast.index) + list(forecast.index[::-1]),
            y=list(forecast['upper']) + list(forecast['lower'][::-1]),
            fill='toself', fillcolor='rgba(99,110,250,0.15)',
            line=dict(color='rgba(0,0,0,0)'), hoverinfo='skip',
            name='95% 구간 / 95% band'
        ))
        trend_fig.add_trace(go.Scatter(
            x=forecast.index, y=forecast['value'].to_numpy(), mode='lines+markers',
            name='예측 / Forecast',
            line=dict(color=QUALITATIVE_COLORS[2], width=3, dash='dot')
        ))

    change = table['change_pct'].dropna()
    change_fig = go.Figure([go.Bar(
        x=change.index, y=change.to_numpy(),
        marker_color=['#dc3545' if v < 0 else '#198754' for v in change],
        name='기간 대비 증감률 / Change %'
    )])

    last_value = float(series.iloc[-1])
    return {
        'table': table,
        'forecast': forecast,
        'figures': {
            'trend': _layout(trend_fig, '추세 · 이동평균 · 예측 / Trend, moving average & forecast'),
            'change': _layout(change_fig, '기간 대비 증감률 / Period-over-period change (%)',
                              yaxis_title='%'),
        },
        'stats': {
            'periods': int(len(series)),
            'last_value': last_value,
            'last_change_pct': float(change.iloc[-1]) if len(change) else None,
            'last_yoy_pct': (float(table['yoy_pct'].dropna().iloc[-1])
                             if table['yoy_pct'].notna().any() else None),
            'slope': float(slope),
            'forecast_next': float(forecast['value'].iloc[0]) if forecast is not None else None,
            'forecast_total': float(forecast['value'].sum()) if forecast is not None else None,
        },
    }


# ---------------------------------------------------------------- 이상치


def outlier_analysis(df, value_col, method='iqr', threshold=1.5, group_col=None, top_n=20):
    """IQR 또는 Z-score 기준으로 이상치를 탐지한다."""
    values = _numeric_series(df, value_col)
    valid = values.dropna()
    if len(valid) < 4:
        return None

    if method == 'zscore':
        mean = float(valid.mean())
        std = float(valid.std(ddof=1)) or 1.0
        score = (values - mean) / std
        mask = score.abs() > threshold
        lower, upper = mean - threshold * std, mean + threshold * std
    else:
        method = 'iqr'
        q1, q3 = float(valid.quantile(0.25)), float(valid.quantile(0.75))
        iqr = q3 - q1
        lower, upper = q1 - threshold * iqr, q3 + threshold * iqr
        score = (values - valid.median()) / (iqr or 1.0)
        mask = (values < lower) | (values > upper)

    mask = mask.fillna(False)
    flagged = df.loc[mask].copy()
    flagged['_value'] = values[mask]
    flagged['_score'] = score[mask]
    flagged = flagged.reindex(flagged['_score'].abs().sort_values(ascending=False).index)

    fig = go.Figure()
    normal = values[~mask]
    fig.add_trace(go.Scatter(
        x=normal.index, y=normal.to_numpy(), mode='markers', name='정상 / Normal',
        marker=dict(color=QUALITATIVE_COLORS[0], size=7, opacity=0.6)
    ))
    fig.add_trace(go.Scatter(
        x=values[mask].index, y=values[mask].to_numpy(), mode='markers',
        name='이상치 / Outlier',
        marker=dict(color='#dc3545', size=11, symbol='x')
    ))
    for bound, label in ((upper, '상한 / Upper'), (lower, '하한 / Lower')):
        fig.add_hline(y=bound, line_dash='dash', line_color='#adb5bd',
                      annotation_text=label, annotation_position='right')

    group_fig = None
    if group_col and group_col in df.columns:
        grouped = pd.DataFrame({'group': df[group_col], 'flag': mask})
        counts = grouped.groupby('group')['flag'].sum().sort_values(ascending=False)
        counts = counts[counts > 0]
        if not counts.empty:
            group_fig = _layout(go.Figure([go.Bar(
                x=counts.index.astype(str).tolist(), y=counts.to_numpy(),
                marker_color=QUALITATIVE_COLORS[:len(counts)]
            )]), f'{group_col}별 이상치 수 / Outliers by {group_col}')

    return {
        'method': method,
        'threshold': threshold,
        'bounds': (float(lower), float(upper)),
        'count': int(mask.sum()),
        'total': int(values.notna().sum()),
        'pct': float(mask.sum() / max(1, values.notna().sum()) * 100),
        'rows': flagged.head(top_n),
        'figures': {'scatter': _layout(fig, f'{value_col} 이상치 탐지 / Outlier detection',
                                       yaxis_title=value_col),
                    'by_group': group_fig},
    }


# ---------------------------------------------------------------- 상관 / 기여도


def correlation_analysis(df, columns=None, top_n=10):
    """숫자 컬럼 간 상관행렬과 상관이 큰 조합을 반환한다."""
    columns = columns or numeric_columns(df)
    if len(columns) < 2:
        return None

    numeric = pd.DataFrame({column: _numeric_series(df, column) for column in columns}).dropna()
    if len(numeric) < 3:
        return None

    matrix = numeric.corr()
    fig = go.Figure(go.Heatmap(
        z=matrix.to_numpy().round(3), x=matrix.columns.tolist(), y=matrix.columns.tolist(),
        colorscale='RdBu', zmid=0, zmin=-1, zmax=1,
        text=matrix.to_numpy().round(2), texttemplate='%{text}',
        colorbar=dict(title='r')
    ))

    pairs = []
    for i, first in enumerate(matrix.columns):
        for second in matrix.columns[i + 1:]:
            value = matrix.loc[first, second]
            if pd.notna(value):
                pairs.append((first, second, float(value)))
    pairs.sort(key=lambda item: abs(item[2]), reverse=True)

    return {
        'matrix': matrix,
        'pairs': pairs[:top_n],
        'sample_size': int(len(numeric)),
        'figures': {'heatmap': _layout(fig, '상관관계 히트맵 / Correlation heatmap', height=480)},
    }


def contribution_analysis(df, target_col, feature_cols=None):
    """표준화 회귀계수로 타깃 변수에 대한 변수별 기여도를 계산한다."""
    feature_cols = [
        column for column in (feature_cols or numeric_columns(df))
        if column != target_col
    ]
    if not feature_cols:
        return None

    data = pd.DataFrame({column: _numeric_series(df, column)
                         for column in [target_col] + feature_cols}).dropna()
    if len(data) <= len(feature_cols) + 1:
        return None

    target = data[target_col]
    features = data[feature_cols]
    std = features.std(ddof=0).replace(0, np.nan)
    standardized = ((features - features.mean()) / std).dropna(axis=1)
    if standardized.empty:
        return None

    target_std = target.std(ddof=0)
    if not target_std:
        return None
    y = ((target - target.mean()) / target_std).to_numpy()
    x = np.column_stack([standardized.to_numpy(), np.ones(len(standardized))])
    coefficients, *_ = np.linalg.lstsq(x, y, rcond=None)
    beta = pd.Series(coefficients[:-1], index=standardized.columns)

    predicted = x @ coefficients
    residual_ss = float(np.sum((y - predicted) ** 2))
    total_ss = float(np.sum((y - y.mean()) ** 2)) or 1.0
    r_squared = 1 - residual_ss / total_ss

    ordered = beta.reindex(beta.abs().sort_values(ascending=True).index)
    fig = go.Figure([go.Bar(
        x=ordered.to_numpy(), y=ordered.index.tolist(), orientation='h',
        marker_color=['#dc3545' if value < 0 else '#0d6efd' for value in ordered]
    )])

    return {
        'target': target_col,
        'coefficients': beta.sort_values(key=abs, ascending=False),
        'r_squared': float(r_squared),
        'sample_size': int(len(data)),
        'figures': {'contribution': _layout(
            fig, f'{target_col} 기여도 (표준화 회귀계수) / Standardized coefficients',
            xaxis_title='β'
        )},
    }
