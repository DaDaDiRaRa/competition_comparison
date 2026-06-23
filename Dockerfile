# Stage 1: React 프론트엔드 빌드
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python 백엔드
FROM python:3.12-slim
WORKDIR /app

COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

COPY backend/requirements-server.txt ./
RUN pip install --no-cache-dir -r requirements-server.txt

COPY backend/ ./backend/
# 사용자 매뉴얼: /api/readme 가 런타임에 HTML로 렌더링하는 단일 소스
COPY README.md ./backend/README.md
WORKDIR /app/backend

ENV PYTHONUNBUFFERED=1
# rhwp-python(Rust 바이너리) freetype 링킹 경로 명시
ENV LD_PRELOAD=/lib/x86_64-linux-gnu/libfreetype.so.6
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
