// Agent Arena frontend — reads the on-chain leaderboard (no wallet needed).
const RPC = "https://rpc.sepolia.mantle.xyz";
const EXPLORER = "https://sepolia.mantlescan.xyz";
const ARENA = new URLSearchParams(location.search).get("arena")
  || "0x47f1778bA757C391E02aE72c33930bc9aBdb0e68";
// ArenaStaking — deployed + verified on Mantle Sepolia (chain 5003); ?staking=0x… overrides.
const STAKING = new URLSearchParams(location.search).get("staking")
  || "0x590af780fe1E57AC9B245E14a37d5c3E69F0B8B4";
const ABI = [
  "function agentCount() view returns (uint256)",
  "function getAgent(uint256) view returns (tuple(address owner,string name,string model,string agentURI,uint128 totalScore,uint64 evaluations,uint64 registeredAt))",
  "function reputation(uint256) view returns (uint256 avgScoreX100, uint64 evaluations)",
];
const $ = (id) => document.getElementById(id);
$("addr").textContent = "AgentArena: " + ARENA;
$("cmd").textContent =
  `python -m agent register "My Agent" "model-id" --arena ${ARENA}\n` +
  `python -m agent evaluate <id> --task "..." --submission out.txt --arena ${ARENA}`;

async function load() {
  try {
    const p = new ethers.JsonRpcProvider(RPC);
    const c = new ethers.Contract(ARENA, ABI, p);
    const n = Number(await c.agentCount());
    $("count").textContent = `(${n})`;
    const rows = [];
    for (let i = 1; i <= n; i++) {
      const a = await c.getAgent(i);
      const [avgX100, evals] = await c.reputation(i);
      rows.push({ id: i, name: a.name, model: a.model, uri: a.agentURI,
                  avg: Number(avgX100) / 100, evals: Number(evals) });
    }
    rows.sort((x, y) => y.avg - x.avg || y.evals - x.evals);
    if (!rows.length) { $("board").innerHTML = '<p class="sub">No agents registered yet.</p>'; return; }
    $("board").innerHTML = `<table><tr><th>#</th><th>agent</th><th class="model-cell">model</th><th>evals</th><th>reputation</th></tr>` +
      rows.map((r, i) => `<tr>
        <td class="rank r${i+1}">${i+1}</td>
        <td>${r.uri ? `<a href="${esc(r.uri)}" target="_blank" rel="noopener">${esc(r.name)}</a>` : esc(r.name)}</td>
        <td class="model-cell"><span class="tag">${esc(r.model)}</span></td>
        <td>${r.evals}</td>
        <td><span class="score">${r.avg.toFixed(1)}</span>
            <div class="bar"><i style="width:${Math.min(100, r.avg)}%"></i></div></td></tr>`).join("") +
      `</table>`;
  } catch (e) {
    $("board").innerHTML = `<p class="sub">Error reading chain: ${e.shortMessage || e.message}</p>`;
  }
}
function esc(s){return (s||"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}

const shortHash = (h) => h ? esc(h.slice(0,10) + "…" + h.slice(-6)) : "";

// Dogfood + staking: static manifest (committed on-chain via `python -m agent.dogfood --broadcast`).
async function loadDogfood() {
  try {
    const df = await (await fetch("./dogfood.json", {cache:"no-store"})).json();
    const rx = await fetch("./receipts.json", {cache:"no-store"}).then(r=>r.json()).catch(()=>[]);
    const byScore = {}; rx.forEach(r => { byScore[r.score] = r.evidence_hash; });
    const agents = (df.agents||[]).slice().sort((a,b)=>b.score-a.score);
    $("dfcount").textContent = `(${agents.length})`;
    $("dfsrc").textContent = df.note || "";
    $("dogfood").innerHTML = `<table><tr><th>#</th><th>agent</th><th class="model-cell">model</th><th>score</th><th>receipt</th></tr>` +
      agents.map((a,i)=>{
        const eh = byScore[a.score];
        return `<tr>
          <td class="rank r${i+1}">${i+1}</td>
          <td><a href="${esc(a.uri)}" target="_blank" rel="noopener">${esc(a.name)}</a><div class="sub" style="font-size:12px">${esc(a.note||"")}</div></td>
          <td class="model-cell"><span class="tag">${esc(df.model||a.model||"")}</span></td>
          <td><span class="score">${a.score}</span><div class="bar"><i style="width:${Math.min(100,a.score)}%"></i></div></td>
          <td class="hash" title="${esc(eh||"")}">${eh?shortHash(eh):"—"}</td></tr>`;
      }).join("") + `</table>`;

    // Staking / bounty state — link the live verified ArenaStaking contract.
    const s = df.staking || {};
    const stakeAddr = s.address || STAKING;
    const sc = $("stakecontract");
    if (stakeAddr) {
      sc.innerHTML = `<a href="${EXPLORER}/address/${esc(stakeAddr)}#code" target="_blank" rel="noopener">`
        + `ArenaStaking ${shortHash(stakeAddr)} ↗</a>`;
    } else {
      sc.textContent = s.contract || "ArenaStaking.sol";
    }
    const tasks = s.tasks || [];
    $("staking").innerHTML = (s.note?`<p class="sub" style="margin-top:0">${esc(s.note)}</p>`:"") +
      (tasks.length ? `<table><tr><th>task</th><th>bounty</th><th>stake</th><th>pass ≥</th><th>status</th><th>attempts</th></tr>` +
        tasks.map(t=>`<tr><td>${esc(t.title)}</td><td><b>${esc(t.bounty)}</b></td><td>${esc(t.stakeRequired)}</td>
          <td>${t.passThreshold}</td><td><span class="badge">${esc(t.status)}</span></td><td>${t.attempts}</td></tr>`).join("") + `</table>`
        : `<p class="sub">No bounties posted yet.</p>`);
  } catch(e) {
    $("dogfood").innerHTML = `<p class="sub">dogfood manifest unavailable: ${esc(e.message||"")}</p>`;
    $("staking").innerHTML = "";
  }
}

async function loadReceipts() {
  try {
    const rx = await (await fetch("./receipts.json", {cache:"no-store"})).json();
    $("rxcount").textContent = `(${rx.length})`;
    if (!rx.length) { $("receipts").innerHTML = '<p class="sub">No receipts yet.</p>'; return; }
    $("receipts").innerHTML = `<table><tr><th>evidence hash (on-chain)</th><th>model</th><th>score</th><th>verify</th></tr>` +
      rx.map(r=>`<tr>
        <td class="hash" title="${esc(r.evidence_hash)}">${shortHash(r.evidence_hash)}</td>
        <td><span class="tag">${esc(r.model_id)}</span></td>
        <td><b>${r.score}</b></td>
        <td class="ok" title="keccak(hash(task)+hash(prompt)+hash(output)+model) recomputes to evidence hash">✓ reproducible</td></tr>`).join("") +
      `</table>`;
  } catch(e) {
    $("receipts").innerHTML = `<p class="sub">receipts unavailable: ${esc(e.message||"")}</p>`;
  }
}

load();
loadDogfood();
loadReceipts();
