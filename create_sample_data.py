"""
샘플 데이터 생성 스크립트
Sample Data Generation Script

테스트용 샘플 데이터를 생성합니다.
Creates sample data for testing purposes.
"""

from app_2 import app, db
from models_old import User, Dataset, DataRecord
import pandas as pd
import os
from datetime import datetime, timedelta
import random

def create_sample_excel_files():
    """샘플 Excel 파일 생성"""
    print("샘플 Excel 파일 생성 중... / Creating sample Excel files...")
    
    # uploads 폴더 생성
    upload_folder = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
    os.makedirs(upload_folder, exist_ok=True)
    
    # 1. 매출 데이터
    sales_data = {
        '날짜': pd.date_range('2024-01-01', periods=12, freq='M').strftime('%Y-%m').tolist(),
        '매출액': [random.randint(1000, 5000) for _ in range(12)],
        '비용': [random.randint(500, 2000) for _ in range(12)],
        '순이익': [random.randint(300, 1500) for _ in range(12)]
    }
    sales_df = pd.DataFrame(sales_data)
    sales_file = os.path.join(upload_folder, 'sample_sales_2024.xlsx')
    sales_df.to_excel(sales_file, index=False)
    print(f"✅ 생성됨 / Created: {sales_file}")
    
    # 2. 고객 데이터
    customer_data = {
        '고객ID': [f'C{i:04d}' for i in range(1, 51)],
        '이름': [f'고객{i}' for i in range(1, 51)],
        '나이': [random.randint(20, 70) for _ in range(50)],
        '구매횟수': [random.randint(1, 20) for _ in range(50)],
        '총구매액': [random.randint(10000, 500000) for _ in range(50)]
    }
    customer_df = pd.DataFrame(customer_data)
    customer_file = os.path.join(upload_folder, 'sample_customers.xlsx')
    customer_df.to_excel(customer_file, index=False)
    print(f"✅ 생성됨 / Created: {customer_file}")
    
    # 3. 제품 데이터
    product_data = {
        '제품명': ['제품A', '제품B', '제품C', '제품D', '제품E'],
        '카테고리': ['전자제품', '의류', '식품', '전자제품', '의류'],
        '가격': [50000, 30000, 15000, 80000, 45000],
        '재고': [100, 200, 150, 50, 120],
        '판매량': [500, 800, 600, 300, 450]
    }
    product_df = pd.DataFrame(product_data)
    product_file = os.path.join(upload_folder, 'sample_products.csv')
    product_df.to_csv(product_file, index=False, encoding='utf-8-sig')
    print(f"✅ 생성됨 / Created: {product_file}")
    
    return {
        'sales': (sales_file, sales_df),
        'customers': (customer_file, customer_df),
        'products': (product_file, product_df)
    }

def load_sample_data_to_db(user_id):
    """샘플 데이터를 데이터베이스에 로드"""
    print("\n데이터베이스에 샘플 데이터 로딩 중...")
    print("Loading sample data to database...")
    
    # 샘플 파일 생성
    sample_files = create_sample_excel_files()
    
    with app.app_context():
        # 각 샘플 파일을 데이터베이스에 저장
        for name, (filepath, df) in sample_files.items():
            # 데이터셋 생성
            dataset = Dataset(
                name=f"샘플 {name.capitalize()} 데이터 / Sample {name.capitalize()} Data",
                description=f"테스트용 샘플 {name} 데이터셋 / Sample {name} dataset for testing",
                filename=os.path.basename(filepath),
                file_path=filepath,
                user_id=user_id,
                row_count=len(df),
                column_count=len(df.columns),
                columns=df.columns.tolist()
            )
            db.session.add(dataset)
            db.session.flush()
            
            # 데이터 레코드 저장
            for _, row in df.iterrows():
                record = DataRecord(
                    dataset_id=dataset.id,
                    data=row.to_dict()
                )
                db.session.add(record)
            
            db.session.commit()
            print(f"✅ {name} 데이터 로드 완료 / {name} data loaded")
        
        print("\n모든 샘플 데이터 로드 완료!")
        print("All sample data loaded successfully!")

def create_complete_sample_environment():
    """완전한 샘플 환경 생성"""
    with app.app_context():
        print("="*60)
        print("완전한 샘플 환경 생성 중...")
        print("Creating complete sample environment...")
        print("="*60)
        
        # 1. 샘플 사용자 확인/생성
        sample_user = User.query.filter_by(email='test@example.com').first()
        if not sample_user:
            sample_user = User(
                email='test@example.com',
                name='테스트 사용자 / Test User'
            )
            sample_user.set_password('test1234')
            db.session.add(sample_user)
            db.session.commit()
            print("✅ 샘플 사용자 생성 완료 / Sample user created")
        else:
            print("ℹ️  샘플 사용자가 이미 존재합니다 / Sample user already exists")
        
        # 2. 기존 샘플 데이터셋 확인
        existing_datasets = Dataset.query.filter_by(user_id=sample_user.id).count()
        if existing_datasets > 0:
            confirm = input(f"\n⚠️  이미 {existing_datasets}개의 데이터셋이 있습니다. 샘플 데이터를 추가하시겠습니까? (y/n) / {existing_datasets} datasets already exist. Add sample data? (y/n): ")
            if confirm.lower() != 'y':
                print("취소되었습니다. / Cancelled.")
                return
        
        # 3. 샘플 데이터 로드
        load_sample_data_to_db(sample_user.id)
        
        # 4. 결과 요약
        print("\n" + "="*60)
        print("샘플 환경 생성 완료! / Sample environment created!")
        print("="*60)
        print(f"\n로그인 정보 / Login credentials:")
        print(f"  이메일 / Email: test@example.com")
        print(f"  비밀번호 / Password: test1234")
        print(f"\n생성된 데이터셋 / Created datasets:")
        
        datasets = Dataset.query.filter_by(user_id=sample_user.id).all()
        for i, dataset in enumerate(datasets, 1):
            print(f"  {i}. {dataset.name}")
            print(f"     - {dataset.row_count} 행 / rows")
            print(f"     - {dataset.column_count} 열 / columns")
        
        print("\n🚀 이제 애플리케이션을 실행하고 로그인하세요!")
        print("🚀 Now run the application and login!")

if __name__ == '__main__':
    print("="*60)
    print("Analytics Platform - 샘플 데이터 생성")
    print("Analytics Platform - Sample Data Generation")
    print("="*60 + "\n")
    
    while True:
        print("옵션을 선택하세요 / Select an option:")
        print("1. 샘플 Excel/CSV 파일만 생성 / Create sample Excel/CSV files only")
        print("2. 완전한 샘플 환경 생성 (사용자 + 데이터) / Create complete sample environment (user + data)")
        print("3. 종료 / Exit")
        
        choice = input("\n선택 / Choice (1-3): ").strip()
        
        if choice == '1':
            create_sample_excel_files()
            print("\n✅ 샘플 파일이 static/uploads/ 폴더에 생성되었습니다!")
            print("✅ Sample files created in static/uploads/ folder!")
        
        elif choice == '2':
            create_complete_sample_environment()
        
        elif choice == '3':
            print("종료합니다. / Exiting...")
            break
        
        else:
            print("잘못된 선택입니다. / Invalid choice.")
        
        print()
