# Language Assistant 문서 안내

이 디렉터리는 FOWOCO Language Assistant의 설계, 구현 계획, 실행 기록을 모은 전용 문서 namespace입니다.

## 현재 구조

- `engineering/specs/`: 그래프·Control Tower 설계
- `engineering/plans/`: 구현 계획과 작업 순서
- `engineering/execution/`: Control Tower, Task Packet, Evidence Pack, Gate 검토 기록
- `../contracts/`가 아니라 저장소 루트의 `docs/contracts/`: 코드와 검증 명령이 직접 참조하는 JSON Schema

## 운영 원칙

- 현재 실행 상태의 권위는 `engineering/execution/control-tower.md`입니다.
- Evidence Pack은 생성 당시의 내용과 SHA를 보존하며 임의로 재작성하지 않습니다.
- 과거 Evidence에 남은 이전 경로 문자열은 당시 실행 환경을 기록한 역사 정보입니다.
- 새 Language Assistant 문서는 이 namespace 아래에 추가합니다.

## 주요 진입점

- [Graph 설계](engineering/specs/2026-08-02-language-assistant-graph-design.md)
- [Control Tower 설계](engineering/specs/2026-08-02-language-assistant-control-tower-design.md)
- [구현 계획](engineering/plans/2026-08-02-language-assistant-graph.md)
- [Control Tower ledger](engineering/execution/control-tower.md)
