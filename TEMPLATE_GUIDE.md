# 템플릿 기반 자동 분석 기능 추가 가이드

## 📋 개요

이 업데이트는 기존 분석 플랫폼에 **템플릿 기반 자동 분석** 기능을 추가합니다.

### 주요 기능
1. **샘플 Excel 템플릿 다운로드**: 정형화된 데이터 구조 제공
2. **자동 테이블 생성**: 업로드된 데이터로 자동 DB 생성
3. **자동 대시보드 생성**: 6가지 정형화된 차트 자동 생성
4. **주요 지표 계산**: 매출, 이익, 판매량 등 자동 집계

## 📁 파일 구조

```
analytics_platform/
├── app.py                          # 업데이트됨 (템플릿 라우트 추가)
├── models.py                       # 업데이트됨 (is_template 필드 추가)
├── requirements.txt                # 업데이트됨 (openpyxl 추가)
├── templates/
│   ├── base.html                  # 업데이트됨 (템플릿 메뉴 추가)
│   ├── visualize.html             # 업데이트됨 (파이차트 Y축 선택사항)
│   ├── template_dashboard.html    # 신규 (템플릿 메인 화면)
│   └── template_analysis.html     # 신규 (자동 대시보드)
└── uploads/                       # 업로드된 파일 저장
```

## 🚀 설치 방법

### 1. 파일 배치

다운로드한 파일들을 다음과 같이 배치하세요:

```bash
# Python 파일
app.py → analytics_platform/app.py (기존 파일 백업 후 교체)
models.py → analytics_platform/models.py (기존 파일 백업 후 교체)

# HTML 템플릿
base.html → analytics_platform/templates/base.html (기존 파일 백업 후 교체)
visualize.html → analytics_platform/templates/visualize.html (기존 파일 백업 후 교체)
template_dashboard.html → analytics_platform/templates/template_dashboard.html (신규)
template_analysis.html → analytics_platform/templates/template_analysis.html (신규)

# 의존성
requirements.txt → analytics_platform/requirements.txt (기존 파일 백업 후 교체)
```

### 2. 의존성 설치

```bash
cd analytics_platform
pip install -r requirements.txt
```

또는 추가된 패키지만 설치:
```bash
pip install openpyxl==3.1.2
```

### 3. 데이터베이스 마이그레이션

**중요:** models.py에 `is_template` 필드가 추가되었습니다.

#### 방법 A: 새로 시작 (데이터 손실)
```bash
# 기존 DB 삭제
rm instance/analytics.db

# 앱 실행 (DB 자동 생성)
python app.py
```

#### 방법 B: 기존 데이터 유지 (SQLite)
```bash
# SQLite 접속
sqlite3 instance/analytics.db

# 컬럼 추가
ALTER TABLE datasets ADD COLUMN is_template BOOLEAN DEFAULT 0;

# 종료
.exit
```

#### 방법 C: MySQL 사용 시
```sql
USE analytics_db;
ALTER TABLE datasets ADD COLUMN is_template BOOLEAN DEFAULT FALSE;
```

### 4. 앱 실행

```bash
python app.py
```

서버가 시작되면: http://localhost:5000

## 📊 사용 방법

### 1단계: 템플릿 메뉴 접속
- 상단 네비게이션에서 **"템플릿 분석"** 클릭

### 2단계: 샘플 다운로드
- **"1. 샘플 템플릿 다운로드"** 버튼 클릭
- `sales_template_sample.xlsx` 파일 다운로드
- 파일을 열어서 데이터 구조 확인

### 3단계: 데이터 준비
샘플 템플릿과 동일한 구조로 데이터 준비:

| 컬럼명 | 설명 | 예시 |
|--------|------|------|
| 날짜 | YYYY-MM-DD 형식 | 2024-01-01 |
| 지역 | 지역명 | 서울 |
| 제품 | 제품명 | 노트북 |
| 카테고리 | 카테고리명 | 전자기기 |
| 판매량 | 숫자 | 5 |
| 매출액 | 숫자 | 5000000 |
| 비용 | 숫자 | 3500000 |

### 4단계: 업로드
- **"2. 데이터 파일 업로드"** 섹션에서 파일 선택
- **"업로드 및 분석"** 버튼 클릭

### 5단계: 대시보드 확인
자동으로 생성되는 대시보드 내용:

#### 주요 지표 카드 (4개)
- 💰 총 매출액
- 📦 총 판매량
- 💵 총 이익
- 📊 총 레코드 수

#### 차트 (6개)
1. **일별 매출 추이** - 라인 차트
2. **지역별 매출** - 바 차트
3. **제품별 판매 비율** - 파이 차트
4. **카테고리별 매출** - 바 차트
5. **판매량 vs 매출액 관계** - 산점도 (추세선 포함)
6. **일별 평균 판매량** - 라인 차트

#### 데이터 테이블
- 원본 데이터 (처음 100행)

## 🔧 주요 변경사항

### app.py 추가 내용
```python
# 새로운 라우트
@app.route('/template')                          # 템플릿 메인
@app.route('/template/download_sample')          # 샘플 다운로드
@app.route('/template/upload')                   # 업로드
@app.route('/template/analysis/<int:id>')        # 대시보드

# 새로운 함수
def generate_template_charts(df)  # 자동 차트 생성
def calculate_metrics(df)         # 지표 계산
```

### models.py 변경
```python
class Dataset(db.Model):
    # ... 기존 필드들 ...
    is_template = db.Column(db.Boolean, default=False)  # 신규 추가
```

### visualize.html 개선
- 파이 차트에서 Y축 선택사항으로 변경
- Y축 없으면 자동으로 빈도수 계산
- 차트 타입별 도움말 추가

## 🎯 기능 비교

| 기능 | 기존 분석 | 템플릿 분석 |
|------|-----------|-------------|
| 파일 업로드 | ✅ | ✅ |
| 차트 타입 선택 | 수동 | 자동 |
| 축 선택 | 수동 | 자동 |
| 차트 개수 | 1개씩 생성 | 6개 자동 생성 |
| 주요 지표 | 없음 | 자동 계산 |
| 대시보드 | 없음 | 자동 생성 |

## 📝 샘플 데이터 구조

다운로드한 템플릿에는 90일간 약 400-700건의 판매 데이터가 포함되어 있습니다:

```
날짜         지역   제품      카테고리    판매량  매출액      비용
2024-01-01  서울   노트북    전자기기    5      10000000    7000000
2024-01-01  경기   스마트폰  전자기기    10     8000000     5600000
2024-01-02  부산   태블릿    전자기기    3      4500000     3150000
...
```

## ⚠️ 주의사항

1. **데이터 구조**: 템플릿과 컬럼명이 정확히 일치해야 합니다
2. **날짜 형식**: YYYY-MM-DD 형식 사용 (예: 2024-01-01)
3. **숫자 데이터**: 판매량, 매출액, 비용은 숫자만 입력
4. **파일 크기**: 대용량 파일은 처리 시간이 오래 걸릴 수 있습니다

## 🔍 트러블슈팅

### 문제: "컬럼을 찾을 수 없습니다" 오류
**해결**: 템플릿의 컬럼명과 정확히 일치하는지 확인

### 문제: 차트가 일부만 표시됨
**해결**: 해당 컬럼의 데이터가 있는지 확인

### 문제: 날짜 차트가 이상함
**해결**: 날짜 형식이 YYYY-MM-DD인지 확인

### 문제: is_template 컬럼 오류
**해결**: 데이터베이스 마이그레이션 재실행

```bash
# SQLite
sqlite3 instance/analytics.db
ALTER TABLE datasets ADD COLUMN is_template BOOLEAN DEFAULT 0;
.exit
```

## 📞 문의

문제가 발생하면 다음을 확인하세요:
1. Python 버전: 3.8 이상
2. 모든 의존성 설치 확인
3. 데이터베이스 마이그레이션 완료 여부
4. 브라우저 콘솔 오류 메시지

## 🎉 완료!

이제 템플릿 기반 자동 분석 기능을 사용할 수 있습니다!

웹 브라우저에서 http://localhost:5000 접속 후:
1. 로그인
2. 상단 메뉴 "템플릿 분석" 클릭
3. 샘플 다운로드
4. 파일 업로드
5. 자동 생성된 대시보드 확인!
