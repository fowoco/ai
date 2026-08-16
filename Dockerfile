# rhwp Linux 공식 릴리스가 x86_64만 제공되므로 runtime platform도 amd64로 고정한다.
# Apple Silicon 개발 환경에서는 Docker Desktop이 amd64 emulation으로 실행한다.
ARG FOWOCO_RUNTIME_PLATFORM=linux/amd64
FROM --platform=${FOWOCO_RUNTIME_PLATFORM} python:3.12-slim-trixie AS rhwp

ADD --checksum=sha256:fe3dc818a44f2bc4d4a001311514ed399d46a1e752b3df0d6e9e2f2ac8058402 \
    https://github.com/edwardkim/rhwp/releases/download/v0.7.19/rhwp-v0.7.19-linux-x86_64.tar.gz \
    /tmp/rhwp.tar.gz
RUN mkdir -p /opt/rhwp \
    && tar -xzf /tmp/rhwp.tar.gz -C /opt/rhwp --strip-components=1 \
    && test -x /opt/rhwp/rhwp \
    && test -f /opt/rhwp/LICENSE

# uv 바이너리 고정 버전 복사
FROM ghcr.io/astral-sh/uv:0.7.20 AS uv

FROM --platform=${FOWOCO_RUNTIME_PLATFORM} python:3.12-slim-trixie

# 컨테이너 작업 디렉터리
WORKDIR /app

# 시스템 기본 인코딩을 UTF-8로 고정
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_NO_CACHE=1 \
    FOWOCO_HWP_TO_HWPX_ENABLED=true \
    FOWOCO_HWPX_TO_HWP_ENABLED=true \
    FOWOCO_HWPX_PDF_ENABLED=true \
    FOWOCO_DOCUMENT_SNAPSHOT_DIR=/data/document-snapshots \
    FOWOCO_MODEL_CACHE_DIR=/opt/fowoco/language-models \
    HF_HOME=/opt/fowoco/hf-cache

COPY --from=uv /uv /usr/local/bin/uv
COPY --from=rhwp /opt/rhwp/rhwp /usr/local/bin/rhwp
COPY --from=rhwp /opt/rhwp/LICENSE /usr/share/licenses/rhwp/LICENSE

# 문서 변환용 Java runtime과 PDF 렌더링용 한글 폰트
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        fonts-noto-cjk \
        default-jre-headless \
    && rm -rf /var/lib/apt/lists/*

# 의존성 정의 파일 + 앱 소스를 먼저 복사한다.
# uv sync는 fowoco-ai 자기 자신도 빌드해서 site-packages에 설치하므로,
# app/ 복사보다 먼저 실행되면 그 시점의 app/(없거나 이전 레이어 캐시의 내용)이
# site-packages에 고정되고, 이후 COPY app ./app은 /app/app만 갱신할 뿐
# 실제 uv run이 임포트하는 설치본은 계속 예전 코드로 남는다 — uv.lock이
# 안 바뀌면 이 RUN 레이어가 캐시 히트되어 app/ 변경이 몇 주간 반영되지
# 않았던 실제 배포 장애의 원인이었다. app/를 먼저 복사해 항상 최신 소스로
# 빌드·설치되게 한다.
COPY pyproject.toml uv.lock README.md ./
COPY app ./app
COPY scripts/download_language_models.py ./scripts/

# uv.lock 기반 재현 가능 설치 — Language retrieval + Intent A.X runtime 포함
RUN uv sync --frozen --no-dev --extra language-retrieval --extra intent-ax

# 고정 revision의 검색 모델을 이미지에 포함해 런타임 다운로드를 없앤다.
RUN /app/.venv/bin/python -m scripts.download_language_models \
    --cache-dir /opt/fowoco/language-models

# uvicorn 기본 포트
EXPOSE 8000
VOLUME ["/data", "/opt/fowoco/hf-cache"]

# FastAPI 앱 기동
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
