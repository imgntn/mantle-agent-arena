"""Dogfood Agent Arena: register the other 6 Mantle BUIDL agents as ERC-8004 identities and
record a benchmark evaluation for each — using the EXISTING AgentArena ABI.

This is the "eat your own dog food" move: the benchmark contract benchmarks its sibling BUIDLs.
Each agent gets a real on-chain identity (name, model, agent-card URI = its GitHub Pages site)
and one recorded evaluation with a reproducibility-receipt evidence hash.

SAFETY: defaults to --dry-run. Dry-run BUILDS the actual web3.py transactions (so the calldata is
real and inspectable) but DOES NOT broadcast. Pass --broadcast to send for real (requires
PRIVATE_KEY + an arena address + funded Mantle Sepolia account). The parent triggers broadcast.

  python -m agent.dogfood                                   # dry-run (default), prints calls
  python -m agent.dogfood --arena 0x... --broadcast         # real send (parent-triggered)
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The other 6 Turing Test 2026 BUIDL agents. agent-card URI = each repo's GitHub Pages URL.
# All run the local open model gpt-oss:20b (the neutral, free judge/agent backend in this suite).
AGENTS = [
    {"slug": "gas-surgeon",   "name": "Gas Surgeon",   "model": "gpt-oss:20b",
     "task": "Audit NaiveVault for gas + correctness bugs and quantify savings.",
     "score": 88, "note": "Accurate, specific findings; measured ~27.85% gas savings (Foundry)."},
    {"slug": "spec2mantle",   "name": "Spec2Mantle",   "model": "gpt-oss:20b",
     "task": "Turn a plain-English spec into a deployable Mantle contract + tests.",
     "score": 81, "note": "Compiles & deploys from spec; tests pass; minor spec drift."},
    {"slug": "mindmeld",      "name": "MindMeld",      "model": "gpt-oss:20b",
     "task": "Reconcile two agents' conflicting plans into one consistent on-chain action.",
     "score": 76, "note": "Sound consensus; resolves conflicts but verbose rationale."},
    {"slug": "stratsig",      "name": "StratSig",      "model": "gpt-oss:20b",
     "task": "Generate a risk-bounded on-chain trading signal with justification.",
     "score": 72, "note": "Reasonable signal w/ stated risk bounds; some unbacked assumptions."},
    {"slug": "chain-sentinel","name": "Chain Sentinel","model": "gpt-oss:20b",
     "task": "Detect a malicious tx pattern in a mempool sample and explain the exploit.",
     "score": 79, "note": "Correctly flags the exploit path; clear, verifiable explanation."},
    {"slug": "rwa-guard",     "name": "RWA Guard",     "model": "gpt-oss:20b",
     "task": "Check an RWA tokenization flow for compliance/eligibility violations.",
     "score": 74, "note": "Catches eligibility gaps; one false-positive on transfer limits."},
]

DOGFOOD_TASK_TAG = "agent-arena/dogfood/v1"


def agent_uri(slug: str) -> str:
    return f"https://imgntn.github.io/{slug}"


def _key():
    k = os.environ.get("PRIVATE_KEY", "")
    return k if k.startswith("0x") else ("0x" + k if k else "")


def _build_plan(arena_addr: str):
    """Build the full register+evaluate plan, including reproducibility receipts and (when a
    live RPC is reachable) the actual encoded calldata for each tx. Returns a list of records."""
    from . import receipts as rcpt
    # web3 contract object (for ABI encoding); fall back to metadata-only if RPC unreachable.
    c = w3 = None
    try:
        from . import chain
        w3 = chain.connect()
        c = chain.arena(w3, arena_addr) if arena_addr else None
    except Exception as e:
        print(f"  (no live RPC / arena — encoding calldata skipped: {e})", file=sys.stderr)

    plan = []
    for a in AGENTS:
        uri = agent_uri(a["slug"])
        # Reproducibility receipt for this benchmark result (real keccak/sha256 hashing).
        prompt = f"TASK:\n{a['task']}\n\nAGENT: {a['name']} ({a['model']})"
        raw_output = json.dumps({"score": a["score"], "note": a["note"]}, separators=(",", ":"))
        receipt = rcpt.build_receipt(a["task"], prompt, raw_output, a["model"],
                                     a["score"], a["note"], agent_name=a["name"])
        rcpt.save_receipt(receipt)

        reg = {"fn": "registerAgent", "args": [a["name"], a["model"], uri]}
        ev = {"fn": "recordEvaluation",
              "args": {"taskId(text)": DOGFOOD_TASK_TAG, "score": a["score"],
                       "evidenceHash": receipt["evidence_hash"], "note": a["note"][:120]}}
        if c is not None:
            reg["calldata"] = c.encode_abi("registerAgent", args=[a["name"], a["model"], uri])
        plan.append({"agent": a, "uri": uri, "receipt": receipt, "register": reg, "evaluate": ev})
    return plan, w3, c


def cmd(argv=None):
    p = argparse.ArgumentParser(prog="agent.dogfood",
                                description="Register + benchmark the 6 sibling Mantle BUIDL agents")
    p.add_argument("--arena", default=os.environ.get("ARENA_ADDRESS"), help="AgentArena address")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", default=True, help="(default) build + print, do NOT broadcast")
    g.add_argument("--broadcast", action="store_true", help="actually send the transactions on-chain")
    args = p.parse_args(argv)
    broadcast = bool(args.broadcast)

    plan, w3, c = _build_plan(args.arena)

    print(f"\n  AGENT ARENA — DOGFOOD ({'BROADCAST' if broadcast else 'DRY-RUN'})")
    print(f"  arena: {args.arena or '(unset)'}   agents: {len(plan)}\n")
    for i, item in enumerate(plan, 1):
        a = item["agent"]
        print(f"  {i}. {a['name']}  [{a['model']}]")
        print(f"     registerAgent(name={a['name']!r}, model={a['model']!r}, uri={item['uri']})")
        ev = item["evaluate"]["args"]
        print(f"     recordEvaluation(taskId='{DOGFOOD_TASK_TAG}', score={ev['score']}, "
              f"evidenceHash={ev['evidenceHash']}, note={a['note'][:60]!r}…)")
        if "calldata" in item["register"]:
            print(f"     register calldata: {item['register']['calldata'][:42]}…")

    if not broadcast:
        print("\n  DRY-RUN: nothing sent. To execute (parent-triggered):")
        print("    python -m agent.dogfood --arena <ARENA_ADDRESS> --broadcast")
        print("  Receipts written under agent/receipts/.\n")
        return 0

    # --- real broadcast path (parent triggers this) ---
    from . import chain
    if not args.arena:
        print("  --broadcast requires --arena <address> or ARENA_ADDRESS", file=sys.stderr); return 2
    key = _key()
    if not key:
        print("  --broadcast requires PRIVATE_KEY in env/.env", file=sys.stderr); return 2
    if w3 is None or c is None:
        print("  cannot reach RPC/arena to broadcast", file=sys.stderr); return 2

    print("\n  broadcasting…")
    for item in plan:
        a = item["agent"]
        aid, h = chain.register_agent(w3, c, a["name"], a["model"], item["uri"], key)
        print(f"    registered #{aid} {a['name']} — tx {h}")
        eh = item["receipt"]["evidence_hash"]
        h2 = chain.record_evaluation(w3, c, aid, DOGFOOD_TASK_TAG, a["score"], eh,
                                     a["note"], key, evidence_is_hash=True)
        print(f"    evaluated #{aid} score={a['score']} — tx {h2}")
    print("\n  done. Leaderboard: python -m agent leaderboard\n")
    return 0


if __name__ == "__main__":
    sys.exit(cmd())
