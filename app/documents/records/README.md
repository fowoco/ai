# ERD 기반 문서 레코드 매핑

## 기준

문서 자동 기입 코드는 ERD 하단 Mermaid의 식별자를 우선 사용한다.
TXT는 실제 테이블 한 행이 아니라 문서 생성에 필요한 JOIN 결과를 모사한다.

```text
company.name=주식회사 한빛정밀
worker.employee_no=HB-2023-001
worker.legal_name=NGUYEN VAN AN
worker.nationality=베트남
worker.stay_expiry=2026-09-15
worker.phone=010-1111-2222
```

`worker.legal_name`과 `worker.phone`은 실제 물리 컬럼이 아니다. DB 어댑터가
`worker.legal_name_enc`, `worker.phone_enc`를 권한 확인 후 복호화하여 반환하는
문서용 projection 별칭이다. 암호화된 bytes를 문서 엔진에 직접 전달하면 안 된다.

현재 네 개 테스트 TXT는 2023년 9월 입국한 E-9 제조업 근로자가 2026년 7월에
취업활동 및 체류기간 연장을 준비하는 하나의 모의 시나리오다. 여권상 성명과
본국 주소처럼 영문 표기가 필요한 값만 영문으로 두고, 국내 사업장·주소·직위·업무
내용은 한글로 작성한다. 기간은 `2026. 9. 16. ~ 2027. 9. 15.`처럼 표기하며
통합신청서의 학교, 예정 근무처, 재입국 기간, 반환 계좌처럼 이번 신청에 해당하지
않는 항목은 기입하지 않는다.

통합신청서의 신청 종류, 성별, 13자리 외국인등록번호 분할 입력과 조건부 공란은
[`integrated_application.md`](integrated_application.md)에 따로 정리했다.

취업활동기간 연장신청서의 사실관계 5개 항목은 다음 boolean 키로 입력한다.

```text
check_eligible_industry=true
check_no_adjustment_dismissal=true
check_no_unpaid_wages=true
check_insurance=true
check_departure_guarantee=true
```

이 값들은 신청 자격과 법적 사실 확인에 해당하므로 Agent가 발화만으로 추정하면 안
된다. DB·보험 가입자료 등으로 확인하거나 사용자에게 명시적으로 확인받은 뒤
전달해야 한다. `submission_authority`에는 사업장 관할 지방고용노동관서장을 넣고,
하단 행정정보 공동이용 동의란의 신청인 이름은 `applicant_name`을 재사용한다.

## 현재 자동 기입되는 ERD 값

| 템플릿 | 문서 필드 | ERD 또는 projection 값 |
|---|---|---|
| 신원보증서 | 피보증인 국적 | `worker.nationality` |
| 신원보증서 | 피보증인 전화번호 | `worker.phone` |
| 신원보증서 | 보증인 근무처 | `company.name` |
| 취업기간 연장 | 사업장명 | `company.name` |
| 취업기간 연장 | 일련번호 | `worker.employee_no` |
| 취업기간 연장 | 근로자 성명 | `worker.legal_name` |
| 취업기간 연장 | 국적 | `worker.nationality` |
| 취업기간 연장 | 체류기간 만료일 | `worker.stay_expiry` |
| 통합신청서 | 국적 | `worker.nationality` |
| 통합신청서 | 휴대전화 | `worker.phone` |
| 통합신청서 | 현재 근무처 | `company.name` |
| 통합신청서 | 이메일 | `worker.email` |
| 통합신청서 | 신청인 이름·동의인 이름 | `worker.legal_name` |
| 표준근로계약서 | 업체명 | `company.name` |
| 표준근로계약서 | 근로자 성명 | `worker.legal_name` |
| 표준근로계약서 | 사업장변경자 계약 시작일 | `worker.contract_start` |
| 표준근로계약서 | 사업장변경자 계약 종료일 | `worker.contract_end` |

문서 전용 키(`family_name`, `passport_number` 등)도 기존과 같이 사용할 수 있다.
향후 Agent가 누락값을 확인한 뒤 DB projection과 합쳐 전달할 때 문서 전용 키가
우선한다.

신원보증서의 `company.name → 보증인 근무처` 매핑은 보증인이 해당 회사
관계자라는 현재 업무 규칙을 전제로 한다. 보증인을 외부인으로 허용하면 이 자동
매핑을 제거하고 별도 보증인 정보를 사용해야 한다.

## ERD에 없는 값

### 회사·사업장 정보

- 회사 전화번호와 주소
- 대표자 법적 성명
- 사업자등록번호
- 업종과 사업 내용

이 값들은 신원보증서, 취업기간 연장신청서, 표준근로계약서에 반복해서 필요하다.
`company` 확장 또는 별도의 `company_profile` 테이블이 필요하다.

### 근로자 신원 정보

- 생년월일과 성별
- 성/이름이 분리된 여권상 영문명
- 외국인등록번호
- 여권번호, 여권 발급일, 여권 만료일
- 대한민국 주소와 본국 주소
- 학교명과 학교 전화번호
- 직업, 연 소득, 환급 계좌

암호화가 필요한 항목은 `worker`에 평문으로 추가하기보다 별도 신원정보
테이블이나 `*_enc` 컬럼으로 관리하는 편이 안전하다.

### 보증인 정보

- 보증인 성명, 국적, 성별, 생년월일 또는 여권번호
- 전화번호와 주소
- 피보증인과의 관계
- 직위
- 보증기간

`user_account.user_name`은 로그인 사용자 이름일 뿐 실제 보증인이라는 보장이
없으므로 자동 매핑하지 않는다. 별도 `guarantor` 또는 문서 요청 입력이 필요하다.

### 근로조건 정보

- 근무 장소와 직무 내용
- 계약 개월 수 또는 정확한 계약 기간
- 수습기간
- 근로시간, 휴게시간, 휴일
- 임금, 수당, 지급일과 지급방법
- 숙식 제공 조건

상단 worker 표에는 `contract_start/end`가 있지만 Mermaid에는 빠져 있다.
유지 여부를 먼저 확정하고, 상세 근로조건은 별도의 `employment_contract`가
필요하다.

현재 표준근로계약서 테스트 TXT는 DB에서 업체명, 근로자 성명, 계약 시작·종료일을
가져오고 나머지 근로조건에는 제조업 예시값을 사용한다. 예시는 09:00~18:00 근무,
휴게 60분, 월 통상임금 2,500,000원, 월 기본급 2,300,000원, 식대 200,000원,
매월 10일 통장 입금, 사업장 건물 숙소와 중식 제공이다. 이 값은 시스템 기본값이
아니며 실제 생성에서는 사용자 확인을 마친 근로계약 조건으로 대체해야 한다.

표준근로계약서에 필요한 값을 ERD 기존값, 회사·근로자 마스터 추가값,
계약별 입력값과 조건부 값으로 나눈 상세 목록은
[`standard_labor_contract.md`](standard_labor_contract.md)에 정리했다.

### 신청별 일회성 값과 파일

- 신청 종류와 체크박스 선택
- 신청일, 보증일, 재입국 신청 기간
- 각종 사실 확인 체크
- 사진과 신청인·근로자·보증인 서명

신청일은 서버 현재 날짜로 만들 수 있지만 사용자가 확인해야 한다. 사진·서명은
`document.doc_type`과 `file_uri_enc`로 찾을 여지는 있으나, 어떤 파일을 어느
서명란에 사용할지에 대한 명시적 규칙과 HWPX 이미지 삽입 구현이 추가로 필요하다.

## ERD 자체에서 먼저 확정할 차이

| 항목 | 상단 표 | 하단 Mermaid |
|---|---|---|
| `company.created_at` | 없음 | 있음 |
| 사용자 회사 FK | `company_name` uuid | `company_id` uuid |
| 사용자 PK | String | uuid |
| 로그인 필드 | `id(email)`, `password` | `email`, `password_hash` |
| 사용자 추가 정보 | 없음 | `user_name`, `approval_permission`, `status` |
| worker PK 의미 | 이름 문자열 | uuid |
| worker 표시 이름 | `worker_id`에 포함 | `display_name` |
| worker 연락처 | `phone` bytes | `phone_enc` |
| 계약기간·이메일·입국일 | 상단 표에 있음 | Mermaid에 없음 |
| task 상세 JSON과 Agent 결과 | 상단 표에 없음 | Mermaid에 있음 |

현재 구현은 FK와 PK 이름은 Mermaid를 따르고, `worker.email`,
`worker.contract_start/end`, `worker.arrival_date`는 상단 표의 후보 컬럼으로
취급한다.
