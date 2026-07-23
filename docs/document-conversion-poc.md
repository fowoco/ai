# HWP/HWPX 양방향 변환 PoC

## 결론

| 변환 | 후보 | 결과 | 운영 반영 |
|---|---|---|---|
| HWP→HWPX | `hwp2hwpx 1.0.1` | 템플릿 4종 변환 및 HWPX 패키지 검증 성공 | 채택 |
| HWPX→HWP | `rhwp 0.7.19` | 템플릿 4종 변환, 페이지 검증 및 표준 CFB 재파싱 성공 | 채택 |
| HWPX→HWP | `hwp-extension 0.4.2` | 자체 파서는 재파싱했으나 표준 CFB 파서에서 FAT 구조 오류 | 제외 |

## 운영 경로

```text
HWP
 └─ HwpToHwpxConverter
     └─ JavaHwp2HwpxEngine
         └─ hwp2hwpx JAR

HWPX
 └─ HwpxToHwpConverter
     └─ RhwpEngine
         └─ rhwp convert --verify --verify-pages
```

두 엔진은 사용자 파일명을 외부 프로세스에 직접 넘기지 않는다. 요청별 임시
디렉터리에 `input.hwp` 또는 `input.hwpx`로 복사해 실행하고 결과 구조를 재검증한 뒤
목적지로 원자적으로 이동한다.

`hwp2hwpx 1.0.1`의 원본 출력은 ZIP의 `mimetype` 항목을 압축해 LibreOffice가
읽지 못했다. 엔진 어댑터에서 해당 항목을 HWPX 패키지 관례에 맞게 무압축으로
재패키징하도록 보정했으며, 보정된 `HWP→HWPX→PDF` 연쇄 변환을 검증했다.

HWP→HWPX 결과의 공백을 제외한 본문 문자열을 원본 HWP 레코드의 본문과 비교한 결과,
템플릿 3종은 일치율 100%, 표준근로계약서는 99.49%였다. HWPX→HWP는 `rhwp`의
`--verify --verify-pages` 검증에서 네 템플릿 모두 IR 및 페이지 차이가 없었다.

## 검증 기준

- HWP→HWPX: ZIP/HWPX 패키지를 열 수 있고 `Contents/section0.xml`이 존재해야 한다.
- HWPX→HWP: `rhwp`의 IR·페이지 검증이 성공해야 한다.
- 생성 HWP: 표준 OLE/CFB 파서로 열리고 `FileHeader` 스트림의 서명이
  `HWP Document File`이어야 한다.
- 프로세스 실패, 제한 시간 초과, 결과 파일 누락, 결과 구조 오류는 모두 변환 실패로
  처리하며 기존 목적지 파일을 교체하지 않는다.

## Docker

- `hwp2hwpx`는 Python 패키지 버전 `1.0.1`로 고정한다.
- Java 실행을 위해 `default-jre-headless`를 설치한다.
- `rhwp` Linux x86_64 릴리스는 버전과 SHA-256을 Dockerfile에 고정한다.
- `rhwp`의 LICENSE도 이미지 `/usr/share/licenses/rhwp/LICENSE`에 포함한다.

## 제한

컨테이너·레코드 수준 검증은 파일 구조와 변환기의 내부 일관성을 보장하지만, 원본과
완전히 동일한 렌더링을 보장하지는 않는다. 복잡한 수식, OLE 개체, 매크로, 특수 글꼴,
암호화·배포용 문서는 별도 fixture와 PDF/이미지 시각 회귀 테스트를 추가해야 한다.

현재 Dockerfile이 포함하는 `rhwp` 바이너리는 Linux x86_64용이다. ARM64 배포가
필요하면 해당 아키텍처 바이너리를 별도로 검증하거나 빌드 단계에서 소스 컴파일해야
한다. HTTP 변환은 동기 처리이므로 높은 동시성이나 장시간 변환이 예상되면 API 요청과
변환 작업을 큐로 분리해야 한다.
