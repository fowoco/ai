# 표준근로계약서 데이터 구분

대상 양식은 `[별지 제6호서식] 표준근로계약서(Standard Labor Contract)`다.
아래 구분은 현재 ERD와 양식의 공식 항목명을 비교한 결과다.

## 1. 현재 ERD에서 바로 가져올 수 있는 값

| 양식상 공식 명칭 | 현재 ERD 값 | 사용 조건 |
|---|---|---|
| 업체명(Name of the enterprise) | `company.name` | 항상 사용 |
| 근로자 성명(Name of the employee) | `worker.legal_name_enc` 복호화 값 | 항상 사용 |
| 사업장변경자 근로계약기간 | `worker.contract_start`, `worker.contract_end` | 사업장변경자인 경우에만 사용 |

`worker.contract_start/end`는 전달받은 ERD의 상단 표에는 있지만 Mermaid
관계도에는 없다. 실제 DB에 유지할 컬럼인지 먼저 확정해야 한다.

`user_account.user_name`은 로그인한 대표자 또는 인사담당자의 계정 이름이다.
양식의 `사용자 성명(Name of the employer)`은 근로계약의 사용자, 즉 사업주나
대표자의 법적 성명이므로 두 값을 자동으로 연결하면 안 된다.

## 2. 회사·사업장 기준으로 저장하기 좋은 값

계약마다 거의 바뀌지 않으므로 회사 또는 별도 사업장 마스터에서 관리하는 편이
좋다.

| 양식상 공식 명칭 | 테스트 TXT 키 | 권장 저장 위치 |
|---|---|---|
| 전화번호(Phone number) | `enterprise_phone` | `company.phone` |
| 소재지(Location of the enterprise) | `enterprise_address` | `company.address_ko` |
| 근로장소(Place of employment) 영문 주소 | `place_of_employment_en` | `workplace.address_en` |
| 사용자 성명(Name of the employer) | `employer_name` | `company.representative_name_ko` |
| 사용자 영문 성명 | `employer_name_en` | `company.representative_name_en` |
| 사업자등록번호(주민등록번호) | `business_number` | `company.business_registration_number` |
| 업종(Industry) | `industry`, `industry_en` | `company.industry_name_ko/en` |
| 사업내용(Business description) | `business_description`, `business_description_en` | `company.business_description_ko/en` |

회사가 여러 공장이나 지점을 운영한다면 `company`에 주소 하나만 추가하지 말고
`workplace` 테이블을 만들어 `workplace_id`, `company_id`, 사업장명, 한글·영문
주소와 전화번호를 두는 편이 안전하다.

## 3. 근로자 기준으로 저장하기 좋은 값

| 양식상 공식 명칭 | 테스트 TXT 키 | 권장 저장 위치 |
|---|---|---|
| 생년월일(Birthdate) | `employee_birthdate` | `worker.birth_date` |
| 본국주소(Address(Home Country)) | `employee_home_address` | `worker.home_country_address_enc` |

법적 실명과 마찬가지로 생년월일과 본국주소는 개인정보이므로 암호화와 접근 감사
대상으로 다루는 것이 좋다.

## 4. 계약마다 사용자 또는 Agent가 확인해야 하는 값

이 값은 회사·근로자 기본정보가 아니라 계약 조건이다. 별도
`employment_contract` 테이블이나 계약 버전 JSON에 저장해야 한다.

| 양식상 공식 명칭 | 테스트 TXT 키 |
|---|---|
| 신규 또는 재입국자 계약 개월 수 / 사업장변경자 계약 시작일·종료일 | `contract_months` 또는 `worker.contract_start/end` |
| 수습기간 활용 여부와 기간 | `probation_not_used` 또는 수습 시작일·종료일·개월 수 |
| 근로장소 | 사업장 선택값 또는 `enterprise_address`, `place_of_employment_en` |
| 직무내용(Job description) | `job_description`, `job_description_en` |
| 근로 시작·종료 시각 | `work_start_time`, `work_end_time` |
| 1일 평균 시간외 근로시간과 최대 변동시간 | `daily_overtime_hours`, `daily_overtime_limit` |
| 교대제 | `day_shift` 또는 2조2교대·3조3교대·4조3교대 |
| 휴게시간 | `recess_minutes` |
| 휴일 | `holiday_sunday`, `holiday_legal`, `holiday_legal_paid`, `holiday_every_saturday` |
| 월 통상임금 | `monthly_normal_wage` |
| 기본급과 임금 산정 단위 | `basic_pay`와 월급·시간급·일급·주급 구분 |
| 고정적 수당 | `fixed_allowances`, `fixed_allowances_en` |
| 상여금 | `bonus` |
| 임금 지급일과 지급방법 | `payment_day`, `payment_bank_transfer` |
| 근로계약 체결일 | `contract_date` |

## 5. 선택 결과에 따라 추가 확인하는 조건부 값

| 조건 | 추가로 필요한 공식 항목 |
|---|---|
| 신규 또는 재입국자 | 근로계약 개월 수 |
| 수습기간 활용 | 수습기간 개월 수 또는 시작일·종료일, 수습기간 중 임금 |
| 교대제 운영 | 2조2교대·3조3교대·4조3교대·기타 중 하나 |
| 숙박시설 제공 | 제공 여부, 숙소 유형, 근로자 월 부담금 |
| 식사 제공 | 제공 여부, 조식·중식·석식, 근로자 월 부담금 |
| 직접 지급 | 직접 지급 선택 |
| 통장 입금 | 근로자 본인 명의 계좌 사용 여부 |
| 문서 확정 | 사용자 서명 또는 인, 근로자 서명 또는 인 |

현재 예시값은 주간 09:00~18:00, 휴게 60분, 월 통상임금 2,500,000원,
월 기본급 2,300,000원, 매월 10일 통장 입금, 사업장 건물 숙소와 중식
제공이다. 테스트용 데이터일 뿐 운영 기본값으로 자동 확정하면 안 된다.

