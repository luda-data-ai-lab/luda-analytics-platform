"""차트 생성 공통 유틸 / Shared Plotly chart helpers."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

QUALITATIVE_COLORS = px.colors.qualitative.Plotly

# 템플릿 자동 분석 차트의 공통 레이아웃
BASE_LAYOUT = dict(
    height=380,
    margin=dict(l=60, r=40, t=60, b=60),
    font=dict(size=12, family="Arial, sans-serif"),
    title_font=dict(size=16, family="Arial, sans-serif"),
    hovermode='closest',
    plot_bgcolor='rgba(0,0,0,0)',
    paper_bgcolor='rgba(0,0,0,0)'
)

# 영문/한글 컬럼명 통일 매핑 (4개 템플릿 전체 포함)
COLUMN_MAP = {
    # 판매 데이터
    '날짜':      ['날짜', 'Date', 'date', 'DATE', 'Start_Date'],
    '매출액':    ['매출액', 'Revenue', 'revenue', 'Total_Sales', 'Sales'],
    '지역':      ['지역', 'Region', 'region'],
    '제품':      ['제품', 'Product', 'product'],
    '카테고리':  ['카테고리', 'Category', 'category'],
    '판매량':    ['판매량', 'Quantity', 'quantity', 'Units_Sold'],
    '비용':      ['비용', 'Cost', 'cost', 'Budget'],
    # 곡물 데이터
    '작물':      ['Crop_Type', 'Crop', 'crop_type'],
    '수확량':    ['Crop_Yield_kg', 'Yield', 'crop_yield'],
    '강수량':    ['Rainfall_mm', 'Rainfall', 'rainfall'],
    '온도':      ['Temperature_C', 'Temperature', 'temperature'],
    '비료':      ['Fertilizer_kg', 'Fertilizer', 'fertilizer'],
    '토양':      ['Soil_Type', 'Soil', 'soil_type'],
    '기후':      ['Climate', 'climate'],
    '관개':      ['Irrigation_hours', 'Irrigation', 'irrigation'],
    # 마케팅 데이터
    '채널':      ['Channel', 'channel', 'Media'],
    '노출':      ['Impressions', 'impressions'],
    '클릭':      ['Clicks', 'clicks'],
    '전환':      ['Conversions', 'conversions'],
    '예산':      ['Budget', 'budget'],
    '캠페인':    ['Campaign_Name', 'Campaign', 'campaign_name'],
    # 고객 데이터
    '세그먼트':  ['Segment', 'segment', 'Customer_Segment'],
    '나이':      ['Age', 'age'],
    '성별':      ['Gender', 'gender'],
    '소득':      ['Income', 'income'],
    '구매횟수':  ['Total_Purchases', 'total_purchases', 'Purchase_Count'],
    '구매금액':  ['Avg_Purchase_Value', 'avg_purchase_value', 'Avg_Order_Value'],
}


def base_layout():
    """공통 레이아웃 사본 반환"""
    return dict(BASE_LAYOUT)


def resolve_column(df, key):
    """한글 키에 대응하는 실제 컬럼명 반환 (없으면 None)"""
    for candidate in COLUMN_MAP.get(key, [key]):
        if candidate in df.columns:
            return candidate
    return None


def resolve_columns(df, *keys):
    """여러 키를 한 번에 해석 — resolve_column 반복 호출 대체"""
    return [resolve_column(df, key) for key in keys]


# ── 데이터 정리 ────────────────────────────────────────────────────
def to_numeric_column(df, column):
    """천단위 구분자/공백 제거 후 숫자형으로 변환"""
    df[column] = df[column].astype(str).str.replace(',', '').str.replace(' ', '')
    df[column] = pd.to_numeric(df[column], errors='coerce')
    return df[column]


def try_parse_date_column(df, column, threshold=0.8):
    """문자열 컬럼을 날짜로 변환 시도 — 성공률이 threshold를 넘으면 적용

    Returns: 날짜로 변환되었는지 여부
    """
    if df[column].dtype != 'object':
        return False
    sample_val = str(df[column].iloc[0])
    if not any(sep in sample_val for sep in ['-', '/', '.']):
        raise ValueError("No date separator found")
    parsed = pd.to_datetime(df[column], errors='coerce')
    if parsed.notna().sum() / len(parsed) <= threshold:
        raise ValueError("Not enough valid dates")
    df[column] = parsed
    return True


def add_month_column(df, date_col, month_col='_month'):
    """날짜 컬럼을 datetime으로 변환하고 월(YYYY-MM) 컬럼 추가"""
    df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
    df[month_col] = df[date_col].dt.to_period('M').astype(str)
    return month_col


def group_sum(df, group_col, value_cols, sort_by=None, ascending=True):
    """그룹별 합계 DataFrame (단일/복수 값 컬럼 모두 지원)"""
    grouped = df.groupby(group_col)[value_cols].sum().reset_index()
    if sort_by is not None:
        grouped = grouped.sort_values(sort_by, ascending=ascending)
    return grouped


def value_counts_frame(df, column, top=None, count_col='count'):
    """빈도수 DataFrame ([column, count]) 생성"""
    counts = df[column].value_counts()
    if top:
        counts = counts.head(top)
    counts = counts.reset_index()
    counts.columns = [column, count_col]
    return counts


# ── 차트 빌더 ─────────────────────────────────────────────────────
def _distribution_trace(kind, series, name=None, color=None, nbins=None):
    if kind == 'box':
        return go.Box(y=series, name=name, marker_color=color, boxpoints='outliers')
    if kind == 'violin':
        return go.Violin(y=series, name=name, marker_color=color,
                         box_visible=True, points='outliers', meanline_visible=True)
    if kind == 'histogram':
        return go.Histogram(x=series, name=name, nbinsx=nbins,
                            opacity=0.85, marker_color=color)
    raise ValueError(f"Unsupported distribution kind: {kind}")


def distribution_by_group(df, value_col, group_col=None, kind='box', title='',
                          layout=None, x_title=None, y_title=None, nbins=None,
                          barmode=None, showlegend=None):
    """그룹별 분포 차트 (box/violin/histogram)

    px.box / px.violin / px.histogram 의 color=categorical 버그 우회를 위해
    graph_objects 로 그룹별 트레이스를 직접 생성한다.
    """
    fig = go.Figure()
    groups = sorted(df[group_col].dropna().unique()) if group_col else [None]
    for i, group in enumerate(groups):
        subset = df[df[group_col] == group] if group is not None else df
        fig.add_trace(_distribution_trace(
            kind, subset[value_col].dropna(),
            name=str(group) if group is not None else None,
            color=QUALITATIVE_COLORS[i % len(QUALITATIVE_COLORS)] if group is not None else None,
            nbins=nbins
        ))

    kw = dict(title=title)
    if x_title:
        kw['xaxis_title'] = x_title
    if y_title:
        kw['yaxis_title'] = y_title
    if barmode and group_col:
        kw['barmode'] = barmode
    if showlegend is not None:
        kw['showlegend'] = showlegend
    if layout:
        kw.update(layout)
    fig.update_layout(**kw)
    return fig


def scatter_by_group(df, x_col, y_col, color_col=None, size_col=None,
                     size_max=15, title='', layout=None, x_label=None, y_label=None):
    """px.scatter color=categorical 버그 우회 — go.Scatter로 그룹별 트레이스 생성"""
    fig = go.Figure()
    groups = sorted(df[color_col].dropna().unique()) if color_col else [None]
    for i, grp in enumerate(groups):
        sub = df[df[color_col] == grp] if grp is not None else df
        x = sub[x_col].tolist()
        y = sub[y_col].tolist()
        if size_col:
            raw = sub[size_col].fillna(0).tolist()
            mx = max(raw) if max(raw) > 0 else 1
            szs = [max(4, int(v / mx * size_max)) for v in raw]
        else:
            szs = 9
        fig.add_trace(go.Scatter(
            x=x, y=y, mode='markers',
            name=str(grp) if grp is not None else '',
            marker=dict(color=QUALITATIVE_COLORS[i % len(QUALITATIVE_COLORS)],
                        size=szs, opacity=0.75)
        ))
    kw = dict(title=title)
    if x_label:
        kw['xaxis_title'] = x_label
    if y_label:
        kw['yaxis_title'] = y_label
    if layout:
        kw.update(layout)
    fig.update_layout(**kw)
    return fig


def simple_bar(data, x_col, y_col, title='', layout=None):
    """단일 시리즈 바 차트 (컬럼별 색상)"""
    fig = go.Figure([go.Bar(
        x=data[x_col].tolist(), y=data[y_col].tolist(),
        marker_color=QUALITATIVE_COLORS[:len(data)]
    )])
    fig.update_layout(title=title, **(layout or {}))
    return fig


def grouped_bar(x_values, series, title='', layout=None, x_title=None):
    """여러 시리즈를 나란히 비교하는 그룹 바 차트

    series: [(name, values, color), ...]
    """
    fig = go.Figure([
        go.Bar(x=list(x_values), y=list(values), name=name, marker_color=color)
        for name, values, color in series
    ])
    kw = dict(barmode='group', title=title)
    if x_title:
        kw['xaxis_title'] = x_title
    if layout:
        kw.update(layout)
    fig.update_layout(**kw)
    return fig


def line_trend(data, x_col, y_col, title='', layout=None, color=None,
               width=3, marker_size=9):
    """마커가 있는 추이 라인 차트"""
    fig = px.line(data, x=x_col, y=y_col, title=title, markers=True)
    line_style = dict(width=width)
    if color:
        line_style['color'] = color
    fig.update_traces(line=line_style, marker=dict(size=marker_size))
    fig.update_layout(**(layout or {}))
    return fig


def horizontal_bar(data, value_col, category_col, title='', layout=None,
                   color_scale='Blues', text_col=None, text_template=None,
                   text_auto=None):
    """연속형 색상 스케일을 사용한 수평 바 차트"""
    kwargs = dict(x=value_col, y=category_col, orientation='h', title=title,
                  color=value_col, color_continuous_scale=color_scale)
    if text_col:
        kwargs['text'] = text_col
    if text_auto:
        kwargs['text_auto'] = text_auto
    fig = px.bar(data, **kwargs)
    if text_template:
        fig.update_traces(texttemplate=text_template, textposition='outside')
    fig.update_layout(**(layout or {}), coloraxis_showscale=False)
    return fig


def pie_chart(data, names_col, values_col, title='', layout=None, hole=None,
              **px_kwargs):
    """비중 파이/도넛 차트 (레이블 = percent+label)"""
    if hole is not None:
        px_kwargs['hole'] = hole
    fig = px.pie(data, names=names_col, values=values_col, title=title, **px_kwargs)
    fig.update_layout(**(layout or {}))
    fig.update_traces(textposition='inside', textinfo='percent+label')
    return fig
