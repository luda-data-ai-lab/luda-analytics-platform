# Analysis Platform — 작업 변경 이력

---

## 2026-04-18

### 1. renderChart() 이중 파싱 버그 수정
**파일:** `templates/template_result.html`

**문제:** `generate_template_charts()`에서 `json.dumps(fig.to_dict())`로 JSON 문자열을 생성하고, Jinja2 `| safe` 필터로 렌더링하면 JS 엔진이 이미 객체로 평가함. 그런데 `renderChart()`에서 `JSON.parse()`를 다시 호출해 `TypeError` 발생 → 차트 미표시.

**수정:**
```js
// Before
function renderChart(divId, chartJson) {
    const fig = JSON.parse(chartJson);  // 이미 객체인데 재파싱 → 오류
    Plotly.newPlot(divId, fig.data, fig.layout, {responsive: true});
}

// After
function renderChart(divId, chartData) {
    Plotly.newPlot(divId, chartData.data, chartData.layout, {responsive: true});
}
```

---

### 2. numpy/NaN 직렬화 오류 수정
**파일:** `app.py` (`template_analyze()`), `init_db.py` (`create_sample_data()`)

**문제:** `pandas` `row.to_dict()`가 numpy int64/float64 타입과 NaN 값을 반환하여 PostgreSQL JSON 컬럼 저장 실패.

**수정:** DataRecord 저장 시 numpy 타입 → Python 기본형 변환, NaN → None 치환
```python
for k, v in row.to_dict().items():
    if hasattr(v, 'item'):
        v = v.item()          # numpy → Python 기본형
    if isinstance(v, float) and math.isnan(v):
        v = None              # NaN → None
    clean[k] = v
db.session.add(DataRecord(dataset_id=dataset.id, data=clean))
```

---

### 3. visualize() columns=None 방어 처리
**파일:** `app.py` (`visualize()`)

**문제:** `dataset.columns or []` 표현식에서 간헐적으로 `None` 전달되어 `template`에서 `TypeError`.

**수정:**
```python
columns = dataset.columns if dataset.columns is not None else []
return render_template('visualize.html', dataset=dataset, columns=columns)
```

---

### 4. 4개 템플릿 차트 자동 감지 및 전용 차트 생성
**파일:** `app.py`

**문제:** `generate_template_charts()`가 판매 데이터 컬럼만 지원 → 곡물/마케팅/고객 데이터 업로드 시 "생성된 차트가 없습니다" 표시.

**수정 내용:**

#### COLUMN_MAP 확장 (4개 템플릿 전체)
```python
COLUMN_MAP = {
    # 판매: Date, Revenue, Region, Product, Category, Quantity, Cost
    # 곡물: Crop_Type, Soil_Type, Climate, Rainfall_mm, Temperature_C, Fertilizer_kg, Irrigation_hours, Crop_Yield_kg
    # 마케팅: Channel, Campaign_Name, Start_Date, Budget, Impressions, Clicks, Conversions, Revenue
    # 고객: Age, Gender, Income, Segment, Total_Purchases, Avg_Purchase_Value, Last_Purchase_Days
}
```

#### `_detect_template_type(df)` 추가
컬럼명 패턴으로 템플릿 유형 자동 감지 (sales / crop / marketing / customer / generic)

#### 전용 차트 함수 분리
| 함수 | 대상 |
|------|------|
| `_charts_sales()` | 판매 데이터 |
| `_charts_crop()` | 곡물 생산량 |
| `_charts_marketing()` | 마케팅 캠페인 |
| `_charts_customer()` | 고객 분석 |
| `_charts_generic()` | 미인식 데이터 (fallback) |

#### `calculate_metrics()` 4개 템플릿 확장
각 템플릿별 핵심 지표 계산 (수확량, ROI, 전환수, 구매금액 등)

---

### 5. 예시 페이지 4개 전체 활성화
**파일:** `app.py`, `templates/examples.html`

**추가:** `/example/<template_type>` 공통 라우트
- `templates_data/` CSV를 직접 읽어 `generate_template_charts()` + `calculate_metrics()` 실행
- `template_result.html` 재사용 (별도 HTML 불필요)
- `types.SimpleNamespace`로 fake dataset 객체 생성

**수정:** `examples.html`에서 판매/고객/마케팅 3개 카드를 "준비 중" → "사용 가능"으로 변경, 예시 보기 버튼 활성화

---

### 6. 각 템플릿 차트 유형 개선
**파일:** `app.py` (`_charts_*` 함수 전체 재작성)

| 템플릿 | 차트 슬롯 | 이전 | 변경 후 |
|--------|-----------|------|---------|
| **판매** | daily_sales | 일별 라인 | 월별 매출 vs 비용 그룹 바 |
| | region_sales | 수직 바 | **수평 바** (내림차순) |
| | product_distribution | 파이 | **도넛** (매출 기준) |
| | category_sales | 바 | 바 + text_auto |
| | quantity_revenue | 산점도 | 산점도 (제품별 색상) |
| | daily_quantity | 라인 | **제품별 이익률(%) 수평 바** |
| **곡물** | daily_sales | 평균 바 | **박스플롯** (분포) |
| | region_sales | 평균 바 | **기후×토양 히트맵** |
| | product_distribution | 파이 | 도넛 |
| | category_sales | 평균 바 | **바이올린 플롯** |
| | quantity_revenue | 산점도 | 산점도 (마커 크기 = 비료량) |
| | daily_quantity | 산점도 | **기온 vs 수확량 산점도** |
| **마케팅** | daily_sales | 라인 | **월별 매출 vs 예산 그룹 바** |
| | region_sales | 바 | **채널별 ROI(%) 수평 바** |
| | product_distribution | 파이 | **채널별 예산 배분 도넛** |
| | category_sales | 바 | **채널별 전환율(%) 수평 바** |
| | quantity_revenue | 산점도 | **예산 vs 매출 버블 차트** (크기=노출수) |
| | daily_quantity | 산점도 | **채널별 마케팅 퍼널** (노출→클릭→전환) |
| **고객** | daily_sales | 히스토그램 | **연령×세그먼트 히스토그램** (오버레이) |
| | region_sales | 바 | **세그먼트별 총 구매금액 수평 바** |
| | product_distribution | 파이 | **성별 구매금액 비중 도넛** |
| | category_sales | 바 | **세그먼트별 구매금액 박스플롯** |
| | quantity_revenue | 산점도 | 산점도 (마커 크기 = 구매횟수) |
| | daily_quantity | 산점도 | **구매 주기(Last_Purchase_Days) 히스토그램** |

---

### 7. 차트별 데이터 기반 인사이트 텍스트 추가
**파일:** `app.py`, `templates/template_result.html`

**추가 함수:**
- `generate_insights(df)` — 템플릿 유형 감지 후 차트별 분석 텍스트 딕셔너리 반환
- `_insights_sales()`, `_insights_crop()`, `_insights_marketing()`, `_insights_customer()`

**인사이트 내용 (예시):**
- 판매: 최고/최저 매출 월, 지역별 매출 비중, 제품 이익률 비교
- 곡물: 최적 작물/기후/토양 조합, 강수량·기온 상관계수
- 마케팅: 채널별 ROI, 전환율 순위, 퍼널 이탈 분석
- 고객: 핵심 연령대, 세그먼트별 구매 패턴, 이탈 위험 고객 비율

**template_result.html 구조 변경:**
```html
<div class="card border-0 shadow-sm h-100">
    <div class="card-body p-2" id="{{ div_id }}"></div>
    <!-- TODO: Claude API 연동 후 이 블록을 API 응답으로 교체 -->
    <div class="card-footer bg-light border-0 insight-box" data-chart="{{ key }}">
        <small><i class="bi bi-lightbulb-fill text-warning"></i> {{ insights[key] | safe }}</small>
    </div>
</div>
```

**Claude API 연동 준비 사항:**
- 각 `insight-box`에 `data-chart="<chart_key>"` 속성 포함
- 향후 `/api/insight/<dataset_id>/<chart_key>` 엔드포인트 생성 후 AJAX로 교체 예정
- `app.py`에 `# TODO: 추후 Claude API 연동으로 교체 예정` 주석 마킹

---

### 8. px.bar grouped barmode KeyError 수정
**파일:** `app.py` (`_charts_sales()`, `_charts_marketing()`)

**문제:** `px.bar(..., y=[col_revenue, col_cost])` wide 형식으로 전달 시 plotly express 내부에서 `KeyError: 'Revenue'` 발생. grouped bar는 long 형식 데이터가 필요.

**수정:** `DataFrame.melt()`로 wide → long 변환 후 `color='항목'`으로 그룹핑
```python
# Before
monthly = df.groupby('_month')[[col_revenue, col_cost]].sum().reset_index()
fig = px.bar(monthly, x='_month', y=[col_revenue, col_cost], barmode='group')

# After
monthly_long = monthly.melt(id_vars='_month', value_vars=[col_revenue, col_cost],
                             var_name='항목', value_name='금액')
fig = px.bar(monthly_long, x='_month', y='금액', color='항목', barmode='group')
```
**동일 수정 적용:** `_charts_marketing()`의 "월별 매출 vs 예산" 차트

---

### 9-10. px.* + color KeyError / ndarray JSON 직렬화 오류 — 전면 수정
**파일:** `app.py` (`_charts_customer()`)

**문제:** `px.histogram(color=col_seg)` 사용 시 plotly express 내부 `get_groups_and_orders()`에서 `KeyError: 'Premium'` 발생. `barmode` 변경(`overlay`→`stack`)으로도 해결 안 됨. `color` 파라미터 자체가 이 plotly 버전에서 버그.

**수정:** `px.histogram` → `go.Figure` + `go.Histogram` traces로 교체. 각 그룹(세그먼트) 값을 직접 필터링해 trace 추가.
```python
for i, grp in enumerate(sorted(df[col_seg].dropna().unique())):
    subset = df[df[col_seg] == grp][col_age].dropna()
    fig.add_trace(go.Histogram(x=subset, name=str(grp), nbinsx=15, ...))
fig.update_layout(barmode='stack', ...)
```
**근본 원인:** 이 plotly express 버전에서 `px.*` 함수에 `color=categorical_column` 조합 사용 시 내부 `get_groups_and_orders()` → `grouped.get_group()` 에서 카테고리 값을 KeyError로 던지는 버그. `px.histogram`, `px.box`, `px.violin` 모두 동일.

**전체 적용 위치:**
- `_charts_customer()`: 연령 분포 히스토그램, 구매 주기 히스토그램 → `go.Histogram`
- `_charts_customer()`: 세그먼트별 구매금액 박스플롯 → `go.Box`
- `_charts_crop()`: 작물별 수확량 박스플롯, 기후별 박스플롯 → `go.Box`
- `_charts_crop()`: 토양별 수확량 바이올린 플롯 → `go.Violin`

**패턴 (그룹별 trace 직접 추가):**
```python
for i, grp in enumerate(sorted(df[col].dropna().unique())):
    subset = df[df[col] == grp][y_col].dropna()
    fig.add_trace(go.Box(y=subset, name=str(grp), marker_color=colors[i % len(colors)]))
```

### 10. ndarray JSON 직렬화 오류 수정
**문제:** `go.Figure.to_dict()`가 numpy ndarray를 포함 → `json.dumps()` 실패 (`TypeError: Object of type ndarray is not JSON serializable`)

**수정:** 전체 차트 함수의 `json.dumps(fig.to_dict())` 36개를 `fig.to_json()`으로 일괄 교체 (`sed` 명령). plotly의 `to_json()`은 numpy 타입 자동 처리.

### 11. px.bar(color='항목') grouped bar KeyError 수정
**문제:** `melt()`로 long 형식 변환 후 `px.bar(color='항목')`을 쓰면 동일 plotly express color 버그 발생.

**근본 결론:** 이 plotly express 버전에서 **`color=` 파라미터가 있는 모든 `px.*` 함수**에서 `get_groups_and_orders` 버그 발생. `px.histogram`, `px.box`, `px.violin`, `px.bar(barmode='group')` 전부 해당.

**수정:** grouped bar도 `go.Bar` 트레이스 직접 사용
```python
fig = go.Figure([
    go.Bar(x=monthly['_month'].tolist(), y=monthly[col_revenue].tolist(), name='매출'),
    go.Bar(x=monthly['_month'].tolist(), y=monthly[col_cost].tolist(),   name='비용'),
])
fig.update_layout(barmode='group', ...)
```
**`.tolist()` 필수** — pandas Series를 list로 변환해야 JSON 직렬화 안전.

**적용 위치:** `_charts_sales()` 월별 매출 vs 비용, `_charts_marketing()` 월별 매출 vs 예산

### 12. px.* color=categorical 버그 — 전면 go.* 헬퍼 교체
**최종 결론:** 이 plotly express 버전에서 `color=categorical_column`이 있는 **모든** `px.*` 함수 (`scatter`, `bar`, `box`, `violin`, `histogram`)가 동일 버그.

**해결책:** `_go_scatter()`, `_go_bar_categorical()` 헬퍼 함수 추가 (COLUMN_MAP 아래). 각 함수는 `go.Scatter` / `go.Bar` 트레이스를 그룹별로 직접 추가해 px 버그 완전 우회.

**교체된 모든 위치:**
| 함수 | 차트 | 교체 내용 |
|------|------|-----------|
| `_charts_sales` | quantity_revenue | `px.scatter(color=col_product)` → `_go_scatter` |
| `_charts_crop` | quantity_revenue | `px.scatter(color=col_crop, size=col_fert)` → `_go_scatter` |
| `_charts_crop` | daily_quantity | `px.scatter(color=col_crop)` → `_go_scatter` |
| `_charts_marketing` | quantity_revenue | `px.scatter(color=col_channel, size=col_impr)` → `_go_scatter` |
| `_charts_marketing` | daily_quantity | `px.scatter(color=col_channel)` → `_go_scatter` |
| `_charts_customer` | region_sales | `px.bar(color=col_seg)` → `go.Bar` 직접 |
| `_charts_customer` | quantity_revenue | `px.scatter(color=col_seg, size=col_purch)` → `_go_scatter` |
| `_charts_customer` | daily_quantity | `px.scatter(color=col_seg)` → `_go_scatter` |

---

## 파일별 변경 요약

| 파일 | 변경 내용 |
|------|-----------|
| `app.py` | COLUMN_MAP 확장, _detect_template_type, _charts_* 4개 함수 재작성, generate_insights + _insights_* 4개 함수 추가, example_view 라우트 추가, visualize columns 방어 처리 |
| `init_db.py` | DataRecord 저장 시 numpy/NaN 직렬화 수정 |
| `templates/template_result.html` | renderChart 이중파싱 수정, 차트 카드에 insight-box 추가, Jinja2 루프로 차트 렌더링 통일 |
| `templates/examples.html` | 4개 예시 카드 전부 활성화, example_view 라우트 연결 |
