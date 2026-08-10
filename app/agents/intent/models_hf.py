# klue/roberta-base Intent 분류 모델 로드·추론

from __future__ import annotations

from typing import Any


# BERT multilabel Intent 분류기
class BertIntentModel:

    # HF Hub/로컬 경로에서 분류기 로드
    def __init__(
        self,
        model_dir: str,
        device: str,
        label_prob_threshold: float = 0.55,
        hf_token: str | None = None,
    ) -> None:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self._torch = torch
        self.device = (
            "cuda"
            if (device == "auto" and torch.cuda.is_available())
            else (device if device != "auto" else "cpu")
        )
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir, token=hf_token)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            model_dir, token=hf_token
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

    _SYSTEM_PROMPT = (
        "당신은 HR 업무 요청 문장(hr_input)을 분석하여 의도(Intent)를 분류하는 전문 AI 에이전트입니다.\n"
        "Intent + evidence 추출까지가 책임입니다.\n"
        '출력은 JSON만: {"intents": [{"intent": "INTENT_CODE", "evidence": "...|null"}]}'
    )

    # 4bit 베이스 + Peft 어댑터 로드
    def __init__(
        self,
        base_model_name: str,
        adapter_path: str,
        device: str,
        max_new_tokens: int = 96,
        hf_token: str | None = None,
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
        base_model = AutoModelForCausalLM.from_pretrained(
            base_model_name,
            quantization_config=bnb_config,
            torch_dtype=torch.float16,
            device_map={"": 0} if device != "cpu" else "cpu",
            token=hf_token,
        )
        self.tokenizer = AutoTokenizer.from_pretrained(base_model_name, token=hf_token)
        self.model = PeftModel.from_pretrained(base_model, adapter_path, token=hf_token)
        self.model.eval()

    # Intent 목록 [{"intent","evidence"}] — 실패 시 예외
    def predict(self, hr_input: str) -> list[dict[str, Any]]:
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
        return list(parsed.get("intents") or [])
