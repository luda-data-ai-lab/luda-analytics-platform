# Analytics Platform - 요구사항 정의서

## 프로젝트 개요
- **시스템명**: Analytics Platform (템플릿 기반 자동 분석 시스템)
- **기술스택**: Flask, MySQL, SQLAlchemy, Pandas, Plotly, Bootstrap 5
- **언어**: 한국어/영어 다국어 지원
- **점검일**: 2026-04-17

---

## 현재 구현된 기능 (AS-IS)

### 기능 1: 사용자 인증
- 회원가입 (이메일, 비밀번호, 이름, 회사명)
- 로그인/로그아웃
- 세션 관리 (24시간)

### 기능 2: 범용 데이터 분석
- CSV/Excel 파일 업로드
- 사용자가 차트 타입, X축, Y축 직접 선택
- 개별 차트 생성 (Bar, Line, Scatter, Pie, Histogram)
- 파이차트 Y축 선택사항 처리 (빈도수 자동 계산)
- 날짜 축 자동 감지 및 변환

### 기능 3: 템플릿 기반 자동 분석
- 정형화된 Excel 템플릿 다운로드
- 파일 업로드만으로 자동 대시보드 생성
- 주요 지표 4개 자동 계산 (총 매출, 총 판매량, 총 이익, 레코드 수)
- 차트 6개 자동 생성 (일별 매출 추이, 지역별 매출, 제품별 판매 비율, 카테고리별 매출, 판매량 vs 매출, 일별 평균 판매량)

### 기능 4: OCR 데이터 추출
- 이미지/PDF 업로드
- 텍스트/표 자동 인식
- 추출 데이터 검증 및 저장

---

## 신규/수정 요구사항 (TO-BE)

### [REQ-01] 회사명 기반 데이터 구분 (필수)
- **현황**: 회원가입 시 회사명 입력 완료, DB에 저장됨
- **문제**: 데이터 조회 시 user_id로만 필터링 → 회사 단위 집계 불가
- **요구사항**:
  - 대시보드에서 동일 회사 소속 사용자 데이터 통합 조회 옵션
  - 데이터 업로드 시 company 태그 자동 연결
  - 관리자/일반 사용자 구분 권한 고려

### [REQ-02] Iindex.txt 항목 처리
- [완료] 회원가입시 회사명 추가 → User.company 필드 구현됨
- [미완료] 데이터 load시 회사명으로 구분 → 대시보드/조회 로직 수정 필요

### [REQ-03] 코드 품질 점검 (권장)
- 중복 import 제거 (app.py 상단에 werkzeug import 2회)
- 중복 datetime import 제거
- 불필요 템플릿 파일 정리 (visualize_0.html, visualize_1.html, base_old.html 등)
- models_old.py 삭제 검토

---

## 데이터 모델

### User
| 필드 | 타입 | 설명 |
|------|------|------|
| id | Integer | PK |
| email | String(120) | 이메일 (unique) |
| password_hash | String(255) | 암호화 비밀번호 |
| name | String(100) | 사용자명 |
| company | String(100) | 회사명 |
| created_at | DateTime | 가입일 |

### Dataset
| 필드 | 타입 | 설명 |
|------|------|------|
| id | Integer | PK |
| name | String(200) | 데이터셋명 |
| user_id | Integer | FK (users) |
| is_template | Boolean | 템플릿 여부 |
| is_ocr | Boolean | OCR 여부 |
