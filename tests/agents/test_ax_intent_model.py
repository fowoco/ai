import hashlib

import pytest

from app.agents.intent.models_hf import AxIntentModel, _validate_ax_intents
from app.agents.intent.prompts import (
    AX_INTENT_PROMPT_SHA256,
    AX_INTENT_PROMPT_VERSION,
    AX_INTENT_SYSTEM_PROMPT,
)


class _NoGrad:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_args: object) -> None:
        return None


class _FakeTorch:
    @staticmethod
    def no_grad() -> _NoGrad:
        return _NoGrad()


class _FakeInputIds:
    shape = (1, 3)


class _FakeInputs(dict[str, object]):
    def to(self, _device: str) -> "_FakeInputs":
        return self


class _FakeTokenizer:
    def __init__(self, decoded: str) -> None:
        self.decoded = decoded
        self.messages: list[dict[str, str]] = []

    def apply_chat_template(
        self, messages: list[dict[str, str]], **_kwargs: object
    ) -> _FakeInputs:
        self.messages = messages
        return _FakeInputs(input_ids=_FakeInputIds())

    def decode(self, _tokens: object, **_kwargs: object) -> str:
        return self.decoded


class _FakeModel:
    device = "cpu"

    def generate(self, **_kwargs: object) -> list[list[int]]:
        return [[1, 2, 3, 4]]


def _model_with_output(decoded: str) -> AxIntentModel:
    model = AxIntentModel.__new__(AxIntentModel)
    model._torch = _FakeTorch()
    model.max_new_tokens = 96
    model.tokenizer = _FakeTokenizer(decoded)
    model.model = _FakeModel()
    return model


def test_ax_prompt_matches_pinned_knowledge_source() -> None:
    digest = hashlib.sha256(AX_INTENT_SYSTEM_PROMPT.encode()).hexdigest()
    assert digest == AX_INTENT_PROMPT_SHA256
    assert AxIntentModel._SYSTEM_PROMPT == AX_INTENT_SYSTEM_PROMPT
    assert AxIntentModel.prompt_version == AX_INTENT_PROMPT_VERSION


def test_ax_predict_sends_knowledge_prompt_and_preserves_intent_order() -> None:
    instruction = "체류연장 준비하고 급여도 확인해줘"
    model = _model_with_output(
        '{"intents": ['
        '{"intent": "EXPIRY_RENEWAL", "evidence": "체류연장"},'
        '{"intent": "PAYROLL_EXPLANATION", "evidence": "급여도 확인"}'
        "]}"
    )

    result = model.predict(instruction)

    assert result == [
        {"intent": "EXPIRY_RENEWAL", "evidence": "체류연장"},
        {"intent": "PAYROLL_EXPLANATION", "evidence": "급여도 확인"},
    ]
    assert model.tokenizer.messages == [
        {"role": "system", "content": AX_INTENT_SYSTEM_PROMPT},
        {"role": "user", "content": instruction},
    ]


@pytest.mark.parametrize(
    ("items", "instruction", "message"),
    [
        ([{"intent": "RENEWAL", "evidence": "연장"}], "연장", "unsupported intent"),
        ([{"intent": "OUT_OF_SCOPE"}], "완료했습니다", "evidence field is required"),
        (
            [{"intent": "EXPIRY_RENEWAL", "evidence": "원문에 없음"}],
            "체류연장",
            "exact input substring",
        ),
        (
            [
                {"intent": "OUT_OF_SCOPE", "evidence": None},
                {"intent": "DOCUMENT_REQUEST", "evidence": "서류"},
            ],
            "서류",
            "cannot be combined",
        ),
        (
            [
                {"intent": "DOCUMENT_REQUEST", "evidence": "서류"},
                {"intent": "DOCUMENT_REQUEST", "evidence": "요청"},
            ],
            "서류 요청",
            "duplicate intent",
        ),
    ],
)
def test_ax_output_contract_rejects_invalid_items(
    items: object, instruction: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _validate_ax_intents(items, instruction)


def test_ax_predict_rejects_non_json_output() -> None:
    model = _model_with_output("설명문만 반환했습니다")

    with pytest.raises(ValueError, match="could not be parsed as JSON"):
        model.predict("체류연장")
