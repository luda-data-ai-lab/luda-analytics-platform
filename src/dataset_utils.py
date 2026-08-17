"""데이터셋 업로드/조회 공통 유틸 / Shared dataset persistence helpers."""

import math
import os
from datetime import datetime

import pandas as pd
from flask import current_app, redirect, url_for
from flask_login import current_user
from werkzeug.utils import secure_filename

from models import DataRecord, Dataset, db
from src.i18n import flash_msg


def upload_folder():
    """업로드 폴더 경로 (없으면 생성)"""
    folder = current_app.config.get('UPLOAD_FOLDER', 'static/uploads')
    os.makedirs(folder, exist_ok=True)
    return folder


def save_upload(file, prefix_parts=()):
    """업로드 파일을 `<prefix>_<timestamp>_<원본명>` 으로 저장

    Returns: (stored_filename, filepath, timestamp)
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    parts = [str(part) for part in prefix_parts if part not in (None, '')]
    stored_filename = '_'.join(parts + [timestamp, secure_filename(file.filename)])
    filepath = os.path.join(upload_folder(), stored_filename)
    file.save(filepath)
    return stored_filename, filepath, timestamp


def read_dataframe(filepath):
    """확장자에 따라 CSV/Excel 읽기"""
    if filepath.lower().endswith('.csv'):
        return pd.read_csv(filepath)
    return pd.read_excel(filepath)


def sanitize_value(value):
    """numpy 스칼라 → 파이썬 값, NaN → None (JSON 직렬화 오류 방지)"""
    if hasattr(value, 'item'):
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def dataframe_rows(df):
    """DataFrame 값을 JSON 직렬화 가능한 2차원 리스트로 변환"""
    return [[sanitize_value(v) for v in row] for row in df.values.tolist()]


def dataframe_records(df, sanitize=False):
    """DataFrame 행을 dict 리스트로 변환"""
    records = (row.to_dict() for _, row in df.iterrows())
    if not sanitize:
        return list(records)
    return [{k: sanitize_value(v) for k, v in record.items()} for record in records]


def create_dataset_from_dataframe(df, name, filename, file_path,
                                  description='', sanitize=False, **flags):
    """Dataset + DataRecord 생성 (commit은 호출자 책임)"""
    dataset = Dataset(
        name=name,
        description=description,
        filename=filename,
        file_path=file_path,
        user_id=current_user.id,
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
    """저장된 DataRecord를 DataFrame으로 로드"""
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
            db.session.commit()


def is_owner(record):
    """현재 사용자가 해당 레코드의 소유자인지 확인"""
    return record.user_id == current_user.id


def access_denied(endpoint='dashboard', **values):
    """권한 없음 메시지 flash 후 리다이렉트 응답 반환"""
    flash_msg('access_denied', 'danger')
    return redirect(url_for(endpoint, **values))
