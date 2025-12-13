# 데이터베이스 설정 가이드 (Database Setup Guide)

## 📋 포함된 DB 스크립트

### Python 스크립트
1. **init_db.py** - 데이터베이스 초기화 (대화형)
2. **create_sample_data.py** - 샘플 데이터 생성

### SQL 스크립트
1. **schema_sqlite.sql** - SQLite 스키마
2. **schema_mysql.sql** - MySQL 스키마

---

## 🚀 빠른 시작 (SQLite - 기본)

### 방법 1: Python 스크립트 사용 (권장)

```bash
# 1. 데이터베이스 초기화
python init_db.py
# 옵션 1 선택 → y 입력

# 2. 샘플 사용자 생성
python init_db.py
# 옵션 2 선택

# 3. 샘플 데이터 생성 (선택사항)
python create_sample_data.py
# 옵션 2 선택
```

### 방법 2: Flask 명령 사용

```bash
# Flask shell에서 직접 실행
python
>>> from app import app, db
>>> with app.app_context():
...     db.create_all()
...     print("Database created!")
>>> exit()
```

### 방법 3: 앱 실행으로 자동 생성

```bash
# app.py 실행 시 자동으로 테이블 생성됨
python app.py
```

---

## 🗄️ MySQL 사용하기

### 1. MySQL 데이터베이스 생성

```bash
# MySQL 접속
mysql -u root -p

# SQL 스크립트 실행
source schema_mysql.sql
```

또는 직접 명령 실행:

```sql
CREATE DATABASE analytics_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE analytics_db;
source schema_mysql.sql
```

### 2. config.py 수정

```python
# config.py에서 주석 해제 및 수정
SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://username:password@localhost/analytics_db'

# 예시:
SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://root:mypassword@localhost/analytics_db'
```

### 3. PyMySQL 설치 확인

```bash
pip install PyMySQL
```

### 4. 데이터베이스 초기화

```bash
python init_db.py
# 옵션 1 선택
```

---

## 📊 샘플 데이터 생성

### 완전한 샘플 환경 만들기

```bash
python create_sample_data.py
# 옵션 2 선택
```

**생성되는 내용:**
- ✅ 테스트 사용자 (test@example.com / test1234)
- ✅ 3개의 샘플 데이터셋
  - 매출 데이터 (12행)
  - 고객 데이터 (50행)
  - 제품 데이터 (5행)
- ✅ Excel/CSV 샘플 파일

---

## 🔧 데이터베이스 관리

### 1. 상태 확인

```bash
python init_db.py
# 옵션 3 선택
```

### 2. 데이터베이스 초기화 (모든 데이터 삭제)

```bash
python init_db.py
# 옵션 1 선택 → y 입력
```

### 3. SQLite 데이터베이스 파일 위치

```
analytics_platform/
├── analytics.db          # SQLite 데이터베이스 파일
└── static/
    └── uploads/          # 업로드된 파일 저장 위치
```

### 4. SQLite 직접 조회

```bash
# SQLite CLI 사용
sqlite3 analytics.db

# 테이블 목록 보기
.tables

# 사용자 조회
SELECT * FROM users;

# 데이터셋 조회
SELECT * FROM datasets;

# 종료
.exit
```

---

## 📝 데이터베이스 스키마

### Users (사용자)
```
- id: INTEGER (Primary Key)
- email: VARCHAR(120) UNIQUE
- password_hash: VARCHAR(255)
- name: VARCHAR(100)
- created_at: DATETIME
```

### Datasets (데이터셋)
```
- id: INTEGER (Primary Key)
- name: VARCHAR(200)
- description: TEXT
- filename: VARCHAR(255)
- file_path: VARCHAR(500)
- user_id: INTEGER (Foreign Key → users.id)
- uploaded_at: DATETIME
- row_count: INTEGER
- column_count: INTEGER
- columns: JSON
```

### Data Records (데이터 레코드)
```
- id: INTEGER (Primary Key)
- dataset_id: INTEGER (Foreign Key → datasets.id)
- data: JSON
- created_at: DATETIME
```

### Data Views (데이터 뷰)
```
- id: INTEGER (Primary Key)
- name: VARCHAR(200)
- dataset_id: INTEGER (Foreign Key → datasets.id)
- user_id: INTEGER (Foreign Key → users.id)
- view_config: JSON
- created_at: DATETIME
```

---

## 🔍 유용한 쿼리

### 1. 사용자별 데이터셋 수

```sql
SELECT u.name, u.email, COUNT(d.id) as dataset_count
FROM users u
LEFT JOIN datasets d ON u.id = d.user_id
GROUP BY u.id;
```

### 2. 데이터셋별 레코드 수

```sql
SELECT d.name, d.row_count, COUNT(dr.id) as actual_records
FROM datasets d
LEFT JOIN data_records dr ON d.id = dr.dataset_id
GROUP BY d.id;
```

### 3. 최근 업로드된 데이터셋 (상위 10개)

```sql
SELECT d.name, d.filename, u.name as user_name, d.uploaded_at
FROM datasets d
JOIN users u ON d.user_id = u.id
ORDER BY d.uploaded_at DESC
LIMIT 10;
```

### 4. 특정 사용자의 모든 데이터

```sql
SELECT * FROM datasets 
WHERE user_id = (SELECT id FROM users WHERE email = 'test@example.com');
```

---

## 🛠️ 문제 해결

### 문제 1: 테이블이 생성되지 않음

**해결:**
```bash
python init_db.py
# 옵션 1 선택
```

### 문제 2: "database is locked" 오류 (SQLite)

**해결:**
```bash
# 애플리케이션 종료 후
rm analytics.db
python init_db.py
```

### 문제 3: MySQL 연결 오류

**확인 사항:**
1. MySQL 서버가 실행 중인지 확인
2. config.py의 연결 정보가 정확한지 확인
3. PyMySQL이 설치되어 있는지 확인

```bash
# MySQL 서비스 상태 확인 (Linux)
sudo systemctl status mysql

# Windows에서 확인
net start | findstr MySQL
```

### 문제 4: 샘플 데이터 생성 오류

**해결:**
```bash
# 먼저 데이터베이스 초기화
python init_db.py
# 옵션 1 선택

# 그 다음 샘플 데이터 생성
python create_sample_data.py
# 옵션 2 선택
```

---

## 🔐 보안 권장사항

### 1. 프로덕션 환경

```python
# config.py 수정
SECRET_KEY = os.environ.get('SECRET_KEY')  # 환경 변수 사용
SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
```

### 2. 샘플 사용자 삭제

프로덕션 배포 전에 test@example.com 사용자 삭제:

```python
python
>>> from app import app, db
>>> from models import User
>>> with app.app_context():
...     user = User.query.filter_by(email='test@example.com').first()
...     if user:
...         db.session.delete(user)
...         db.session.commit()
>>> exit()
```

---

## 📚 추가 리소스

- SQLite 문서: https://www.sqlite.org/docs.html
- MySQL 문서: https://dev.mysql.com/doc/
- Flask-SQLAlchemy: https://flask-sqlalchemy.palletsprojects.com/

---

## ✅ 체크리스트

개발 환경 설정:
- [ ] Python 가상환경 활성화
- [ ] 패키지 설치 완료
- [ ] 데이터베이스 초기화 (init_db.py)
- [ ] 샘플 사용자 생성
- [ ] (선택) 샘플 데이터 생성
- [ ] 애플리케이션 실행 테스트

프로덕션 배포:
- [ ] SECRET_KEY 환경 변수 설정
- [ ] 데이터베이스 연결 정보 환경 변수 설정
- [ ] MySQL 데이터베이스 생성
- [ ] schema_mysql.sql 실행
- [ ] 샘플 사용자 삭제
- [ ] 백업 계획 수립

---

**💡 팁:** 처음 시작할 때는 SQLite로 테스트하고, 프로덕션 배포 시 MySQL로 전환하는 것을 권장합니다.
