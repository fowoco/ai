---
name: review
description: "프로젝트 변경사항을 검토한다. 프로젝트 컨벤션이 있으면 이를 우선 적용하고, 없으면 diff·테스트·보안·에러 처리의 기본 기준으로 검토한다. 코드 리뷰, PR 준비, 변경사항 품질 점검 시 사용."
---

# /review — 변경사항 검토

변경된 코드와 문서를 근거로 위험을 찾는다. `wiki/conventions/`가 있으면 프로젝트 기준을 적용하고, 없거나 비어 있어도 기본 검토를 계속한다.

## Step 0 — 대상 결정

검토 전에 scope를 `working-tree`, `branch`, `explicit-files` 중 하나로 확정하고 다음 명령으로 fingerprint를 기록한다.

```bash
project-scaffold review fingerprint working-tree --json
```

**인자가 있으면** 해당 파일·디렉토리를 대상으로 한다.

**인자가 없으면** 변경된 파일 목록을 확인한다.

```bash
{ git diff --name-only HEAD; git ls-files --others --exclude-standard; } | sort -u
```

- 변경 파일이 있으면 해당 목록으로 진행
- 변경 파일이 없으면 경로를 직접 지정해달라고 안내하고 종료

## Step 1 — 검토 모드 결정

### 프로젝트 컨벤션 모드

`wiki/conventions/`에 코드 관련 문서가 있으면 관련된 페이지만 읽는다.

우선순위:

1. `03-naming.md`
2. `05-architecture.md`
3. `06-tdd.md`
4. `11-error-handling.md`
5. `12-security.md`
6. `02-tech-stack.md`

존재하지 않는 파일은 건너뛴다. 프로젝트 컨벤션과 기본 기준이 충돌하면 프로젝트 컨벤션을 우선한다.

### 기본 모드

`wiki/conventions/`가 없거나 비어 있으면 중단하지 않는다.

1. `AGENT.md`, README, package manifest, 변경 diff, 관련 테스트를 확인한다.
2. 다음 기본 기준으로 검토한다.
   - 하드코딩된 secret·token·credential
   - 검증되지 않은 외부 입력과 path traversal
   - 예상하지 못한 삭제·덮어쓰기·권한 변경
   - 오류 무시, 예외 삼키기, 실패를 성공처럼 보고하는 흐름
   - 변경 기능을 검증할 테스트 누락
   - 문서와 실제 동작의 불일치
3. 시작할 때 한 번만 다음처럼 알린다.

```text
프로젝트 컨벤션이 없어 기본 review 모드로 진행합니다.
프로젝트 고유 기준이 필요하면 나중에 /wiki setup으로 정의할 수 있습니다.
```

컨벤션 부재는 검토 실패가 아니며 `/wiki setup`은 권장 사항이다.

## Step 2 — 프로젝트가 이미 구성한 검증 실행

package manifest, CI 설정, README에서 프로젝트가 이미 사용하는 명령을 찾는다. 변경 범위에 맞는 typecheck, lint, test, build를 실행한다.

- 새 dependency나 global tool을 동의 없이 설치하지 않는다.
- 구성된 도구가 현재 환경에서 실행 불가능하면 `실행 불가(이유)`로 기록하고 나머지 검토를 계속한다.
- 프로젝트 컨벤션에 별도 명령이 있으면 그 명령을 우선한다.
- 명령이 전혀 없어도 LLM 기반 diff 검토는 계속한다.

## Step 3 — LLM 기반 검토

정적 도구가 잡지 못하는 맥락을 중심으로 점검한다.

| 항목 | 점검 내용 |
|---|---|
| 정확성 | 요청한 동작과 구현이 일치하는지, 경계 조건이 빠지지 않았는지 |
| 안전 | secret 노출, 입력 검증, 경로 탈출, 파괴적 변경 |
| 에러 처리 | 실패 전파, rollback, 부분 성공 보고, 오류 무시 |
| 테스트 | 변경된 행동을 재현하는 테스트와 실패 경로 |
| 유지보수 | 중복 판단, 숨은 상태 변경, 문서·코드 drift |
| 프로젝트 규칙 | 컨벤션 모드에서 로드한 프로젝트 고유 규칙 |

발견 사항은 반드시 파일과 줄 번호, 재현 근거를 포함한다. 추측은 확인 필요로 표시한다.

## Step 4 — 통합 리포트

심각도 순으로 결과를 제시한다.

```text
## /review 결과 — YYYY-MM-DD

모드: project-conventions | baseline

### Findings
- [HIGH] path/to/file.ts:23 — 문제와 실제 영향
  근거: 재현 방법 또는 위반한 프로젝트 규칙

### Verification
- typecheck: pass
- test: 실행 불가(이유)

### Recommendation
- 지금 수정할 항목
- 후속으로 검토할 항목
```

발견 사항이 없으면 `중대한 문제를 찾지 못함`이라고 쓰고, 실행하지 못한 검증과 남은 위험을 함께 적는다.

동시에 결과를 `.project-scaffold/local/reviews/<timestamp>.json`에 `ReviewResultV1`로 저장한다. requirements와 acceptance criteria를 입력 그대로 보존하고 다음 명령으로 검증한다.

```bash
project-scaffold review validate .project-scaffold/local/reviews/<timestamp>.json
project-scaffold review freshness .project-scaffold/local/reviews/<timestamp>.json
```

repository fingerprint가 바뀌면 이전 passed 결과도 stale이다. stale review를 현재 통과 증거로 사용하지 않는다. review 결과는 Project State의 goal, priority, milestone 상태를 직접 바꾸지 않는다.

## Step 5 — HITL 확인

HIGH 문제가 있으면 자동 수정하지 않고 먼저 결과를 보여준다. 사용자가 수정을 요청하면 해당 범위만 고친 뒤 검증을 다시 실행한다.

프로젝트 컨벤션의 예외를 인정해야 한다면 `wiki/conventions/` 변경은 별도 승인 후 수행한다.

## 규칙

| 항목 | 규칙 |
|---|---|
| 컨벤션 기준 | 있으면 우선 적용, 없으면 기본 모드로 계속 |
| 정적 도구 | 프로젝트에 이미 구성된 도구만 실행. 동의 없는 설치 금지 |
| 자동 수정 | 금지. 사용자가 수정을 요청한 범위만 적용 |
| 근거 | 모든 finding에 파일·줄·영향 또는 재현 근거 포함 |
| HITL | HIGH 문제는 수정 전에 사람 확인 |
| wiki 업데이트 | 예외 규칙 기록은 별도 승인 필요 |
