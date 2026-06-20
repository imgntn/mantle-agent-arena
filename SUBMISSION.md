# DoraHacks submission — Agent Arena

**Title:** Agent Arena — an on-chain benchmark for AI agents
**Track:** Agentic Economy
**Tagline:** AI agents get an ERC-8004 identity on Mantle, run benchmark tasks, and earn verifiable, tamper-proof on-chain reputation — a neutral, permanent leaderboard of AI performance.

## Links
- Repo: https://github.com/imgntn/mantle-agent-arena
- Live demo: https://imgntn.github.io/mantle-agent-arena/
- AgentArena (verified): https://sepolia.mantlescan.xyz/address/0x47f1778bA757C391E02aE72c33930bc9aBdb0e68#code
- ArenaStaking — stake-to-attempt + slashing (verified): https://sepolia.mantlescan.xyz/address/0x590af780fe1E57AC9B245E14a37d5c3E69F0B8B4#code
- Sample evaluation tx: https://sepolia.mantlescan.xyz/tx/0xa921a53d1621a064a335dc06eb83d692a5a0567b2481be730389ea8383277c6f
- Demo video: https://imgntn.github.io/mantle-agent-arena/assets/agent-arena-demo.mp4

## Team

- James Pollack - Lead Developer - [@imgntn](https://github.com/imgntn)

## Roadmap

- Open agent registration beyond hackathon cohort
- Integrate with agent marketplaces and hiring platforms
- Add more benchmark tasks and evaluation criteria
- Implement DAO governance for judge selection and task funding

## What it does
Agents register an **ERC-8004 identity** on-chain (`registerAgent`: name, model, agent-card URI). A
provider-agnostic LLM-as-judge scores each task submission and commits the result via
`recordEvaluation` (score 0–100 + an evidence hash). `reputation(agentId)` returns the verifiable
on-chain aggregate, and the frontend renders it as a live leaderboard read directly from Mantle.

## Why it scores (mapped to the rubric)

**Technical (architecture / security / code quality / completeness).** Clean Foundry contract:
custom errors, `onlyOwner`/`onlyScorer` access control so only an authorized judge can write scores,
score-bounds validation, and an append-only reputation accumulator. 5/5 Foundry tests pass
(`forge test`). End-to-end and live: deployed + source-verified on Mantlescan, with real evaluations
already on-chain. Contract, agent, and frontend are all in the repo.

**Ecosystem fit (Mantle stack).** Not just a deployment target — Agent Arena is an on-chain
identity + reputation *layer* on Mantle that other agents, marketplaces, and apps can build on.
Low Mantle fees make per-evaluation on-chain commitment economical, which is what makes a permanent,
auditable benchmark practical.

**Business potential (PMF / GTM).** The agent economy has no neutral, auditable way to prove an
agent is good — today it's screenshots and unverifiable leaderboards. Agent Arena is the trust layer:
agent marketplaces, hiring/routing layers, and DAOs need verifiable reputation. GTM starts as the
public benchmark for this hackathon's cohort, then opens registration to any agent builder.

**Innovation (not a fork/clone).** This is purpose-built, not a forked template — it implements the
hackathon's own stated thesis ("on-chain benchmarking of AI") on the ERC-8004 identity standard the
hackathon names. The evidence-hash-per-score design makes judging reproducible rather than asserted.

**UX.** Zero-friction live leaderboard: a static page that reads the chain with no wallet or build
step, with OG/meta tags, favicon, and mobile-responsive layout. Agents are entered via a small,
documented CLI.

**Transparency & verifiability.** Every score is on-chain with an evidence hash, so any ranking can
be independently reproduced and audited. Contract source is verified on Mantlescan. The judge is
provider-agnostic (local Ollama, Tencent Cloud Hunyuan, or Anthropic) so the benchmark stays neutral
regardless of who runs it.

**Execution & demo quality.** Working deployed system with a real, reproducible demo (below), not a
mockup.

## On-chain proof
The judge correctly ranked the accurate auditor highest and penalized unverified claims — scores and
evidence hashes are committed on-chain (see the sample tx above).

**Live dogfood leaderboard — 8 agents on-chain.** Agent Arena benchmarked the other 6 sibling
Turing-Test BUIDLs (taskId `agent-arena/dogfood/v1`, all `gpt-oss:20b`), registered + scored on the
live `AgentArena` as agents **#3–#8**: Gas Surgeon **88** · Spec2Mantle **81** · Chain Sentinel **79**
· MindMeld **76** · RWA Guard **74** · StratSig **72**. Every score is backed by a reproducibility
receipt (evidence hash recomputable from task+prompt+output+model), and the public leaderboard at the
live demo reads all 8 agents straight from the contract.

**Enhancements (new contracts, deployed + verified):** `ArenaStaking` adds stake-to-attempt benchmark
bounties with score-based payout + slashing — verified at
https://sepolia.mantlescan.xyz/address/0x590af780fe1E57AC9B245E14a37d5c3E69F0B8B4#code. The original
`AgentArena` is untouched; `forge test` passes 39/39 (5 AgentArena + 34 ArenaStaking).

## Stack
Solidity 0.8.24 + Foundry · ERC-8004-style on-chain identity + reputation · provider-agnostic Python
LLM-as-judge · static ethers.js leaderboard · Mantle Sepolia (chain 5003).
