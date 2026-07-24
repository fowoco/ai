---
title: "Git 컨벤션"
type: convention
created: 2026-07-24
updated: 2026-07-24
---

# Git 컨벤션

## 커밋 메시지 규격
| 항목 | 내용 |
|---|---|
| **규칙** | Conventional Commits 규칙 준수 (`type: 설명`). Type 종류: `feat:`, `fix:`, `docs:`, `style:`, `refactor:`, `test:`, `chore:` |
| **이유** | 커밋 히스토리의 명확한 분류 및 변경사항 파악 용이성 보장 |
| **예시** | `feat: HWPX 문서 구조 Manifest 추출 기능 추가`, `docs: HWPX MCP README 한국어화` |
| **위반 시** | 의미 없는 커밋 메시지("수정", "update", "asdf") 사용 시 수정 요청 |

## 브랜치 전략 및 명명 규칙
| 항목 | 내용 |
|---|---|
| **규칙** | GitHub Flow 기반. `main` 브랜치를 기준으로 기능별 작업 브랜치(`feat/기능명`, `fix/버그명`, `docs/문서명`) 생성 후 작업 |
| **이유** | 팀 작업 간 충돌 방지 및 개별 파트 단위의 안전한 개발 |
| **예시** | `feat/manifest-extractor`, `fix/xml-escaping` |
| **위반 시** | `main` 브랜치 직접 push 작업 금지 |

## Pull Request 및 Merge 정책
| 항목 | 내용 |
|---|---|
| **규칙** | 작업 완료 후 PR 생성. 리뷰 및 테스트 통과 후 표준 PR Merge (Merge commit 생성 방식) 실행 |
| **이유** | 세부 개발 이력 보존 및 팀원 간 작업 내용 투명성 확보 |
| **예시** | feature 브랜치 작업 후 PR 작성 -> 리뷰 후 `Merge pull request` 실행 |
| **위반 시** | 검증 테스트 미통과 PR은 merge 불가 |
