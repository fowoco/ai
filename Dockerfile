# rhwp 공식 릴리스 바이너리를 체크섬으로 고정해 가져오는 빌드 단계
FROM python:3.12-slim-trixie AS rhwp

ADD --checksum=sha256:fe3dc818a44f2bc4d4a001311514ed399d46a1e752b3df0d6e9e2f2ac8058402 \
    https://github.com/edwardkim/rhwp/releases/download/v0.7.19/rhwp-v0.7.19-linux-x86_64.tar.gz \
    /tmp/rhwp.tar.gz
RUN mkdir -p /opt/rhwp \
    && tar -xzf /tmp/rhwp.tar.gz -C /opt/rhwp --strip-components=1 \
    && test -x /opt/rhwp/rhwp \
    && test -f /opt/rhwp/LICENSE

FROM python:3.12-slim-trixie

# 컨테이너 작업 디렉터리
WORKDIR /app

# 시스템 기본 인코딩을 UTF-8로 고정
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FOWOCO_HWP_TO_HWPX_ENABLED=true \
    FOWOCO_HWPX_TO_HWP_ENABLED=true \
    FOWOCO_HWPX_PDF_ENABLED=true \
    FOWOCO_DOCUMENT_SNAPSHOT_DIR=/data/document-snapshots

COPY --from=rhwp /opt/rhwp/rhwp /usr/local/bin/rhwp
COPY --from=rhwp /opt/rhwp/LICENSE /usr/share/licenses/rhwp/LICENSE

# COM 없이 HWPX를 읽고 PDF로 렌더링하는 headless 엔진과 한글 폰트
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        fonts-noto-cjk \
        default-jre-headless \
        libreoffice-h2orestart \
        libreoffice-writer \
    && rm -rf /var/lib/apt/lists/*

# 의존성 정의 파일만 먼저 복사해 캐시를 활용
COPY pyproject.toml README.md ./

# 앱 패키지 복사
COPY app ./app

# 프로덕션 의존성만 설치
RUN pip install --no-cache-dir .

# uvicorn 기본 포트
EXPOSE 8000
VOLUME ["/data"]

# FastAPI 앱 기동
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
