# project status 작성과 승인

`wiki/project-status.md`는 사람이 선언한 현재 상태의 기준 문서다. `/brief`는 근거를 확인해 변경안을 만들 수 있지만 승인 전에 파일을 생성하거나 수정하지 않는다.

## 표준 형식

```md
---
id: project-status
type: project-status
title: Project Status
sources:
---

## Goal

현재 목표 한 문장. 달성할 결과와 검증 기준만 쓴다.

## Why

현재까지 확보한 상태 한 문장. 지금 풀 병목 한 문장.

## Focus

- 현재 집중할 범위

## Priorities

1. 첫 번째 우선순위

## Deferred

- 명시적으로 나중에 할 것

## Decision queue

- 결정이 필요한 항목

## Risks

- 현재 위험

## Next actions

- [ ] 지금 할 일
- [x] 완료한 일
```

표준 제목은 영어로 저장하고 Hub는 한국어로 표시한다. 기존 문서의 `Current goal`, `Why now`, `Current focus`, `Explicitly deferred`, `Risks and trust`와 대응하는 한국어 제목은 읽기 호환만 제공한다.

## 문장 계약

`Goal`과 `Why`는 caveman lite 방식으로 쓴다. 짧지만 완전한 문장을 사용하고 기술적 의미는 줄이지 않는다.

- `Goal`: 1문장. 무엇을 어떤 상태로 만들고 어떻게 확인할지만 쓴다.
- `Why`: 최대 2문장. 현재까지 확보한 상태와 지금 풀 병목을 한 문장씩 쓴다.
- 기능 목록, 구현 이력, 배경 설명을 한 문장에 이어 붙이지 않는다.
- 자세한 구현 범위는 `Focus`, `Priorities`, 근거 문서로 내린다.
- raw source, 인용문, 명령어, 오류, 보안 지침은 축약하지 않는다.

## 사람 승인

새 파일 생성 또는 의미 있는 내용 변경 전에 다음처럼 한 번만 묻는다.

```text
현황판을 이렇게 바꾸려고 합니다.

목표
  SpecFlow의 Notion read-only 연결을 실제 workspace에서 검증

오늘 할 일
  + OAuth 승인
  + read smoke test
  - 완료되어 제거: OAuth API skeleton

판단 필요 2개 · 위험 1개

근거
  wiki/dashboard.md
  최신 devlog 2개
  현재 Git branch와 working tree

이 내용으로 wiki/project-status.md를 업데이트할까요?
```

전체 Markdown diff부터 보여주지 않는다. 목표, 추가·제거된 할 일, 결정·위험 개수와 핵심 근거를 먼저 보여준다. 사용자가 상세 내용을 요청할 때만 diff를 펼친다.

승인하면 파일을 한 번 쓰고 `project-scaffold brief refresh`를 실행한다. 거절하면 아무 파일도 바꾸지 않는다. 일부 수정 요청이면 요청받은 항목만 고쳐 다시 한 번 묻는다.

다음은 승인 없이 수행한다.

- `brief 30s`, `5m`, `detail`로 현재 상태 읽기
- `brief start`, `status`, `stop`
- snapshot 재계산
- freshness 확인

문장 다듬기, 시각화 갱신, snapshot 변경만으로 매번 승인받지 않는다. 사람의 목표, 우선순위, 결정, 위험, 다음 행동 의미가 바뀔 때만 승인받는다.
