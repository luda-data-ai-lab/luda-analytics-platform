"""업로드 파일 처리 및 데이터셋 저장/조회 공용 유틸리티.

업로드(`/upload`), 템플릿 업로드(`/template/upload`), 템플릿 분석
(`/template_analyze`), OCR 저장(`/ocr/save`) 라우트에서 중복되던
파일 저장 · NaN 정리 · Dataset/DataRecord 생성 로직을 모았다.
"""

import logging
import math
import os
from datetime import datetime

import pandas as pd
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.utils import secure_filename

from models import DataRecord, Dataset, db

logger = logging.getLogger(__name__)


def upload_folder():
    """업로드 디렉터리 경로를 반환하고 없으면 생성한다."""
    folder = current_app.config['UPLOAD_FOLDER']
    os.makedirs(folder, exist_ok=True)
    return folder


def save_upload(file, *prefix_parts):
    """업로드 파일을 `<접두사>_<타임스탬프>_<원본명>` 으로 저장한다.

    저장 실패(OSError)는 호출자가 사용자 안내를 결정할 수 있도록 그대로 전파한다.
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    parts = [str(part) for part in prefix_parts if part not in (None, '')]
    stored_name = '_'.join(parts + [timestamp, secure_filename(file.filename)])
    filepath = os.path.join(upload_folder(), stored_name)
    file.save(filepath)
    return filepath, timestamp


def read_dataframe(filepath):
    """확장자에 따라 CSV/Excel 을 DataFrame 으로 읽는다."""
    if filepath.lower().endswith('.csv'):
        return pd.read_csv(filepath)
    return pd.read_excel(filepath)


def remove_file(path):
    """임시/업로드 파일 삭제 — 실패는 치명적이지 않지만 반드시 로그로 남긴다."""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        logger.warning("파일 삭제 실패: %s", path, exc_info=True)


def sanitize_value(value):
    """numpy 스칼라를 파이썬 기본형으로, NaN 을 None 으로 바꿔 JSON 직렬화 오류를 막는다."""
    if hasattr(value, 'item'):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def dataframe_rows(df):
    """DataFrame 을 JSON 직렬화 가능한 2차원 리스트로 변환한다."""
    return [[sanitize_value(value) for value in row] for row in df.values.tolist()]


def dataframe_records(df, sanitize=False):
    """DataFrame 각 행을 dict 로 변환한다."""
    if not sanitize:
        return [row.to_dict() for _, row in df.iterrows()]
    return [
        {key: sanitize_value(value) for key, value in row.to_dict().items()}
        for _, row in df.iterrows()
    ]


def create_dataset_with_records(df, name, filename, file_path, user_id,
                                description='', sanitize=False, **flags):
    """Dataset 과 DataRecord 를 생성해 세션에 추가한다 (commit 은 호출자 책임)."""
    dataset = Dataset(
        name=name,
        description=description,
        filename=filename,
        file_path=file_path,
        user_id=user_id,
        row_count=len(df),
        column_count=len(df.columns),
        columns=df.columns.tolist(),
        **flags
    )
    db.session.add(dataset)
    db.session.flush()
    for record in dataframe_records(df, sanitize=sanitize):
        db.session.add(DataRecord(dataset_id=dataset.id, data=record))
    return dataset


def load_dataset_dataframe(dataset_id):
    """저장된 DataRecord 전체를 DataFrame 으로 읽는다."""
    records = DataRecord.query.filter_by(dataset_id=dataset_id).all()
    return pd.DataFrame([record.data for record in records])


def fix_dataset_meta(dataset):
    """columns/row_count가 None인 경우 DataRecord에서 복구"""
    if dataset.columns is None:
        first = DataRecord.query.filter_by(dataset_id=dataset.id).first()
        if first:
            cols = list(first.data.keys())
            count = DataRecord.query.filter_by(dataset_id=dataset.id).count()
            dataset.columns = cols
            dataset.row_count = count
            dataset.column_count = len(cols)
            try:
                db.session.commit()
            except SQLAlchemyError:
                db.session.rollback()
                logger.exception("데이터셋 메타데이터 복구 실패: dataset_id=%s", dataset.id)
