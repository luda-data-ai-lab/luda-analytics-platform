# 📊 Analytics Platform - 템플릿 기반 자동 분석 시스템

lu_dag@lincolnuni.ac.nz/a12345

## 🎯 전체 시스템 구성

### 기능 1: 범용 데이터 분석 (기존)
- CSV/Excel 파일 업로드
- 사용자가 직접 차트 타입, X축, Y축 선택
- 개별 차트 생성
- **장점**: 자유로운 분석
- **단점**: 매번 설정 필요

### 기능 2: 템플릿 기반 자동 분석 (신규) ⭐
- 정형화된 Excel 템플릿 사용
- 파일 업로드만으로 자동 대시보드 생성
- 6개 차트 + 4개 주요 지표 자동 생성
- **장점**: 빠른 인사이트, 일관된 분석
- **단점**: 템플릿 구조 준수 필요

## 📦 제공 파일

### 1. 백엔드 파일
```
app.py (41KB)
├── 기존 기능 (범용 분석)
│   ├── 업로드
│   ├── 데이터 조회
│   └── 차트 생성 API
└── 신규 기능 (템플릿 분석)
    ├── 템플릿 다운로드
    ├── 자동 분석
    └── 대시보드 생성

models.py (2.6KB)
└── Dataset 모델에 is_template 필드 추가

requirements.txt (173B)
└── openpyxl 추가 (Excel 생성용)
```

### 2. 프론트엔드 파일
```
templates/
├── base.html (5.7KB)
│   └── 네비게이션에 "템플릿 분석" 메뉴 추가
│
├── visualize.html (15KB)
│   └── 파이 차트 Y축 선택사항 처리 개선
│
├── template_dashboard.html (8.4KB) ⭐ 신규
│   ├── 샘플 템플릿 다운로드
│   ├── 파일 업로드
│   └── 이전 분석 목록
│
└── template_analysis.html (9.0KB) ⭐ 신규
    ├── 주요 지표 카드 4개
    ├── 자동 생성 차트 6개
    └── 원본 데이터 테이블
```

### 3. 문서
```
TEMPLATE_GUIDE.md (7.2KB)
└── 설치 및 사용 가이드
```

## 🚀 빠른 시작

### 1단계: 파일 배치
```bash
# 프로젝트 구조 확인
analytics_platform/
├── app.py
├── models.py
├── requirements.txt
├── templates/
│   ├── base.html
│   ├── visualize.html
│   ├── template_dashboard.html
│   └── template_analysis.html
└── instance/
    └── analytics.db
```

### 2단계: 설치
```bash
pip install -r requirements.txt
```

### 3단계: DB 업데이트
```bash
# 방법 A: 새로 시작
rm instance/analytics.db
python app.py

# 방법 B: 기존 유지
sqlite3 instance/analytics.db
ALTER TABLE datasets ADD COLUMN is_template BOOLEAN DEFAULT 0;
.exit
```

### 4단계: 실행
```bash
python app.py
# → http://localhost:5000
```

## 📊 자동 생성 대시보드 미리보기

업로드 즉시 생성되는 콘텐츠:

### 📈 주요 지표 (4개 카드)
```
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│ 💰 총 매출액     │ │ 📦 총 판매량     │ │ 💵 총 이익       │ │ 📊 레코드 수     │
│                │ │                │ │                │ │                │
│ 450,000,000원  │ │ 1,234개        │ │ 90,000,000원   │ │ 543건          │
│ 평균: 828,342원 │ │ 평균: 2.3개    │ │ 마진: 20%      │ │ 제품: 5개      │
└─────────────────┘ └─────────────────┘ └─────────────────┘ └─────────────────┘
```

### 📉 차트 (6개)

1. **일별 매출 추이** (Line Chart)
   - 시간에 따른 매출 변화 추적

2. **지역별 매출** (Bar Chart)
   - 어느 지역이 매출이 높은지 비교

3. **제품별 판매 비율** (Pie Chart)
   - 제품별 판매 비중 확인

4. **카테고리별 매출** (Bar Chart)
   - 카테고리 성과 비교

5. **판매량 vs 매출액** (Scatter Plot)
   - 상관관계 분석 (추세선 포함)

6. **일별 평균 판매량** (Line Chart)
   - 판매 패턴 분석

### 📋 데이터 테이블
- 원본 데이터 처음 100행 표시

## 🎨 주요 개선사항

### 1. 파이 차트 개선
```javascript
// 이전: Y축 필수
선택: X축(카테고리), Y축(값) - 필수

// 개선: Y축 선택사항
선택: X축(카테고리), Y축(값) - 선택사항
- Y축 있음 → 값 합계로 파이 차트
- Y축 없음 → 빈도수로 파이 차트
```

### 2. 날짜 축 지원
```python
# 자동 감지
- 문자열 "2024-01-01" → 날짜로 변환
- 숫자 336 → 숫자 유지 (날짜로 변환 안함)

# 차트에 자동 적용
- X축이 날짜 → type='date' 설정
- Y축이 날짜 → type='date' 설정
```

### 3. 모든 차트 타입 JSON 직렬화
```python
# 처리 대상
- x, y (라인/바/산점도)
- labels, values (파이 차트)
- 히스토그램 특수 처리

# numpy array → list 변환
- 모든 ndarray 자동 변환
- JSON 직렬화 오류 방지
```

## 📸 사용 시나리오

### 시나리오 1: 영업팀 주간 리포트
```
1. 월요일: 샘플 템플릿 다운로드
2. 화요일: 주간 판매 데이터 입력
3. 수요일: 파일 업로드
4. 즉시: 대시보드 생성 완료!
5. 목요일: 팀 미팅에서 리포트 공유
```

### 시나리오 2: 마케팅 캠페인 분석
```
1. 캠페인 전: 베이스라인 데이터 업로드
2. 캠페인 중: 주간 데이터 업로드
3. 캠페인 후: 최종 데이터 업로드
4. 결과: 시계열 대시보드로 효과 측정
```

### 시나리오 3: 지역별 성과 비교
```
1. 전국 판매 데이터 수집
2. 템플릿에 입력
3. 업로드
4. 즉시: 지역별 성과 시각화
5. 인사이트: 어느 지역에 집중할지 결정
```

## 🔐 데이터 보안

- 각 사용자별 독립된 데이터 공간
- 로그인 필수
- 업로드 파일 사용자별 분리
- 삭제 시 관련 데이터 완전 제거

## 📱 반응형 디자인

- Bootstrap 5 기반
- 모바일, 태블릿, 데스크톱 최적화
- Plotly 차트 자동 크기 조절

## 🌍 다국어 지원

- 한국어/영어 지원
- 실시간 언어 전환
- UI, 메시지, 차트 제목 모두 번역

## 📈 성능

- 대용량 파일 처리 (수천 행)
- 차트 캐싱
- 효율적인 DB 쿼리
- 비동기 처리 준비 완료

## 🛠 커스터마이징

### 템플릿 구조 변경
`app.py`의 `generate_template_charts()` 함수 수정:
```python
def generate_template_charts(df):
    charts = {}
    
    # 원하는 차트 추가
    if '새컬럼' in df.columns:
        fig = px.bar(df, x='새컬럼', y='값')
        charts['new_chart'] = json.dumps(fig.to_dict())
    
    return charts
```

### 지표 추가
`calculate_metrics()` 함수 수정:
```python
def calculate_metrics(df):
    metrics = {}
    
    # 새 지표 추가
    metrics['new_metric'] = df['컬럼'].sum()
    
    return metrics
```

## 🆘 도움말

문제가 생기면:
1. `TEMPLATE_GUIDE.md` 확인
2. 브라우저 개발자 도구 콘솔 확인
3. 서버 터미널 로그 확인

## 📞 다음 단계

시스템 확장 아이디어:
- [ ] 더 많은 템플릿 타입 (재고, HR, 재무 등)
- [ ] 대시보드 PDF 내보내기
- [ ] 예측 분석 추가
- [ ] 실시간 데이터 연동
- [ ] 팀 공유 기능

## ✨ 완료!

모든 파일이 준비되었습니다:

1. ✅ app.py - 백엔드 로직
2. ✅ models.py - DB 모델
3. ✅ requirements.txt - 의존성
4. ✅ base.html - 네비게이션
5. ✅ visualize.html - 개선된 차트 생성
6. ✅ template_dashboard.html - 템플릿 메인
7. ✅ template_analysis.html - 자동 대시보드
8. ✅ TEMPLATE_GUIDE.md - 설치 가이드

**이제 시작하세요!** 🎉
