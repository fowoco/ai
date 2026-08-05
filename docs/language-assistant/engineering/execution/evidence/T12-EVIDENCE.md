# T12 Internal HTTP Contract and Router Integration Evidence Pack

```yaml
evidence_version: 1
wave: W3
task: T12
packet_version: 1
base_sha: 020bfce5288fbaf8c8ce7565576a08416fb9a5d3
packet_sha: a23fea2a3dc58f06110055e07395cd2cf517e17e
implementation_sha: eb83026d7a9171116dbe7e1ab1d0cc61c1518394
branch: task/la-internal-api
worktree: /Users/parktaejung/Desktop/workspace/ai-language-assistant-t12-internal-api
clean_worktree_at_implementation: true
```

## Claims

| ID | Claim | Evidence |
|---|---|---|
| T12-C01 | 내부 HTTP 라우트 `POST /internal/v1/language-assistant`는 허용된 4개 필드(`worker_id`, `preferred_language`, `nationality_code`, `request_context`)만 프로젝션하고 상위 Extra 필드(예: `source_text`, DB 정보)는 도메인 입력으로 전달하지 않고 격리 차단한다. | `test_http_request_treats_source_text_as_ignored_parent_extra`, `test_endpoint_ignores_source_text_parent_extra` |
| T12-C02 | FastAPI 의존성 오버라이드(`dependency_overrides[get_language_assistant_service]`)를 통해 외부 실 LLM API 또는 Qdrant 연결 없이 엔드포인트 단독 테스트가 가능하다. | `test_endpoint_returns_structured_output`, `test_endpoint_returns_422_for_unsupported_preferred_language_without_fallback` |
| T12-C03 | 앱 생성 및 OpenAPI 스키마 생성 시 모델 가중치 로드나 네트워크 연결 없이 `/internal/v1/language-assistant` 엔드포인트 경로가 올바르게 노출된다 (`/api/v1` 미중복 확인). | `test_endpoint_available_in_openapi_at_exact_path`, `test_endpoint_not_mounted_under_api_v1` |

## RED before implementation

구현 전 packet SHA(`a23fea2a3dc58f06110055e07395cd2cf517e17e`)에서 다음 focused 명령을 실행했다.

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest tests/api/test_language_endpoint.py -q
```

- Exit code: `2`
- 결과: `ImportError: cannot import name 'get_language_assistant_service'`
- 의미: T12 endpoint 및 dependency 함수가 작성되지 않아 예상대로 RED 발생.

## Implementation verification

모든 명령은 implementation SHA `eb83026d7a9171116dbe7e1ab1d0cc61c1518394`에서 실행했다.

### Focused test

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest tests/api/test_language_endpoint.py -q
```

- Exit code: `0`
- 결과: `12 passed`

### Repository regression

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/python -m pytest -q
```

- Exit code: `0`
- 결과: `394 passed`

### Ruff

```bash
/Users/parktaejung/Desktop/workspace/ai-language-assistant/.venv/bin/ruff check app/api/schemas/language.py app/api/routes/language.py app/api/dependencies.py app/api/openapi.py app/main.py scripts/export_language_schemas.py tests/api/test_language_endpoint.py
```

- Exit code: `0`
- 결과: `All checks passed!`

### Diff and scope

```bash
git diff --check
git diff --name-status a23fea2a3dc58f06110055e07395cd2cf517e17e..eb83026d7a9171116dbe7e1ab1d0cc61c1518394
```

- Exit code: `0`
- 변경 파일은 허용 파일 범위 10개 한정:

```text
M  app/api/dependencies.py
M  app/api/openapi.py
A  app/api/routes/language.py
A  app/api/schemas/language.py
A  docs/contracts/language-assistant-http-request.schema.json
M  app/main.py
M  scripts/export_language_schemas.py
A  tests/api/test_language_endpoint.py
A  tests/fixtures/language/backend-language-request.json
A  tests/fixtures/language/backend-language-response.json
```

## Scope audit

```yaml
implementation_allowed_files_only: true
unexpected_implementation_files: []
vendor_imports_in_http_contract_domain: []
evidence_artifact: docs/language-assistant/engineering/execution/evidence/T12-EVIDENCE.md
```

## Unrun and unverified

- 단위 테스트 중 외부 실 LLM API 및 Qdrant 데이터베이스 통신은 수행하지 않았다 (fake graph service dependency override 사용).
- T13 Production Runtime Composition 조립은 시작하지 않았다.

## Rollback

- Safe point: `a23fea2a3dc58f06110055e07395cd2cf517e17e`
