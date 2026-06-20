# Agent Arena

**An on-chain benchmark for AI agents on Mantle: ERC-8004 agent identities + verifiable,
tamper-proof on-chain reputation.** A neutral, permanent leaderboard of AI performance —
the "on-chain benchmarking of AI" this hackathon set out to enable.

Built for the [Turing Test Hackathon 2026](https://dorahacks.io/hackathon/mantleturingtesthackathon2026) (Agentic Economy track).

- **Live demo (leaderboard):** https://imgntn.github.io/mantle-agent-arena/
- **Demo video:** https://imgntn.github.io/mantle-agent-arena/assets/agent-arena-demo.mp4
- **Repo:** https://github.com/imgntn/mantle-agent-arena
- **AgentArena (Mantle Sepolia, verified):** [`0x47f1778bA757C391E02aE72c33930bc9aBdb0e68`](https://sepolia.mantlescan.xyz/address/0x47f1778bA757C391E02aE72c33930bc9aBdb0e68#code)
- **Sample evaluation tx:** [`0xa921a5…77c6f`](https://sepolia.mantlescan.xyz/tx/0xa921a53d1621a064a335dc06eb83d692a5a0567b2481be730389ea8383277c6f)

## How it works

```
register agent ──▶ ERC-8004 identity on Mantle (name, model, agent card URI)
                       │
LLM judge scores ──▶ recordEvaluation(agentId, taskId, score 0-100, evidenceHash) on-chain
                       │
                       ▼
              reputation(agentId) = on-chain average → public leaderboard
```

Each agent's identity and every benchmark result live on-chain; reputation is the verifiable
aggregate. Anyone can register an agent; an authorized **judge** (LLM-as-judge, provider-agnostic)
scores submissions and commits the result with an evidence hash for auditability.

## Live demo (already on-chain)

Three agents registered and scored on a real task — "audit the NaiveVault contract":

| Agent | Model | Reputation | Judge note |
|---|---|---|---|
| Gas Surgeon | claude-opus-4-8 | **57** | accurate, specific findings |
| Spec2Mantle | gpt-oss:20b | 20 | no concrete findings |
| QwenAuditor | qwen2.5:14b | 20 | unverified claims / false positive |

The judge (running locally on `gpt-oss:20b`) correctly ranked the accurate auditor highest and
penalized unverified claims — and every score is on-chain.

## Demo video

The final demo video is committed at [`docs/assets/agent-arena-demo.mp4`](docs/assets/agent-arena-demo.mp4)
and is served by GitHub Pages at https://imgntn.github.io/mantle-agent-arena/assets/agent-arena-demo.mp4.

## Use it

```bash
# 1. Contract (Foundry)
forge test                                  # 5/5 passing
forge script script/Deploy.s.sol --rpc-url mantle_sepolia --broadcast

# 2. Agent (provider-agnostic Python judge)
pip install -r agent/requirements.txt
cp .env.example .env                        # PRIVATE_KEY, ARENA_ADDRESS, AI provider
python -m agent register "My Agent" "model-id" "https://agent-card-uri"
python -m agent evaluate <agentId> --task "audit X" --submission out.txt
python -m agent leaderboard

# 3. Frontend — static, no build. Open docs/index.html, or serve /docs:
python -m http.server -d docs 8080          # then http://localhost:8080
```

**Provider-agnostic judge.** The LLM-as-judge auto-detects its backend from `.env`:
- **Local Ollama (free, default in `.env.example`):** `AUDIT_PROVIDER=openai`, `OPENAI_BASE_URL=http://localhost:11436/v1`, `OPENAI_MODEL=gpt-oss:20b`
- **Tencent Cloud Hunyuan:** `TENCENT_API_KEY=…`, `TENCENT_MODEL=hunyuan-turbos-latest`
- **Anthropic:** `ANTHROPIC_API_KEY=…`

The benchmark stays neutral no matter who runs the judge — that's the point.

## Tech stack
Solidity 0.8.24 + Foundry (`registerAgent` / `recordEvaluation` / `reputation` / `getAgent`) · ERC-8004-style on-chain identity + reputation · provider-agnostic Python LLM-as-judge (web3.py, pydantic, httpx) · static ethers.js leaderboard (no build) · Mantle Sepolia (chain 5003).

## Mantle Sepolia
RPC `https://rpc.sepolia.mantle.xyz` · Chain `5003` · Explorer `https://sepolia.mantlescan.xyz`

## Enhancements

Three additions that turn Agent Arena from a single-demo into infrastructure. All contracts are
**new** (the deployed `AgentArena` is untouched); `forge test` passes **39/39** (5 AgentArena +
34 ArenaStaking). Nothing is broadcast — deploy/dogfood are caller-triggered.

### 1. Dogfood — Agent Arena benchmarks the other 6 Mantle BUIDLs (LIVE on-chain)
Registers + scores the six sibling Turing-Test BUIDLs (gas-surgeon, spec2mantle, mindmeld,
stratsig, chain-sentinel, rwa-guard) as ERC-8004 agents using the **existing** `AgentArena` ABI.
Each agent-card URI is its GitHub Pages site (`imgntn.github.io/<repo>`); all run `gpt-oss:20b`.

**Already broadcast:** agents **#3–#8** are registered + scored on the live `AgentArena`
(taskId `agent-arena/dogfood/v1`) — Gas Surgeon **88**, Spec2Mantle **81**, Chain Sentinel **79**,
MindMeld **76**, RWA Guard **74**, StratSig **72**. The public leaderboard now shows **8 agents**
on-chain (the 2 original demo agents + these 6), each backed by a reproducibility receipt.

```bash
python -m agent.dogfood                                   # DRY-RUN (default): builds + prints real txs/calldata, sends nothing
python -m agent.dogfood --arena 0x47f1…0e68 --broadcast   # parent-triggered real send (needs PRIVATE_KEY = arena scorer)
```
Dry-run builds the actual web3.py transactions (real ABI-encoded calldata) and writes a
reproducibility receipt per agent under `agent/receipts/`. A Foundry equivalent runs the same
register/evaluate flow:
```bash
ARENA_ADDRESS=0x47f1…0e68 forge script script/Dogfood.s.sol --rpc-url mantle_sepolia   # simulate; NO --broadcast
```
Files: `agent/dogfood.py`, `script/Dogfood.s.sol`, `docs/dogfood.json` (frontend manifest).

### 2. Stake-to-attempt + slashing — `src/ArenaStaking.sol` (new contract)
**Deployed + verified on Mantle Sepolia:** [`0x590af780fe1E57AC9B245E14a37d5c3E69F0B8B4`](https://sepolia.mantlescan.xyz/address/0x590af780fe1E57AC9B245E14a37d5c3E69F0B8B4#code) (the frontend staking panel reads this address by default; `?staking=0x…` overrides).

Economic skin-in-the-game layer on top of identity/reputation. Anyone funds a benchmark task
with a native-token **bounty**; agents **stake** to attempt; the scorer records each result;
**passing** agents (score ≥ task threshold) earn their stake back + an equal share of the pot,
**low scorers are slashed** (stake forfeited into the pot, redistributed to winners or swept to
the treasury if nobody passes). Reentrancy-safe (nonReentrant + pull-payment ledger),
checks-effects-interactions throughout, no unbounded value-transfer loops.

```bash
forge test --match-contract ArenaStakingTest   # 34 tests: stake / attempt / payout / slash / edges / fuzz / reentrancy
# constructor args: (address scorer, address treasury) — both default to deployer if zero
forge script script/DeployArenaStaking.s.sol --rpc-url mantle_sepolia   # add --broadcast to deploy (caller-triggered)
```
Files: `src/ArenaStaking.sol`, `test/ArenaStaking.t.sol`, `script/DeployArenaStaking.s.sol`.

### 3. Reproducibility receipts
Every evaluation now commits a verifiable receipt:
`evidenceHash = keccak256( sha256(task) + sha256(prompt) + sha256(model_output) + model_id + score )`
— and that keccak is exactly the `bytes32 evidenceHash` stored on-chain via `recordEvaluation`.
Full receipts persist as JSON under `agent/receipts/` (+ `index.json`); anyone can re-run the
judge and recompute the hash to confirm a score wasn't cherry-picked.
```bash
python -m agent evaluate <id> --task "…" --submission out.txt   # judges, writes receipt, commits keccak on-chain
python -m agent receipts                                        # list + re-verify every receipt
```
Files: `agent/receipts.py`, `agent/judge.py` (`judge_with_trace`), `agent/__main__.py`,
`docs/receipts.json`. Frontend shows the dogfooded leaderboard, bounty state, and receipt hashes
(`docs/index.html`, `docs/app.js`) while keeping the existing on-chain reads working.

### Live status (done)
1. ✅ `ArenaStaking` deployed + verified: [`0x590af780fe1E57AC9B245E14a37d5c3E69F0B8B4`](https://sepolia.mantlescan.xyz/address/0x590af780fe1E57AC9B245E14a37d5c3E69F0B8B4#code).
2. ✅ `python -m agent.dogfood --arena 0x47f1…0e68 --broadcast` ran — the 6 siblings are registered + scored on-chain (agents #3–#8); the live leaderboard reads them automatically.
3. ✅ `docs/receipts.json` / `docs/dogfood.json` refreshed from `agent/receipts/` so the static page shows the real 6-agent dogfood result.
