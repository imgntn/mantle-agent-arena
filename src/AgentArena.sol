// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title AgentArena — on-chain identity + reputation registry for AI agents on Mantle.
/// @notice An ERC-8004-style "trustless agents" registry: each AI agent gets a permanent
///         on-chain identity, and its performance on benchmark tasks accrues as verifiable
///         on-chain reputation. This is the hackathon's "on-chain benchmarking of AI" thesis
///         made concrete — a neutral, permanent leaderboard of AI agents, recorded on Mantle.
contract AgentArena {
    /// @dev ERC-8004 identity + accumulated reputation.
    struct Agent {
        address owner;       // who registered/controls the agent
        string name;         // display name
        string model;        // backing model (e.g. claude-opus-4-8, hunyuan, qwen2.5)
        string agentURI;     // resolvable agent card (ERC-8004 identity metadata)
        uint128 totalScore;  // sum of evaluation scores
        uint64 evaluations;  // number of evaluations
        uint64 registeredAt;
    }

    address public owner;
    address public scorer; // authorized evaluator (the off-chain LLM-judge agent)
    uint256 public agentCount;

    mapping(uint256 => Agent) public agents;
    mapping(address => uint256[]) public agentsOf;

    event AgentRegistered(uint256 indexed agentId, address indexed owner, string name, string model, string agentURI);
    event EvaluationRecorded(uint256 indexed agentId, bytes32 indexed taskId, uint8 score, bytes32 evidenceHash, string note);
    event ScorerUpdated(address indexed scorer);

    error NotOwner();
    error NotScorer();
    error NoSuchAgent();
    error BadScore();

    modifier onlyOwner() { if (msg.sender != owner) revert NotOwner(); _; }
    modifier onlyScorer() { if (msg.sender != scorer) revert NotScorer(); _; }

    constructor(address _scorer) {
        owner = msg.sender;
        scorer = _scorer == address(0) ? msg.sender : _scorer;
        emit ScorerUpdated(scorer);
    }

    function setScorer(address _scorer) external onlyOwner {
        scorer = _scorer;
        emit ScorerUpdated(_scorer);
    }

    /// @notice Register an AI agent (ERC-8004 identity). Anyone can register their agent.
    function registerAgent(string calldata name, string calldata model, string calldata agentURI)
        external returns (uint256 agentId)
    {
        agentId = ++agentCount;
        agents[agentId] = Agent({
            owner: msg.sender, name: name, model: model, agentURI: agentURI,
            totalScore: 0, evaluations: 0, registeredAt: uint64(block.timestamp)
        });
        agentsOf[msg.sender].push(agentId);
        emit AgentRegistered(agentId, msg.sender, name, model, agentURI);
    }

    /// @notice The judge records an agent's benchmark result on-chain (0-100). Reputation accrues.
    function recordEvaluation(
        uint256 agentId, bytes32 taskId, uint8 score, bytes32 evidenceHash, string calldata note
    ) external onlyScorer {
        Agent storage a = agents[agentId];
        if (a.registeredAt == 0) revert NoSuchAgent();
        if (score > 100) revert BadScore();
        a.totalScore += score;
        a.evaluations += 1;
        emit EvaluationRecorded(agentId, taskId, score, evidenceHash, note);
    }

    /// @notice Aggregate reputation: average score (x100 for precision) and evaluation count.
    function reputation(uint256 agentId) external view returns (uint256 avgScoreX100, uint64 evaluations) {
        Agent storage a = agents[agentId];
        evaluations = a.evaluations;
        avgScoreX100 = evaluations == 0 ? 0 : (uint256(a.totalScore) * 100) / evaluations;
    }

    function getAgent(uint256 agentId) external view returns (Agent memory) {
        return agents[agentId];
    }
}
