"""다국어 메시지 공통 유틸 / Shared bilingual message helpers."""

from flask import flash, session

# 라우트 전반에서 반복 사용되는 한/영 메시지 쌍
MESSAGES = {
    'access_denied': ('접근 권한이 없습니다.', 'Access denied.'),
    'no_file_selected': ('파일이 선택되지 않았습니다.', 'No file selected.'),
    'no_file_uploaded': ('파일이 없습니다.', 'No file uploaded.'),
    'invalid_file_format': ('허용되지 않는 파일 형식입니다.', 'Invalid file format.'),
    'invalid_ocr_format': (
        '지원하지 않는 파일 형식입니다. (PNG, JPG, PDF만 가능)',
        'Unsupported file format. (PNG, JPG, PDF only)',
    ),
    'csv_only': ('CSV 파일만 업로드 가능합니다.', 'Only CSV files allowed.'),
    'upload_error': ('파일 업로드 중 오류가 발생했습니다.', 'File upload error.'),
    'no_extracted_data': ('추출된 데이터가 없습니다.', 'No extracted data.'),
    'required_fields': ('필수 항목을 입력해주세요.', 'Please fill in required fields.'),
    'data_saved': ('데이터가 성공적으로 저장되었습니다!', 'Data saved successfully!'),
    'data_uploaded': ('데이터가 성공적으로 업로드되었습니다!', 'Data uploaded successfully!'),
    'file_uploaded': ('파일이 성공적으로 업로드되었습니다.', 'File uploaded successfully.'),
    'template_uploaded': ('템플릿이 성공적으로 업로드되었습니다!', 'Template uploaded successfully!'),
    'template_not_found': ('존재하지 않는 템플릿입니다.', 'Template not found.'),
    'template_type_required': ('템플릿 유형을 선택하세요.', 'Select template type.'),
    'invalid_template_type': ('잘못된 템플릿 유형입니다.', 'Invalid template type.'),
    'sample_not_found': ('샘플 파일을 찾을 수 없습니다.', 'Sample file not found.'),
    'template_download_error': (
        '템플릿 다운로드 중 오류가 발생했습니다.', 'Error downloading template.'
    ),
    'dataset_deleted': ('데이터셋이 삭제되었습니다.', 'Dataset deleted successfully.'),
    'email_taken': ('이미 등록된 이메일입니다.', 'Email already registered.'),
    'registered': ('회원가입이 완료되었습니다!', 'Registration successful!'),
    'logged_in': ('로그인 되었습니다.', 'Successfully logged in.'),
    'logged_out': ('로그아웃 되었습니다.', 'Successfully logged out.'),
    'invalid_credentials': (
        '이메일 또는 비밀번호가 올바르지 않습니다.', 'Invalid email or password.'
    ),
    'no_data': ('데이터가 없습니다.', 'No data available.'),
    'no_valid_data': (
        '유효한 데이터가 없습니다. 숫자 데이터를 포함한 컬럼을 선택하세요.',
        'No valid data. Please select columns with numeric data.',
    ),
    'unsupported_chart': ('지원하지 않는 차트 유형입니다.', 'Unsupported chart type.'),
    # {value} / {error} 플레이스홀더를 포함한 메시지
    'column_not_found': ('컬럼을 찾을 수 없습니다: {value}', 'Column not found: {value}'),
    'file_process_error': (
        '파일 처리 중 오류가 발생했습니다: {error}', 'Error processing file: {error}'
    ),
    'save_error': (
        '데이터 저장 중 오류가 발생했습니다: {error}', 'Error saving data: {error}'
    ),
    'ocr_failed': ('OCR 처리 실패: {error}', 'OCR failed: {error}'),
    'ocr_error': (
        'OCR 처리 중 오류가 발생했습니다: {error}', 'OCR processing error: {error}'
    ),
    'chart_failed': ('차트 생성 실패: {error}', 'Chart creation failed: {error}'),
    'generic_error': ('오류가 발생했습니다: {error}', 'Error occurred: {error}'),
    'error_occurred': ('오류 발생: {error}', 'Error occurred: {error}'),
}


def get_message(ko_msg, en_msg):
    """현재 세션 언어에 맞는 문자열 반환"""
    return ko_msg if session.get('language') == 'ko' else en_msg


def msg(key, **fmt):
    """MESSAGES 키로 현재 언어의 메시지를 반환 (플레이스홀더 치환 지원)"""
    ko_msg, en_msg = MESSAGES[key]
    text = get_message(ko_msg, en_msg)
    return text.format(**fmt) if fmt else text


def flash_msg(key, category='info', **fmt):
    """MESSAGES 키로 flash 메시지 등록"""
    flash(msg(key, **fmt), category)
