#!/usr/bin/env bash
# 경매·공매 물건 분석 앱 실행 스크립트
set -e
cd "$(dirname "$0")/backend"

if [ ! -d ".venv" ]; then
  echo "▶ 가상환경 생성 및 패키지 설치..."
  python3 -m venv .venv
  ./.venv/bin/pip install -q --upgrade pip
  ./.venv/bin/pip install -q -r requirements.txt
fi

# 실데이터를 쓰려면 아래 주석을 풀고 발급받은 키를 넣으세요.
# export ONBID_SERVICE_KEY="발급받은_serviceKey"

echo "▶ http://localhost:8000 에서 실행합니다 (Ctrl+C 종료)"
./.venv/bin/uvicorn main:app --reload --port 8000
