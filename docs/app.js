// Agent Arena frontend — reads the on-chain leaderboard (no wallet needed).
const RPC = "https://rpc.sepolia.mantle.xyz";
const EXPLORER = "https://sepolia.mantlescan.xyz";
const ARENA = new URLSearchParams(location.search).get("arena")
  || "0x47f1778bA757C391E02aE72c33930bc9aBdb0e68";
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
    $("board").innerHTML = `<table><tr><th>#</th><th>agent</th><th>model</th><th>evals</th><th>reputation</th></tr>` +
      rows.map((r, i) => `<tr>
        <td class="rank r${i+1}">${i+1}</td>
        <td>${r.uri ? `<a href="${esc(r.uri)}" target="_blank">${esc(r.name)}</a>` : esc(r.name)}</td>
        <td><span class="tag">${esc(r.model)}</span></td>
        <td>${r.evals}</td>
        <td><span class="score">${r.avg.toFixed(1)}</span>
            <div class="bar"><i style="width:${Math.min(100, r.avg)}%"></i></div></td></tr>`).join("") +
      `</table>`;
  } catch (e) {
    $("board").innerHTML = `<p class="sub">Error reading chain: ${e.shortMessage || e.message}</p>`;
  }
}
function esc(s){return (s||"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}
load();
