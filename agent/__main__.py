"""Agent Arena CLI.

  python -m agent register "Gas Surgeon" "claude-opus-4-8" [uri] --arena 0x..
  python -m agent evaluate <agentId> --task "audit this vault" --submission file.txt --arena 0x..
  python -m agent leaderboard --arena 0x..

register = ERC-8004 identity on-chain. evaluate = LLM-judge scores the submission and writes
the result on-chain (reputation accrues). leaderboard = read the on-chain rankings.
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            s = line.strip()
            if s and not s.startswith("#") and "=" in s:
                k, v = s.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _key():
    k = os.environ.get("PRIVATE_KEY", "")
    return k if k.startswith("0x") else ("0x" + k if k else "")


def cmd_register(args):
    from . import chain
    w3 = chain.connect(); c = chain.arena(w3, args.arena)
    aid, h = chain.register_agent(w3, c, args.name, args.model, args.uri, _key())
    print(f"  registered agent #{aid}: {args.name} ({args.model})")
    print(f"  tx https://sepolia.mantlescan.xyz/tx/{h}")
    return 0


def cmd_evaluate(args):
    from . import chain
    from .judge import judge, model_label
    submission = Path(args.submission).read_text(encoding="utf-8") if args.submission else args.text
    if not submission:
        print("provide --submission <file> or --text", file=sys.stderr); return 2
    v = judge(args.task, submission)
    print(f"  judge ({model_label()}): {v.score}/100 — {v.note}")
    w3 = chain.connect(); c = chain.arena(w3, args.arena)
    h = chain.record_evaluation(w3, c, args.agent_id, args.task, v.score, args.submission or "inline", v.note, _key())
    print(f"  recorded on-chain: https://sepolia.mantlescan.xyz/tx/{h}")
    return 0


def cmd_leaderboard(args):
    from . import chain
    w3 = chain.connect(); c = chain.arena(w3, args.arena)
    rows = chain.leaderboard(w3, c)
    print(f"\n  AGENT ARENA — on-chain leaderboard ({len(rows)} agents)\n")
    print(f"  {'rank':<5}{'agent':<22}{'model':<22}{'avg':>6}{'evals':>7}")
    for i, r in enumerate(rows, 1):
        print(f"  {i:<5}{r['name'][:20]:<22}{r['model'][:20]:<22}{r['avg']:>6.1f}{r['evals']:>7}")
    return 0


def main(argv=None):
    _load_env()
    p = argparse.ArgumentParser(prog="agent", description="Agent Arena — on-chain AI benchmark")
    p.add_argument("--arena", default=os.environ.get("ARENA_ADDRESS"), help="AgentArena address")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("register"); sp.add_argument("name"); sp.add_argument("model")
    sp.add_argument("uri", nargs="?", default=""); sp.set_defaults(fn=cmd_register)
    sp = sub.add_parser("evaluate"); sp.add_argument("agent_id", type=int)
    sp.add_argument("--task", required=True); sp.add_argument("--submission"); sp.add_argument("--text")
    sp.set_defaults(fn=cmd_evaluate)
    sp = sub.add_parser("leaderboard"); sp.set_defaults(fn=cmd_leaderboard)
    args = p.parse_args(argv)
    if not args.arena:
        print("set --arena <address> or ARENA_ADDRESS", file=sys.stderr); return 2
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
