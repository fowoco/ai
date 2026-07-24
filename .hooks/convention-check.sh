#!/bin/bash
# wiki/conventions/ 규칙 기반 pre-commit 검사
# Node CLI 설치 시 .git/hooks/pre-commit 으로 복사됨

FAILED=0
WIKI_CONVENTIONS="wiki/conventions"
ALLOWLIST_FILE="${PROJECT_SCAFFOLD_SECRET_ALLOWLIST:-.project-scaffold/local/secret-allowlist}"

STAGED_FILES=()
while IFS= read -r -d '' file; do
  [ -f "$file" ] && STAGED_FILES+=("$file")
done < <(git diff --cached --name-only --diff-filter=ACMR -z)

if [ ${#STAGED_FILES[@]} -eq 0 ]; then
  exit 0
fi

echo "🔍 convention-check 실행 중..."

# staged blob을 검사한다. working tree가 staged 내용과 달라도 커밋 대상만 판정한다.
# allowlist 형식: RULE_ID|project/relative/path|line
is_allowlisted() {
  local rule_id=$1
  local file=$2
  local line=$3
  [ -f "$ALLOWLIST_FILE" ] && grep -Fqx -- "${rule_id}|${file}|${line}" "$ALLOWLIST_FILE"
}

report_rule_matches() {
  local file=$1
  local rule_id=$2
  local pattern=$3
  local line_number
  local ignored
  while IFS=: read -r line_number ignored; do
    [ -n "$line_number" ] || continue
    if is_allowlisted "$rule_id" "$file" "$line_number"; then
      continue
    fi
    local display_file=${file//$'\n'/\\n}
    display_file=${display_file//$'\r'/\\r}
    printf '🔴 [%s] %s:%s\n' "$rule_id" "$display_file" "$line_number"
    FAILED=1
  done < <(git show ":$file" 2>/dev/null | grep -nEI -- "$pattern" || true)
}

for file in "${STAGED_FILES[@]}"; do
  if ! git show ":$file" 2>/dev/null | grep -Iq .; then
    continue
  fi
  report_rule_matches "$file" "PSC_SECRET_ASSIGNMENT" "(password|secret|api[_-]?key|token)[[:space:]]*[:=][[:space:]]*['\"][^'\"]{4,}"
  report_rule_matches "$file" "PSC_PRIVATE_KEY" "-----BEGIN ([A-Z0-9 ]+ )?PRIVATE KEY-----"
  report_rule_matches "$file" "PSC_PROVIDER_TOKEN" "(gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,})"
done

if [ ! -d "$WIKI_CONVENTIONS" ]; then
  echo "⚠️  wiki/conventions/ 없음. secret scan은 실행했으며 프로젝트별 convention 검사는 생략합니다."
fi

PY_FILES=()
JS_FILES=()
for file in "${STAGED_FILES[@]}"; do
  case "$file" in
    *.py) PY_FILES+=("$file") ;;
    *.js|*.jsx|*.ts|*.tsx) JS_FILES+=("$file") ;;
  esac
done

if [ ${#PY_FILES[@]} -gt 0 ] && command -v pylint >/dev/null 2>&1; then
  if ! pylint --errors-only --score=no -- "${PY_FILES[@]}"; then
    echo "🔴 [pylint] 에러 발견"
    FAILED=1
  fi
fi

ESLINT=""
if [ -x "node_modules/.bin/eslint" ]; then
  ESLINT="node_modules/.bin/eslint"
elif command -v eslint >/dev/null 2>&1; then
  ESLINT=$(command -v eslint)
fi

if [ ${#JS_FILES[@]} -gt 0 ] && [ -n "$ESLINT" ]; then
  if compgen -G ".eslintrc*" >/dev/null 2>&1 || compgen -G "eslint.config.*" >/dev/null 2>&1; then
    if ! "$ESLINT" --quiet -- "${JS_FILES[@]}"; then
      echo "🔴 [eslint] 에러 발견"
      FAILED=1
    fi
  fi
fi

echo ""
if [ "$FAILED" -eq 1 ]; then
  echo "❌ convention-check 실패. 위반 사항을 수정 후 다시 커밋하세요."
  echo "   출력은 file, line, rule ID만 포함하며 secret 원문은 표시하지 않습니다."
  echo "   상세 검사: /review"
  exit 1
fi

echo "✅ convention-check 통과"
exit 0
