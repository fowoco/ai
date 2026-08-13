# klue/roberta-base Intent 분류 모델 로드·추론

from __future__ import annotations

from .prompts import AX_INTENT_PROMPT_VERSION, AX_INTENT_SYSTEM_PROMPT

ALLOWED_INTENTS = frozenset(
    {
        "WORK_INSTRUCTION",
        "DOCUMENT_REQUEST",
        "PAYROLL_EXPLANATION",
        "WORKER_ONBOARDING",
        "EMPLOYMENT_CHANGE",
        "EXPIRY_RENEWAL",
        "OUT_OF_SCOPE",
    }
)


def _validate_ax_intents(
    items: object, hr_input: str
) -> list[dict[str, str | None]]:
    if not isinstance(items, list) or not items:
        raise ValueError("A.X output must contain at least one intent")

    validated: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("A.X intent item must be an object")

        intent = item.get("intent")
        if not isinstance(intent, str) or intent not in ALLOWED_INTENTS:
            raise ValueError(f"A.X returned unsupported intent: {intent!r}")
        if intent in seen:
            raise ValueError(f"A.X returned duplicate intent: {intent}")
        seen.add(intent)

        if "evidence" not in item:
            raise ValueError(f"A.X evidence field is required for {intent}")
        evidence = item.get("evidence")
        if intent == "OUT_OF_SCOPE":
            if evidence is not None:
                raise ValueError("OUT_OF_SCOPE evidence must be null")
        elif not isinstance(evidence, str) or not evidence or evidence not in hr_input:
            raise ValueError(
                f"A.X evidence must be an exact input substring for {intent}: {evidence!r}"
            )

        validated.append({"intent": intent, "evidence": evidence})

    if "OUT_OF_SCOPE" in seen and len(validated) != 1:
        raise ValueError("OUT_OF_SCOPE cannot be combined with another intent")
    return validated


# BERT multilabel Intent 분류기
class BertIntentModel:

    # HF Hub/로컬 경로에서 분류기 로드
    def __init__(
        self,
        model_dir: str,
        device: str,
        label_prob_threshold: float = 0.55,
        hf_token: str | None = None,
        revision: str | None = None,
    ) -> None:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self._torch = torch
        self.device = (
            "cuda"
            if (device == "auto" and torch.cuda.is_available())
            else (device if device != "auto" else "cpu")
        )
        hub_kwargs: dict[str, str] = {}
        if hf_token:
            hub_kwargs["token"] = hf_token
        if revision:
            hub_kwargs["revision"] = revision
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir, **hub_kwargs)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            model_dir, **hub_kwargs
        )
        self.model.to(self.device).eval()
        self.id2label = self.model.config.id2label
        self.label_prob_threshold = label_prob_threshold

    # 확률 dict·margin·활성 intent 목록
    def predict(self, text: str) -> tuple[dict[str, float], float, list[str]]:
        torch = self._torch
        with torch.no_grad():
            enc = self.tokenizer(
                text, truncation=True, max_length=64, return_tensors="pt"
            ).to(self.device)
            logits = self.model(**enc).logits
            probs_array = torch.sigmoid(logits)[0].cpu().numpy()

        probs_dict = {self.id2label[i]: float(p) for i, p in enumerate(probs_array)}
        activated = [p for p in probs_array if p >= self.label_prob_threshold]
        not_activated = [p for p in probs_array if p < self.label_prob_threshold]
        if not activated:
            margin = float(max(probs_array)) - self.label_prob_threshold
        else:
            margin = float(min(activated)) - (
                float(max(not_activated)) if not_activated else 0.0
            )
        picked = [
            self.id2label[i]
            for i, p in enumerate(probs_array)
            if p >= self.label_prob_threshold
        ]
        if not picked:
            picked = [self.id2label[int(probs_array.argmax())]]
        return probs_dict, margin, picked


# A.X-4.0-Light QLoRA Intent 보조 모델 (GPU·bitsandbytes 필요)
class AxIntentModel:

    _SYSTEM_PROMPT = AX_INTENT_SYSTEM_PROMPT
    prompt_version = AX_INTENT_PROMPT_VERSION

    # 4bit 베이스 + Peft 어댑터 로드
    def __init__(
        self,
        base_model_name: str,
        adapter_path: str,
        device: str,
        max_new_tokens: int = 96,
        hf_token: str | None = None,
        base_revision: str | None = None,
        adapter_revision: str | None = None,
    ) -> None:
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        self._torch = torch
        self.max_new_tokens = max_new_tokens
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
        )
        base_hub_kwargs: dict[str, str] = {}
        adapter_hub_kwargs: dict[str, str] = {}
        if hf_token:
            base_hub_kwargs["token"] = hf_token
            adapter_hub_kwargs["token"] = hf_token
        if base_revision:
            base_hub_kwargs["revision"] = base_revision
        if adapter_revision:
            adapter_hub_kwargs["revision"] = adapter_revision

        base_model = AutoModelForCausalLM.from_pretrained(
            base_model_name,
            quantization_config=bnb_config,
            torch_dtype=torch.float16,
            device_map={"": 0} if device != "cpu" else "cpu",
            **base_hub_kwargs,
        )
        self.tokenizer = AutoTokenizer.from_pretrained(
            base_model_name, **base_hub_kwargs
        )
        self.model = PeftModel.from_pretrained(
            base_model, adapter_path, **adapter_hub_kwargs
        )
        self.model.eval()

    # Intent 목록 [{"intent","evidence"}] — 실패 시 예외
    def predict(self, hr_input: str) -> list[dict[str, str | None]]:
        import json
        import re

        messages = [
            {"role": "system", "content": self._SYSTEM_PROMPT},
            {"role": "user", "content": hr_input},
        ]
        inputs = self.tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
        ).to(self.model.device)
        with self._torch.no_grad():
            output = self.model.generate(
                **inputs, max_new_tokens=self.max_new_tokens, do_sample=False
            )
        raw = self.tokenizer.decode(
            output[0][inputs["input_ids"].shape[-1] :], skip_special_tokens=True
        )
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise ValueError(f"A.X output could not be parsed as JSON: {raw!r}")
        parsed = json.loads(match.group(0))
        if not isinstance(parsed, dict):
            raise ValueError("A.X output JSON root must be an object")
        return _validate_ax_intents(parsed.get("intents"), hr_input)
