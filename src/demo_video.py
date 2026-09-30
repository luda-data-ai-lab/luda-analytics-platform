"""데모 영상 링크를 안전한 임베드 URL 로 바꾼다 (YouTube / 직접 mp4)."""

from urllib.parse import parse_qs, urlparse

# 개인정보 보호 모드 도메인 (쿠키를 덜 남긴다)
YOUTUBE_EMBED_BASE = 'https://www.youtube-nocookie.com/embed/'
YOUTUBE_HOSTS = {
    'youtube.com', 'www.youtube.com', 'm.youtube.com',
    'youtube-nocookie.com', 'www.youtube-nocookie.com',
}
SHORT_HOSTS = {'youtu.be', 'www.youtu.be'}
VIDEO_SUFFIXES = ('.mp4', '.webm', '.ogg')


def _youtube_video_id(parsed):
    if parsed.hostname in SHORT_HOSTS:
        return parsed.path.lstrip('/').split('/')[0]
    if parsed.hostname not in YOUTUBE_HOSTS:
        return None
    if parsed.path == '/watch':
        return (parse_qs(parsed.query).get('v') or [''])[0]
    for prefix in ('/embed/', '/shorts/', '/live/', '/v/'):
        if parsed.path.startswith(prefix):
            return parsed.path[len(prefix):].split('/')[0]
    return None


def demo_video(url):
    """설정된 링크를 템플릿이 바로 쓸 수 있는 형태로 정규화한다.

    반환: {'kind': 'youtube'|'file', 'url': <임베드/재생 URL>} 또는 None.
    지원하지 않는 링크(http, 알 수 없는 호스트 등)는 None 이라 화면에 아무것도 나오지 않는다.
    """
    if not url:
        return None
    parsed = urlparse(url.strip())
    if parsed.scheme != 'https':
        return None

    video_id = _youtube_video_id(parsed)
    if video_id:
        return {'kind': 'youtube', 'url': YOUTUBE_EMBED_BASE + video_id}
    if parsed.path.lower().endswith(VIDEO_SUFFIXES):
        return {'kind': 'file', 'url': parsed.geturl()}
    return None
