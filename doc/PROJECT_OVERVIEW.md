# 데이터 분석 플랫폼 - 프로젝트 개요

## 🎯 프로젝트 목표

쉽게 이용 가능한 데이터 분석 플랫폼을 구축하여, 비전문가도 손쉽게 데이터를 업로드하고 시각화할 수 있도록 합니다.

## 📦 제공된 파일 목록

### 핵심 파일
- `app.py` - Flask 메인 애플리케이션 (모든 라우트와 비즈니스 로직)
- `models.py` - 데이터베이스 모델 정의 (User, Dataset, DataRecord, DataView)
- `config.py` - 애플리케이션 설정
- `requirements.txt` - Python 패키지 의존성

### HTML 템플릿
- `templates/base.html` - 기본 레이아웃 (네비게이션, 푸터 포함)
- `templates/index.html` - 메인 랜딩 페이지
- `templates/register.html` - 회원가입 페이지
- `templates/login.html` - 로그인 페이지
- `templates/dashboard.html` - 사용자 대시보드
- `templates/upload.html` - 파일 업로드 페이지
- `templates/view_dataset.html` - 데이터 테이블 보기
- `templates/visualize.html` - 데이터 시각화 페이지

### 스타일 및 리소스
- `static/css/style.css` - 커스텀 CSS 스타일
- `static/uploads/` - 업로드된 파일 저장 디렉토리

### 문서
- `README.md` - 상세 프로젝트 문서
- `QUICKSTART.md` - 빠른 시작 가이드
- `sample_data.xlsx` - 테스트용 샘플 데이터

### 실행 스크립트
- `run.bat` - Windows용 실행 스크립트
- `run.sh` - Linux/Mac용 실행 스크립트

### 설정 파일
- `.env.example` - 환경 변수 예시
- `.gitignore` - Git 무시 파일 목록

## ✨ 구현된 주요 기능

### 1. 사용자 인증
- ✅ 이메일 기반 회원가입
- ✅ 로그인/로그아웃
- ✅ 세션 관리 (Flask-Login)
- ✅ 비밀번호 해시화 (Werkzeug)

### 2. 데이터 관리
- ✅ 엑셀(.xlsx, .xls) 파일 업로드
- ✅ CSV 파일 업로드
- ✅ 자동 파일 검증
- ✅ 데이터베이스 자동 저장
- ✅ 데이터셋 메타데이터 관리

### 3. 데이터 보기
- ✅ 테이블 형태로 데이터 표시
- ✅ 최대 100행 미리보기
- ✅ 반응형 테이블 (스크롤 가능)
- ✅ 행/열 개수 통계 표시

### 4. 데이터 시각화
- ✅ 라인 차트 - 시간 추이 분석
- ✅ 바 차트 - 카테고리별 비교
- ✅ 산점도 - 변수 간 상관관계
- ✅ 파이 차트 - 비율 분석
- ✅ 히스토그램 - 데이터 분포
- ✅ 인터랙티브 차트 (Plotly.js)
- ✅ 실시간 차트 생성

### 5. UI/UX
- ✅ 반응형 디자인 (Bootstrap 5)
- ✅ 직관적인 네비게이션
- ✅ 아이콘 사용 (Bootstrap Icons)
- ✅ Flash 메시지로 사용자 피드백
- ✅ 로딩 인디케이터
- ✅ 깔끔하고 현대적인 디자인

## 🏗 시스템 아키텍처

```
┌─────────────────┐
│   프론트엔드     │
│  (HTML/CSS/JS)  │
│   Bootstrap 5   │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│   Flask 백엔드   │
│  - 라우팅        │
│  - 인증          │
│  - 파일 처리     │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│   데이터 계층    │
│  - SQLAlchemy   │
│  - Pandas       │
│  - Plotly       │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│   데이터베이스   │
│ SQLite/MySQL    │
└─────────────────┘
```

## 📊 데이터베이스 스키마

### Users 테이블
- id (PK)
- email (Unique)
- password_hash
- name
- created_at
- last_login

### Datasets 테이블
- id (PK)
- name
- description
- filename
- file_path
- user_id (FK → Users)
- uploaded_at
- row_count
- column_count

### DataRecords 테이블
- id (PK)
- dataset_id (FK → Datasets)
- data (JSON)
- created_at

### DataViews 테이블 (향후 확장용)
- id (PK)
- name
- dataset_id (FK → Datasets)
- user_id (FK → Users)
- view_config (JSON)
- created_at

## 🔒 보안 기능

- ✅ 비밀번호 해시화 (bcrypt via Werkzeug)
- ✅ CSRF 보호 (Flask-WTF)
- ✅ 파일 형식 검증
- ✅ 파일 크기 제한 (16MB)
- ✅ 세션 보안
- ✅ SQL 인젝션 방지 (SQLAlchemy ORM)

## 🚀 배포 준비사항

### 개발 환경
- ✅ SQLite 데이터베이스
- ✅ 디버그 모드
- ✅ 로컬 파일 저장

### 운영 환경 고려사항
- 🔄 MySQL/PostgreSQL 전환
- 🔄 환경 변수 설정
- 🔄 HTTPS 적용
- 🔄 Nginx/Gunicorn 설정
- 🔄 AWS S3/GCS 파일 저장
- 🔄 로깅 시스템

## 📈 성능 최적화

- ✅ 데이터 페이지네이션 (100행 제한)
- ✅ 정적 파일 캐싱
- ✅ 데이터베이스 인덱싱
- ✅ JSON 형태 데이터 저장 (빠른 조회)

## 🎨 UI 특징

### 색상 테마
- Primary: #0d6efd (파란색)
- Success: #198754 (녹색)
- Danger: #dc3545 (빨간색)
- Warning: #ffc107 (노란색)

### 주요 컴포넌트
- 카드 기반 레이아웃
- 그림자 효과
- 호버 애니메이션
- 아이콘 통합
- 반응형 그리드

## 💻 브라우저 호환성

- ✅ Chrome (최신)
- ✅ Firefox (최신)
- ✅ Safari (최신)
- ✅ Edge (최신)
- ⚠️ IE11 (제한적 지원)

## 📱 모바일 지원

- ✅ 반응형 레이아웃
- ✅ 터치 친화적 UI
- ✅ 모바일 네비게이션
- ✅ 작은 화면 최적화

## 🔧 확장 가능성

### 2단계 계획 (준비됨)
- AI 기반 데이터 분석
- ML 모델 통합
- 이미지 분석
- 고급 통계 분석

### 가능한 추가 기능
- 데이터 공유 및 협업
- 대시보드 커스터마이징
- 데이터 필터링 및 정렬
- 엑셀 내보내기
- PDF 리포트 생성
- 이메일 알림
- API 제공

## 📝 코드 품질

- ✅ PEP 8 스타일 가이드 준수
- ✅ 명확한 함수/변수명
- ✅ 주석 포함
- ✅ 에러 핸들링
- ✅ 로깅 준비

## 🎓 학습 포인트

이 프로젝트를 통해 배울 수 있는 것:
1. Flask 웹 애플리케이션 개발
2. 데이터베이스 모델링 (ORM)
3. 사용자 인증 시스템
4. 파일 업로드 처리
5. 데이터 시각화 (Plotly)
6. 반응형 웹 디자인 (Bootstrap)
7. RESTful API 설계
8. 프론트엔드-백엔드 통신

## 🤝 기여 가이드

1. 이슈 등록
2. 기능 제안
3. 버그 리포트
4. 문서 개선
5. 코드 리뷰

## 📚 참고 자료

- Flask: https://flask.palletsprojects.com/
- SQLAlchemy: https://www.sqlalchemy.org/
- Plotly: https://plotly.com/python/
- Bootstrap: https://getbootstrap.com/
- Pandas: https://pandas.pydata.org/

---

**프로젝트 완성도: 1단계 100% 완료** ✅

**다음 단계: AI 통합 및 고급 분석 기능 추가**
