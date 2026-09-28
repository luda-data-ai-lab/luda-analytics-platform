"""
OCR 기능을 위한 데이터베이스 마이그레이션

실행 방법:
python migrate_ocr_db.py
"""

from flask import Flask
from models_old import db, OCRSession
from sqlalchemy import text
import os

# Flask 앱 생성
app = Flask(__name__)

# DB 설정 (app.py와 동일하게)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'mysql+pymysql://root:root@localhost/analytics_db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

def migrate_ocr():
    """OCR 관련 테이블 및 컬럼 추가"""
    
    with app.app_context():
        try:
            # OCR 세션 테이블 생성
            print("OCR 세션 테이블 생성 중...")
            db.create_all()
            print("✓ OCR 세션 테이블 생성 완료")
            
            # Dataset 테이블에 is_ocr 컬럼 추가
            print("\nDataset 테이블에 is_ocr 컬럼 추가 중...")
            try:
                with db.engine.connect() as conn:
                    conn.execute(text("ALTER TABLE datasets ADD COLUMN is_ocr BOOLEAN DEFAULT FALSE"))
                    conn.commit()
                print("✓ is_ocr 컬럼 추가 완료")
            except Exception as e:
                if 'Duplicate column name' in str(e):
                    print("✓ is_ocr 컬럼이 이미 존재합니다")
                else:
                    raise
            
            print("\n✅ OCR 마이그레이션 완료!")
            print("\n다음 단계:")
            print("1. app.py에 OCR 라우트 추가")
            print("2. templates 폴더에 HTML 파일 추가")
            print("3. ocr_utils.py 파일 추가")
            print("4. Tesseract OCR 설치 확인")
            
        except Exception as e:
            print(f"\n❌ 오류 발생: {e}")
            print("\n해결 방법:")
            print("1. MySQL 서버가 실행 중인지 확인")
            print("2. DB 연결 정보가 올바른지 확인")
            print("3. 필요한 라이브러리가 설치되었는지 확인: pip install -r requirements.txt")
            # 마이그레이션 실패를 종료 코드로 전달해야 스크립트/CI 가 실패를 감지할 수 있다.
            raise

if __name__ == '__main__':
    print("=" * 50)
    print("OCR 기능 데이터베이스 마이그레이션")
    print("=" * 50)
    print()
    
    migrate_ocr()
