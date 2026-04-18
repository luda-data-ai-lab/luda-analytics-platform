import os
from datetime import timedelta

class Config:
    # 기본 설정
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # 데이터베이스 설정
    # PostgreSQL
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'postgresql+psycopg2://postgres:postgres@localhost/analytics_db'
    
    # SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # 파일 업로드 설정
    UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'csv'}
    
    # 세션 설정
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    
    # 언어 설정
    LANGUAGES = ['ko', 'en']
    DEFAULT_LANGUAGE = 'ko'
