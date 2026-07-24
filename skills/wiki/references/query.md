# wiki query — 프로젝트 지식 질의응답

wiki/ 를 기반으로 질문에 답한다.
기본 동작은 읽기 전용이다. 사용자가 명시적으로 저장을 요청한 답변만 wiki/synthesis/ 에 저장한다.


## Step 0.5 — 기존 그래프 우선 탐색

`graphify-out/graph.json` 존재 여부를 확인한다.

- **있으면**: freshness metadata가 현재 Wiki digest와 일치할 때만 연관 문서 후보로 사용한다. inferred edge는 명시적 backlink와 구분한다.
- **없으면**: Graphify 설치 여부를 확인하거나 설치를 권하지 않고 Step 1로 진행한다.
- 사용자가 Graphify 사용이나 설정을 명시한 요청은 query가 아니라 setup·Graphify 작업으로 분리한다.

---

## Step 1 — index.md 먼저 읽기

Step 0.5에서 충분히 좁혀지지 않았거나 Graphify를 안 쓰는 경우 여기서 진행한다.

`wiki/index.md` 를 읽어 질문과 관련된 페이지를 파악한다.

우선순위:
1. `wiki/conventions/` — 컨벤션 관련 질문
2. `wiki/decisions/` — 아키텍처 결정 관련 질문
3. `wiki/devlog/` — 개발 진행 관련 질문
4. `wiki/dashboard.md` — 할 일·우선순위 관련 질문
5. `wiki/meetings/` — 회의 결정 관련 질문

---

## Step 2 — 관련 페이지 읽기 & 답변 합성

파악한 페이지들을 읽고 답변을 합성한다.

**답변 형식:**
- 출처는 반드시 `[[페이지명]]` wikilink로 인용
- 사실과 해석을 구분한다
- 모순이 있으면 `> ⚠️ 모순` 블록으로 양쪽 제시

**답변 유형별 형식:**
- 컨벤션 질문 → 규칙·이유·예시 포함
- 진행 상황 질문 → 타임라인 형식
- 의사결정 질문 → 결정 배경과 근거 포함

---

## Step 3 — raw/ 보충 (필요 시)

wiki/ 에 정보가 부족한 경우에만 `raw/` 를 추가로 읽는다.
raw/ 에서 가져온 정보는 "(raw/ 직접 참조)" 표시를 붙인다.

---

## Step 4 — 명시적 요청에서만 저장

사용자가 저장을 명시한 경우에만 `wiki/synthesis/[슬러그].md` 로 저장한다. 일반 질문, 여러 source 종합, 새로운 연결 발견만으로 자동 저장하지 않는다.

저장 시 log.md에 기록:
```text
## [YYYY-MM-DD] query | [질문 요약]

- **참조 페이지:** 목록
- **Synthesis 저장:** [[페이지명]] 또는 "없음"
```

---

## 규칙

| 항목 | 규칙 |
|---|---|
| 읽기 순서 | fresh graph 후보 → index.md → wiki/ → raw/shared/ (최후 수단) |
| 그래프 미설치 | 안내를 반복하지 않고 index.md 폴백 |
| 인용 형식 | `[[페이지명]]` wikilink 필수 |
| raw/ | 절대 수정 금지 |
| 기본 mutation | 0개. 명시적 save intent에서만 synthesis와 operation log 생성 |
| 답변 없을 때 | "현재 wiki에 충분한 정보가 없습니다. /wiki ingest 로 관련 소스를 추가해보세요." |
