"""app.py 라우트 테스트 (인증, 대시보드, 업로드, 차트 API, 삭제)."""

import io
import json
import os

import flask
import pytest

import app as app_module
from models import DataRecord, Dataset, User


@pytest.fixture
def client(flask_app, db_session, tmp_path):
    flask_app.config['UPLOAD_FOLDER'] = str(tmp_path)
    with flask_app.test_client() as test_client:
        yield test_client


@pytest.fixture
def user(db_session):
    user = User(email='route@example.com', name='라우트', company='LUDA')
    user.set_password('pw1234')
    db_session.session.add(user)
    db_session.session.commit()
    return user


def _login(client, email='route@example.com', password='pw1234'):
    return client.post('/login', data={'email': email, 'password': password}, follow_redirects=False)


def _make_dataset(db, user, name='데이터셋', rows=None):
    rows = rows or [{'Date': '2024-01-01', 'Revenue': 100}, {'Date': '2024-02-01', 'Revenue': 200}]
    dataset = Dataset(
        name=name, filename='f.csv', file_path='/tmp/does-not-exist.csv',
        user_id=user.id, columns=list(rows[0].keys()), row_count=len(rows),
        column_count=len(rows[0]),
    )
    db.session.add(dataset)
    db.session.flush()
    for row in rows:
        db.session.add(DataRecord(dataset_id=dataset.id, data=row))
    db.session.commit()
    return dataset


def test_index_renders_for_anonymous_user(client):
    response = client.get('/')
    assert response.status_code == 200


def test_index_redirects_authenticated_user_to_dashboard(client, user):
    _login(client)
    response = client.get('/')
    assert response.status_code == 302
    assert '/dashboard' in response.headers['Location']


def test_register_creates_user(client, db_session):
    response = client.post('/register', data={
        'email': 'new@example.com', 'password': 'password123', 'name': '신규',
        'company': 'LUDA',
    })

    assert response.status_code == 302
    assert '/login' in response.headers['Location']
    created = User.query.filter_by(email='new@example.com').one()
    assert created.check_password('password123')
    assert created.company == 'LUDA'


def test_register_rejects_short_password(client, db_session):
    response = client.post('/register', data={
        'email': 'short@example.com', 'password': 'pw', 'name': '짧은비밀번호',
    })

    assert response.status_code == 302
    assert '/register' in response.headers['Location']
    assert User.query.filter_by(email='short@example.com').count() == 0


def test_register_rejects_duplicate_email(client, user):
    response = client.post('/register', data={
        'email': user.email, 'password': 'pw', 'name': '중복',
    }, follow_redirects=True)

    assert response.status_code == 200
    assert User.query.filter_by(email=user.email).count() == 1


def test_register_get_renders_form(client):
    assert client.get('/register').status_code == 200


def test_register_redirects_logged_in_user(client, user):
    _login(client)
    response = client.get('/register')
    assert '/dashboard' in response.headers['Location']


def test_login_with_valid_credentials(client, user):
    response = _login(client)

    assert response.status_code == 302
    assert '/dashboard' in response.headers['Location']


def test_login_honours_next_parameter(client, user):
    response = client.post('/login?next=/upload', data={
        'email': user.email, 'password': 'pw1234',
    })

    assert response.headers['Location'] == '/upload'


def test_login_with_invalid_password_rerenders_form(client, user):
    response = client.post('/login', data={'email': user.email, 'password': 'wrong'})

    assert response.status_code == 200


def test_login_get_renders_form(client):
    assert client.get('/login').status_code == 200


def test_logout_requires_login_then_clears_session(client, user):
    assert client.get('/logout').status_code == 302  # 로그인 페이지로 리다이렉트

    _login(client)
    response = client.get('/logout')
    assert '/' in response.headers['Location']
    assert client.get('/dashboard').status_code == 302


def test_dashboard_lists_own_datasets(client, user, db_session):
    _make_dataset(db_session, user, name='내 데이터')
    _login(client)

    response = client.get('/dashboard')

    assert response.status_code == 200
    assert '내 데이터' in response.get_data(as_text=True)


def test_dashboard_company_view_includes_colleague_datasets(client, user, db_session):
    colleague = User(email='mate@example.com', name='동료', company='LUDA')
    colleague.set_password('pw')
    db_session.session.add(colleague)
    db_session.session.commit()
    _make_dataset(db_session, colleague, name='동료 데이터')
    _login(client)

    response = client.get('/dashboard?view=company')

    assert '동료 데이터' in response.get_data(as_text=True)


def test_dashboard_falls_back_to_my_view_for_unknown_view(client, user, db_session):
    _make_dataset(db_session, user, name='내 데이터')
    _login(client)

    response = client.get('/dashboard?view=unknown')

    assert response.status_code == 200
    assert '내 데이터' in response.get_data(as_text=True)


def test_upload_csv_creates_dataset_and_records(client, user, db_session):
    _login(client)
    csv_bytes = b'Date,Revenue\n2024-01-01,100\n2024-02-01,200\n'

    response = client.post('/upload', data={
        'file': (io.BytesIO(csv_bytes), 'sales.csv'),
        'name': '업로드 데이터',
        'description': '설명',
    }, content_type='multipart/form-data')

    dataset = Dataset.query.filter_by(name='업로드 데이터').one()
    assert response.status_code == 302
    assert f'/dataset/{dataset.id}' in response.headers['Location']
    assert dataset.row_count == 2
    assert dataset.columns == ['Date', 'Revenue']
    assert DataRecord.query.filter_by(dataset_id=dataset.id).count() == 2


def test_upload_rejects_disallowed_extension(client, user, db_session):
    _login(client)

    response = client.post('/upload', data={
        'file': (io.BytesIO(b'nope'), 'notes.txt'), 'name': 'x',
    }, content_type='multipart/form-data')

    assert response.status_code == 200
    assert Dataset.query.count() == 0


def test_upload_rejects_empty_filename(client, user, db_session):
    _login(client)

    response = client.post('/upload', data={
        'file': (io.BytesIO(b''), ''), 'name': 'x',
    }, content_type='multipart/form-data')

    assert response.status_code == 302
    assert Dataset.query.count() == 0


def test_upload_without_file_field_redirects(client, user, db_session):
    _login(client)

    response = client.post('/upload', data={'name': 'x'})

    assert response.status_code == 302
    assert Dataset.query.count() == 0


def test_upload_rolls_back_on_unparsable_file(client, user, db_session, tmp_path):
    _login(client)

    response = client.post('/upload', data={
        'file': (io.BytesIO(b'\x00\x01\x02'), 'broken.xlsx'), 'name': '깨진 파일',
    }, content_type='multipart/form-data')

    assert response.status_code == 302
    assert '/upload' in response.headers['Location']
    assert Dataset.query.count() == 0
    assert os.listdir(tmp_path) == []  # 실패한 업로드 파일은 삭제된다


def test_upload_get_renders_form(client, user):
    _login(client)
    assert client.get('/upload').status_code == 200


def test_view_dataset_renders_records(client, user, db_session):
    dataset = _make_dataset(db_session, user)
    _login(client)

    response = client.get(f'/dataset/{dataset.id}')

    assert response.status_code == 200
    assert 'Revenue' in response.get_data(as_text=True)


def test_view_dataset_denies_other_users(client, user, db_session):
    other = User(email='other@example.com', name='타인')
    other.set_password('pw')
    db_session.session.add(other)
    db_session.session.commit()
    dataset = _make_dataset(db_session, other)
    _login(client)

    response = client.get(f'/dataset/{dataset.id}')

    assert response.status_code == 302
    assert '/dashboard' in response.headers['Location']


def test_view_dataset_returns_404_for_missing_dataset(client, user):
    _login(client)
    assert client.get('/dataset/9999').status_code == 404


def test_visualize_page_lists_columns(client, user, db_session):
    dataset = _make_dataset(db_session, user)
    _login(client)

    response = client.get(f'/visualize/{dataset.id}')

    assert response.status_code == 200
    assert 'Revenue' in response.get_data(as_text=True)


def test_visualize_denies_other_users(client, user, db_session):
    other = User(email='other2@example.com', name='타인')
    other.set_password('pw')
    db_session.session.add(other)
    db_session.session.commit()
    dataset = _make_dataset(db_session, other)
    _login(client)

    assert client.get(f'/visualize/{dataset.id}').status_code == 302


def test_generate_chart_returns_plotly_payload(client, user, db_session):
    dataset = _make_dataset(db_session, user)
    _login(client)

    response = client.post('/api/generate_chart', json={
        'dataset_id': dataset.id, 'chart_type': 'bar',
        'x_column': 'Date', 'y_column': 'Revenue',
    })

    assert response.status_code == 200
    payload = response.get_json()
    assert 'chart' in payload
    assert 'data' in json.loads(payload['chart'])


def test_generate_chart_rejects_unknown_column(client, user, db_session):
    dataset = _make_dataset(db_session, user)
    _login(client)

    response = client.post('/api/generate_chart', json={
        'dataset_id': dataset.id, 'chart_type': 'bar',
        'x_column': 'Nope', 'y_column': 'Revenue',
    })

    assert response.status_code == 400
    assert 'error' in response.get_json()


def test_generate_chart_denies_other_users(client, user, db_session):
    other = User(email='other3@example.com', name='타인')
    other.set_password('pw')
    db_session.session.add(other)
    db_session.session.commit()
    dataset = _make_dataset(db_session, other)
    _login(client)

    response = client.post('/api/generate_chart', json={
        'dataset_id': dataset.id, 'chart_type': 'bar',
        'x_column': 'Date', 'y_column': 'Revenue',
    })

    assert response.status_code == 403


def test_generate_chart_errors_without_records(client, user, db_session):
    dataset = Dataset(name='빈 데이터', filename='f.csv', file_path='/tmp/f.csv', user_id=user.id)
    db_session.session.add(dataset)
    db_session.session.commit()
    _login(client)

    response = client.post('/api/generate_chart', json={
        'dataset_id': dataset.id, 'chart_type': 'bar', 'x_column': 'Date',
    })

    assert response.status_code == 400


def test_delete_dataset_removes_rows_and_file(client, user, db_session, tmp_path):
    file_path = tmp_path / 'stored.csv'
    file_path.write_text('Date,Revenue\n2024-01-01,100\n')
    dataset = _make_dataset(db_session, user)
    dataset.file_path = str(file_path)
    db_session.session.commit()
    _login(client)

    response = client.post(f'/dataset/{dataset.id}/delete')

    assert response.status_code == 302
    assert Dataset.query.count() == 0
    assert DataRecord.query.count() == 0
    assert not file_path.exists()


def test_delete_dataset_denies_other_users(client, user, db_session):
    other = User(email='other4@example.com', name='타인')
    other.set_password('pw')
    db_session.session.add(other)
    db_session.session.commit()
    dataset = _make_dataset(db_session, other)
    _login(client)

    client.post(f'/dataset/{dataset.id}/delete')

    assert Dataset.query.count() == 1


def test_set_language_route_switches_language(client):
    response = client.get('/set_language/en')

    assert response.status_code == 302
    with client.session_transaction() as sess:
        assert sess['language'] == 'en'


def test_static_pages_require_login(client):
    for path in ('/dashboard', '/upload', '/examples', '/template_analysis', '/ocr/scan'):
        assert client.get(path).status_code == 302


def test_examples_and_template_pages_render(client, user):
    _login(client)

    for path in ('/examples', '/template_analysis', '/ocr/scan', '/template'):
        assert client.get(path).status_code == 200


@pytest.mark.parametrize('template_type', list(app_module.TEMPLATES))
def test_example_view_renders_each_template(client, user, template_type):
    _login(client)

    response = client.get(f'/example/{template_type}')

    assert response.status_code == 200


def test_example_view_rejects_unknown_template(client, user):
    _login(client)

    response = client.get('/example/unknown')

    assert response.status_code == 302
    assert '/examples' in response.headers['Location']


def test_download_template_serves_file(client, user):
    _login(client)
    template_type = next(iter(app_module.TEMPLATES))

    response = client.get(f'/download_template/{template_type}')

    assert response.status_code == 200
    assert 'attachment' in response.headers['Content-Disposition']


def test_download_template_rejects_unknown_template(client, user):
    _login(client)

    response = client.get('/download_template/unknown')

    assert response.status_code == 302
    assert '/template_analysis' in response.headers['Location']


def test_crop_example_renders(client, user):
    # /crop_example의 px.scatter(trendline="ols")는 statsmodels가 필요하다
    pytest.importorskip('statsmodels')
    _login(client)

    assert client.get('/crop_example').status_code == 200


def _timeseries_rows(count=18):
    return [
        {'Date': f'2023-{month % 12 + 1:02d}-01', 'Revenue': 100 + 10 * month,
         'Cost': 50 + 4 * month, 'Region': '서울' if month % 2 else '부산'}
        for month in range(count)
    ]


def test_advanced_analytics_renders_timeseries_tab(client, user, db_session):
    dataset = _make_dataset(db_session, user, rows=_timeseries_rows())
    _login(client)

    response = client.get(f'/analytics/{dataset.id}?tab=timeseries&date_col=Date&value_col=Revenue')

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'chart_trend' in body and 'chart_change' in body


def test_advanced_analytics_renders_outlier_and_correlation_tabs(client, user, db_session):
    dataset = _make_dataset(db_session, user, rows=_timeseries_rows())
    _login(client)

    outlier = client.get(
        f'/analytics/{dataset.id}?tab=outlier&value_col=Revenue&method=zscore&threshold=2'
    )
    correlation = client.get(f'/analytics/{dataset.id}?tab=correlation&target_col=Revenue')

    assert 'chart_scatter' in outlier.get_data(as_text=True)
    assert 'chart_heatmap' in correlation.get_data(as_text=True)


def test_advanced_analytics_falls_back_for_invalid_params(client, user, db_session):
    dataset = _make_dataset(db_session, user, rows=_timeseries_rows())
    _login(client)

    response = client.get(
        f'/analytics/{dataset.id}?tab=unknown&value_col=없는컬럼&window=999&threshold=abc'
    )

    assert response.status_code == 200


def test_advanced_analytics_denies_other_users(client, user, db_session):
    other = User(email='analytics-other@example.com', name='타인')
    other.set_password('pw')
    db_session.session.add(other)
    db_session.session.commit()
    dataset = _make_dataset(db_session, other, rows=_timeseries_rows())
    _login(client)

    response = client.get(f'/analytics/{dataset.id}')

    assert response.status_code == 302
    assert '/dashboard' in response.headers['Location']


def test_advanced_analytics_requires_login(client, user, db_session):
    dataset = _make_dataset(db_session, user)

    response = client.get(f'/analytics/{dataset.id}')

    assert response.status_code == 302
    assert '/login' in response.headers['Location']


def _segment_rows():
    """고객 4명 × 월별 거래 (RFM/코호트/파레토/AB 탭 공용)."""
    rows = []
    for index, customer in enumerate(['C1', 'C2', 'C3', 'C4']):
        for month in range(1, 4 + index):
            rows.append({
                'Customer': customer,
                'Date': f'2024-{month:02d}-05',
                'Revenue': 100 * (index + 1),
                'Category': f'Cat{index % 2}',
                'Variant': 'A' if index % 2 else 'B',
            })
    return rows


def test_advanced_analytics_renders_rfm_and_pareto_tabs(client, user, db_session):
    dataset = _make_dataset(db_session, user, rows=_segment_rows())
    _login(client)

    rfm = client.get(f'/analytics/{dataset.id}'
                     '?tab=rfm&customer_col=Customer&date_col=Date&value_col=Revenue')
    pareto = client.get(f'/analytics/{dataset.id}'
                        '?tab=pareto&category_col=Category&value_col=Revenue')

    assert 'chart_rfm_segments' in rfm.get_data(as_text=True)
    assert 'chart_pareto' in pareto.get_data(as_text=True)


def test_advanced_analytics_renders_cohort_and_abtest_tabs(client, user, db_session):
    dataset = _make_dataset(db_session, user, rows=_segment_rows())
    _login(client)

    cohort = client.get(f'/analytics/{dataset.id}'
                        '?tab=cohort&customer_col=Customer&date_col=Date&cohort_freq=M')
    abtest = client.get(f'/analytics/{dataset.id}'
                        '?tab=abtest&group_col=Variant&value_col=Revenue&metric=mean')

    assert 'chart_cohort' in cohort.get_data(as_text=True)
    assert 'chart_ab_test' in abtest.get_data(as_text=True)


def test_advanced_analytics_clamps_cohort_periods(client, user, db_session):
    dataset = _make_dataset(db_session, user, rows=_segment_rows())
    _login(client)

    response = client.get(f'/analytics/{dataset.id}'
                          '?tab=cohort&customer_col=Customer&date_col=Date'
                          '&cohort_freq=BOGUS&periods=9999')

    assert response.status_code == 200
    assert 'chart_cohort' in response.get_data(as_text=True)


def test_advanced_analytics_shows_tab_guide_in_both_languages(client, user, db_session):
    dataset = _make_dataset(db_session, user, rows=_segment_rows())
    _login(client)

    client.get('/set_language/ko')
    korean = client.get(f'/analytics/{dataset.id}'
                        '?tab=rfm&customer_col=Customer&date_col=Date&value_col=Revenue')
    client.get('/set_language/en')
    english = client.get(f'/analytics/{dataset.id}'
                         '?tab=rfm&customer_col=Customer&date_col=Date&value_col=Revenue')

    korean_body = korean.get_data(as_text=True)
    english_body = english.get_data(as_text=True)
    assert 'RFM 세그먼트' in korean_body and '필요한 컬럼' in korean_body
    assert 'RFM segments' in english_body and 'Columns needed' in english_body
    assert '/manual#segment' in korean_body


def test_analytics_guide_covers_every_tab(client, user, db_session):
    dataset = _make_dataset(db_session, user, rows=_segment_rows())
    _login(client)

    for tab in app_module.ANALYTICS_TABS:
        response = client.get(f'/analytics/{dataset.id}?tab={tab}')

        assert response.status_code == 200
        guide = app_module.ANALYTICS_TAB_GUIDE[tab]
        assert guide['ko'][1] in response.get_data(as_text=True)


def test_analytics_report_includes_tab_guide(client, user, db_session):
    dataset = _make_dataset(db_session, user, rows=_segment_rows())
    _login(client)

    response = client.get(f'/analytics/{dataset.id}/report'
                          '?tab=pareto&category_col=Category&value_col=Revenue')

    assert app_module.ANALYTICS_TAB_GUIDE['pareto']['ko'][3] in response.get_data(as_text=True)


def test_analytics_export_returns_excel_file(client, user, db_session):
    dataset = _make_dataset(db_session, user, rows=_segment_rows())
    _login(client)

    response = client.get(f'/analytics/{dataset.id}/export'
                          '?tab=pareto&category_col=Category&value_col=Revenue')

    assert response.status_code == 200
    assert 'attachment' in response.headers['Content-Disposition']
    assert response.headers['Content-Type'].startswith(
        'application/vnd.openxmlformats-officedocument.spreadsheetml')
    assert response.data[:2] == b'PK'


def test_analytics_report_page_renders_charts(client, user, db_session):
    dataset = _make_dataset(db_session, user, rows=_segment_rows())
    _login(client)

    response = client.get(f'/analytics/{dataset.id}/report'
                          '?tab=pareto&category_col=Category&value_col=Revenue')

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'chart_pareto' in body and 'window.print()' in body


def test_analytics_export_and_report_deny_other_users(client, user, db_session):
    other = User(email='export-other@example.com', name='타인')
    other.set_password('password123')
    db_session.session.add(other)
    db_session.session.commit()
    dataset = _make_dataset(db_session, other, rows=_segment_rows())
    _login(client)

    export = client.get(f'/analytics/{dataset.id}/export')
    report = client.get(f'/analytics/{dataset.id}/report')

    assert export.status_code == 302 and '/dashboard' in export.headers['Location']
    assert report.status_code == 302 and '/dashboard' in report.headers['Location']


def test_analytics_export_requires_login(client, user, db_session):
    dataset = _make_dataset(db_session, user, rows=_segment_rows())

    response = client.get(f'/analytics/{dataset.id}/export')

    assert response.status_code == 302
    assert '/login' in response.headers['Location']


def test_analytics_export_redirects_when_no_result(client, user, db_session):
    dataset = _make_dataset(db_session, user, rows=[
        {'Customer': 'C1', 'Date': '2024-01-01', 'Revenue': 10},
        {'Customer': 'C1', 'Date': '2024-02-01', 'Revenue': 20},
    ])
    _login(client)

    response = client.get(f'/analytics/{dataset.id}/export'
                          '?tab=rfm&customer_col=Customer&date_col=Date&value_col=Revenue'
                          '&dataset_id=999')

    assert response.status_code == 302
    assert f'/analytics/{dataset.id}?' in response.headers['Location']


def test_stat_cards_use_localized_labels_and_fixed_precision():
    stats = {
        'test': "Welch's t-test",
        'p_value': 1.0,
        'difference': 1234.5,
        'lift_pct': -12.34,
        'significant': False,
        'best_cohort_pct': None,
    }

    with app_module.app.test_request_context('/'):
        cards = app_module._stat_cards(stats)

    assert cards == [
        {'label': 'Test', 'value': "Welch's t-test"},
        {'label': 'p-value', 'value': '1.0000'},
        {'label': 'Difference', 'value': '1,234.50'},
        {'label': 'Lift', 'value': '-12.3%'},
        {'label': 'Significance', 'value': 'Not significant'},
    ]

    with app_module.app.test_request_context('/'):
        flask.session['language'] = 'ko'
        korean = app_module._stat_cards({'p_value': 4.5648935e-05, 'significant': True})

    assert korean == [
        {'label': 'p 값', 'value': '4.56e-05'},
        {'label': '통계적 유의성', 'value': '유의함'},
    ]


def test_every_tab_metric_has_a_label(client, user, db_session):
    dataset = _make_dataset(db_session, user, rows=_segment_rows())
    _login(client)
    queries = {
        'timeseries': 'date_col=Date&value_col=Revenue',
        'outlier': 'value_col=Revenue',
        'correlation': 'target_col=Revenue',
        'rfm': 'customer_col=Customer&date_col=Date&value_col=Revenue',
        'pareto': 'category_col=Category&value_col=Revenue',
        'cohort': 'customer_col=Customer&date_col=Date',
        'abtest': 'group_col=Variant&value_col=Revenue',
    }

    for tab, query in queries.items():
        response = client.get(f'/analytics/{dataset.id}?tab={tab}&{query}')

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        for key in app_module.ANALYTICS_STAT_LABELS:
            assert key.replace('_', ' ').upper() not in body
