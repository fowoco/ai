---
name: brief
description: "프로젝트 현황을 사람이 따라갈 수 있는 브리핑으로 정리한다. 현재 목표, 변경점, 결정 필요 항목, 다음 행동을 30초·5분·상세 깊이로 설명하고 dashboard, 회의·스프린트·ADR report, 세션 handoff를 생성한다. 진행 상황 파악, 대시보드 갱신, 보고서 작성, 세션 인계가 필요할 때 사용."
---

# /brief — 사람 중심 프로젝트 브리핑

항상 사람이 현재 상황과 자신의 결정 지점을 빠르게 파악하도록 구성한다.

## 사용자 호출 UX

자연어 요청에서 목적이 명확하면 묻지 말고 바로 적절한 작업을 수행한다.

- “지금 어디까지 했어?” → 기본 현황 브리핑
- “회의 내용 공유용으로 정리해줘” → report
- “다음 세션에서 이어가게 해줘” → handoff

사용자가 **`/brief`만 단독으로 호출하면**, git 상태·최근 devlog·대화 흐름을 먼저 확인하고 가장 적절한 항목을 추천한다. 내부 모드명 대신 사람이 이해하는 행동으로 묻는다.

```text
지금 맥락상 "현재 상태와 다음 우선순위 확인"이 가장 적절해 보여요.

1. 현재 상태를 30초로 보기 ← 추천
2. 최근 변화까지 5분으로 보기
3. 프로젝트 현황판 갱신하기
4. 회의·ADR·스프린트 문서 만들기
5. 다음 세션용 인계 남기기

어떤 걸 할까요? 번호나 원하는 내용을 말해줘도 됩니다.
```

추천 근거는 한 줄만 말한다. 사용자가 번호 대신 자연어로 답해도 의도를 다시 해석한다. 이미 목적이 분명한 요청에는 선택 메뉴를 보여주지 않는다.

## 기본 브리핑

별도 모드가 없으면 다음 순서로 답한다.

먼저 `project-scaffold brief 30s`를 실행해 검증된 Project State를 생성한다. 직접 Git·Wiki를 다시 조합해 별도 현황을 만들지 않는다.

프로젝트 설명·전체 목표·대상 사용자·운영 방식이 필요하면 `references/project-profile.md`를 읽는다. `wiki/project-profile.md`는 장기 정체성, `wiki/project-status.md`는 현재 실행 상태로 분리한다. 둘의 내용을 임의로 합치지 않는다.

브리핑 과정에서 현재 목표·우선순위·결정·위험·다음 행동이 바뀌었다면 `references/project-status.md`의 형식과 승인 절차를 따른다. 파일이 없으면 같은 절차로 생성을 제안한다. 추측으로 빈칸을 채우지 않는다.

CLI의 `brief refresh`, `brief start`와 Hub watcher는 `wiki/project-status.md`를 읽어 clone-local Project State를 재계산할 뿐 Markdown 원문을 수정하지 않는다. 사람이 직접 수정한 내용도 같은 입력으로 취급한다.

1. **Now** — 지금 목표와 현재 작업
2. **Why** — 이 작업을 하는 이유
3. **Since last visit** — 최근 코드·문서·결정 변화
4. **Decision queue** — 사용자가 판단해야 할 항목
5. **Next** — 가장 가까운 다음 한 단계
6. **근거** — 현재 상태를 계산할 때 사용한 wiki·devlog·Git 경로와 신뢰 상태

기본 깊이는 30초 분량이다. 사용자가 더 알고 싶어 하면 5분 또는 상세 보기로 확장한다. 진행률은 구현 근거가 있을 때만 숫자로 표시하고, 미구현 계획은 0%로 둔다.

`30s`, `5m`, `detail`은 같은 `snapshotId`를 사용한다. state가 stale이면 최신 정보처럼 설명하지 말고 `project-scaffold brief refresh`를 먼저 제안한다.

## 내부 모드 라우팅

| 모드 | 대표 의도 | 읽을 참조 |
|---|---|---|
| `dashboard` | 현황판 갱신, TODO·마일스톤 관리, terminal/web 렌더 | `references/dashboard.md` |
| `report` | 회의록, 인터뷰, ADR, 스프린트 요약 | `references/report.md` |
| `handoff` | 세션 저장·복원·목록·정리 | `references/handoff.md` |

사용자가 프로젝트 현황, 최근 변경, 다음 우선순위를 물으면 명시적 호출이 없어도 기본 브리핑으로 처리한다.

## 프로젝트 프로필

사용자가 프로젝트 소개, 전체 목표, 대상 사용자, Personal·Team 운영 방식, Home 내용을 묻거나 바꾸려 하면 `references/project-profile.md`를 따른다.

- 확인한 사실, 근거 있는 제안, 미확정 항목을 구분한다.
- agent 추론을 확정 사실로 기록하지 않는다.
- 기존 사람이 작성한 내용을 승인 없이 정리하거나 교체하지 않는다.
- 새 파일과 의미 있는 변경은 preview 뒤 사람 승인을 받는다.
- 승인 전 tracked file mutation은 0건이다.
- 승인된 write 뒤 `project-scaffold brief refresh`를 실행한다.
- profile 부재나 오류가 current status briefing을 막지 않게 한다.

## 공통 원칙

- `brief start`, `status`, `stop`은 localhost read-only Hub의 백그라운드 lifecycle을 관리한다.
- `brief serve`는 같은 Hub를 foreground에서 실행하는 개발·진단용 명령이다.
- `brief serve --share-lan`은 임시 token을 요구하며 private·quarantine source를 전송하지 않는다.
- 완료된 구현과 미래 계획을 분리한다.
- project identity와 current execution을 분리한다.
- 요약만 제공하고 끝내지 말고 사용자가 결정해야 할 지점을 드러낸다.
- 원본과 해석을 구분하고 관련 파일로 이동할 수 있게 한다.
- 같은 내용을 여러 산출물에 복제하지 말고 기존 PR·커밋·wiki 경로를 참조한다.
- 민감 정보는 handoff와 report에 저장하기 전에 검열한다.
- caveman skill이 설치되어 있으면 briefing과 Wiki 문장에 caveman lite를 사용한다. raw source, 인용문, command, error output, security guidance는 압축하지 않는다.
- `Goal`은 핵심 결과를 1문장으로 쓴다. 구현 목록을 이어 붙이지 않는다.
- `Why`는 최대 2문장으로 쓴다. 첫 문장은 현재까지 확보한 상태, 둘째 문장은 지금 풀 병목을 말한다.
- 한 문장에는 한 주장만 둔다. 군더더기·예고·중복 설명을 빼되 기술명과 검증 조건은 보존한다.
