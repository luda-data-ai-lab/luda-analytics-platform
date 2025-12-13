#!/bin/bash

echo "=========================================="
echo "데이터 분석 플랫폼 시작"
echo "=========================================="
echo ""

# 가상환경 활성화 (있는 경우)
if [ -d "venv" ]; then
    echo "가상환경 활성화..."
    source venv/bin/activate
fi

# 애플리케이션 실행
echo ""
echo "서버를 시작합니다..."
echo "브라우저에서 http://localhost:5000 으로 접속하세요"
echo "종료하려면 Ctrl+C를 누르세요"
echo ""
python3 app.py
