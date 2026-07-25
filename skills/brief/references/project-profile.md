# project profile 제안과 승인

`wiki/project-profile.md`는 프로젝트의 정체성 기준 문서다. 사람과 agent가 함께 관리하지만 최종 승인 권한은 사람에게 있다.

## status와 분리

- profile: 프로젝트 설명, 대상 사용자, 전체 목표, 운영 방식, 성공 기준
- status: 현재 집중, 우선순위, 결정, 위험, 다음 행동

현재 branch, 최근 PR, 오늘 할 일은 `wiki/project-status.md`에 둔다. 장기 정체성과 현재 실행 상태를 한 문서에 합치지 않는다.

## 읽기 순서

1. 기존 `wiki/project-profile.md`
2. README와 package metadata
3. `wiki/index.md`와 핵심 Wiki 문서
4. 현재 코드 구조

기존 profile이 있으면 사람이 작성한 내용을 기준으로 삼는다. 다른 source와 다르다는 이유만으로 자동 교체하지 않는다.

## 정보 상태

초안의 각 핵심 내용은 다음 중 하나로 분류한다.

- `확인됨`: source가 직접 뒷받침한다.
- `제안`: source를 바탕으로 agent가 제안한다.
- `미확정`: 근거가 부족하거나 사람 판단이 필요하다.

추론을 사실로 기록하지 않는다. 모르면 `operationModel: undecided`, `goalStatus: draft`, open question 또는 빈 값으로 둔다.

contributor 수, commit author 수, remote 수로 Personal·Team을 판정하지 않는다.

## 표준 형식

```md
---
id: project-profile
type: project-profile
schemaVersion: 1
title: Project Profile
operationModel: undecided
goalStatus: draft
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: []
---

# Project Profile

## Summary

프로젝트 한 줄 설명

## Description

프로젝트가 해결하는 문제와 존재 이유

## Target users

- 대상 사용자

## Overall goal

전체 목표

## Success measures

- [ ] 측정 가능한 성공 기준

## Open questions

- 아직 결정하지 않은 질문

## Core technologies

- 핵심 기술

## Key documents

- [[project-status]]
```

`sources`에는 Wiki stable ID만 넣는다. repository path는 `Key documents`에 둔다. 근거가 없으면 `sources: []`로 둔다.

## proposal workflow

1. profile 존재 여부와 문법 상태를 확인한다.
2. source에서 확인한 사실을 수집한다.
3. 사실·제안·미확정 항목을 나눈다.
4. 기존 사람이 작성한 문장을 보존한 변경안을 만든다.
5. 핵심 변경 preview를 보여준다.
6. 사람에게 승인을 묻는다.
7. 승인하면 파일을 한 번 쓴다.
8. `project-scaffold brief refresh`를 실행한다.

승인 전 mutation은 0건이다. 거절하면 파일과 Project State를 바꾸지 않는다. 수정 요청을 받으면 해당 항목만 고쳐 다시 preview한다.

## preview

긴 raw Markdown 전체를 먼저 보여주지 않는다.

```text
프로젝트 프로필 초안

설명
  repo-native project context와 Brief Hub를 제공하는 CLI

전체 목표 · 가안
  여러 coding agent가 같은 프로젝트 정체성과 현재 상태를 읽게 한다.

운영 방식
  아직 정하지 않음

확인이 필요한 항목 · 2개
  - 대상 사용자 범위
  - 성공 기준

근거
  - README.md
  - wiki/index.md

이 내용으로 wiki/project-profile.md를 만들까요?
```

선택은 `만들기`, `전체 초안 보기`, `취소`다. 기본 선택은 `취소`다.

기존 파일 변경이면 추가·수정·보존 항목을 구분한다. 전체 diff는 사용자가 요청할 때 보여준다.

## 항상 승인받는 변경

- Summary
- Description
- Target users
- Overall goal
- Success measures
- `operationModel`
- `goalStatus`

`created`, `updated` 날짜만 바꾸기 위한 write는 하지 않는다.

## 오류와 부재

profile 없음:

- 읽기 요청은 `missing`으로 보고한다.
- install, update, briefing을 막지 않는다.
- 생성을 원하면 preview와 승인을 거친다.

profile 문법 오류:

- 원문을 보존한다.
- 자동 template 교체를 하지 않는다.
- 오류 위치와 고칠 값을 제안한다.
- 수정도 preview와 승인을 거친다.

unknown frontmatter key와 section:

- 읽을 수 있으면 보존한다.
- agent가 필요 없다고 판단해 삭제하지 않는다.

## 승인 없이 가능한 작업

- profile 읽기
- schema 검증
- Project State와 Hub freshness 확인
- 현재 파일 기준 `brief 30s`, `5m`, `detail`

Hub refresh는 tracked Markdown을 쓰지 않는다. 승인된 profile write가 끝난 뒤에만 state refresh를 실행한다.

