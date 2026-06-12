"""Reproducibility receipts for Agent Arena evaluations.

Every evaluation produces a *receipt*: a small JSON record binding the exact inputs and the
model output behind a score, so anyone can re-run the judge and verify the result wasn't
cherry-picked. The on-chain `recordEvaluation(..., bytes32 evidenceHash, ...)` field stores the
keccak256 of this receipt, so the chain commits to the evidence; the full receipt is persisted
under agent/receipts/ and surfaced on the frontend.

Hashes:
  task_hash    = sha256(task_input)
  prompt_hash  = sha256(full prompt sent to the model: SYSTEM + task + submission)
  output_hash  = sha256(model_output, i.e. the judge's raw verdict text)
  evidence_hash = keccak256(canonical receipt JSON)   <- the bytes32 committed on-chain
"""
import hashlib
import json
import time
from pathlib import Path

try:
    # web3 ships keccak; reuse it so the hash matches what Solidity / the chain layer expects.
    from web3 import Web3

    def _keccak_hex(data: bytes) -> str:
        return Web3.keccak(data).hex()
except Exception:  # pragma: no cover - fallback if web3 absent (eth-hash provides keccak)
    from eth_hash.auto import keccak as _eth_keccak

    def _keccak_hex(data: bytes) -> str:
        return "0x" + _eth_keccak(data).hex()

RECEIPTS_DIR = Path(__file__).resolve().parent / "receipts"


def _sha256_hex(text: str) -> str:
    return "0x" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _norm_hex(h: str) -> str:
    return h if h.startswith("0x") else "0x" + h


def build_receipt(task_input: str, prompt: str, model_output: str, model_id: str,
                  score: int, note: str, agent_id=None, agent_name=None) -> dict:
    """Build a reproducibility receipt. `evidence_hash` is the keccak256 of the canonical
    (sorted-key, compact) JSON of the *content* fields — that exact value is committed on-chain."""
    content = {
        "task_hash": _sha256_hex(task_input),
        "prompt_hash": _sha256_hex(prompt),
        "output_hash": _sha256_hex(model_output),
        "model_id": model_id,
        "score": int(score),
    }
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":")).encode("utf-8")
    evidence_hash = _norm_hex(_keccak_hex(canonical))
    return {
        **content,
        "note": note,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "evidence_hash": evidence_hash,  # bytes32 stored on-chain via recordEvaluation
        "created_at": int(time.time()),
        "spec": "agent-arena/receipt/v1",
    }


def verify_receipt(receipt: dict) -> bool:
    """Recompute evidence_hash from the receipt's content fields and confirm it matches."""
    content = {
        "task_hash": receipt["task_hash"],
        "prompt_hash": receipt["prompt_hash"],
        "output_hash": receipt["output_hash"],
        "model_id": receipt["model_id"],
        "score": int(receipt["score"]),
    }
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _norm_hex(_keccak_hex(canonical)).lower() == str(receipt["evidence_hash"]).lower()


def save_receipt(receipt: dict) -> Path:
    """Persist a receipt as JSON under agent/receipts/ and refresh the index."""
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    short = str(receipt["evidence_hash"])[2:14]
    path = RECEIPTS_DIR / f"{receipt['created_at']}-{short}.json"
    path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    _rebuild_index()
    return path


def _rebuild_index() -> None:
    """Maintain agent/receipts/index.json — a list the static frontend can fetch."""
    items = []
    for p in sorted(RECEIPTS_DIR.glob("*.json")):
        if p.name == "index.json":
            continue
        try:
            items.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    items.sort(key=lambda r: r.get("created_at", 0), reverse=True)
    (RECEIPTS_DIR / "index.json").write_text(json.dumps(items, indent=2), encoding="utf-8")


def load_index() -> list:
    idx = RECEIPTS_DIR / "index.json"
    if idx.exists():
        return json.loads(idx.read_text(encoding="utf-8"))
    return []
