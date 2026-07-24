#!/bin/bash
# 커밋 후 raw/dev-logs/ 에 자동으로 dev-log 항목 생성
# Node CLI 설치 시 .git/hooks/post-commit 으로 복사됨

DATE=$(date +%Y-%m-%d)
TIME=$(date +%H:%M)
COMMIT_MSG=$(git log -1 --pretty=%B)
COMMIT_HASH=$(git log -1 --pretty=%h)

CHANGED_FILES=()
while IFS= read -r -d '' status && IFS= read -r -d '' first_path; do
  case "$status" in
    R*|C*)
      if IFS= read -r -d '' second_path; then
        safe_first=${first_path//$'\n'/\\n}
        safe_first=${safe_first//$'\r'/\\r}
        safe_second=${second_path//$'\n'/\\n}
        safe_second=${safe_second//$'\r'/\\r}
        CHANGED_FILES+=("$status $safe_first -> $safe_second")
      fi
      ;;
    *)
      safe_path=${first_path//$'\n'/\\n}
      safe_path=${safe_path//$'\r'/\\r}
      CHANGED_FILES+=("$status $safe_path")
      ;;
  esac
  [ ${#CHANGED_FILES[@]} -ge 20 ] && break
done < <(git diff-tree --root --no-commit-id -r -M --name-status -z HEAD 2>/dev/null)

DEV_LOG_DIR="raw/dev-logs"
DEV_LOG_FILE="$DEV_LOG_DIR/${DATE}_dev-log_auto.md"
mkdir -p "$DEV_LOG_DIR"

if [ ! -f "$DEV_LOG_FILE" ]; then
  cat > "$DEV_LOG_FILE" << FRONTMATTER
---
title: "${DATE} 개발 일지 (자동 생성)"
raw_type: "dev-log"
date: ${DATE}
created: ${DATE}
description: "${DATE} 커밋 기록 자동 수집"
ingest_status: "⏳ pending"
tags:
  - "raw/dev-log"
  - "auto-generated"
---

# ${DATE} 개발 일지
FRONTMATTER
  printf '📝 dev-log 생성: %s\n' "$DEV_LOG_FILE"
else
  printf '📝 dev-log 갱신: %s\n' "$DEV_LOG_FILE"
fi

{
  printf '\n### 커밋 `%s` — %s\n\n' "$COMMIT_HASH" "$TIME"
  printf '**메시지:**\n\n'
  printf '%s\n' "$COMMIT_MSG" | sed 's/^/    /'
  printf '\n**변경 파일:**\n\n'
  if [ ${#CHANGED_FILES[@]} -eq 0 ]; then
    printf '%s\n' '- (없음)'
  else
    for file in "${CHANGED_FILES[@]}"; do
      printf -- '- %s\n' "$file"
    done
  fi
} >> "$DEV_LOG_FILE"
