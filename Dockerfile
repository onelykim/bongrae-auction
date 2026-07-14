FROM python:3.11-slim

WORKDIR /app

# 의존성 먼저(캐시 활용)
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# 소스 복사
COPY backend ./backend
COPY frontend ./frontend

WORKDIR /app/backend

# 호스팅 플랫폼이 주는 PORT 환경변수를 사용(없으면 8000)
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
