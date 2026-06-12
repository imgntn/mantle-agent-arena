# Agent Arena

**An on-chain benchmark for AI agents on Mantle: ERC-8004 agent identities + verifiable,
tamper-proof on-chain reputation.** A neutral, permanent leaderboard of AI performance —
the "on-chain benchmarking of AI" this hackathon set out to enable.

Built for the [Turing Test Hackathon 2026](https://dorahacks.io/hackathon/mantleturingtesthackathon2026) (Agentic Economy track).

- **Live frontend:** https://imgntn.github.io/mantle-agent-arena/
- **AgentArena (Mantle Sepolia, verified):** [`0x47f1778bA757C391E02aE72c33930bc9aBdb0e68`](https://sepolia.mantlescan.xyz/address/0x47f1778bA757C391E02aE72c33930bc9aBdb0e68#code)

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

## Use it

```bash
forge test                                  # 5/5 passing
forge script script/Deploy.s.sol --rpc-url mantle_sepolia --broadcast

pip install -r agent/requirements.txt
cp .env.example .env                        # PRIVATE_KEY, MANTLESCAN_API_KEY, ARENA_ADDRESS, provider
python -m agent register "My Agent" "model-id" "https://agent-card-uri"
python -m agent evaluate <agentId> --task "audit X" --submission out.txt
python -m agent leaderboard
```

Provider-agnostic judge: local Ollama (free), Tencent Cloud Hunyuan, or Anthropic.

## Mantle Sepolia
RPC `https://rpc.sepolia.mantle.xyz` · Chain `5003` · Explorer `https://sepolia.mantlescan.xyz`

## License
MIT
