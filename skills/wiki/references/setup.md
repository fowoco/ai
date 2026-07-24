# wiki setup — 프로젝트 초기 인터뷰

프로젝트 시작 시 실행. 기존 코드베이스가 있으면 먼저 스캔해 컨벤션을 추론한 뒤,
2~3시간 인터뷰를 통해 팀 컨벤션을 확정하고 `wiki/conventions/`와 `AGENT.project.md`를 갱신한다. 생성물인 `AGENT.md`와 package policy는 직접 편집하지 않는다.

## 목차

- Step 0: 기존 설정 확인과 코드베이스 스캔
- Step 1: 14개 인터뷰 카테고리 안내
- Step 2: 카테고리별 인터뷰와 즉시 저장
- Step 3: 프로젝트 policy 갱신
- Step 4: Graphify 확인
- 페이지 형식과 실행 규칙


## Step 0 — 기존 설정 확인

`wiki/conventions/`에 실제 컨벤션 문서(`.gitkeep` 제외한 `*.md` 파일)가 있는지 확인한다.

- **문서가 없으면**: Step 0.5로 진행
- **문서가 있으면**: 다음을 안내한다:

  > "이미 설정된 컨벤션이 있습니다. 재설정하면 기존 `wiki/conventions/`가 덮어써집니다.
  > 재설정할까요? (yes / no)"

  - `no` → 종료
  - `yes` → Step 0.5로 진행

---

## Step 0.5 — 코드베이스 스캔 (기존 프로젝트 감지)

코드베이스에 **소스 파일이 있는지** 확인한다 (`.git/`, `wiki/`, `skills/`, `scripts/` 제외).

- **소스 파일이 없으면** (완전히 빈 새 프로젝트): 스캔 생략, Step 1로 진행
- **소스 파일이 있으면** (기존 프로젝트): 아래 스캔을 실행한다

### 스캔 항목

| 항목 | 방법 |
|---|---|
| 주 언어 | 파일 확장자 빈도 (`find . -name "*.py" -o -name "*.ts" ...` 등) |
| 테스트 프레임워크 | `pytest.ini`, `setup.cfg [tool:pytest]`, `jest.config.*`, `vitest.config.*`, `go test`, `*.test.ts` 존재 여부 |
| 패키지 매니저·의존성 | `requirements.txt`, `pyproject.toml`, `package.json`, `go.mod`, `Cargo.toml` 읽기 |
| 폴더 구조 | 최상위 폴더명 목록 → feature-based / layer-based / flat 판단 |
| Git 커밋 형식 | `git log --oneline -20` → "feat:", "fix:", "[JIRA-]" 등 패턴 분석 |
| 브랜치 전략 | `git branch -a` → main/develop/feature/* 등 패턴 |
| 네이밍 패턴 | 실제 파일명 샘플 10개 → snake_case / camelCase / PascalCase 판단 |

### 스캔 결과 출력

```text
기존 코드베이스 감지 — 컨벤션을 추론했어요

✅ 확실    Python 3.x / FastAPI (requirements.txt에서 확인)
✅ 확실    pytest 사용 중 (pytest.ini 존재)
✅ 확실    커밋 형식 "feat: / fix:" (최근 15/20 커밋 적합)
⚠️ 추정    폴더 구조 layer-based (src/, tests/, docs/ 감지)
⚠️ 추정    함수명 snake_case (파일명 샘플 8/10 적합)
❓ 불명확  브랜치 전략 — main 1개만 존재
```

인터뷰 중 해당 카테고리에서 `(감지: pytest)` 형식으로 사전 제안값을 보여주고,
사용자가 확인 또는 수정할 수 있게 한다.

Step 1로 진행한다.

---

## Step 1 — 인터뷰 개요 안내

다음 14개 카테고리를 보여주고 시작 여부를 확인한다:

```
인터뷰 카테고리 (예상 소요: 2~3시간)

1.  프로젝트 개요        8.  HITL 리스크 기준
2.  기술 스택            9.  대시보드 설정
3.  네이밍 컨벤션        10. 코드리뷰 체크리스트
4.  Git 컨벤션           11. 에러 핸들링
5.  아키텍처 규칙        12. 보안 컨벤션
6.  TDD 규칙             13. 의존성 관리
7.  devlog 템플릿        14. 개인 작업 선호 (SOUL.local.md, 선택)
```

> "각 카테고리가 끝날 때마다 `wiki/conventions/` 페이지가 생성됩니다.
> 중간에 중단해도 완료된 카테고리는 보존됩니다. 시작할까요?"

- `yes` → Step 2로 진행
- `no` → 종료

---

## Step 2 — 카테고리별 인터뷰

각 카테고리를 순서대로 진행한다. **카테고리마다 아래 사이클을 반복한다:**

```text
[카테고리명] 시작 알림
  → Step 0.5 스캔 결과 중 해당 카테고리 관련 추론값이 있으면 먼저 보여준다
     예: "현재 코드 기준으로 pytest 감지. 이걸로 확정할까요?"
  → 서브 질문들을 하나씩 순서대로 질문 (이미 추론된 항목은 확인만)
  → 각 답변마다 ambiguity-check.md 실행
  → 모든 서브 질문 완료
  → 카테고리 요약 보여주고 확인
  → wiki/conventions/[슬러그].md 즉시 생성
  → 다음 카테고리로
```

**사전 제안값 표시 형식:**

> "테스트 프레임워크는 **pytest** (감지됨)로 확정할까요? 다른 게 있으면 말해줘."

스캔 결과가 없는 항목은 기존 인터뷰 방식과 동일하게 질문한다.

### ambiguity-check 규칙

모든 답변에 대해 `skills/wiki/references/ambiguity-check.md`의 기준을 적용한다.
기준을 통과할 때까지 follow-up을 멈추지 않는다.

---

### 카테고리 1 — 프로젝트 개요
**파일**: `wiki/conventions/01-project-overview.md`

서브 질문:
1. 이 프로젝트로 무엇을 달성하려 해?
2. 완성 기준이 뭐야? 어떻게 되면 끝이야?
3. 마일스톤이 있어? 몇 단계야?
4. 데드라인이 있어?
5. 혼자야 팀이야? 팀이면 역할 분담은?

---

### 카테고리 2 — 기술 스택
**파일**: `wiki/conventions/02-tech-stack.md`

서브 질문:
1. 주 언어가 뭐야?
2. 프레임워크가 정해졌어?
3. DB를 쓸 거야? 어떤 거?
4. 배포 환경은?
5. 외부 API 연동이 있어?

---

### 카테고리 3 — 네이밍 컨벤션
**파일**: `wiki/conventions/03-naming.md`

서브 질문:
1. 변수·함수명 스타일이 뭐야? (snake_case, camelCase, PascalCase...)
2. 클래스명 규칙은?
3. 파일명 규칙은?
4. 폴더 구조 패턴은? (feature-based, layer-based...)
5. 상수 표기법은?

---

### 카테고리 4 — Git 컨벤션
**파일**: `wiki/conventions/04-git.md`

서브 질문:
1. 브랜치 전략이 뭐야? (Git Flow, GitHub Flow...)
2. 브랜치명 형식은? (feat/, fix/, hotfix/...)
3. 커밋 메시지 형식은?
4. PR은 어떻게 올려? 리뷰어 지정이 있어?
5. merge 방식은? (squash, rebase, merge commit)

---

### 카테고리 5 — 아키텍처 규칙
**파일**: `wiki/conventions/05-architecture.md`

서브 질문:
1. 폴더 구조 패턴이 뭐야? (MVC, Clean Architecture, DDD...)
2. 레이어 간 의존성 방향 규칙이 있어?
3. 레이어 간 통신 방식은?

---

### 카테고리 6 — TDD 규칙
**파일**: `wiki/conventions/06-tdd.md`

서브 질문:
1. 테스트 프레임워크가 뭐야?
2. 테스트 파일 위치는? (같은 폴더? tests/ 폴더?)
3. 테스트명 형식은?
4. 최소 커버리지 기준은?
5. 단위·통합·E2E 어디까지 할 거야?

---

### 카테고리 7 — devlog 템플릿
**파일**: `wiki/conventions/07-devlog.md`

서브 질문:
1. 각 devlog 항목에 뭐가 들어가야 해?
2. 공유 대상이 누구야? (팀원, 상사, 공개?)
3. 형식은? (bullet, 서술형...)

---

### 카테고리 8 — HITL 리스크 기준
**파일**: `wiki/conventions/08-hitl-risk.md`

서브 질문:
1. 반드시 사람이 확인해야 하는 변경이 뭐야? (HIGH)
2. 자동 승인해도 되는 변경은? (LOW)
3. 알림만 받고 싶은 중간 수준은? (MEDIUM)

---

### 카테고리 9 — 대시보드 설정
**파일**: `wiki/conventions/09-dashboard.md`

서브 질문:
1. 가장 먼저 보고 싶은 정보가 뭐야?
2. 오늘 할 일 목록은 어떻게 보여줄까?
3. 마일스톤 진행도가 보여야 해?

---

### 카테고리 10 — 코드리뷰 체크리스트
**파일**: `wiki/conventions/10-code-review.md`

서브 질문:
1. PR 올리기 전 스스로 확인해야 할 것들이 뭐야?
2. 리뷰어가 반드시 봐야 할 것들은?
3. 자동으로 체크할 수 있는 게 뭐야?

---

### 카테고리 11 — 에러 핸들링
**파일**: `wiki/conventions/11-error-handling.md`

서브 질문:
1. 예외 처리 방식이 뭐야? (try-except 어디까지?)
2. 로깅 레벨 기준은? (DEBUG, INFO, ERROR 언제?)
3. 에러 메시지 형식은?

---

### 카테고리 12 — 보안 컨벤션
**파일**: `wiki/conventions/12-security.md`

서브 질문:
1. 환경변수 관리 방식이 뭐야? (.env, secret manager...)
2. 코드에 절대 하드코딩 금지인 것들은?
3. 인증·인가 처리 규칙이 있어?

---

### 카테고리 13 — 의존성 관리
**파일**: `wiki/conventions/13-dependencies.md`

서브 질문:
1. 패키지 추가 전 승인이 필요해?
2. 버전 고정 정책은? (pin, range...)
3. 허용·금지 패키지 목록이 있어?

---

### 카테고리 14 — 개인 작업 선호
**파일**: `SOUL.local.md` (선택, Git에 커밋하지 않는 로컬 파일)

> 팀 정책과 분리해야 하는 대화 방식·설명 깊이만 기록한다. 이 파일의 내용은 프로젝트 정책, 안전 규칙, 현재 사용자 지시를 덮어쓸 수 없다.

서브 질문:
1. 말투는 어떻게 해줘? (격식체/비격식체, 반말/존댓말)
2. 내 개발 경험 수준은 어느 정도야? (설명 깊이 기준)
3. 틀린 게 있으면 바로 말해줘 vs 부드럽게 유도해줘?
4. 모르면 먼저 물어봐 vs 일단 시도해봐?
5. 주로 어떤 언어로 대화할 거야?

사용자가 원할 때만 `SOUL.local.md`를 답변 기반으로 갱신한다. 기존 파일이 있으면 변경 내용을 먼저 보여주고 승인을 받는다.

---

## Step 3 — 프로젝트 policy 갱신

모든 14개 카테고리 완료 후 팀이 편집하는 `AGENT.project.md`를 갱신한다. `.project-scaffold/policy/base.md`는 package가 관리하고, `AGENT.md`는 두 source를 deterministic compiler로 합성한 결과이므로 직접 수정하지 않는다.

### AGENT.project.md 구조

```markdown
# Project policy — [프로젝트명]

## 프로젝트 개요
(카테고리 1 요약)

## 기술 스택
(카테고리 2 요약)

## 핵심 불변 규칙 (항상 적용)

### TDD 강제
- 기능 코드 작성 전 반드시 테스트 파일 먼저 작성
- (카테고리 6의 TDD 규칙 핵심 embed)

### HITL 리스크 기준
- HIGH: 반드시 사람 확인 후 진행
- MEDIUM: 비동기 알림
- LOW: 자동 승인
(카테고리 8의 리스크 기준 embed)

### 보안 필수 규칙
- (카테고리 12의 핵심 규칙 embed)

## 컨벤션 참조
작업 전 관련 컨벤션 페이지를 읽고 따른다:
- 네이밍: @wiki/conventions/03-naming.md
- Git: @wiki/conventions/04-git.md
- 아키텍처: @wiki/conventions/05-architecture.md
- TDD: @wiki/conventions/06-tdd.md
- 에러 핸들링: @wiki/conventions/11-error-handling.md
- 보안: @wiki/conventions/12-security.md
- 의존성: @wiki/conventions/13-dependencies.md

## 스킬 사용법
- /wiki — setup·capture·devlog·ingest·query·lint
- /brief — 현황 브리핑·dashboard·report·handoff
- /review — 컨벤션 기반 변경사항 검토

## Intent Router

사용자가 스킬명을 기억하지 않아도 요청 의도에 따라 관련 스킬을 선택한다:
- 프로젝트의 현재 상태·다음 우선순위 → /brief
- 과거 결정·컨벤션·프로젝트 맥락 질문 → /wiki query
- 회의·결정 기록 → /wiki capture
- 작업 세션 기록 → /wiki devlog
- raw 소스 반영 또는 wiki 품질 점검 → /wiki ingest 또는 /wiki lint
- PR·push 전 변경사항 검토 → /review

```

---

## wiki/conventions/ 페이지 형식

각 페이지의 모든 규칙은 다음 4필드로 작성한다:

```markdown
---
title: "[카테고리명]"
type: convention
created: YYYY-MM-DD
updated: YYYY-MM-DD
---

# [카테고리명]

## [규칙명]

| 항목 | 내용 |
|---|---|
| **규칙** | 구체적인 규칙 서술 |
| **이유** | 이 규칙을 정한 이유 |
| **예시** | 올바른 예 / 잘못된 예 |
| **위반 시** | 에이전트·훅이 취할 액션 |
```

---

## Step 4 — 선택 기능 안내

프로젝트 policy 갱신 완료 후 Graphify를 선택적으로 설정할 수 있다고 한 번만 안내한다. 과장된 절감 수치나 자동 설치 명령은 제시하지 않는다.

> "큰 wiki의 관계 탐색이 필요하면 Graphify를 별도로 설정할 수 있습니다. 지금 설정 방법을 볼까요?"

- **Yes** → 공식 문서와 대상 scope를 먼저 보여주고 설치·indexing 전 각각 동의를 받는다.
- **No** → 안내를 저장하지 않고 종료한다. 이후 query·ingest에서 다시 묻지 않는다.
- Graphify 없이도 index와 Markdown 기반 wiki 흐름은 정상 동작한다.

---

## 규칙

| 항목 | 규칙 |
|---|---|
| ambiguity-check | 모든 답변에 반드시 실행. 통과할 때까지 follow-up |
| 중단 복구 | 이미 생성된 카테고리 파일은 재실행 시 스킵 가능 |
| 카테고리 순서 | 1→14 순서 고정. 건너뛰기 불가 |
| 프로젝트 policy 갱신 | 14개 전부 완료 후 `AGENT.project.md`에 반영. 생성된 `AGENT.md`를 직접 편집하지 않음 |
| SOUL.local.md | 카테고리 14에서 사용자가 원할 때만 로컬에 갱신. 프로젝트 policy보다 우선하지 않음 |
| 기존 파일 덮어쓰기 | Step 0에서 명시적 동의 받은 경우에만 허용 |
| 코드베이스 스캔 | Step 0.5는 읽기만. 어떤 파일도 수정하지 않는다 |
| 사전 제안값 | 추론이 불명확(❓)한 항목은 제안 없이 직접 질문 |
| 스캔 실패 시 | 항목별로 조용히 건너뜀. 전체 스캔 실패해도 인터뷰 계속 진행 |
