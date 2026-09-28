"""템플릿 차트 생성 공용 유틸리티.

컬럼명 매핑, 공통 레이아웃, 그리고 4개 템플릿(판매·작물·마케팅·고객)
차트에서 반복되던 Plotly 그림 생성 패턴을 모았다.
px 의 categorical color 버그를 우회하는 go 기반 빌더도 여기에 있다.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

QUALITATIVE_COLORS = px.colors.qualitative.Plotly

# 템플릿 차트 공통 레이아웃
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


def resolve_column(df, key):
    """매핑 후보 중 DataFrame 에 실제로 존재하는 컬럼명을 반환한다."""
    for candidate in COLUMN_MAP.get(key, [key]):
        if candidate in df.columns:
            return candidate
    return None


def resolve_columns(df, *keys):
    """여러 키를 한 번에 해석한다."""
    return [resolve_column(df, key) for key in keys]


def group_sum(df, group_col, value_cols, sort_by=None, ascending=True):
    """그룹별 합계를 DataFrame 으로 반환한다."""
    grouped = df.groupby(group_col)[value_cols].sum().reset_index()
    if sort_by is not None:
        grouped = grouped.sort_values(sort_by, ascending=ascending)
    return grouped


def value_counts_frame(df, column, top=None, count_col='count'):
    """빈도수를 `[column, count]` 컬럼의 DataFrame 으로 반환한다."""
    counts = df[column].value_counts()
    if top:
        counts = counts.head(top)
    counts = counts.reset_index()
    counts.columns = [column, count_col]
    return counts


def add_month_column(df, date_col, month_col='_month'):
    """날짜 컬럼을 파싱해 `YYYY-MM` 문자열 컬럼을 추가한다."""
    df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
    df[month_col] = df[date_col].dt.to_period('M').astype(str)
    return month_col


def _apply_layout(fig, title, layout=None, **extra):
    kwargs = dict(title=title)
    kwargs.update({key: value for key, value in extra.items() if value is not None})
    if layout:
        kwargs.update(layout)
    fig.update_layout(**kwargs)
    return fig


def go_scatter(df, x_col, y_col, color_col=None, size_col=None,
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
    return _apply_layout(fig, title, layout, xaxis_title=x_label, yaxis_title=y_label)


def go_bar_categorical(df, x_col, y_col, color_col, title='', layout=None, orientation='v'):
    """px.bar color=categorical 버그 우회 — go.Bar로 그룹별 트레이스 생성"""
    fig = go.Figure()
    if orientation == 'h':
        data = df.sort_values(y_col)
        fig.add_trace(go.Bar(
            x=data[y_col].tolist(), y=data[x_col].tolist(),
            orientation='h',
            marker=dict(color=QUALITATIVE_COLORS[:len(data)]),
            showlegend=False
        ))
    else:
        for i, grp in enumerate(sorted(df[color_col].dropna().unique())):
            sub = df[df[color_col] == grp]
            fig.add_trace(go.Bar(
                x=sub[x_col].tolist(), y=sub[y_col].tolist(),
                name=str(grp),
                marker_color=QUALITATIVE_COLORS[i % len(QUALITATIVE_COLORS)]
            ))
    return _apply_layout(fig, title, layout)


def horizontal_bar(data, value_col, label_col, title, layout=None,
                   color_scale='Blues', text=None, texttemplate=None, text_auto=None):
    """값 크기에 따라 색이 변하는 수평 바 차트 (컬러바는 숨김)."""
    kwargs = {}
    if text is not None:
        kwargs['text'] = text
    if text_auto is not None:
        kwargs['text_auto'] = text_auto
    fig = px.bar(data, x=value_col, y=label_col, orientation='h', title=title,
                 color=value_col, color_continuous_scale=color_scale, **kwargs)
    if texttemplate is not None:
        fig.update_traces(texttemplate=texttemplate, textposition='outside')
    fig.update_layout(**(layout or {}), coloraxis_showscale=False)
    return fig


def simple_bar(data, x_col, y_col, title, layout=None):
    """단색 바 차트 (범주별 색상은 QUALITATIVE_COLORS 순서)."""
    fig = go.Figure([go.Bar(
        x=data[x_col].tolist(), y=data[y_col].tolist(),
        marker_color=QUALITATIVE_COLORS[:len(data)]
    )])
    return _apply_layout(fig, title, layout)


def grouped_bar(x_values, series, title, layout=None, xaxis_title=None):
    """`series` = [(이름, 값 리스트, 색상)] 형태의 그룹 바 차트."""
    fig = go.Figure([
        go.Bar(x=x_values, y=values, name=name, marker_color=color)
        for name, values, color in series
    ])
    return _apply_layout(fig, title, layout, barmode='group', xaxis_title=xaxis_title)


def line_trend(data, x_col, y_col, title, layout=None, color=None,
               width=3, marker_size=9):
    """마커가 있는 추이 라인 차트."""
    fig = px.line(data, x=x_col, y=y_col, title=title, markers=True)
    line = dict(width=width)
    if color:
        line['color'] = color
    fig.update_traces(line=line, marker=dict(size=marker_size))
    if layout:
        fig.update_layout(**layout)
    return fig


def pie_chart(data, names_col, values_col, title, layout=None, hole=0.4,
              color_sequence=None):
    """라벨/비율을 내부에 표시하는 (도넛) 파이 차트."""
    kwargs = {}
    if hole is not None:
        kwargs['hole'] = hole
    if color_sequence is not None:
        kwargs['color_discrete_sequence'] = color_sequence
    fig = px.pie(data, names=names_col, values=values_col, title=title, **kwargs)
    if layout:
        fig.update_layout(**layout)
    fig.update_traces(textposition='inside', textinfo='percent+label')
    return fig


def distribution_by_group(df, group_col, value_col, title, layout=None,
                          kind='box', yaxis_title=None, showlegend=True):
    """px.box/violin 의 color 버그 우회 — 그룹별 Box/Violin 트레이스 생성."""
    fig = go.Figure()
    groups = sorted(df[group_col].dropna().unique()) if group_col else []
    for i, grp in enumerate(groups):
        subset = df[df[group_col] == grp][value_col].dropna()
        color = QUALITATIVE_COLORS[i % len(QUALITATIVE_COLORS)]
        if kind == 'violin':
            fig.add_trace(go.Violin(y=subset, name=str(grp), marker_color=color,
                                    box_visible=True, points='outliers',
                                    meanline_visible=True))
        else:
            fig.add_trace(go.Box(y=subset, name=str(grp), marker_color=color,
                                 boxpoints='outliers'))
    return _apply_layout(fig, title, layout, yaxis_title=yaxis_title,
                         showlegend=showlegend)


def histogram_by_group(df, value_col, group_col, title, layout=None,
                       nbins=15, xaxis_title=None):
    """px.histogram 의 color 버그 우회 — 그룹별 누적 히스토그램 생성."""
    fig = go.Figure()
    if group_col:
        for i, grp in enumerate(sorted(df[group_col].dropna().unique())):
            subset = df[df[group_col] == grp][value_col].dropna()
            fig.add_trace(go.Histogram(
                x=subset, name=str(grp), nbinsx=nbins, opacity=0.85,
                marker_color=QUALITATIVE_COLORS[i % len(QUALITATIVE_COLORS)]
            ))
        fig.update_layout(barmode='stack')
    else:
        fig.add_trace(go.Histogram(x=df[value_col].dropna(), nbinsx=nbins, opacity=0.85))
    return _apply_layout(fig, title, layout, xaxis_title=xaxis_title)
