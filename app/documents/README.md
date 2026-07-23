# Documents

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
| HWP→PDF | Headless LibreOffice 직접 변환 |
| HWPX→HWP | `rhwp v0.7.19` |
| HWPX→PDF | Headless LibreOffice, 실패 시 HWP 경유 |
| HWPX→XML | section XML 추출과 스냅샷 저장 |
| XML→HWPX | 참조 스냅샷에 수정 XML 재패키징 |

외부 엔진은 요청별 ASCII 이름의 임시 디렉터리와 격리된 프로필에서 실행한다.
프로세스 종료 코드만 믿지 않고 결과도 다시 검증한다.

- HWP: CFB `FileHeader`와 HWP 5.x 서명
- HWPX: ZIP 구조, 필수 항목, 무압축 `mimetype`
- PDF: `%PDF-` 헤더

HWPX→PDF 직접 렌더링이 `DocumentConversionError`로 실패하면 임시 HWP를 만들고
HWP→PDF 변환기를 재사용한다. fallback까지 실패하면 직접 변환과 fallback 양쪽
오류를 함께 반환하며 임시 HWP는 항상 제거한다.

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

## 설정

```text
FOWOCO_HWP_TO_HWPX_ENABLED=true
FOWOCO_JAVA_PATH=java
FOWOCO_HWPX_TO_HWP_ENABLED=true
FOWOCO_RHWP_PATH=rhwp
FOWOCO_HWPX_PDF_ENABLED=true
FOWOCO_SOFFICE_PATH=soffice
FOWOCO_DOCUMENT_CONVERSION_TIMEOUT_SECONDS=120
FOWOCO_DOCUMENT_SNAPSHOT_DIR=/data/document-snapshots
```

Docker 이미지는 Java, 고정된 rhwp 바이너리, LibreOffice Writer, H2Orestart 필터와
CJK 글꼴을 포함한다.

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
