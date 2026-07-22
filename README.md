# FOWOCO AI Agent Server

AI Agent Workflow: Intent, Slot Filling, Ambiguity, Guardrail, Language, Response Agent

FastAPI 기반 AI 에이전트 서버 뼈대입니다.

## 구조

```text
app/
  main.py              # 앱 진입점
  api/                 # 라우터 뼈대 (엔드포인트 미구현)
  agents/language/     # Agent B 자리 (구현 예정)
  core/                # 설정·UTF-8 등 공통
```

## 로컬 실행

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env

.\scripts\run.ps1
```

- Docs: `http://localhost:8000/docs`
