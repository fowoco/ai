#!/usr/bin/env python3
"""T13 — 언어 모델 사전 다운로드 스크립트.

정확한 리비전을 고정해 BGE-M3, BGE-Reranker-v2-m3를 캐시 디렉터리에 저장.
Docker 빌드 시 또는 배포 전 1회 실행. HTTP 요청 중 동적 다운로드 금지.

사용법:
    python scripts/download_language_models.py [--cache-dir /path/to/cache]

ponytail: huggingface_hub 미설치 시 안내 메시지만 출력하고 종료. 단위테스트에서
  실제 네트워크 접근 없이 verify_model_cache()만 사용 가능.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.agents.language.retrieval.manifest import (
    BGE_M3_MODEL_REPO,
    BGE_M3_REVISION,
)

# 정확한 모델 리비전 — 변경 금지 (T13 계약)
BGE_RERANKER_REVISION = "953dc6f6f85ac1e88eb36f5f9ce67a74a6edbc22"

MODEL_SPECS: list[dict[str, str]] = [
    {
        "name": "bge-m3",
        "repo": BGE_M3_MODEL_REPO,
        "revision": BGE_M3_REVISION,
    },
    {
        "name": "bge-reranker-v2-m3",
        "repo": "BAAI/bge-reranker-v2-m3",
        "revision": BGE_RERANKER_REVISION,
    },
]

# 캐시 히트 판단 기준 파일
_SENTINEL_FILE = "config.json"


def verify_model_cache(cache_dir: Path) -> list[str]:
    """캐시 디렉터리에서 누락된 모델 이름 목록 반환.

    네트워크 접근 없음. 파일 존재 여부만 확인.
    """
    missing: list[str] = []
    for spec in MODEL_SPECS:
        sentinel = cache_dir / spec["name"] / spec["revision"] / _SENTINEL_FILE
        if not sentinel.exists():
            missing.append(spec["name"])
    return missing


def download_models(cache_dir: Path, force: bool = False) -> None:
    """각 모델을 고정 리비전으로 캐시 디렉터리에 다운로드.

    huggingface_hub 필요. 미설치 시 ImportError 안내 후 종료.
    """
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print(
            "huggingface_hub 미설치. 설치 후 재실행:\n"
            "  pip install huggingface_hub",
            file=sys.stderr,
        )
        sys.exit(1)

    for spec in MODEL_SPECS:
        local_dir = cache_dir / spec["name"] / spec["revision"]
        sentinel = local_dir / _SENTINEL_FILE
        if sentinel.exists() and not force:
            print(f"[skip] {spec['name']} 이미 캐시됨: {local_dir}")
            continue
        print(f"[download] {spec['repo']}@{spec['revision'][:8]} → {local_dir}")
        snapshot_download(
            repo_id=spec["repo"],
            revision=spec["revision"],
            local_dir=str(local_dir),
            ignore_patterns=["*.msgpack", "flax_model*", "tf_model*", "rust_model*"],
        )
        print(f"[ok] {spec['name']} 완료")


def main() -> None:
    parser = argparse.ArgumentParser(description="BGE 모델 사전 다운로드")
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path("/data/model-cache"),
        help="모델 캐시 디렉터리 (기본: /data/model-cache)",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="다운로드 없이 캐시 상태만 확인",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="이미 캐시된 모델도 재다운로드",
    )
    args = parser.parse_args()

    missing = verify_model_cache(args.cache_dir)
    if args.verify_only:
        if missing:
            print(f"[missing] {', '.join(missing)}", file=sys.stderr)
            sys.exit(1)
        print("[ok] 모든 모델 캐시 확인 완료")
        return

    if missing or args.force:
        download_models(args.cache_dir, force=args.force)
    else:
        print("[ok] 모든 모델 캐시 확인 완료 (다운로드 불필요)")


if __name__ == "__main__":
    main()
