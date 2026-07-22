# 가벼운 Python 런타임
FROM python:3.12-slim

# 컨테이너 작업 디렉터리
WORKDIR /app

# 시스템 기본 인코딩을 UTF-8로 고정
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 의존성 정의 파일만 먼저 복사해 캐시를 활용
COPY pyproject.toml README.md ./

# 앱 패키지 복사
COPY app ./app

# 프로덕션 의존성만 설치
RUN pip install --no-cache-dir .

# uvicorn 기본 포트
EXPOSE 8000

# FastAPI 앱 기동
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
