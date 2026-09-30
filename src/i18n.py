"""한/영 이중 언어 메시지 유틸리티.

`app.py` 전반에서 반복되던 `flash(get_message('...', '...'), ...)` 쌍을
한 곳에 모아 문구 불일치를 막는다.
사용자에게 노출되는 문구에는 예외 상세를 포함하지 않는다 (서버 로그 전용).
"""

from flask import flash, has_request_context, session

# 여러 라우트에서 반복되는 문구 (한글, 영문)
MESSAGES = {
    'access_denied': ('접근 권한이 없습니다.', 'Access denied.'),
    'no_file_selected': ('파일이 선택되지 않았습니다.', 'No file selected.'),
    'invalid_file_format': ('허용되지 않는 파일 형식입니다.', 'Invalid file format.'),
    'save_failed': (
        '파일을 저장할 수 없습니다. 잠시 후 다시 시도해주세요.',
        'Could not save the file. Please try again later.',
    ),
    'process_failed': ('파일 처리 중 오류가 발생했습니다.', 'Error processing file.'),
    'data_uploaded': ('데이터가 성공적으로 업로드되었습니다!', 'Data uploaded successfully!'),
    'template_uploaded': ('템플릿이 성공적으로 업로드되었습니다!', 'Template uploaded successfully!'),
    'dataset_deleted': ('데이터셋이 삭제되었습니다.', 'Dataset deleted successfully.'),
    'no_data': ('데이터가 없습니다.', 'No data available.'),
}


def get_message(ko_msg, en_msg):
    """현재 세션 언어에 맞는 문구를 반환한다 (요청 밖/기본값은 영문)."""
    if not has_request_context():
        return en_msg
    return ko_msg if session.get('language') == 'ko' else en_msg


def msg(key):
    """`MESSAGES` 에 등록된 문구를 현재 언어로 반환한다."""
    ko_msg, en_msg = MESSAGES[key]
    return get_message(ko_msg, en_msg)


def flash_msg(key, category='info'):
    """`MESSAGES` 문구를 flash 한다."""
    flash(msg(key), category)
