from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from app import runtime
from app.core.config import Settings


def _settings(**overrides: object) -> SimpleNamespace:
    values = {
        "clova_ocr_enabled": False,
        "intent_model_enabled": True,
        "intent_warmup_on_start": True,
        "intent_warmup_required": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_intent_warmup_is_enabled_by_default_when_models_are_enabled() -> None:
    assert Settings.model_fields["intent_warmup_on_start"].default is True


@pytest.mark.asyncio
async def test_app_lifespan_warms_intent_before_serving(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _IntentAgent:
        def __init__(self) -> None:
            self.calls = 0

        def warmup(self) -> None:
            self.calls += 1

    intent_agent = _IntentAgent()
    monkeypatch.setattr(runtime, "get_intent_agent", lambda: intent_agent)
    app = FastAPI()

    async with runtime.create_app_lifespan(_settings())(app):
        assert app.state.intent_warmup_completed is True

    assert intent_agent.calls == 1


@pytest.mark.asyncio
async def test_app_lifespan_fails_when_required_warmup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _IntentAgent:
        def warmup(self) -> None:
            raise RuntimeError("model unavailable")

    monkeypatch.setattr(runtime, "get_intent_agent", _IntentAgent)
    app = FastAPI()

    with pytest.raises(RuntimeError, match="model unavailable"):
        async with runtime.create_app_lifespan(_settings())(app):
            pass

    assert app.state.intent_warmup_error == "model unavailable"


@pytest.mark.asyncio
async def test_app_lifespan_can_serve_degraded_when_warmup_is_optional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _IntentAgent:
        def warmup(self) -> None:
            raise RuntimeError("model unavailable")

    monkeypatch.setattr(runtime, "get_intent_agent", _IntentAgent)
    app = FastAPI()

    async with runtime.create_app_lifespan(
        _settings(intent_warmup_required=False)
    )(app):
        assert app.state.intent_warmup_error == "model unavailable"
