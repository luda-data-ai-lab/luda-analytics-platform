from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    company = db.Column(db.String(100))
    purpose = db.Column(db.String(500))  # 가입 시 입력하는 사용 목적 (승인 심사용)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # 관리자 승인 (pending / approved / rejected)
    is_admin = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    approval_status = db.Column(
        db.String(20), nullable=False, default='pending', server_default='pending'
    )
    approval_decided_at = db.Column(db.DateTime)
    approved_by_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    rejection_reason = db.Column(db.String(500))

    # 로그인 실패 누적/잠금 (여러 워커에서 공유되도록 DB에 저장)
    failed_login_count = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    locked_until = db.Column(db.DateTime)
    last_login_at = db.Column(db.DateTime)
    
    datasets = db.relationship('Dataset', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Dataset(db.Model):
    __tablename__ = 'datasets'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    row_count = db.Column(db.Integer)
    column_count = db.Column(db.Integer)
    columns = db.Column(db.JSON)
    is_template = db.Column(db.Boolean, default=False)  # 템플릿 기반 데이터셋 여부
    is_ocr = db.Column(db.Boolean, default=False)  # OCR로 생성된 데이터셋 여부
    
    records = db.relationship('DataRecord', backref='dataset', lazy=True, cascade='all, delete-orphan')
    views = db.relationship('DataView', backref='dataset', lazy=True, cascade='all, delete-orphan')

class DataRecord(db.Model):
    __tablename__ = 'data_records'
    
    id = db.Column(db.Integer, primary_key=True)
    dataset_id = db.Column(db.Integer, db.ForeignKey('datasets.id'), nullable=False)
    data = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class DataView(db.Model):
    __tablename__ = 'data_views'
    
    id = db.Column(db.Integer, primary_key=True)
    dataset_id = db.Column(db.Integer, db.ForeignKey('datasets.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    chart_type = db.Column(db.String(50), nullable=False)
    x_column = db.Column(db.String(100))
    y_column = db.Column(db.String(100))
    config = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class OCRSession(db.Model):
    __tablename__ = 'ocr_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    extracted_data = db.Column(db.JSON)  # 추출된 데이터 (임시 저장)
    status = db.Column(db.String(50), default='pending')  # pending, processing, completed, failed
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref='ocr_sessions')
