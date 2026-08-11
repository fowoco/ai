from __future__ import annotations

from pathlib import Path

# fowoco/knowledge 25e778ad의 A.X 추론 계약을 배포 패키지에 고정한다.
AX_INTENT_PROMPT_VERSION = "knowledge-25e778ad"
AX_INTENT_PROMPT_SHA256 = "58f3aefc45831990ab871f2dca1d69b59277cbac333d9e7b2856bad7b79e8bbe"
_AX_INTENT_PROMPT_PATH = Path(__file__).with_name("prompts") / "ax_intent_v1.txt"
AX_INTENT_SYSTEM_PROMPT = _AX_INTENT_PROMPT_PATH.read_text(encoding="utf-8").strip()
