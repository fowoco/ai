# Internal API

`app/api`는 FastAPI 라우팅, 요청·응답 검증, 파일 전송, 문서 서비스 조립을 담당한다.
실제 HWP/HWPX 편집이나 외부 변환 프로세스 실행 코드는 `app/documents`에 둔다.
내부 문서 처리 방식은 [문서 처리 아키텍처](../documents/README.md)를 참고한다.

## 진입점

| 항목 | 주소 |
|---|---|
| Swagger UI | `GET /docs` |
| OpenAPI JSON | `GET /openapi.json` |
| 문서 기능 조회 | `GET /api/v1/documents/capabilities` |
| 범용 문서 변환 | `POST /api/v1/documents/convert` |
| XML 변환 호환 경로 | `POST /api/v1/documents/convert/from-xml` |

`/convert/from-xml`은 기존 클라이언트 호환을 위해 유지한다. 신규 호출은 입력 포맷을
자동 감지하는 `/convert` 하나를 사용하면 된다.

## 범용 문서 변환

```http
POST /api/v1/documents/convert
Content-Type: multipart/form-data
```

요청 필드는 두 개뿐이다.

| 필드 | 형식 | 필수 | 설명 |
|---|---|---:|---|
| `file` | binary | 예 | HWP, HWPX, XML 또는 PDF 입력 |
| `target_format` | string | 예 | `hwp`, `hwpx`, `xml`, `pdf` 중 출력 포맷 |

`source_format`, `options`, `template_id`는 받지 않는다. 서버가 다음 구조를 검사해 입력
포맷을 자동 판별한다.

- HWP: OLE/CFB 컨테이너와 `FileHeader`
- HWPX: ZIP 패키지와 `mimetype`
- XML: 안전한 XML 파싱
- PDF: `%PDF-` 헤더

파일 확장자가 알려진 포맷이면서 감지 결과와 다르면 HTTP 400을 반환한다. 성공 응답의
`X-Detected-Source-Format` 헤더에서 감지된 입력 포맷을 확인할 수 있다.

### HWP→XML

```powershell
curl.exe -X POST "http://localhost:8000/api/v1/documents/convert" `
  -F "file=@document.hwp" `
  -F "target_format=xml" `
  --output document.xml
```

이 호출은 XML만 추출하는 것이 아니라 원본 리소스가 포함된 HWPX 스냅샷도 영속
저장한다. 반환 XML에는 원본 패키지를 가리키는 불투명한 `snapshot-ref`가 포함된다.

### 편집한 XML→HWP

```powershell
curl.exe -X POST "http://localhost:8000/api/v1/documents/convert" `
  -F "file=@document.xml" `
  -F "target_format=hwp" `
  --output document.hwp
```

### 편집한 XML→PDF

```powershell
curl.exe -X POST "http://localhost:8000/api/v1/documents/convert" `
  -F "file=@document.xml" `
  -F "target_format=pdf" `
  --output document.pdf
```

XML 내부 `snapshot-ref`가 있으면 파일명을 바꿔도 정확한 원본 스냅샷을 찾는다. 참조가
없으면 확장자를 제외한 XML 파일명으로 최신 스냅샷 별칭을 조회한다.

## 지원 조합

실행 중인 worker에 실제 등록된 변환 조합은
`/api/v1/documents/capabilities` 응답을 기준으로 판단한다. Docker 기본 구성에서는
다음 조합을 제공한다.

```text
HWP  → HWPX, XML, PDF
HWPX → HWP,  XML, PDF
XML  → HWP,  HWPX, PDF
```

직접 변환기가 없으면 가장 짧은 변환 그래프를 조합한다.

```text
HWP → XML: HWP → HWPX → XML
XML → HWP: XML → HWPX → HWP
XML → PDF: XML → HWPX → PDF
```

HWP는 LibreOffice로 바로 PDF 변환한다. HWPX→PDF가 문서 호환성 문제로 실패하면
`HWPX → HWP → PDF` fallback을 자동 실행하며 XML→PDF도 같은 fallback을 사용한다.

## 응답과 오류

성공 시 변환 파일을 attachment로 반환하며 원래 파일명의 stem과 출력 확장자를
사용한다.

| 상태 | 의미 |
|---:|---|
| 200 | 변환 성공 |
| 400 | 파일 확장자 불일치 또는 XML 전용 경로에 잘못된 입력 |
| 404 | XML이 참조하는 스냅샷을 찾을 수 없음 |
| 409 | 같은 문서 이름이 서로 다른 양식 구조에 이미 연결됨 |
| 413 | 업로드 크기 제한 초과 |
| 422 | 지원하지 않는 조합, 손상된 문서, 변환 실패 |
| 503 | Java, rhwp, LibreOffice 등 설정된 엔진을 사용할 수 없음 |

기본 업로드 제한은 50 MiB이며
`FOWOCO_DOCUMENT_UPLOAD_MAX_BYTES`로 변경한다. 현재 변환 API는 동기 방식이므로
reverse proxy에도 요청 크기와 timeout을 함께 설정해야 한다.

## 코드 배치

```text
app/api/
├─ dependencies.py                 worker 단위 서비스·변환기 조립
├─ router.py                       `/api/v1` 하위 라우터 구성
├─ routes/documents/
│  ├─ capabilities.py              등록된 기능 조회
│  └─ convert.py                   업로드·변환·다운로드
└─ schemas/documents/
   └─ capabilities.py              capability 응답 모델
```

새 API를 추가할 때 지킬 경계:

- 라우트는 HTTP 입력을 도메인 타입으로 바꾸고 오류를 HTTP 상태로 매핑한다.
- 파일 포맷 로직과 외부 프로세스 실행은 `app/documents`에 구현한다.
- 구현체 조립은 `dependencies.py`에서 수행한다.
- OpenAPI 요청 필드와 실제 동작을 API 테스트로 함께 고정한다.
