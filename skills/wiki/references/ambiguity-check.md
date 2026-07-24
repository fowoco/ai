# ambiguity-check — Intent Routing 진입점

`wiki setup` 인터뷰의 모든 서브 질문에 적용하는 라우팅 규칙.
질문을 던지기 **전** 아래 3-way routing으로 처리 경로를 결정한다.

---

## Routing 테이블

| 분류 | 조건 | 참조 |
|---|---|---|
| **CLEAR** | 원하는 결과가 명확, 열린 항목은 선호·트레이드오프뿐 | `references/clear-path.md` |
| **UNCLEAR** | 결과 자체가 모호하거나 아직 미결정 | `references/unclear-path.md` |
| **FENCE** | CLEAR/UNCLEAR 구분 불명확 | CLEAR로 처리 + 딱 하나의 질문만 |

> CLEAR/UNCLEAR 경계가 애매할 때만 **FENCE**로 분류한다. 진짜 미결정 항목은 UNCLEAR 경로에 남긴다.
