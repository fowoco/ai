# 통합신청서(신고서) 데이터 구분

대상 양식은 출입국관리법 시행규칙 `[별지 제34호서식] 통합신청서(신고서)`다.
현재 테스트 시나리오는 E-9 근로자의 `체류기간 연장허가` 신청이다.

## 현재 자동 입력하는 항목

| 양식 영역 | 입력 내용 |
|---|---|
| 신청/신고 선택 | 체류기간 연장허가 체크 |
| 성명 | 여권상 성과 이름 |
| 생년월일 | 연·월·일 분리 입력 |
| 성별 | 남 또는 여 체크 |
| 국적 | `worker.nationality` |
| 외국인등록번호 | 하이픈을 제외한 13자리 숫자를 13개 셀에 한 자리씩 입력 |
| 여권 | 여권번호, 발급일자, 유효기간 |
| 주소·연락처 | 대한민국 주소, 전화번호, 휴대전화, 본국 주소·전화번호 |
| 재학 여부 | 현재 예시는 미취학(Non-school) 체크 |
| 근무처 | 현재 근무처, 사업자등록번호, 전화번호 |
| 소득·직업 | 연 소득금액, 직업 |
| 전자우편 | `worker.email` |
| 신청 | 신청일, 신청인 이름 |
| 행정정보 공동이용 동의 | 신청인 이름 |

`worker.legal_name_enc`에는 여권상 전체 이름만 있으므로 성과 이름을 정확히
나누려면 `worker.passport_family_name_enc`와
`worker.passport_given_names_enc` 같은 별도 값이 필요하다. 공백 위치만으로
자동 분리하면 복합 성명에서 오류가 날 수 있다.

## 지원하는 신청/신고 체크 키

다음 키 가운데 실제 신청에 해당하는 값만 `true`로 전달한다.

```text
application_foreign_registration
application_activity_permission
application_card_reissue
application_workplace_change
application_stay_extension
application_reentry
application_status_change
application_address_change
application_status_grant
application_information_change
```

현재 모의 데이터는 `application_stay_extension=true`만 사용한다.

## 이번 체류기간 연장 신청에서 의도적으로 비워 두는 항목

| 공란 | 이유 |
|---|---|
| 사진 | 외국인등록 또는 등록증 재발급 신청 시에만 부착 |
| 희망 체류자격 | 체류자격 외 활동·변경·부여 신청이 아님 |
| 학교 이름·종류·전화번호 | 미취학(Non-school)을 선택함 |
| 예정 근무처 | 근무처 변경·추가 신청이 아님 |
| 재입국 신청 기간 | 재입국허가 신청이 아님 |
| 반환용 계좌번호 | 외국인등록 또는 등록증 재발급 신청이 아님 |
| 배우자·부·모 이름과 서명 | 해당 가족의 행정정보 조회가 필요한 신청이 아님 |
| 공용란 | 출입국 담당 공무원이 접수·허가 과정에서 작성 |

사진과 실제 서명 이미지는 TXT scalar 값이 아니라 `document.file_uri_enc`가
가리키는 asset으로 처리해야 한다. 현재 TXT 경로에서는 신청인 이름을 서명란에
표시하지만, 제출용 문서에서는 본인 서명 또는 인 이미지로 교체해야 한다.

