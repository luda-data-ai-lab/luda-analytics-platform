import pytest

from src.demo_video import demo_video


@pytest.mark.parametrize('url', [
    'https://www.youtube.com/watch?v=abc123XYZ_-',
    'https://youtu.be/abc123XYZ_-',
    'https://www.youtube.com/embed/abc123XYZ_-',
    'https://www.youtube.com/shorts/abc123XYZ_-',
    'https://www.youtube-nocookie.com/embed/abc123XYZ_-',
    '  https://youtu.be/abc123XYZ_-  ',
])
def test_youtube_links_become_nocookie_embed(url):
    assert demo_video(url) == {
        'kind': 'youtube',
        'url': 'https://www.youtube-nocookie.com/embed/abc123XYZ_-',
    }


def test_https_mp4_is_played_directly():
    assert demo_video('https://cdn.example.com/demo.mp4') == {
        'kind': 'file',
        'url': 'https://cdn.example.com/demo.mp4',
    }


@pytest.mark.parametrize('url', [
    None,
    '',
    '   ',
    'http://www.youtube.com/watch?v=abc123XYZ_-',   # https 만 허용
    'https://evil.example.com/demo.exe',            # 알 수 없는 미디어
    'https://www.youtube.com/results?search_query=x',
    'javascript:alert(1)',
])
def test_unsupported_links_are_ignored(url):
    assert demo_video(url) is None
