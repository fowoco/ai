# Analyses Runtime 계약 (AI 소유)

Server `docs/ai-runtime-contract.md`와 맞추기 위한 AI 쪽 계약 요약이다.
Language Agent는 아래 응답 fixture를 임시 입력으로 써도 된다.

## Endpoint

```text
POST /internal/v1/analyses
```

`/api/v1` prefix를 붙이지 않는다. (이전 `/api/v1/internal/v1/analyses` 는 제거)

## workflowId

두 형태를 모두 받는다.

| 형태 | 예 | 언제 |
|---|---|---|
| Intent형 | `EXPIRY_RENEWAL` | Server 계약 fixture / projection projection |
| Catalog형 | `WF-STY-001` | knowledge Workflow Catalog |

- 요청 `workflowConstraints[].workflowId`에 **Intent형**이 있으면, 응답 candidate의
  `workflowId`도 **같은 문자열**을 되돌려 Server 검증을 통과시킨다.
- Catalog형 constraint면 Catalog형 id를 그대로 반환한다.
- constraint가 비어 있으면 내부 분류 결과인 Catalog형 id(`WF-…`)를 반환한다.

내부 Ambiguity/Workflow 검증은 항상 Catalog형 id로 수행한다.

## Fixtures (Language 임시 입력)

| 파일 | 용도 |
|---|---|
| `examples/analyses/request_expiry_renewal.json` | Server 스타일 요청 |
| `examples/analyses/response_needs_info.json` | 안내문 생성이 필요한 응답 예시 |
| `examples/analyses/response_review_required.json` | HR 검토용 응답 예시 |

## Versions

`contractVersion=1.0.0`, `requiredKnowledgeVersion=0.2.0` 을 기본으로 둔다.
MVP 응답의 model* 필드는 `stub`이다.
