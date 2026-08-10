# AI ↔ Server 런타임 핸드셰이크 (#8)

`requestId` / `attemptId` 일치와 Internal 호출 인증을 맞추기 위한 AI 쪽 계약이다.
Server AI Run(#24)이 Agent를 호출할 때 이 규칙을 따른다.

## 식별자

| 필드 | 누가 발급 | 규칙 |
|---|---|---|
| `requestId` | Server (AI Run / 원요청) | **한 업무 요청 수명 동안 고정**. Analyses·renewal·재호출 모두 동일 |
| `attemptId` | Server (시도마다) | **호출·재시도마다 새 UUID**. AI는 검증만 하고 응답에 에코 |

- Analyses: 요청에 `requestId`+`attemptId` **필수**, 응답에 `requestId`만 에코 (`attemptId`는 응답 와이어에 넣지 않음 — Server strict JSON)
- renewal/run: 요청에 `requestId` **필수**, `attemptId` **권장(재호출 시 필수에 가깝게)**, 응답에 둘 다 에코

같은 `requestId`로 slots만 채워 재호출하는 흐름은 [#74 slot-refill-contract](slot-refill-contract.md)를 본다.

## 인증

Server → AI Internal API (PR #56):

```http
Authorization: Bearer <AI_RUNTIME_SERVICE_CREDENTIAL>
X-Request-Id: <requestId>
traceparent: <optional W3C trace parent>
```

AI는 동일 값을 `FOWOCO_INTERNAL_API_TOKEN`으로 검증한다.

| 환경 | 동작 |
|---|---|
| `FOWOCO_INTERNAL_API_TOKEN` 미설정 | 개발 편의상 인증 생략 (로컬) |
| 설정됨 | Bearer 불일치 시 `401` |

적용 경로: `POST /internal/v1/analyses`, `POST /internal/v1/workflows/renewal/run`

AI → Server 콜백이 생기면 동일 토큰 또는 Server 발급 서비스 토큰을 쓰도록 추후 확장한다.

## 상호 “통화 OK” 체크리스트

1. Server AI Run 생성 시 `requestId` 확정
2. Agent 호출마다 새 `attemptId`
3. Bearer 토큰으로 AI Internal 도달
4. AI 응답 `requestId`가 Run과 일치하는지 Server가 검증
5. 슬롯 부족 시 같은 `requestId` + 새 `attemptId`로 재호출 (#74)

## 관련 코드

- 설정: `FOWOCO_INTERNAL_API_TOKEN` ([app/core/config.py](../app/core/config.py))
- 가드: [app/api/security.py](../app/api/security.py)
