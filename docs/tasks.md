# Analytics Platform - 작업 목록

## 점검일: 2026-04-17

---

## [Back_Dev] 백엔드 작업

### B-01: 회사명 기반 데이터 조회 구현 [우선순위: 높음]
- **파일**: `app.py` → `dashboard()` 함수 (line 124)
- **작업 내용**:
  - 대시보드에 "내 데이터" / "회사 전체 데이터" 탭 분리
  - 동일 company 소속 User의 Dataset을 함께 조회하는 쿼리 추가
  - Dataset 목록 API에 company 필터 파라미터 추가
- **예시 쿼리**:
  ```python
  # 같은 회사 사용자들의 데이터 조회
  company_users = User.query.filter_by(company=current_user.company).all()
  company_user_ids = [u.id for u in company_users]
  datasets = Dataset.query.filter(Dataset.user_id.in_(company_user_ids)).all()
  ```

### B-02: 코드 중복 제거 [우선순위: 중간]
- **파일**: `app.py` 상단
- **문제**: `werkzeug.utils.secure_filename` 2회 import (line 3, 12)
- **문제**: `datetime` 2회 import (line 8, 13)
- **작업**: 중복 import 제거

### B-03: 불필요 파일 정리 [우선순위: 낮음]
- **삭제 검토 파일**:
  - `src/models_old.py`
  - `src/migrate_ocr_db.py` (마이그레이션 완료 후)
- **정리 후 README 업데이트**

---

## [Front_Dev] 프론트엔드 작업

### F-01: 대시보드 회사별 보기 UI [우선순위: 높음]
- **파일**: `templates/dashboard.html`
- **작업 내용**:
  - "내 데이터" / "회사 전체" 탭 버튼 추가
  - 회사명 표시 (current_user.company가 있을 때)
  - 업로더 이름 컬럼 추가 (회사 전체 보기 시)

### F-02: 불필요 템플릿 파일 정리 [우선순위: 중간]
- **삭제 검토 파일**:
  - `templates/base_old.html`
  - `templates/visualize_0.html`
  - `templates/visualize_1.html`
  - `templates/visualize_old.html`
  - `templates/crop_example_old.html`

### F-03: 회원가입 폼 회사명 필드 확인 [우선순위: 낮음]
- **파일**: `templates/register.html`
- **확인 사항**: 회사명 입력 필드가 폼에 실제로 존재하는지 검증
- **현황**: app.py에서는 `company = request.form.get('company', '')` 처리 중

---

## 작업 완료 기준

| 작업 ID | 설명 | 담당 | 상태 |
|---------|------|------|------|
| B-01 | 회사명 기반 데이터 조회 | Back_Dev | [x] 완료 |
| B-02 | 코드 중복 제거 | Back_Dev | [x] 완료 |
| B-03 | 불필요 파일 정리 | Back_Dev | 대기 |
| F-01 | 대시보드 회사별 탭 UI | Front_Dev | [x] 완료 |
| F-02 | 불필요 템플릿 정리 | Front_Dev | [!] 수동 삭제 필요 |
| F-03 | 회원가입 폼 회사명 필드 확인 | Front_Dev | [x] 완료 (버그 수정) |
