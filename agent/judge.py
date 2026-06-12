"""LLM-as-judge: score an AI agent's output on a benchmark task (0-100) with a one-line
rationale. Provider-agnostic (Tencent / Anthropic / OpenAI-compatible — same env contract
as the rest of the suite)."""
import json
import os
import re

from pydantic import BaseModel, Field

TENCENT_BASE_URL = os.environ.get("TENCENT_BASE_URL", "https://api.hunyuan.cloud.tencent.com/v1")

SYSTEM = """You are an impartial benchmark judge for AI agents that produce on-chain / Solidity
work. Given a task and an agent's submission, score the submission 0-100 on correctness,
usefulness, and rigor, and give a one-line rationale. Be discerning: 90+ is excellent and rare,
70-89 solid, 50-69 mediocre, below 50 poor or wrong. Reward verifiable specifics; penalize
generic filler and incorrect claims."""

_JSON = 'Respond with ONLY: {"score": <int 0-100>, "note": "<one line>"}'


class Verdict(BaseModel):
    score: int = Field(ge=0, le=100)
    note: str


def _provider() -> str:
    p = os.environ.get("AUDIT_PROVIDER", "").strip().lower()
    if p:
        return p
    if os.environ.get("TENCENT_API_KEY"):
        return "tencent"
    if os.environ.get("OPENAI_BASE_URL") or os.environ.get("OPENAI_MODEL"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    raise RuntimeError("No AI provider configured.")


def model_label() -> str:
    p = _provider()
    return {"tencent": os.environ.get("TENCENT_MODEL", "hunyuan"),
            "anthropic": os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8"),
            "openai": os.environ.get("OPENAI_MODEL", "openai")}.get(p, p)


def _build_prompt(task: str, submission: str) -> str:
    return f"TASK:\n{task}\n\nAGENT SUBMISSION:\n{submission}"


def judge_with_trace(task: str, submission: str):
    """Like judge(), but also returns the exact (full_prompt, raw_output) used, so callers can
    build a reproducibility receipt = hash(task)+hash(prompt)+hash(output)+model. Returns
    (Verdict, full_prompt, raw_output)."""
    prompt = _build_prompt(task, submission)
    p = _provider()
    if p == "anthropic":
        import anthropic
        full_prompt = SYSTEM + "\n\n" + prompt
        r = anthropic.Anthropic().messages.parse(
            model=os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8"), max_tokens=2000,
            thinking={"type": "adaptive"}, output_config={"effort": "medium"},
            system=SYSTEM, messages=[{"role": "user", "content": prompt}], output_format=Verdict)
        verdict = r.parsed_output
        raw = verdict.model_dump_json()
        return verdict, full_prompt, raw
    # tencent + openai → OpenAI-compatible
    import httpx
    base = (TENCENT_BASE_URL if p == "tencent" else (os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1")).rstrip("/")
    model = (os.environ.get("TENCENT_MODEL", "hunyuan-turbos-latest") if p == "tencent" else os.environ.get("OPENAI_MODEL"))
    key = (os.environ.get("TENCENT_API_KEY") if p == "tencent" else os.environ.get("OPENAI_API_KEY", "x")) or "x"
    system = SYSTEM + "\n\n" + _JSON
    full_prompt = system + "\n\n" + prompt
    body = {"model": model, "messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt}], "temperature": 0.1,
        "response_format": {"type": "json_object"}, "stream": False}
    r = httpx.post(f"{base}/chat/completions", json=body, headers={"Authorization": f"Bearer {key}"}, timeout=180)
    if r.status_code >= 400:
        body.pop("response_format", None)
        r = httpx.post(f"{base}/chat/completions", json=body, headers={"Authorization": f"Bearer {key}"}, timeout=180)
    r.raise_for_status()
    raw = r.json()["choices"][0]["message"]["content"]
    return _parse(raw), full_prompt, raw


def judge(task: str, submission: str) -> Verdict:
    verdict, _prompt, _raw = judge_with_trace(task, submission)
    return verdict


def _parse(content: str) -> Verdict:
    t = content.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.DOTALL)
    try:
        return Verdict.model_validate_json(t)
    except Exception:
        m = re.search(r"\{.*\}", t, re.DOTALL)
        return Verdict.model_validate(json.loads(m.group(0)))
