# 🚀 빠른 시작 가이드

## 언어 전환 기능이 통합된 analytics_platform

완전한 다국어(한국어/English) 지원 데이터 분석 플랫폼입니다.

## ⚡ 5분 안에 시작하기

### 1단계: 가상환경 생성 및 활성화
```bash
cd analytics_platform
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### 2단계: 패키지 설치
```bash
pip install -r requirements.txt
```

### 3단계: 서버 실행
```bash
python app.py
```

### 4단계: 브라우저 접속
```
http://localhost:5000
```

## 🌟 주요 기능

### ✅ 완료된 기능
- ✨ **한국어/영어 실시간 전환** (네비게이션 바에서 🌐 아이콘 클릭)
- 🔐 사용자 인증 (회원가입/로그인)
- 📤 Excel/CSV 파일 업로드
- 📊 5가지 차트 타입 (라인, 바, 산점도, 파이, 히스토그램)
- 💾 데이터 관리 (조회, 삭제)
- 🎨 반응형 디자인 (모바일 지원)

### 🎯 언어 전환 사용법
1. 페이지 우측 상단의 **🌐 한국어** 또는 **🌐 English** 클릭
2. 드롭다운에서 원하는 언어 선택
3. **전체 사이트가 즉시 선택한 언어로 변경**
4. 선택한 언어는 세션 동안 유지됨

## 📁 프로젝트 구조

```
analytics_platform/
├── app.py              # 언어 전환 기능 포함
├── config.py           # LANGUAGES 설정 포함
├── models.py           # DB 모델
├── requirements.txt    # 업데이트된 pandas 버전
├── README.md          # 상세 문서
├── static/
│   └── css/
│       └── style.css  # 커스텀 스타일
└── templates/         # 모든 템플릿 다국어 지원
    ├── base.html      # 언어 선택 드롭다운 포함
    ├── index.html
    ├── login.html
    ├── register.html
    ├── dashboard.html
    ├── upload.html
    ├── view_dataset.html
    └── visualize.html
```

## 💡 팁

1. **테스트 계정 생성**: 먼저 회원가입으로 테스트 계정을 만드세요
2. **샘플 데이터**: Excel이나 CSV 파일로 샘플 데이터를 준비하세요
3. **언어 테스트**: 페이지를 이동하며 언어 전환이 잘 작동하는지 확인하세요
4. **차트 실험**: 다양한 차트 타입과 데이터 조합을 시도해보세요

## 🎉 완성!

이제 analytics_platform이 완전히 준비되었습니다!
- ✅ 모든 기능 작동
- ✅ 한국어/영어 전환
- ✅ 프로덕션 준비 완료

---

**Enjoy your bilingual data analytics platform! 🚀**
**다국어 데이터 분석 플랫폼을 즐기세요! 🎊**
