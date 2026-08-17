"""src/ocr_utils.py (OCRProcessor) 테스트."""

import os

import cv2
import numpy as np
import pandas as pd
import pytest

import ocr_utils
from ocr_utils import OCRProcessor, process_ocr_document


@pytest.fixture
def table_image(tmp_path):
    """수평/수직선을 가진 간단한 표 이미지를 생성한다."""
    img = np.full((200, 400, 3), 255, dtype=np.uint8)
    for y in (20, 70, 120, 170):
        cv2.line(img, (20, y), (380, y), (0, 0, 0), 2)
    for x in (20, 140, 260, 380):
        cv2.line(img, (x, 20), (x, 170), (0, 0, 0), 2)
    path = str(tmp_path / 'table.png')
    cv2.imwrite(path, img)
    return path


@pytest.fixture
def processor():
    return OCRProcessor()


def test_init_has_no_temp_dir(processor):
    assert processor.temp_dir is None


def test_preprocess_image_writes_binary_copy(processor, table_image):
    processed_path = processor.preprocess_image(table_image)

    assert processed_path == table_image.replace('.png', '_processed.png')
    assert os.path.exists(processed_path)

    processed = cv2.imread(processed_path, cv2.IMREAD_GRAYSCALE)
    assert processed.shape == (200, 400)
    assert set(np.unique(processed)).issubset({0, 255})


def test_preprocess_image_raises_for_unreadable_file(processor, tmp_path):
    missing = str(tmp_path / 'missing.png')

    with pytest.raises(ValueError):
        processor.preprocess_image(missing)


def test_detect_table_structure_finds_cells(processor, table_image):
    cells = processor.detect_table_structure(table_image)

    assert cells
    assert all(len(cell) == 4 for cell in cells)
    assert all(w > 30 and h > 20 for _, _, w, h in cells)


def test_extract_text_from_cells_uses_ocr_per_cell(processor, table_image, monkeypatch):
    monkeypatch.setattr(ocr_utils.pytesseract, 'image_to_string', lambda img, config=None: ' 텍스트 \n')

    cells = [(10, 20, 50, 40), (70, 20, 50, 40)]
    result = processor.extract_text_from_cells(table_image, cells)

    assert [cell['text'] for cell in result] == ['텍스트', '텍스트']
    assert result[0] == {'x': 10, 'y': 20, 'w': 50, 'h': 40, 'text': '텍스트'}


def test_organize_cells_to_dataframe_groups_rows_and_sorts_columns(processor):
    cell_texts = [
        {'x': 100, 'y': 10, 'w': 1, 'h': 1, 'text': 'B'},
        {'x': 10, 'y': 12, 'w': 1, 'h': 1, 'text': 'A'},
        {'x': 100, 'y': 60, 'w': 1, 'h': 1, 'text': '2'},
        {'x': 10, 'y': 60, 'w': 1, 'h': 1, 'text': '1'},
    ]

    df = processor.organize_cells_to_dataframe(cell_texts)

    assert df.columns.tolist() == ['A', 'B']
    assert df.values.tolist() == [['1', '2']]


def test_organize_cells_pads_short_rows(processor):
    cell_texts = [
        {'x': 10, 'y': 10, 'w': 1, 'h': 1, 'text': 'A'},
        {'x': 100, 'y': 10, 'w': 1, 'h': 1, 'text': 'B'},
        {'x': 10, 'y': 60, 'w': 1, 'h': 1, 'text': '1'},
    ]

    df = processor.organize_cells_to_dataframe(cell_texts)

    assert df.values.tolist() == [['1', '']]


def test_organize_cells_single_row_uses_default_columns(processor):
    cell_texts = [
        {'x': 10, 'y': 10, 'w': 1, 'h': 1, 'text': 'A'},
        {'x': 100, 'y': 10, 'w': 1, 'h': 1, 'text': 'B'},
    ]

    df = processor.organize_cells_to_dataframe(cell_texts)

    assert df.columns.tolist() == ['Column_1', 'Column_2']
    assert df.values.tolist() == [['A', 'B']]


def test_organize_cells_empty_input_returns_empty_dataframe(processor):
    df = processor.organize_cells_to_dataframe([])

    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_extract_table_basic_splits_on_double_spaces(processor, table_image, monkeypatch):
    text = '이름  수량  금액\n사과  10  1000\n배  5  500\n'
    monkeypatch.setattr(ocr_utils.pytesseract, 'image_to_string', lambda img, config=None: text)

    df = processor.extract_table_basic(table_image)

    assert df.columns.tolist() == ['이름', '수량', '금액']
    assert df.values.tolist() == [['사과', '10', '1000'], ['배', '5', '500']]


def test_extract_table_basic_normalizes_ragged_rows(processor, table_image, monkeypatch):
    text = 'A  B  C\n1  2\n3  4  5  6\n'
    monkeypatch.setattr(ocr_utils.pytesseract, 'image_to_string', lambda img, config=None: text)

    df = processor.extract_table_basic(table_image)

    # 가장 긴 행(4칸)에 맞춰 헤더와 각 행이 빈 문자열로 패딩된다
    assert df.columns.tolist() == ['A', 'B', 'C', '']
    assert df.values.tolist() == [['1', '2', '', ''], ['3', '4', '5', '6']]


def test_extract_table_basic_single_line_uses_default_columns(processor, table_image, monkeypatch):
    monkeypatch.setattr(ocr_utils.pytesseract, 'image_to_string', lambda img, config=None: 'A  B\n')

    df = processor.extract_table_basic(table_image)

    assert df.columns.tolist() == ['Column_1', 'Column_2']


def test_extract_table_basic_empty_text_returns_empty_dataframe(processor, table_image, monkeypatch):
    monkeypatch.setattr(ocr_utils.pytesseract, 'image_to_string', lambda img, config=None: '\n  \n')

    df = processor.extract_table_basic(table_image)

    assert df.empty


def test_extract_table_basic_returns_empty_dataframe_on_error(processor, tmp_path):
    df = processor.extract_table_basic(str(tmp_path / 'missing.png'))

    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_extract_table_img2table_returns_none_when_import_fails(processor, table_image):
    # img2table 임포트/실행 실패 시 예외 없이 None을 반환해야 한다
    assert processor.extract_table_img2table('does-not-exist.png') is None


def test_process_document_uses_img2table_result(processor, table_image, monkeypatch):
    expected = pd.DataFrame({'A': [1]})
    monkeypatch.setattr(OCRProcessor, 'extract_table_img2table', lambda self, path: expected)

    result = processor.process_document(table_image)

    assert result['success'] is True
    assert result['method'] == 'img2table'
    assert result['data'] is expected
    assert result['error'] is None


def test_process_document_falls_back_to_structure_detection(processor, table_image, monkeypatch):
    expected = pd.DataFrame({'A': ['1']})
    monkeypatch.setattr(OCRProcessor, 'extract_table_img2table', lambda self, path: None)
    monkeypatch.setattr(OCRProcessor, 'detect_table_structure', lambda self, path: [(0, 0, 1, 1)] * 6)
    monkeypatch.setattr(OCRProcessor, 'extract_text_from_cells', lambda self, path, cells: ['cell'])
    monkeypatch.setattr(OCRProcessor, 'organize_cells_to_dataframe', lambda self, texts: expected)

    result = processor.process_document(table_image)

    assert result['success'] is True
    assert result['method'] == 'structure_detection'
    assert result['data'] is expected


def test_process_document_falls_back_to_basic_ocr(processor, table_image, monkeypatch):
    expected = pd.DataFrame({'A': ['1']})
    monkeypatch.setattr(OCRProcessor, 'extract_table_img2table', lambda self, path: None)
    monkeypatch.setattr(OCRProcessor, 'detect_table_structure', lambda self, path: [])
    monkeypatch.setattr(OCRProcessor, 'extract_table_basic', lambda self, path: expected)

    result = processor.process_document(table_image)

    assert result['success'] is True
    assert result['method'] == 'basic_ocr'


def test_process_document_basic_ocr_after_empty_structure_dataframe(processor, table_image, monkeypatch):
    expected = pd.DataFrame({'A': ['1']})
    monkeypatch.setattr(OCRProcessor, 'extract_table_img2table', lambda self, path: None)
    monkeypatch.setattr(OCRProcessor, 'detect_table_structure', lambda self, path: [(0, 0, 1, 1)] * 6)
    monkeypatch.setattr(OCRProcessor, 'extract_text_from_cells', lambda self, path, cells: ['cell'])
    monkeypatch.setattr(OCRProcessor, 'organize_cells_to_dataframe', lambda self, texts: pd.DataFrame())
    monkeypatch.setattr(OCRProcessor, 'extract_table_basic', lambda self, path: expected)

    result = processor.process_document(table_image)

    assert result['success'] is True
    assert result['method'] == 'basic_ocr'


def test_process_document_reports_failure_when_all_methods_fail(processor, table_image, monkeypatch):
    monkeypatch.setattr(OCRProcessor, 'extract_table_img2table', lambda self, path: None)
    monkeypatch.setattr(OCRProcessor, 'detect_table_structure', lambda self, path: [])
    monkeypatch.setattr(OCRProcessor, 'extract_table_basic', lambda self, path: pd.DataFrame())

    result = processor.process_document(table_image)

    assert result['success'] is False
    assert result['data'] is None
    assert result['error'] == '표 데이터를 추출할 수 없습니다'


def test_process_document_captures_exception_message(processor, tmp_path):
    result = processor.process_document(str(tmp_path / 'missing.png'))

    assert result['success'] is False
    assert '이미지를 읽을 수 없습니다' in result['error']


def test_process_document_converts_pdf_first_page(processor, tmp_path, monkeypatch):
    class FakePage:
        def __init__(self, target):
            self.target = target

        def save(self, path, fmt):
            img = np.full((50, 50, 3), 255, dtype=np.uint8)
            cv2.imwrite(path, img)
            self.target.append((path, fmt))

    saved = []
    monkeypatch.setattr(ocr_utils, 'convert_from_path', lambda path, dpi: [FakePage(saved)])
    monkeypatch.setattr(OCRProcessor, 'extract_table_img2table', lambda self, path: pd.DataFrame({'A': [1]}))

    pdf_path = str(tmp_path / 'doc.pdf')
    with open(pdf_path, 'wb') as handle:
        handle.write(b'%PDF-1.4')

    result = processor.process_document(pdf_path)

    assert saved and saved[0][1] == 'PNG'
    assert saved[0][0].endswith('_page1.png')
    assert result['success'] is True


def test_process_document_fails_when_pdf_has_no_pages(processor, tmp_path, monkeypatch):
    monkeypatch.setattr(ocr_utils, 'convert_from_path', lambda path, dpi: [])

    pdf_path = str(tmp_path / 'empty.pdf')
    with open(pdf_path, 'wb') as handle:
        handle.write(b'%PDF-1.4')

    result = processor.process_document(pdf_path)

    assert result['success'] is False
    assert 'PDF' in result['error']


def test_process_ocr_document_wrapper_ignores_extra_kwargs(table_image, monkeypatch):
    expected = pd.DataFrame({'A': [1]})
    monkeypatch.setattr(OCRProcessor, 'process_document', lambda self, path: {'data': expected, 'path': path})

    result = process_ocr_document(table_image, preprocess=True, unused='x')

    assert result['data'] is expected
    assert result['path'] == table_image


def test_test_ocr_handles_missing_test_image(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    ocr_utils.test_ocr()

    assert '테스트 이미지가 없습니다' in capsys.readouterr().out


def test_test_ocr_prints_extracted_data(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with open('test_table.png', 'wb') as handle:
        handle.write(b'')
    monkeypatch.setattr(
        OCRProcessor, 'process_document',
        lambda self, path: {'success': True, 'data': pd.DataFrame({'A': [1]})},
    )

    ocr_utils.test_ocr()

    assert '추출된 데이터' in capsys.readouterr().out


def test_test_ocr_prints_error(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with open('test_table.png', 'wb') as handle:
        handle.write(b'')
    monkeypatch.setattr(
        OCRProcessor, 'process_document',
        lambda self, path: {'success': False, 'error': '실패'},
    )

    ocr_utils.test_ocr()

    assert '실패' in capsys.readouterr().out
