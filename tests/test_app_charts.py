"""app.py 차트 생성 함수 테스트 (_go_scatter, _go_bar_categorical, generate_template_charts)."""

import json

import pandas as pd
import plotly.graph_objects as go

import app as app_module


def _figure(chart_json):
    """차트 결과(JSON 문자열)를 dict로 파싱."""
    return json.loads(chart_json)


def test_go_scatter_single_trace_without_grouping():
    df = pd.DataFrame({'x': [1, 2, 3], 'y': [4, 5, 6]})

    fig = app_module._go_scatter(df, 'x', 'y', title='산점도', x_label='X', y_label='Y')

    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1
    assert fig.data[0].x == (1, 2, 3)
    assert fig.data[0].mode == 'markers'
    assert fig.layout.title.text == '산점도'
    assert fig.layout.xaxis.title.text == 'X'
    assert fig.layout.yaxis.title.text == 'Y'


def test_go_scatter_creates_trace_per_group_sorted():
    df = pd.DataFrame({
        'x': [1, 2, 3, 4],
        'y': [1, 2, 3, 4],
        'grp': ['B', 'A', 'B', None],
    })

    fig = app_module._go_scatter(df, 'x', 'y', color_col='grp')

    assert [trace.name for trace in fig.data] == ['A', 'B']
    assert fig.data[0].x == (2,)
    assert fig.data[1].x == (1, 3)


def test_go_scatter_scales_marker_sizes():
    df = pd.DataFrame({'x': [1, 2], 'y': [1, 2], 'size': [10, 0]})

    fig = app_module._go_scatter(df, 'x', 'y', size_col='size', size_max=20)

    assert fig.data[0].marker.size == (20, 4)


def test_go_scatter_uses_minimum_size_when_all_sizes_zero():
    df = pd.DataFrame({'x': [1, 2], 'y': [1, 2], 'size': [0, 0]})

    fig = app_module._go_scatter(df, 'x', 'y', size_col='size')

    assert fig.data[0].marker.size == (4, 4)


def test_go_scatter_applies_extra_layout():
    df = pd.DataFrame({'x': [1], 'y': [1]})

    fig = app_module._go_scatter(df, 'x', 'y', layout=dict(height=400))

    assert fig.layout.height == 400


def test_go_bar_categorical_vertical_groups():
    df = pd.DataFrame({
        'x': ['a', 'b', 'a'],
        'y': [1, 2, 3],
        'grp': ['G2', 'G1', 'G2'],
    })

    fig = app_module._go_bar_categorical(df, 'x', 'y', 'grp', title='막대')

    assert [trace.name for trace in fig.data] == ['G1', 'G2']
    assert fig.data[1].y == (1, 3)
    assert fig.layout.title.text == '막대'


def test_go_bar_categorical_horizontal_is_sorted_single_trace():
    df = pd.DataFrame({'label': ['a', 'b', 'c'], 'value': [3, 1, 2]})

    fig = app_module._go_bar_categorical(df, 'label', 'value', None, orientation='h')

    assert len(fig.data) == 1
    assert fig.data[0].orientation == 'h'
    assert fig.data[0].y == ('b', 'c', 'a')
    assert fig.data[0].x == (1, 2, 3)
    assert fig.data[0].showlegend is False


def test_generate_template_charts_sales(sales_df):
    charts = app_module.generate_template_charts(sales_df)

    assert charts
    assert all(isinstance(value, str) for value in charts.values())
    for chart_json in charts.values():
        figure = _figure(chart_json)
        assert 'data' in figure and 'layout' in figure


def test_generate_template_charts_crop(crop_df):
    charts = app_module.generate_template_charts(crop_df)

    assert charts
    for chart_json in charts.values():
        assert 'data' in _figure(chart_json)


def test_generate_template_charts_marketing(marketing_df):
    charts = app_module.generate_template_charts(marketing_df)

    assert charts
    for chart_json in charts.values():
        assert 'data' in _figure(chart_json)


def test_generate_template_charts_customer(customer_df):
    charts = app_module.generate_template_charts(customer_df)

    assert charts
    for chart_json in charts.values():
        assert 'data' in _figure(chart_json)


def test_generate_template_charts_generic_fallback():
    df = pd.DataFrame({'Foo': [1, 2, 3, 4], 'Bar': ['a', 'b', 'a', 'b']})

    charts = app_module.generate_template_charts(df)

    assert charts
    for chart_json in charts.values():
        assert 'data' in _figure(chart_json)


def test_generate_template_charts_returns_empty_on_error():
    df = pd.DataFrame({'Revenue': ['x', 'y'], 'Quantity': ['a', 'b'], 'Region': [1, 2]})

    charts = app_module.generate_template_charts(df)

    assert isinstance(charts, dict)
