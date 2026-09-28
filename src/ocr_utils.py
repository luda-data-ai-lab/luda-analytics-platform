"""
OCR 문서 스캔 유틸리티
"""

import cv2
import numpy as np
from PIL import Image
import pytesseract
import pandas as pd
from pdf2image import convert_from_path
import logging
import os
import re
import platform

logger = logging.getLogger(__name__)

# Windows: Tesseract 경로 자동 설정
if platform.system() == 'Windows':
    # 일반적인 Tesseract 설치 경로들
    possible_paths = [
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
        r'C:\Tesseract-OCR\tesseract.exe',
        r'C:\Users\{}\AppData\Local\Tesseract-OCR\tesseract.exe'.format(os.getenv('USERNAME')),
    ]
    
    tesseract_found = False
    for path in possible_paths:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            tesseract_found = True
            print(f"✅ Tesseract 찾음: {path}")
            break
    
    if not tesseract_found:
        print("⚠️ Tesseract를 찾을 수 없습니다.")
        print("다음 중 한 곳에 Tesseract를 설치하세요:")
        for path in possible_paths:
            print(f"  - {path}")
        print("\n다운로드: https://github.com/UB-Mannheim/tesseract/wiki")

class OCRProcessor:
    def __init__(self):
        """OCR 프로세서 초기화"""
        self.temp_dir = None
        # 단계별 실패 이유 — 모든 방식이 실패했을 때 호출자에게 전달하기 위해 보관한다.
        self.failures = []

    def _record_failure(self, step, exc):
        logger.warning("OCR 단계 실패: %s", step, exc_info=True)
        self.failures.append(f"{step}: {exc}")
        
    def preprocess_image(self, image_path):
        """
        이미지 전처리
        - 그레이스케일 변환
        - 노이즈 제거
        - 이진화
        """
        print(f"이미지 전처리 시작: {image_path}")
        
        # 이미지 읽기
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"이미지를 읽을 수 없습니다: {image_path}")
        
        # 그레이스케일 변환
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 노이즈 제거
        denoised = cv2.fastNlMeansDenoising(gray)
        
        # 적응형 이진화
        binary = cv2.adaptiveThreshold(
            denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
            cv2.THRESH_BINARY, 11, 2
        )
        
        # 전처리된 이미지 저장
        processed_path = image_path.replace('.png', '_processed.png')
        cv2.imwrite(processed_path, binary)
        print(f"전처리 완료: {processed_path}")
        
        return processed_path
    
    def extract_table_img2table(self, image_path):
        """
        img2table을 사용한 표 추출
        """
        try:
            from img2table.document import Image as Img2TableImage
            from img2table.ocr import TesseractOCR
            
            print(f"img2table로 표 추출 시작: {image_path}")
            
            # OCR 엔진 초기화 (Tesseract)
            ocr = TesseractOCR(n_threads=1, lang="eng")
            
            # 이미지 문서 생성
            doc = Img2TableImage(src=image_path)
            
            # 표 추출
            extracted_tables = doc.extract_tables(
                ocr=ocr,
                implicit_rows=True,
                borderless_tables=True,
                min_confidence=50
            )
            
            if extracted_tables:
                print(f"✅ img2table로 {len(extracted_tables)}개 표 추출 성공")
                
                # 첫 번째 표를 DataFrame으로 변환
                table = extracted_tables[0]
                df = table.df
                
                # ✅ DataFrame 정리 및 검증
                # 빈 행/열 제거
                df = df.dropna(how='all').dropna(axis=1, how='all')
                
                # ✅ 컬럼명 정리 (None이나 빈 값 제거)
                if df.empty:
                    print("⚠️ 표가 비어있음")
                    return None
                
                # 컬럼이 None이거나 빈 값이면 기본 컬럼명 사용
                try:
                    # 컬럼명 확인 및 정리
                    columns = []
                    for i, col in enumerate(df.columns):
                        if pd.isna(col) or str(col).strip() == '':
                            columns.append(f'Column_{i+1}')
                        else:
                            columns.append(str(col).strip())
                    df.columns = columns
                    
                    print(f"✅ DataFrame 정리 완료: {df.shape}")
                    print(f"컬럼: {df.columns.tolist()}")
                    
                    return df
                    
                except Exception as e:
                    self._record_failure('img2table DataFrame 정리', e)
                    # 오류 발생 시 기본 컬럼명으로 재시도
                    df.columns = [f'Column_{i+1}' for i in range(len(df.columns))]
                    print(f"✅ 기본 컬럼명으로 DataFrame 생성: {df.shape}")
                    return df
            else:
                print("⚠️ img2table로 표를 찾지 못함")
                return None
                
        except Exception as e:
            self._record_failure('img2table 표 생성', e)
            return None
    
    def detect_table_structure(self, image_path):
        """
        OpenCV를 사용한 표 구조 인식
        """
        print(f"표 구조 인식 시작: {image_path}")
        
        # 이미지 읽기
        img = cv2.imread(image_path)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 이진화
        _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
        
        # 수평선 검출
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
        horizontal_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel)
        
        # 수직선 검출
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
        vertical_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel)
        
        # 표 격자 생성
        table_grid = cv2.add(horizontal_lines, vertical_lines)
        
        # 컨투어 찾기
        contours, _ = cv2.findContours(table_grid, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        
        # 셀 영역 찾기
        cells = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w > 30 and h > 20:  # 최소 크기 필터
                cells.append((x, y, w, h))
        
        print(f"✅ {len(cells)}개 셀 검출")
        return cells
    
    def extract_text_from_cells(self, image_path, cells):
        """
        각 셀에서 텍스트 추출
        """
        print("셀에서 텍스트 추출 중...")
        
        img = cv2.imread(image_path)
        
        cell_texts = []
        for i, (x, y, w, h) in enumerate(cells):
            # 셀 영역 추출
            cell_img = img[y:y+h, x:x+w]
            
            # PIL 이미지로 변환
            pil_img = Image.fromarray(cv2.cvtColor(cell_img, cv2.COLOR_BGR2RGB))
            
            # OCR 수행
            text = pytesseract.image_to_string(pil_img, config='--psm 6')
            text = text.strip()
            
            cell_texts.append({
                'x': x,
                'y': y,
                'w': w,
                'h': h,
                'text': text
            })
        
        return cell_texts
    
    def organize_cells_to_dataframe(self, cell_texts):
        """
        셀 텍스트를 DataFrame으로 구성
        """
        print("DataFrame 구성 중...")
        
        if not cell_texts:
            return pd.DataFrame()
        
        # Y 좌표로 행 그룹화 (오차 범위 10px)
        rows = {}
        for cell in cell_texts:
            y = cell['y']
            
            # 기존 행 찾기
            found = False
            for row_y in rows.keys():
                if abs(y - row_y) < 10:
                    rows[row_y].append(cell)
                    found = True
                    break
            
            if not found:
                rows[y] = [cell]
        
        # 각 행의 셀을 X 좌표로 정렬
        sorted_rows = []
        for row_y in sorted(rows.keys()):
            sorted_cells = sorted(rows[row_y], key=lambda c: c['x'])
            sorted_rows.append([c['text'] for c in sorted_cells])
        
        if not sorted_rows:
            return pd.DataFrame()
        
        # ✅ 컬럼 수 불일치 해결
        # 모든 행의 최대 컬럼 수 찾기
        max_cols = max(len(row) for row in sorted_rows)
        
        # 모든 행을 같은 길이로 맞춤
        normalized_rows = []
        for row in sorted_rows:
            if len(row) < max_cols:
                # 부족한 컬럼은 빈 문자열로 채움
                row.extend([''] * (max_cols - len(row)))
            elif len(row) > max_cols:
                # 초과 컬럼은 잘라냄
                row = row[:max_cols]
            normalized_rows.append(row)
        
        # DataFrame 생성
        if len(normalized_rows) > 1:
            try:
                # 첫 행을 헤더로 사용
                df = pd.DataFrame(normalized_rows[1:], columns=normalized_rows[0])
                print(f"✅ DataFrame 생성: {df.shape}")
                return df
            except Exception as e:
                self._record_failure('셀 헤더 DataFrame 생성', e)
                # 헤더 사용 실패 시 기본 컬럼명 사용
                df = pd.DataFrame(normalized_rows[1:])
                df.columns = [f'Column_{i+1}' for i in range(len(df.columns))]
                print(f"✅ DataFrame 생성 (기본 컬럼명): {df.shape}")
                return df
        else:
            # 행이 1개뿐이면 그대로 DataFrame 생성
            df = pd.DataFrame(normalized_rows)
            df.columns = [f'Column_{i+1}' for i in range(len(df.columns))]
            print(f"✅ DataFrame 생성 (단일 행): {df.shape}")
            return df
    
    def extract_table_basic(self, image_path):
        """
        기본 OCR 방식으로 표 추출
        """
        print("기본 OCR 방식으로 표 추출 시작")
        
        try:
            # PIL 이미지로 읽기
            pil_img = Image.open(image_path)
            
            # 전체 텍스트 추출
            text = pytesseract.image_to_string(pil_img, config='--psm 6')
            
            print(f"추출된 텍스트 길이: {len(text)} 문자")
            
            # 줄 단위로 분리
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            
            if not lines:
                return pd.DataFrame()
            
            # 각 줄을 공백으로 분리하여 컬럼으로 만들기
            data = []
            for line in lines:
                # 여러 공백을 하나로 통일
                parts = re.split(r'\s{2,}', line)
                if parts:
                    data.append(parts)
            
            if not data:
                return pd.DataFrame()
            
            # ✅ 가장 긴 행의 길이 찾기
            max_cols = max(len(row) for row in data)
            
            # ✅ 모든 행을 같은 길이로 만들기 (빈 값으로 채움)
            normalized_data = []
            for row in data:
                if len(row) < max_cols:
                    # 부족한 컬럼은 빈 문자열로 채움
                    normalized_row = row + [''] * (max_cols - len(row))
                elif len(row) > max_cols:
                    # 초과 컬럼은 잘라냄
                    normalized_row = row[:max_cols]
                else:
                    normalized_row = row
                normalized_data.append(normalized_row)
            
            # ✅ DataFrame 생성 (안전하게)
            try:
                if len(normalized_data) > 1:
                    # 첫 행을 헤더로 사용
                    df = pd.DataFrame(normalized_data[1:], columns=normalized_data[0])
                    print(f"✅ DataFrame 생성: {df.shape}")
                else:
                    # 행이 1개뿐이면 기본 컬럼명 사용
                    df = pd.DataFrame(normalized_data)
                    df.columns = [f'Column_{i+1}' for i in range(len(df.columns))]
                    print(f"✅ DataFrame 생성 (단일 행): {df.shape}")
                
                return df
                
            except Exception as e:
                self._record_failure('기본 OCR 헤더 DataFrame 생성', e)
                # 헤더 사용 실패 시 모든 데이터를 포함하고 기본 컬럼명 사용
                df = pd.DataFrame(normalized_data)
                df.columns = [f'Column_{i+1}' for i in range(len(df.columns))]
                print(f"✅ DataFrame 생성 (기본 컬럼명): {df.shape}")
                return df
            
        except Exception as e:
            self._record_failure('기본 OCR 표 생성', e)
            return pd.DataFrame()
    
    def process_document(self, file_path):
        """
        문서 처리 메인 함수
        
        Args:
            file_path: 이미지 또는 PDF 파일 경로
            
        Returns:
            dict: 추출된 데이터와 메타정보
        """
        print(f"\n{'='*60}")
        print(f"OCR 처리 시작: {file_path}")
        print(f"{'='*60}\n")
        
        result = {
            'success': False,
            'data': None,
            'error': None,
            'method': None
        }
        self.failures = []
        
        try:
            # 파일 확장자 확인
            _, ext = os.path.splitext(file_path)
            ext = ext.lower()
            
            # PDF인 경우 이미지로 변환
            if ext == '.pdf':
                print("PDF를 이미지로 변환 중...")
                images = convert_from_path(file_path, dpi=300)
                
                # 첫 페이지만 처리
                if images:
                    image_path = file_path.replace('.pdf', '_page1.png')
                    images[0].save(image_path, 'PNG')
                    file_path = image_path
                    print(f"✅ PDF 변환 완료: {image_path}")
                else:
                    raise ValueError("PDF에서 이미지를 추출할 수 없습니다")
            
            # 이미지 전처리
            processed_path = self.preprocess_image(file_path)
            
            # 방법 1: img2table 시도
            df = self.extract_table_img2table(processed_path)
            
            if df is not None and not df.empty:
                result['success'] = True
                result['data'] = df
                result['method'] = 'img2table'
                print(f"✅ img2table로 성공: {df.shape}")
            else:
                # 방법 2: 표 구조 인식 + OCR
                print("\n표 구조 인식 방식 시도...")
                cells = self.detect_table_structure(processed_path)
                
                if cells and len(cells) > 5:
                    cell_texts = self.extract_text_from_cells(processed_path, cells)
                    df = self.organize_cells_to_dataframe(cell_texts)
                    
                    if not df.empty:
                        result['success'] = True
                        result['data'] = df
                        result['method'] = 'structure_detection'
                        print(f"✅ 구조 인식으로 성공: {df.shape}")
                    else:
                        # 방법 3: 기본 OCR
                        print("\n기본 OCR 방식 시도...")
                        df = self.extract_table_basic(processed_path)
                        
                        if not df.empty:
                            result['success'] = True
                            result['data'] = df
                            result['method'] = 'basic_ocr'
                            print(f"✅ 기본 OCR로 성공: {df.shape}")
                else:
                    # 방법 3: 기본 OCR
                    print("\n기본 OCR 방식 시도...")
                    df = self.extract_table_basic(processed_path)
                    
                    if not df.empty:
                        result['success'] = True
                        result['data'] = df
                        result['method'] = 'basic_ocr'
                        print(f"✅ 기본 OCR로 성공: {df.shape}")
            
            if not result['success']:
                result['error'] = "표 데이터를 추출할 수 없습니다"
                if self.failures:
                    result['error'] += " (" + ' / '.join(self.failures) + ")"
                logger.error("OCR 모든 방식 실패: %s (%s)", file_path, '; '.join(self.failures) or '상세 없음')

        except Exception as e:
            result['error'] = str(e)
            logger.exception("OCR 처리 오류: %s", file_path)
        
        print(f"\n{'='*60}")
        print(f"OCR 처리 완료: {'성공' if result['success'] else '실패'}")
        print(f"{'='*60}\n")
        
        return result

# 하위 호환성을 위한 래퍼 함수
def process_ocr_document(file_path, **kwargs):
    """
    OCR 문서 처리 (하위 호환성 함수)
    
    Args:
        file_path: 이미지 또는 PDF 파일 경로
        **kwargs: 추가 인자 (하위 호환성을 위해 무시됨)
        
    Returns:
        dict: 추출된 데이터와 메타정보
    """
    # kwargs는 받지만 사용하지 않음 (하위 호환성)
    processor = OCRProcessor()
    return processor.process_document(file_path)

# 테스트 함수
def test_ocr():
    """OCR 기능 테스트"""
    processor = OCRProcessor()
    
    # 테스트 이미지 경로
    test_image = "test_table.png"
    
    if os.path.exists(test_image):
        result = processor.process_document(test_image)
        
        if result['success']:
            print("\n추출된 데이터:")
            print(result['data'])
        else:
            print(f"\n오류: {result['error']}")
    else:
        print(f"테스트 이미지가 없습니다: {test_image}")

if __name__ == '__main__':
    test_ocr()
