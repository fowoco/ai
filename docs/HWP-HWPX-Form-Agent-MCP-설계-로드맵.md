# HWP·HWPX Form Agent MCP 설계·로드맵

- 상태: 로컬 구현·검증 중
- 작성일: 2026-07-24
- 목표: 기존 행정서식 HWPX를 읽고, 사용자 인터뷰로 입력값을 수집하고, 승인된 변경만 안전하게 적용하는 범용 MCP Server

## 1. 제품 방향

### 1.1 최종 목표

Codex의 DOCX 편집 경험과 비슷한 HWP·HWPX 편집 MCP를 만든다.

사용자는 문서 구조를 알 필요 없다.

```text
HWPX 전달
  Agent가 문서 분석
  입력 가능한 항목 제시
  사용자와 섹션별 인터뷰
  수정 계획 미리보기
  사용자 승인
  새 파일 생성
  원본·수정본 비교
  검증 통과 후 결과 제공
```

### 1.2 첫 MVP

기준 문서: 표준근로계약서 HWPX

첫 입력 범위:

- 업체명
- 전화번호
- 소재지
- 사용자 성명
- 근로자 성명
- 생년월일
- 본국 주소

첫 MVP에서 제외:

- 새 문서 생성
- HWP 바이너리 직접 편집
- 계약기간·임금 입력
- 체크란·사진·전자서명
- 자유로운 레이아웃 재설계
- 원본 덮어쓰기

## 2. 핵심 설계 원칙

- 자연어는 입력 방식이다.
- 실제 편집은 제한된 Edit Plan으로만 수행한다.
- XML 분석 결과와 화면 렌더링 결과를 함께 사용한다.
- 같은 라벨이 여러 번 나오면 자동 결정하지 않는다.
- 미확정 필수 여부를 Agent가 추정하지 않는다.
- 값 형식 변환은 원본과 변환안을 함께 보여준다.
- 승인 전에는 파일을 생성하지 않는다.
- 수정 후 레이아웃 오류가 있으면 파일 생성을 차단한다.
- 원본은 항상 보존한다.
- 개인정보는 양식 프로필에 저장하지 않는다.

## 3. 전체 워크플로우

### 3.1 문서 분석

1. 사용자가 HWPX 파일을 전달한다.
2. 허용된 작업 폴더 안으로 입력 파일을 확인한다.
3. HWPX ZIP·XML 구조를 검증한다.
4. `rhwp`로 페이지를 렌더링한다.
5. 문단·표·셀·이미지·체크란 후보를 만든다.
6. XML 좌표와 화면 좌표를 연결한다.
7. 문서 Manifest를 반환한다.

Manifest 예시:

```json
{
  "document_id": "doc-001",
  "format": "hwpx",
  "pages": 2,
  "sections": ["section0"],
  "tables": 8,
  "images": 0,
  "field_candidates": [
    {
      "id": "table.0.cell.12",
      "label": "업체명",
      "type": "text",
      "current_value": "",
      "status": "unconfirmed"
    }
  ]
}
```

### 3.2 Agent 인터뷰

Agent가 한 번에 모든 질문을 쏟아내지 않는다.

섹션별로 3~5개 필드를 묶는다.

```text
1. 사용자 정보
2. 근로자 정보
3. 계약기간
4. 근로장소·업무
5. 근로시간·휴일
6. 임금
7. 숙식·지급방법
8. 서명·날짜
```

질문 규칙:

- 값이 비어 있는 후보만 질문한다.
- 선택 필드는 건너뛸 수 있다.
- 미확정 필수 여부는 사용자에게 묻는다.
- 같은 라벨 후보가 여러 개면 위치를 보여주고 선택받는다.
- 질문에 필요한 페이지 캡처를 함께 제공할 수 있다.
- 입력값이 모호하면 재질문한다.
- 법적 의미나 필수 여부를 Agent가 임의로 판단하지 않는다.

### 3.3 값 검증·정규화

전화번호·날짜·금액은 문서 형식에 맞는 변환안을 만든다.

```text
입력값: 1990.1.1
변환안: 1990년 1월 1일

입력값: 01012345678
변환안: 010-1234-5678
```

변환 결과는 적용 전에 보여준다. 사용자 승인 없이 조용히 바꾸지 않는다.

### 3.4 Edit Plan 생성

사용자 답변을 바로 XML에 쓰지 않는다.

```json
{
  "document_id": "doc-001",
  "operations": [
    {
      "operation": "set_cell_text",
      "target_id": "table.0.cell.12",
      "label": "업체명",
      "old_value": "",
      "new_value": "ABC",
      "confidence": "confirmed"
    }
  ],
  "approval_required": true
}
```

Edit Plan에 없는 변경은 실행하지 않는다.

### 3.5 미리보기·승인

미리보기에는 다음을 포함한다.

- 수정 대상
- 표·행·열·셀 위치
- 기존값
- 변경값
- 값 정규화 결과
- 수정 전 페이지 캡처
- 수정 후 예상 페이지 캡처
- 변경 영역 강조
- 레이아웃 위험 경고

사용자가 명시적으로 승인하기 전에는 `apply_edit_plan`을 호출하지 않는다.

### 3.6 적용·검증

1. 원본을 임시 작업 대상으로 복사한다.
2. 승인된 Edit Plan만 적용한다.
3. 새 출력 경로에 저장한다.
4. HWPX ZIP·XML 구조를 검증한다.
5. `rhwp`로 수정본을 같은 조건에서 렌더링한다.
6. 구조 차이와 이미지 차이를 계산한다.
7. 예상하지 않은 변경을 찾는다.
8. 레이아웃 오류가 있으면 출력 파일을 제공하지 않는다.
9. 통과하면 결과 파일·검증 보고서·비교 캡처를 제공한다.

## 4. Reviewer 구조

Reviewer는 Agent의 시각 판단 하나로 끝내지 않는다.

```text
구조 검사
  페이지 수
  표·셀 수
  문단 수
  이미지 수
  XML 참조

렌더링 검사
  원본 PNG
  수정본 PNG
  변경 영역
  글자 잘림
  셀 밖 넘침
  표 크기 변화
  이미지 위치 변화

`rhwp`가 원본에도 보고한 `LAYOUT_OVERFLOW`는 기준선으로 보존한다. 수정본에서 새로 발생한 레이아웃 경고만 결과 차단 사유로 삼는다.

Agent Reviewer
  예상된 변경인지 설명
  양식 훼손 여부 판단

사용자 승인
  최종 파일 제공
```

### 정상 변경

- 승인한 이름·주소·전화번호 입력
- 승인한 값 정규화
- 승인한 셀 텍스트 변경

### 비정상 변경

- 다른 셀 내용 변경
- 표 크기 붕괴
- 글자 잘림
- 이미지 위치 이탈
- 페이지 수의 예상 외 증가
- 빈 페이지 생성
- 한글·영문 일부 소실

예상하지 않은 변경이 있으면 파일 생성을 차단한다.

## 5. 프레임워크·구성 요소

### 5.1 MCP

공식 MCP Python SDK의 `FastMCP` 사용.

현재 프로젝트는 안정 버전 계열을 사용한다.

```toml
mcp[cli]>=1.27,<2
```

공식 SDK 문서 기준 v1.x가 현재 안정 계열이고, v2는 사전 릴리스 계열이다. 버전 변경 시 별도 마이그레이션 작업으로 처리한다. [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)

### 5.2 FastMCP 역할

FastMCP는 MCP Tool·Resource·Prompt를 선언하고 MCP Client와 연결하는 서버 레이어다.

담당:

- Tool 노출
- 입력 Schema 생성
- MCP Client 연결
- `stdio` Transport
- 향후 Streamable HTTP Transport

담당하지 않음:

- 사용자 인터뷰 전체 상태
- HWPX 의미 분석
- 편집 승인 정책
- 시각 비교 알고리즘

### 5.3 FastAPI 역할

FastAPI는 일반 HTTP Control Plane으로 사용한다. FastAPI 자체가 MCP Server를 대체하지 않는다. 현재는 같은 MCP 기능을 호출하는 로컬 최소 골격까지 구현했다. [FastAPI 공식 문서](https://fastapi.tiangolo.com/)

담당:

- 현재: 상태 확인, 문서 분석, Edit Plan 생성, 승인·적용 요청
- 예정: 파일 업로드, 세션 상태 조회, 인터뷰 진행 상태 조회
- 예정: 미리보기 이미지·검증 보고서 제공, 웹 UI·팀 서비스 연결

초기에는 로컬 실행만 허용한다. 원격 배포·인증은 로컬 검증 이후 추가한다.

### 5.4 rhwp 역할

`rhwp`는 Rust·WebAssembly 기반 HWP/HWPX 문서 엔진이다. 파싱·렌더링·편집·저장·페이지 출력·Debug Overlay를 제공한다. [rhwp 공식 저장소](https://github.com/edwardkim/rhwp)

초기 역할:

- HWP/HWPX 구조 분석
- 페이지 PNG·SVG 렌더링
- 표·문단 경계 확인
- 페이지·문단 레이아웃 조회
- 수정 전후 시각 비교

연동 방식은 PoC 후 결정한다.

후보:

- `rhwp` CLI를 별도 프로세스로 실행
- Rust sidecar와 연결
- WASM API를 별도 Node 프로세스로 실행
- 안정적인 API 확인 후 직접 라이브러리 연동

첫 선택은 CLI 또는 sidecar다. Python MCP Server와 Rust 문서 엔진을 느슨하게 분리한다.

### 5.5 데이터·검증 구성

- Python: MCP·HTTP·업무 흐름
- Pydantic: 입력·Edit Plan·검증 결과 Schema
- `defusedxml`: 안전한 XML 읽기
- Pillow 또는 동등한 이미지 비교 모듈: PNG 차이 계산
- pytest: 단위·통합·프로토콜 테스트
- JSON: 초기 양식 프로필 저장
- SQLite: 세션·프로필이 복잡해질 때 확장

LangGraph는 1차에 사용하지 않는다. 현재 흐름은 명확한 상태 전이로 구현하고, 분기·재시도·장기 세션이 복잡해질 때 검토한다.

## 6. MCP Tool 설계

### 6.1 1차 Tool

```text
inspect_document
  HWPX 구조·필드 후보·유효성 반환

render_document
  페이지별 PNG·SVG·Debug Overlay 생성

create_edit_plan
  사용자 답변을 승인 대기 Edit Plan으로 변환

preview_edit_plan
  예상 수정본 렌더링·경고·변경 목록 생성

apply_edit_plan
  승인된 Plan만 새 파일에 적용

compare_document_versions
  원본·수정본 구조와 이미지 비교

validate_document
  HWPX 재검증
```

`interview_user`는 1차 MCP Tool로 만들지 않는다. 사용자와의 대화는 Host의 Agent가 수행하고, MCP는 문서 구조·후보·계획·실행 결과를 제공한다.

### 6.2 서브 기능

```text
save_form_profile
  필드 위치·구조 지문·검증 규칙 저장

load_form_profile
  같은 양식의 기존 매핑 불러오기

compare_form_profile
  양식 구조 변경 여부 확인
```

기본 저장 위치는 사용자 컴퓨터다. 프로젝트 공유는 선택 기능이다.

저장하지 않는 값:

- 이름
- 주소
- 주민등록번호
- 전화번호
- 실제 문서 입력값

## 7. FastAPI Endpoint 초안

```text
POST /documents
  HWPX 업로드·문서 ID 발급

POST /documents/{document_id}/analyze
  XML·rhwp 분석 실행

GET /documents/{document_id}/manifest
  구조·필드 후보 조회

POST /sessions
  인터뷰 세션 생성

GET /sessions/{session_id}
  현재 질문·답변·미확정 필드 조회

POST /sessions/{session_id}/answers
  사용자 답변 저장

POST /plans/{plan_id}/preview
  예상 변경본과 캡처 생성

POST /plans/{plan_id}/apply
  승인된 Plan 적용

GET /artifacts/{artifact_id}
  캡처·보고서·결과 파일 제공
```

MCP와 FastAPI는 같은 Application Service를 호출한다. 두 진입점이 XML을 각각 직접 수정하지 않는다.

## 8. 상태 모델

```text
RECEIVED
  ANALYZED
  INTERVIEWING
  PLAN_READY
  PREVIEW_READY
  WAITING_APPROVAL
  APPLYING
  REVIEWING
  VALIDATED
  BLOCKED
  FAILED
```

### 상태별 규칙

- `ANALYZED`: 읽기만 가능
- `INTERVIEWING`: 답변·미확정 필드 기록
- `PLAN_READY`: Edit Plan 생성, 파일 변경 없음
- `WAITING_APPROVAL`: 사용자 승인 필요
- `APPLYING`: 새 출력 경로만 사용
- `REVIEWING`: 구조·렌더링 비교
- `VALIDATED`: 결과 파일 제공 가능
- `BLOCKED`: 오류 원인·수정안만 제공

## 9. 양식 프로필

### 기본 동작

```text
처음 보는 양식
  자동 분석
  사용자 확인
  선택적으로 프로필 저장

다시 보는 양식
  구조 지문 확인
  프로필 불러오기
  변경된 부분만 재확인
```

프로필 저장 대상:

- 양식 식별자
- 구조 지문
- 필드 이름
- 표·행·열·셀 위치
- 체크란 위치
- 이미지 삽입 위치
- 입력 형식
- 필수·선택·미확정 상태
- 검증 규칙

## 10. 보안·Harness 경계

- 허용된 작업 폴더만 접근
- 입력 파일과 출력 파일 분리
- 원본 덮어쓰기 차단
- `..`·심볼릭 링크 경로 탈출 차단
- 파일·압축 해제 크기 제한
- 안전한 XML 파서 사용
- Script 실행 금지
- 승인 없는 Edit Plan 실행 금지
- 실패한 출력 파일 삭제
- 임시 파일 만료 처리
- 개인정보를 양식 프로필에 저장하지 않음
- 모든 적용 결과에 검증 보고서 연결

MCP는 기능 연결을 담당한다. FastAPI는 현재 분석·계획·승인 적용 경로를 제공하고, 향후 세션·미리보기를 확장한다. 실제 허용·차단·검증은 공유 실행 경계가 담당한다.

## 11. 개발 단계

### Phase 0. rhwp 연동 검증

- 표준근로계약서 샘플 읽기
- 페이지 PNG·SVG 생성
- 표·문단 Debug Overlay 확인
- 필드·표 셀 구조 조회
- 원본 저장 없이 round-trip 가능성 확인

완료 기준: 샘플을 열고 구조와 화면을 재현한다.

### Phase 1. 문서 Manifest

- `inspect_document` 확장
- 표·셀·문단·이미지 후보 모델 정의
- XML 위치와 화면 위치 연결
- `render_document` 구현

### Phase 2. 다중 필드 입력

- 사용자·근로자 정보 7개 필드
- `fill_cells`로 확인된 여러 셀에 값 입력
- 섹션별 인터뷰
- 중복 라벨 후보 선택
- 날짜·전화번호 정규화
- 필수·선택·미확정 상태

### Phase 3. 승인·비교·차단

- Edit Plan
- 수정 전·후 캡처
- 구조 diff
- 이미지 diff
- 예상 외 변경 차단
- 검증 보고서

### Phase 4. 양식 프로필

- 로컬 JSON 저장
- 구조 지문
- 재사용 매핑
- 구조 변경 시 재분석
- 선택적 프로젝트 공유

### Phase 5. 행정서식 기능 확장

- 계약기간
- 임금
- 체크란
- 사진
- 전자서명
- 표 셀 병합·분할
- 필드 형식 검증

### Phase 6. 범용화

- HWP 5.0 지원 검증
- 여러 행정서식 프로필
- HWPX→HWP 변환 경로
- Streamable HTTP
- 인증·사용자별 권한
- 웹 UI
- 팀 공유 저장소

## 12. 1차 Acceptance Criteria

표준근로계약서 HWPX에 대해:

- 사용자가 파일을 전달할 수 있다.
- Agent가 사용자·근로자 정보 필드 후보를 보여준다.
- 섹션별 인터뷰가 진행된다.
- 7개 필드를 한 번에 수집할 수 있다.
- 중복 라벨을 자동 오입력하지 않는다.
- 날짜·전화번호 변환안을 보여준다.
- 승인 전 파일이 생성되지 않는다.
- 올바른 셀에만 값이 입력된다.
- 원본이 변경되지 않는다.
- 수정 전·후 캡처가 제공된다.
- 구조 diff와 이미지 diff가 생성된다.
- 레이아웃 오류 시 결과 제공이 차단된다.
- 정상 결과만 새 `.hwpx`로 제공된다.
- HWPX 재검증이 통과한다.

## 13. 현재 상태

현재 구현:

- 로컬 stdio MCP Server
- 로컬 FastAPI Control Plane 최소 Endpoint
- HWPX ZIP·XML 검사
- 표·행·열·셀 구조 Manifest
- 라벨 셀·인접 빈 셀 기반 입력 후보와 `requires_user_confirmation` 반환
- `rhwp` CLI 호출 어댑터
- `render_document` Tool의 페이지별 SVG·Debug Overlay 렌더링
- `compare_document_versions` Tool의 구조·SVG SHA-256 비교
- 승인 대기 `EditPlan` 생성과 원본 지문·계획 무결성 검증 후 적용
- 날짜·전화번호 정규화 결과를 원본과 함께 반환
- 표준근로계약서 대표 7개 입력 후보 확인
- 표준근로계약서 7개 후보의 실제 Edit Plan 적용·검토 확인
- 승인된 셀 외 변경·문서 구조 변화·페이지 수 변화를 적용 후 차단
- 원본 `rhwp` 레이아웃 경고 기준선 보존 및 신규 경고 차단
- 확인된 셀 여러 개 값 입력
- 본문 텍스트 추출
- 제한적 문자열 치환
- 원본 덮어쓰기 방지
- 출력 파일 재검증
- 테스트 `18 passed`
- 공식 `rhwp v0.7.19`로 표준근로계약서 2페이지 렌더링 확인

아직 구현하지 않은 것:

- Agent 인터뷰 세션
- 렌더링 결과를 포함한 미리보기와 레이아웃 차단
- 픽셀 기반 렌더링 비교 (PNG 렌더러 확보 전)
- PNG 렌더링
- 양식 프로필
- 표준근로계약서 7개 필드 인터뷰 세션
- FastAPI 파일 업로드·세션·인증

## 14. 다음 작업

1. 이미지 포함 HWPX 샘플과 이미지 삽입·교체 구조를 검증한다.
2. 승인된 Edit Plan에 수정 전·후 렌더 비교와 예상 외 변경 차단을 연결한다.
3. 표준근로계약서 7개 후보를 Agent 인터뷰 질문과 연결한다.
4. FastAPI 파일 업로드·세션 Endpoint가 필요한지 실제 사용으로 검증한다.
5. 결과에 따라 Python 편집기를 유지할지 `rhwp` 기반으로 교체할지 결정한다.

## 참고 자료

- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [FastAPI 공식 문서](https://fastapi.tiangolo.com/)
- [rhwp 공식 저장소](https://github.com/edwardkim/rhwp)
- [MCP Architecture](https://modelcontextprotocol.io/docs/learn/architecture)
