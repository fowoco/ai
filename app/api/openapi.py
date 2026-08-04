"""OpenAPI 태그 이름과 Swagger 표시 정보 관리"""

ANALYSES_TAG = "Analyses"
WORKFLOWS_TAG = "Workflows"
OCR_TAG = "OCR"
DOCUMENT_CAPABILITIES_TAG = "Document Capabilities"
DOCUMENT_TEMPLATES_TAG = "Document Templates"
DOCUMENT_INSPECTION_TAG = "Document Inspection"
DOCUMENT_EDITING_TAG = "Document Editing"
DOCUMENT_GENERATION_TAG = "Document Generation"
DOCUMENT_CONVERSION_TAG = "Document Conversion"

OPENAPI_TAGS_METADATA = [
    {
        "name": ANALYSES_TAG,
        "description": (
            "Server가 호출하는 핵심 분석 API. "
            "analysisInput 지시문에서 Intent 분류, Slot 추출, 모호성 검사 수행"
        ),
    },
    {
        "name": WORKFLOWS_TAG,
        "description": (
            "재갱신 등 LangGraph 오케스트레이션 API. "
            "담당자 입력(슬롯)·근로자 서류(OCR) 분기와 문서생성 stub 실행"
        ),
    },
    {
        "name": OCR_TAG,
        "description": "CLOVA Template OCR를 실행하고 worker_document에 결과를 저장합니다.",
    },
    {
        "name": DOCUMENT_CAPABILITIES_TAG,
        "description": "현재 서버에서 사용할 수 있는 문서 처리 기능과 변환 조합을 조회합니다.",
    },
    {
        "name": DOCUMENT_TEMPLATES_TAG,
        "description": "등록된 문서 템플릿 목록과 편집 가능한 필드를 조회합니다.",
    },
    {
        "name": DOCUMENT_INSPECTION_TAG,
        "description": "업로드한 문서의 실제 포맷을 감지하고 일치하는 템플릿을 식별합니다.",
    },
    {
        "name": DOCUMENT_EDITING_TAG,
        "description": "HWP 또는 HWPX 문서에 구조화된 값, 사진, 서명 등의 파일을 입력합니다.",
    },
    {
        "name": DOCUMENT_GENERATION_TAG,
        "description": "등록된 템플릿을 기반으로 새로운 HWP 또는 HWPX 문서를 생성합니다.",
    },
    {
        "name": DOCUMENT_CONVERSION_TAG,
        "description": "지원되는 HWP, HWPX, XML, PDF 포맷 사이에서 문서를 변환합니다.",
    },
]
