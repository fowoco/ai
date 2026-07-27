# brief dashboard — 하나의 Project State 보기

대시보드가 Git과 Wiki를 독자적으로 다시 계산하지 않게 한다. terminal, 30초, 5분, 상세, HTML은 모두 `.project-scaffold/local/state/project-state.json`을 읽는다.

## 기본 흐름

```bash
project-scaffold brief refresh
project-scaffold brief 30s
project-scaffold brief 5m
project-scaffold brief detail
```

모든 view에 같은 `snapshotId`를 표시한다.

## 화면 우선순위

- 개요 첫 화면은 릴리스보다 `오늘 할 일`을 먼저 보여준다.
- 릴리스와 마일스톤이 없는 프로젝트도 정상이다. 이때 `계획` 화면은 현재 집중, 우선순위, 다음 행동, 나중에 할 것을 보여준다.
- 결정, 위험, 다음 행동은 항목마다 독립된 카드로 보여준다. 여러 항목을 하나의 긴 문단처럼 합치지 않는다.
- 검토 결과가 없으면 빈 화면 대신 `/review 현재 작업 트리를 검토해줘`라는 다음 행동을 안내한다.
- 체크박스는 Project State의 읽기 전용 표현이다. Hub가 Markdown 원문을 직접 수정하지 않는다.

`wiki/project-status.md`의 작성 형식과 사람 승인 절차는 [project-status.md](project-status.md)를 따른다.

## source 권한

- `wiki/project-status.md`: 사람이 선언한 goal, why, focus, priority
- Git: HEAD, dirty state, recent changes의 관찰 근거
- Wiki page: decision, risk, provenance의 근거
- ReviewResult: 특정 repository fingerprint의 검토 evidence
- HTML과 terminal: 검증된 state의 view

Git 관찰로 사람이 선언한 goal이나 milestone을 자동 완료 처리하지 않는다. `candidate` milestone은 progress 분모에서 제외한다.

## 기존 dashboard

`wiki/dashboard.md`는 0.2 호환 문서다. 자동 삭제하거나 덮어쓰지 않는다. 0.3 현황은 Project State를 기준으로 하며, 기존 dashboard는 migration candidate로만 표시한다.

## freshness

state의 HEAD, working tree fingerprint 또는 참조 Wiki digest가 현재와 다르면 stale이다. stale state는 최신 현황처럼 보여주지 않고 refresh action을 먼저 제공한다.
