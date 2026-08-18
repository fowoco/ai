# Documents

## 레코드 기반 XML 자동 기입

DB 연결 전에는 `app/documents/records`의 `TextRecordReader`가 UTF-8
`key=value` TXT 파일을 DB 레코드 대신 읽는다. 읽은 값은 템플릿별 고정 규칙을
거쳐 HWPX 내부 `Contents/section0.xml`의 지정 셀에 입력된다.

```text
테스트 TXT 또는 향후 DB Reader
→ 공통 RecordReader 계약
→ template_id별 XmlCellRule
→ XML 테이블/행/열에 값 기입
→ 중간 HWPX 패키지 저장
→ API에서 HWP로 변환해 다운로드
```

규칙은 단순한 라벨 검색이 아니라 `table_index`, `row`, `column`과 기입 방식을
사용한다. 기입 방식은 빈 셀 설정(`set`), 기존 라벨 뒤에 값 추가(`append`),
기존 단위 앞에 값 추가(`prepend`), 값 다음 줄에 원문 안내문을 보존하는
`prepend_line`, 셀 안의 표식 치환(`replace`)을 지원한다.
따라서 한 양식 안에 `성명`, `전화번호`처럼 같은 라벨이 여러 번 있어도 서로
다른 XML 셀에 연결할 수 있다.

현재 다음 네 템플릿의 규칙과 테스트 TXT가 준비되어 있다.

- `identity_guaranty_v129`
- `employment_extension_application_v12_3`
- `immigration_integrated_application_v34`
- `standard_labor_contract_v6`

DB를 연결할 때는 `RecordReader` 계약을 구현하는 DB 어댑터를 추가하면 된다.
템플릿 규칙과 HWPX 생성 코드는 변경하지 않는다. `company.company_id`처럼 문서에
매핑되지 않은 DB 컬럼은 무시하며, 실제로 매핑된 컬럼이 하나도 없으면 오류를
반환한다. ERD 컬럼과 양식별 누락값은
[ERD 기반 문서 레코드 매핑](records/README.md)에 정리되어 있다.

`app/documents`는 자연어와 무관한 문서 도메인 계층이다. HWP 5.x 바이너리 편집,
HWPX ZIP/XML 처리, 템플릿 식별, 포맷 변환, XML 왕복을 위한 스냅샷을 담당한다.

한컴오피스 COM 자동화는 사용하지 않는다.
HTTP 요청과 오류 계약은 [Internal API 문서](../api/README.md)를 참고한다.

## 디렉터리 구조

```text
app/documents/
├─ common/
│  ├─ formats.py                  공통 포맷 enum
│  └─ detection.py                내용 기반 포맷 감지
├─ conversion/
│  ├─ protocol.py                 DocumentConverter 규약
│  ├─ registry.py                 변환기 등록·최단 경로 실행
│  ├─ errors.py                   변환 공통 오류
│  ├─ converters/                 포맷별 변환 구현
│  └─ engines/                    외부 프로세스 어댑터
├─ editing/
│  ├─ service.py                  HWP/HWPX 편집·생성 facade
│  ├─ models.py                   템플릿·검사·편집 결과
│  ├─ template_names.py           공식 양식 표시명
│  └─ exceptions.py               편집 도메인 오류
├─ hwp5/
│  ├─ editor.py                   HWP 5.x 본문 레코드 편집
│  ├─ compound_file.py            OLE/CFB 재구성
│  ├─ image_processing.py         사진·서명 전처리
│  ├─ service.py                  템플릿 기반 공개 서비스
│  ├─ template_registry.py        SHA-256 식별
│  └─ templates/                  원본 HWP와 필드 맵 JSON
├─ hwpx/
│  ├─ package.py                  안전한 ZIP 검증·재패키징
│  ├─ section_xml.py              section XML 처리
│  ├─ editor.py                   공개 편집 facade
│  ├─ service.py                  생성·XML 추출·재패키징
│  ├─ template_registry.py        HWPX 템플릿 조회
│  └─ templates/                  원본 HWPX
├─ records/
│  ├─ text_reader.py              TXT/DB RecordReader 계약
│  ├─ rules.py                    템플릿별 XmlCellRule
│  ├─ service.py                  레코드 → HWPX 자동 기입
│  └─ README.md                   ERD 매핑 정리
├─ snapshots/
│  ├─ repository.py               패키지·메타데이터·이름 별칭
│  ├─ fingerprint.py              입력값을 제외한 레이아웃 지문
│  └─ xml_metadata.py             XML snapshot-ref 처리
└─ xml/                            XML 전용 확장 위치
```

## 변환 구조

모든 변환기는 `DocumentConverter` 규약을 구현하고 하나의 입력/출력 포맷 쌍을
선언한다. `DocumentConversionService`는 등록된 변환기를 그래프로 보고 가장 짧은
경로를 실행한다.

| 변환기 | 엔진 또는 방식 |
|---|---|
| HWP→HWPX | `hwp2hwpx==1.0.1` Java/JAR |
| HWP→PDF | `rhwp v0.7.19` native PDF exporter |
| HWPX→HWP | `rhwp v0.7.19` |
| HWPX→PDF | `rhwp v0.7.19` native PDF exporter |
| HWPX→XML | section XML 추출과 스냅샷 저장 |
| XML→HWPX | 참조 스냅샷에 수정 XML 재패키징 |

외부 엔진은 요청별 ASCII 이름의 임시 디렉터리와 격리된 프로필에서 실행한다.
프로세스 종료 코드만 믿지 않고 결과도 다시 검증한다.

- HWP: CFB `FileHeader`와 HWP 5.x 서명
- HWPX: ZIP 구조, 필수 항목, 무압축 `mimetype`
- PDF: `%PDF-` 헤더

PDF 변환은 LibreOffice의 HWP import filter를 사용하지 않는다. `rhwp export-pdf`가
원본 HWP/HWPX를 직접 해석하고, Server가 제공한 실제 데모 양식의 페이지 수와
가독성을 Smoke Test로 확인한다. 산출물은 PDF 서명뿐 아니라 PDF parser로 페이지와
media box 구조까지 다시 검증하며 임시 파일은 항상 제거한다.

## XML 스냅샷 왕복

HWP/HWPX→XML 변환은 다음 순서로 동작한다.

```text
HWP 입력이면 HWPX로 변환
→ HWPX 패키지 구조 지문 계산
→ 원본 HWPX 패키지 스냅샷 저장
→ section XML 추출
→ XML에 snapshot-ref 처리 명령 삽입
```

예시 메타데이터:

```xml
<?fowoco snapshot-ref="64자리-sha256" section="0"?>
```

XML→HWPX/HWP/PDF에서는 이 참조로 원본 패키지를 찾고, 수정된 section XML만 교체한다.
따라서 원본 양식의 스타일, 이미지, 바이너리 리소스와 패키지 메타데이터를 유지할 수
있다.

XML 편집 시 지켜야 할 규칙:

- `snapshot-ref` 처리 명령을 유지한다.
- XML 네임스페이스와 태그 구조를 유지한다.
- 일반적으로 텍스트 노드와 의도한 체크 상태만 수정한다.
- 표·문단·리소스 참조를 임의로 제거하면 재패키징 후 렌더링이 깨질 수 있다.

처리 명령이 제거된 경우 확장자를 제외한 파일명으로 별칭을 찾는다.

```text
신원보증서.hwp → 신원보증서.xml
```

이름은 Unicode NFC, 대소문자, 연속 공백을 정규화한다. 같은 이름과 같은 구조에서
입력값만 달라진 문서는 같은 양식으로 판단하고 별칭을 최신 스냅샷으로 갱신한다.
같은 이름에 다른 구조 지문이 들어오면 기존 양식을 덮어쓰지 않고 충돌로 처리한다.

스냅샷 저장 구조:

```text
document-snapshots/
├─ packages/       SHA-256로 명명한 불변 HWPX
├─ metadata/       구조 지문, section, 이름 정보
└─ aliases/        정규화한 문서 이름 → 최신 snapshot-ref
```

Docker에서는 `FOWOCO_DOCUMENT_SNAPSHOT_DIR=/data/document-snapshots`를 사용하며
Compose가 `fowoco-document-data:/data` 볼륨을 연결한다. 볼륨이 사라지면 기존 XML의
참조도 복원할 수 없다.

## HWP 5.x 템플릿 편집

등록된 템플릿으로 문서를 생성한다.

```python
from app.documents.hwp5 import Hwp5DocumentService

service = Hwp5DocumentService()
result = service.generate(
    "immigration_integrated_application_v34",
    output_path,
    values={
        "family_name": "HONG",
        "given_names": "GILDONG",
        "application_stay_extension": True,
    },
    images={
        "photo": photo_path,
        "applicant_signature": signature_path,
    },
)
```

업로드 HWP는 SHA-256으로 템플릿을 자동 식별한 뒤 편집할 수 있다.

```python
result = service.fill(
    uploaded_hwp,
    output_path,
    values=values,
    images=images,
)
```

원본 템플릿 해시와 필드 맵이 일치하지 않으면 바이너리 레코드 위치를 추측하지 않고
생성을 거부한다.

## HWPX 템플릿 편집

```python
from app.documents.hwpx import HwpxDocumentService

service = HwpxDocumentService()
result = service.generate(
    "immigration_integrated_application_v34",
    output_path,
    values={"성": "PARK", "명": "TAEJUNG"},
    application_options={"외국인 등록": True},
)
```

HWPX 처리는 ZIP entry 경로, 중복 entry, 압축 해제 크기, 필수 패키지 파일을 검증한
뒤 수행한다.

## 통합 편집 facade

API는 포맷별 서비스를 직접 분기하지 않고 `DocumentEditingService`를 사용한다.

```text
DocumentEditingService
├─ HWP  → Hwp5DocumentService.fill()/generate()
└─ HWPX → HwpxDocumentService.fill()/generate()
```

이 facade는 다음을 한 곳에서 처리한다.

- 네 가지 템플릿의 HWP/HWPX 변형 조회
- 업로드 파일 포맷과 원본 템플릿 식별
- 입력 포맷을 유지하는 구조화 편집
- 템플릿 기반 신규 생성
- HWPX에서 요청한 동적 라벨이 실제로 모두 변경됐는지 검증
- 포맷별 asset 지원 차이를 명시적 오류로 반환

HWP 필드 맵의 `text`, `checkbox`, `photo`, `signature` 타입은 API 템플릿 상세에 그대로
노출한다. HWPX는 아직 정적 필드 맵이 없고 표 라벨을 동적으로 찾으므로 템플릿 응답의
필드 목록은 비어 있으며 `supports_dynamic_labels=true`다.

## 설정

```text
FOWOCO_HWP_TO_HWPX_ENABLED=true
FOWOCO_JAVA_PATH=java
FOWOCO_HWPX_TO_HWP_ENABLED=true
FOWOCO_RHWP_PATH=rhwp
FOWOCO_HWPX_PDF_ENABLED=true
FOWOCO_DOCUMENT_CONVERSION_TIMEOUT_SECONDS=120
FOWOCO_DOCUMENT_SNAPSHOT_DIR=/data/document-snapshots
```

Docker 이미지는 Java, 고정된 rhwp 바이너리와 CJK 글꼴을 포함한다.
rhwp Linux 공식 바이너리가 x86_64만 제공되므로 이미지는 `linux/amd64`로 빌드한다.
Apple Silicon Docker Desktop에서는 amd64 emulation을 사용한다.

### Server 실제 데모 양식 Smoke Test

Server 저장소와 AI 저장소를 함께 받은 개발 환경에서는 아래 스크립트로 Server의
합성 HWP 1종과 HWPX 3종을 그대로 검증한다. 성공 기준은 계약서 2쪽, 취업활동기간
연장신청서 2쪽, 통합신청서 1쪽이며 PDF parser 검증과 최소 파일 크기도 함께 확인한다.

```bash
python -m scripts.smoke_server_document_pdf \
  --fixture-dir ../server/src/main/resources/demo-data/document-templates \
  --output-dir /tmp/fowoco-document-preview \
  --rhwp-path rhwp
```

macOS에서는 `rhwp` 공식 macOS binary의 절대 경로를 `--rhwp-path`에 지정할 수 있다.

## 확장 방법

새 포맷 변환을 추가할 때:

1. `conversion/converters/`에 `DocumentConverter` 구현을 추가한다.
2. 외부 프로그램 호출은 `conversion/engines/`로 분리한다.
3. 입력과 출력 컨테이너를 모두 검증한다.
4. `app/api/dependencies.py`에서 기능 플래그에 따라 등록한다.
5. 단위 테스트와 Docker 실제 변환 테스트를 추가한다.
6. 신규 양식은 PDF 시각 회귀 검증을 별도로 수행한다.

현재 스냅샷 저장소는 단일 테넌트 파일 저장소다. 다중 테넌트 운영에서는 저장 키에
tenant ID를 포함하고 패키지는 객체 스토리지, 메타데이터와 별칭은 DB로 분리하는 것이
안전하다.
