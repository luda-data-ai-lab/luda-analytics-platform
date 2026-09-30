# LUDA Analytics Platform

데이터 파일을 업로드하면 자동으로 대시보드를 생성해주는 웹 기반 데이터 분석 플랫폼입니다.

## 주요 기능

| 기능 | 설명 |
|------|------|
| 범용 데이터 분석 | CSV/Excel 업로드 후 차트 타입·축 직접 설정 |
| 템플릿 기반 자동 분석 | 정형 템플릿 업로드만으로 대시보드 자동 생성 |
| OCR 데이터 추출 | 이미지/PDF에서 표 데이터 자동 인식 |
| 회사별 데이터 관리 | 동일 회사 구성원 데이터 통합 조회 |
| 다국어 지원 | 한국어 / 영어 실시간 전환 |

## 기술 스택

- **Backend**: Python 3.13+, Flask 3.0
- **Database**: SQLite (개발) / PostgreSQL (프로덕션)
- **Frontend**: Bootstrap 5, Plotly.js
- **ORM**: SQLAlchemy 2.0+

## 프로젝트 구조

```
luda-analytics-platform/
├── app.py                  # 메인 애플리케이션 (라우트 전체)
├── models.py               # DB 모델 (User, Dataset, DataRecord 등)
├── config.py               # 환경 설정
├── init_db.py              # DB 초기화 스크립트
├── requirements.txt        # Python 패키지 목록
├── templates/              # HTML 템플릿
│   ├── base.html           # 공통 레이아웃
│   ├── dashboard.html      # 데이터셋 목록 (회사별 탭)
│   ├── upload.html         # 파일 업로드
│   ├── visualize.html      # 차트 생성
│   ├── template_analysis.html   # 템플릿 분석 메인(업로드 + 이력)
│   ├── _template_history.html   # 템플릿 업로드 이력 부분 템플릿
│   └── ocr_scan.html       # OCR 스캔
├── static/                 # CSS, 이미지 등 정적 파일
├── sql/                    # DB 스키마
│   ├── schema_sqlite.sql
│   └── schema_postgresql.sql
├── templates_data/         # 샘플 Excel 템플릿
└── docs/                   # 기획/QA 문서
```

## 로컬 개발 환경 설정

### 1. 저장소 클론

```bash
git clone https://github.com/luda-data-ai-lab/analytics_platform
cd analytics_platform
```

### 2. 가상환경 생성 및 패키지 설치

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 3. 환경 변수 설정

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"   # 생성된 값을 SECRET_KEY 에 붙여넣기
```

루트의 `.env` 는 실행 시 자동으로 읽힙니다(python-dotenv). 이미 설정된 셸 환경변수가 `.env` 값보다 우선합니다.

### 4. DB 스키마 생성

```bash
flask db upgrade        # migrations/ 기준으로 테이블 생성·갱신 (FLASK_APP=app.py)
python init_db.py       # 2번: 샘플 사용자, 3번: 샘플 데이터 (개발용 시드)
```

이미 `init_db.py` 로 만들어둔 DB라면 한 번만 `flask db stamp head` 로 현재 리버전을 기록하세요. 이후 모델 변경은 `flask db migrate -m "..."` → `flask db upgrade` 로 반영합니다.

### 5. 앱 실행

```bash
python app.py
```

브라우저에서 `http://localhost:5000` 접속

## 환경 변수 (프로덕션)

| 변수 | 설명 | 예시 |
|------|------|------|
| `SECRET_KEY` | Flask 세션 암호화 키 | 랜덤 64자 문자열 |
| `DATABASE_URL` | DB 접속 URL | `postgresql+psycopg2://user:pw@host/db` |

> `postgresql://` 처럼 드라이버를 생략해도 psycopg2 로 자동 보정됩니다. psycopg3 를 쓰려면
> `postgresql+psycopg://` 를 명시하고 `pip install "psycopg[binary]"` 를 함께 설치하세요.

`.env` 파일 예시 (자동으로 로드됨, 추적 제외 대상):
```
SECRET_KEY=your-strong-secret-key
DATABASE_URL=postgresql+psycopg2://postgres:password@localhost/analytics_db
```

## DB 설정

### 로컬 개발 (SQLite — 기본값)
별도 설치 없이 바로 사용 가능. `analytics.db` 파일이 자동 생성됩니다.

### 프로덕션 (PostgreSQL)
1. PostgreSQL 설치 및 DB 생성:
   ```sql
   CREATE DATABASE analytics_db;
   ```
2. `.env` 에 `DATABASE_URL` 지정
3. 스키마 적용:
   ```bash
   flask db upgrade
   ```

## 라이선스

LUDA Data AI Lab
