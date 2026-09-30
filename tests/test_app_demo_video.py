"""홈·매뉴얼 화면의 데모 영상 노출 (DEMO_VIDEO_URL 설정 여부)."""

import pytest

EMBED_URL = 'https://www.youtube-nocookie.com/embed/abc123XYZ_-'


@pytest.fixture
def client(flask_app, db_session):
    with flask_app.test_client() as test_client:
        yield test_client


@pytest.fixture
def demo_configured(flask_app):
    previous = flask_app.config['DEMO_VIDEO_URL']
    flask_app.config['DEMO_VIDEO_URL'] = 'https://youtu.be/abc123XYZ_-'
    yield
    flask_app.config['DEMO_VIDEO_URL'] = previous


@pytest.mark.parametrize('path', ['/', '/manual'])
def test_demo_video_hidden_when_url_unset(client, flask_app, path):
    flask_app.config['DEMO_VIDEO_URL'] = ''

    body = client.get(path).get_data(as_text=True)

    assert 'youtube-nocookie.com' not in body


@pytest.mark.parametrize('path', ['/', '/manual'])
def test_demo_video_embedded_when_url_set(client, demo_configured, path):
    body = client.get(path).get_data(as_text=True)

    assert EMBED_URL in body
    assert '<iframe' in body


def test_csp_allows_the_youtube_embed_frame(client):
    csp = client.get('/').headers['Content-Security-Policy']

    assert 'frame-src' in csp
    assert 'https://www.youtube-nocookie.com' in csp
