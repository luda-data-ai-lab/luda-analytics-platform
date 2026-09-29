"""
데이터베이스 초기화 스크립트
Database Initialization Script

이 스크립트는 데이터베이스 테이블을 생성하고 초기 데이터를 추가합니다.
This script creates database tables and adds initial data.
"""

from app import app, db
from flask_migrate import stamp
from models import User, Dataset, DataRecord, DataView
from werkzeug.security import generate_password_hash
import pandas as pd
import os
import secrets

def init_database():
    """데이터베이스 초기화"""
    with app.app_context():
        # 기존 테이블 삭제 (주의: 모든 데이터가 삭제됩니다!)
        print("기존 테이블 삭제 중... / Dropping existing tables...")
        db.drop_all()
        
        # 새 테이블 생성
        print("새 테이블 생성 중... / Creating new tables...")
        db.create_all()

        # 마이그레이션 이력을 최신 리버전으로 표시 (이후 flask db migrate 가 이 스키마를 기준으로 동작)
        stamp()

        print("✅ 데이터베이스 테이블이 생성되었습니다!")
        print("✅ Database tables created successfully!")
        
        # 테이블 목록 출력
        print("\n생성된 테이블 / Created tables:")
        print("- users")
        print("- datasets")
        print("- data_records")
        print("- data_views")
        print("- ocr_sessions")

def create_sample_user():
    """샘플 사용자 생성 (개발 환경 전용)"""
    if app.config.get('IS_PRODUCTION'):
        print("❌ 프로덕션 환경에서는 샘플 사용자를 생성할 수 없습니다.")
        print("❌ Refusing to create a sample user in production.")
        return

    with app.app_context():
        # 기존 샘플 사용자 확인
        existing_user = User.query.filter_by(email='test@example.com').first()
        if existing_user:
            print("⚠️  샘플 사용자가 이미 존재합니다.")
            print("⚠️  Sample user already exists.")
            return
        
        # 샘플 사용자 생성 (비밀번호는 환경변수 또는 랜덤 생성)
        password = os.environ.get('SAMPLE_USER_PASSWORD') or secrets.token_urlsafe(16)
        sample_user = User(
            email='test@example.com',
            name='테스트 사용자 / Test User'
        )
        sample_user.set_password(password)
        
        db.session.add(sample_user)
        db.session.commit()
        
        print("✅ 샘플 사용자가 생성되었습니다!")
        print("✅ Sample user created successfully!")
        print("\n로그인 정보 / Login credentials:")
        print(f"   이메일 / Email: test@example.com")
        print(f"   비밀번호 / Password: {password}")

def create_sample_data():
    """샘플 데이터셋 4종 DB 삽입"""
    with app.app_context():
        user = User.query.filter_by(email='test@example.com').first()
        if not user:
            print("⚠️  먼저 샘플 사용자를 생성하세요 (옵션 2)")
            return

        TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), 'templates_data')
        TEMPLATE_FILES = {
            '판매 데이터 샘플':     'sales_data_template.csv',
            '고객 분석 샘플':       'customer_data_template.csv',
            '마케팅 캠페인 샘플':   'marketing_campaign_template.csv',
            '곡물 생산량 샘플':     'crop_yield_template.csv',
        }

        created = 0
        for name, filename in TEMPLATE_FILES.items():
            filepath = os.path.join(TEMPLATES_DIR, filename)
            if not os.path.exists(filepath):
                print(f"⚠️  파일 없음: {filename}")
                continue

            # 이미 존재하면 건너뜀
            if Dataset.query.filter_by(user_id=user.id, name=name).first():
                print(f"⏭️  이미 존재: {name}")
                continue

            df = pd.read_csv(filepath)
            dataset = Dataset(
                name=name,
                description=f'샘플 데이터 — {filename}',
                filename=filename,
                file_path=filepath,
                user_id=user.id,
                row_count=len(df),
                column_count=len(df.columns),
                columns=df.columns.tolist(),
                is_template=True
            )
            db.session.add(dataset)
            db.session.flush()

            import math
            for _, row in df.iterrows():
                clean = {}
                for k, v in row.to_dict().items():
                    if hasattr(v, 'item'):
                        v = v.item()
                    if isinstance(v, float) and math.isnan(v):
                        v = None
                    clean[k] = v
                db.session.add(DataRecord(dataset_id=dataset.id, data=clean))

            db.session.commit()
            print(f"✅ {name} — {len(df)}행 삽입 완료")
            created += 1

        print(f"\n총 {created}개 샘플 데이터셋 생성 완료!")

def check_database():
    """데이터베이스 상태 확인"""
    with app.app_context():
        print("\n" + "="*50)
        print("데이터베이스 상태 확인 / Database Status Check")
        print("="*50)
        
        # 사용자 수
        user_count = User.query.count()
        print(f"사용자 수 / Total Users: {user_count}")
        
        # 데이터셋 수
        dataset_count = Dataset.query.count()
        print(f"데이터셋 수 / Total Datasets: {dataset_count}")
        
        # 데이터 레코드 수
        record_count = DataRecord.query.count()
        print(f"데이터 레코드 수 / Total Records: {record_count}")
        
        # 뷰 수
        view_count = DataView.query.count()
        print(f"데이터 뷰 수 / Total Views: {view_count}")
        
        print("="*50 + "\n")

if __name__ == '__main__':
    print("="*60)
    print("Analytics Platform - 데이터베이스 초기화")
    print("Analytics Platform - Database Initialization")
    print("="*60 + "\n")
    
    while True:
        print("옵션을 선택하세요 / Select an option:")
        print("1. 데이터베이스 초기화 (모든 데이터 삭제) / Initialize DB (Delete all data)")
        print("2. 샘플 사용자 생성 / Create sample user")
        print("3. 샘플 데이터 삽입 / Insert sample data")
        print("4. 데이터베이스 상태 확인 / Check database status")
        print("5. 종료 / Exit")

        choice = input("\n선택 / Choice (1-5): ").strip()

        if choice == '1':
            confirm = input("⚠️  모든 데이터가 삭제됩니다. 계속하시겠습니까? (y/n) / All data will be deleted. Continue? (y/n): ")
            if confirm.lower() == 'y':
                init_database()
            else:
                print("취소되었습니다. / Cancelled.")

        elif choice == '2':
            create_sample_user()

        elif choice == '3':
            create_sample_data()

        elif choice == '4':
            check_database()

        elif choice == '5':
            print("종료합니다. / Exiting...")
            break
        
        else:
            print("잘못된 선택입니다. / Invalid choice.")
        
        print()
