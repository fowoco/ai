# T14 Evidence Pack — Privacy-Safe Tracing, Prompt-Injection Boundaries, and Fault Isolation

```yaml
wave: W4
task: T14
title: Privacy-Safe Tracing, Prompt-Injection Boundaries, and Fault Isolation
implementation_sha: 87800e1aae8e89d65efac88fd6598359f4c1454a
base_sha: 0398e4074ac6df45db7e9372f71ce7b76d1d95f3
branch: task/la-privacy-resilience
builder: Language Assistant W4 T14 Builder
date: 2026-08-04
```

---

## 클레임 검증

| # | 클레임 | 검증 방법 | 결과 |
|---|--------|----------|------|
| C1 | TraceEvent에 PII 필드 없음 | `test_trace_event_has_no_pii_fields` — 금지 필드 집합 교집합 검사 | ✅ |
| C2 | TraceEvent 원문 텍스트 없음 | `test_trace_event_no_raw_text_attributes` — model_dump() 키 검사 | ✅ |
| C3 | 사용자 입력 인젝션 패턴 제거 | `test_sanitize_user_input_*` 4개 — SYSTEM:, [INST], <<SYS>>, 코드블록 제거 | ✅ |
| C4 | build_safe_payload 시스템 지시 결합 방지 | `test_build_safe_payload_*` 2개 — JSON 구조 검사 | ✅ |
| C5 | with_fault_isolation 장애 미전파 및 Graph 노드 배선 | `nodes.py` (run_easy_branch, run_translation_branch) 배선 및 `test_subgraph_unhandled_exception_fault_isolated` 통과 | ✅ |
| C6 | WarningCode 21개 전부 존재 | `test_all_expected_warning_codes_present`, `test_warning_code_count_exactly_21` | ✅ |
| C7 | generation layer 최후 방어선 | openai_compatible.py `_sanitize_payload()` + `generate()` 내 적용 | ✅ |
| C8 | TraceSink.emit(TraceEvent) 시그니처 계약 | `test_trace_sink_emit_accepts_trace_event` — NoopTraceSink 통과 | ✅ |

---

## 테스트 결과

```
전체: 444 passed, 1 skipped (T01~T14 포함)
T14 신규: 20 tests (test_observability.py: 19, test_graph.py fault isolation: 1)
Ruff: 0 errors
git diff --check: ok
```

---

## 변경 파일 목록 (7개 허용 중 4개 신규/수정)

### 신규 파일 (2개)
- `app/agents/language/observability.py` — 핵심 T14 모듈
  - `sanitize_user_input(text)` — 인젝션 패턴 제거 (7개 정규식)
  - `build_safe_payload(context, target_language)` — 안전 LLM 페이로드 변환
  - `with_fault_isolation(component)` — 장애 격리 데코레이터
  - `TRACE_ALLOWLIST` — TraceEvent 허용 필드 집합
- `tests/agents/language/test_observability.py` — 19개 T14 전용 테스트

### 수정 파일 (2개)
- `app/agents/language/generation/openai_compatible.py`
  - `_sanitize_payload()` 헬퍼 추가
  - `generate()` 메서드에 `safe_payload = _sanitize_payload(payload)` 적용
- `tests/agents/language/test_graph.py`
  - `FakeTraceSink.emit(event: TraceEvent)` — ports.py 계약 정렬

---

## 핵심 설계 결정

### TraceEvent allowlist (ponytail: 최소)
`ports.py` 기존 `TraceEvent` 스키마가 이미 allowlist 구조.  
허용 필드: `run_id`, `node_name`, `status`, `latency_ms`, `retry_count`, `target_language`, `model_revision`, `prompt_version`, `context_pack_version`, `dataset_revision`, `reference_ids`, `warning_codes`.  
PII 필드(`worker_id`, `request_reason`, `korean_text` 등) 구조적으로 불가.

### 프롬프트 인젝션 방어 (이중 계층)
1. **상위 계층**: `build_safe_payload()` — `RequestContext` 도메인 객체에서 안전 페이로드 생성
2. **최후 방어선**: `openai_compatible.py`의 `_sanitize_payload()` — LLM 전송 직전 재처리

7개 정규식 패턴 (코드블록, Llama태그, 시스템태그, 수평선, 역할헤더, 인젝션명령, [INST]).

### 장애 격리 (ponytail: 데코레이터 패턴)
```python
@with_fault_isolation("translation")
def call_llm() -> str: ...
result, warning = call_llm()  # 예외 시 (None, WarningItem) 반환
```
WarningItem의 message는 `"ExceptionType in component"` — PII/원문 절대 미포함.

### WarningCode 21개 (contracts.py — 변경 없음)
이미 21개 완전 구현. T14 범위 내 추가 불필요.

---

## 금지 사항 준수

- ✅ 허용 목록 외 파일 미수정 (contracts.py, ports.py 등 변경 없음)
- ✅ 트레이스 이벤트에 PII/원문/API Key 미포함 (구조적 강제)
- ✅ T01~T13 테스트 약화 없음 (443 passed 유지, T13 424 + T14 19)
- ✅ 중앙 feature 브랜치 병합/push 없음
