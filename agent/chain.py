"""Mantle bridge for AgentArena: register agents, record evaluations, read the leaderboard."""
import json
import os
from pathlib import Path

from web3 import Web3

RPC = os.environ.get("MANTLE_RPC", "https://rpc.sepolia.mantle.xyz")
CHAIN_ID = 5003
ABI_PATH = Path(__file__).resolve().parent.parent / "out" / "AgentArena.sol" / "AgentArena.json"


def connect() -> Web3:
    w3 = Web3(Web3.HTTPProvider(RPC))
    if not w3.is_connected():
        raise RuntimeError(f"cannot reach Mantle RPC at {RPC}")
    return w3


def arena(w3, address):
    abi = json.loads(ABI_PATH.read_text())["abi"]
    return w3.eth.contract(address=Web3.to_checksum_address(address), abi=abi)


def _send(w3, fn, key, gas=300000):
    acct = w3.eth.account.from_key(key)
    tx = fn.build_transaction({
        "from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address, "pending"),
        "chainId": CHAIN_ID, "gas": gas, "maxFeePerGas": w3.eth.gas_price * 2,
        "maxPriorityFeePerGas": w3.to_wei(0.01, "gwei")})
    h = w3.eth.send_raw_transaction(acct.sign_transaction(tx).raw_transaction)
    rcpt = w3.eth.wait_for_transaction_receipt(h, timeout=120)
    return h.hex(), rcpt


def register_agent(w3, c, name, model, uri, key):
    h, rcpt = _send(w3, c.functions.registerAgent(name, model, uri or ""), key)
    # agentId = new agentCount
    return c.functions.agentCount().call(), h


def record_evaluation(w3, c, agent_id, task_id, score, evidence_hash, note, key, evidence_is_hash=False):
    """Record an evaluation on-chain. If `evidence_is_hash` is True, `evidence_hash` is treated as
    an already-computed bytes32 (e.g. a reproducibility-receipt keccak, 0x-prefixed hex); otherwise
    it's keccak-hashed from text for backwards compatibility."""
    tid = Web3.keccak(text=task_id)
    if evidence_is_hash and evidence_hash:
        eh = bytes.fromhex(evidence_hash[2:] if evidence_hash.startswith("0x") else evidence_hash)
    elif evidence_hash:
        eh = Web3.keccak(text=evidence_hash)
    else:
        eh = b"\x00" * 32
    h, _ = _send(w3, c.functions.recordEvaluation(agent_id, tid, int(score), eh, note[:120]), key)
    return h


def leaderboard(w3, c):
    n = c.functions.agentCount().call()
    rows = []
    for i in range(1, n + 1):
        a = c.functions.getAgent(i).call()
        avg, evals = c.functions.reputation(i).call()
        rows.append({"id": i, "name": a[1], "model": a[2], "owner": a[0],
                     "avg": avg / 100 if avg else 0, "evals": evals})
    rows.sort(key=lambda r: (r["avg"], r["evals"]), reverse=True)
    return rows
