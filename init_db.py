"""
데이터베이스 초기화 스크립트
Database Initialization Script

이 스크립트는 데이터베이스 테이블을 생성하고 초기 데이터를 추가합니다.
This script creates database tables and adds initial data.
"""

from app import app, db
from models_old import User, Dataset, DataRecord, DataView
from werkzeug.security import generate_password_hash

def init_database():
    """데이터베이스 초기화"""
    with app.app_context():
        # 기존 테이블 삭제 (주의: 모든 데이터가 삭제됩니다!)
        print("기존 테이블 삭제 중... / Dropping existing tables...")
        db.drop_all()
        
        # 새 테이블 생성
        print("새 테이블 생성 중... / Creating new tables...")
        db.create_all()
        
        print("✅ 데이터베이스 테이블이 생성되었습니다!")
        print("✅ Database tables created successfully!")
        
        # 테이블 목록 출력
        print("\n생성된 테이블 / Created tables:")
        print("- users")
        print("- datasets")
        print("- data_records")
        print("- data_views")

def create_sample_user():
    """샘플 사용자 생성"""
    with app.app_context():
        # 기존 샘플 사용자 확인
        existing_user = User.query.filter_by(email='test@example.com').first()
        if existing_user:
            print("⚠️  샘플 사용자가 이미 존재합니다.")
            print("⚠️  Sample user already exists.")
            return
        
        # 샘플 사용자 생성
        sample_user = User(
            email='test@example.com',
            name='테스트 사용자 / Test User'
        )
        sample_user.set_password('test1234')
        
        db.session.add(sample_user)
        db.session.commit()
        
        print("✅ 샘플 사용자가 생성되었습니다!")
        print("✅ Sample user created successfully!")
        print("\n로그인 정보 / Login credentials:")
        print(f"   이메일 / Email: test@example.com")
        print(f"   비밀번호 / Password: test1234")

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
        print("3. 데이터베이스 상태 확인 / Check database status")
        print("4. 종료 / Exit")
        
        choice = input("\n선택 / Choice (1-4): ").strip()
        
        if choice == '1':
            confirm = input("⚠️  모든 데이터가 삭제됩니다. 계속하시겠습니까? (y/n) / All data will be deleted. Continue? (y/n): ")
            if confirm.lower() == 'y':
                init_database()
            else:
                print("취소되었습니다. / Cancelled.")
        
        elif choice == '2':
            create_sample_user()
        
        elif choice == '3':
            check_database()
        
        elif choice == '4':
            print("종료합니다. / Exiting...")
            break
        
        else:
            print("잘못된 선택입니다. / Invalid choice.")
        
        print()
