// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

/// @title ArenaStaking — stake-to-attempt benchmark bounties with score-based payout / slashing.
/// @notice Complements the deployed `AgentArena` identity+reputation registry: where AgentArena
///         records *who* an agent is and *how it scored*, ArenaStaking adds economic skin in the game.
///         Anyone funds a benchmark task with a native-token bounty. Agents stake to attempt it.
///         The authorized scorer (the same off-chain LLM-judge) records each attempt's score 0-100.
///         When the task is settled, attempts at/above the task's pass threshold get their stake
///         back plus a proportional cut of the pot; attempts below threshold are slashed — their
///         stake is forfeited into the pot and redistributed to the passing agents (or, if nobody
///         passes, swept to the treasury).
/// @dev Security: pull-payment withdrawals + nonReentrant on every external value-moving function,
///      strict checks-effects-interactions ordering, and no unbounded loops over attempts during
///      value transfer (settlement only tallies; agents pull their own winnings).
contract ArenaStaking {
    // ------------------------------------------------------------------ types
    enum Status {
        None, // task does not exist
        Open, // accepting attempts
        Settled // scored & finalized; winners may withdraw
    }

    struct Task {
        address sponsor; // who created & funded the bounty
        uint96 bounty; // native-token bounty seeded by the sponsor
        uint96 stakeRequired; // exact stake each attempt must post
        uint96 pot; // bounty + all forfeited (slashed) stakes available to winners
        uint8 passThreshold; // minimum score (0-100) to "pass" and be eligible for payout
        Status status;
        uint64 createdAt;
        uint32 attemptCount; // number of attempts posted
        uint32 winnerCount; // number of attempts that passed (set at settlement)
        uint96 winnerStakeReturn; // total stake to return to winners (sum of winners' stakes)
    }

    struct Attempt {
        address agent; // who staked / attempted
        uint96 stake; // stake posted (== task.stakeRequired at attempt time)
        uint8 score; // judge score 0-100 (0 until scored)
        bool scored; // scorer has recorded a result
        bool claimed; // winnings/refund already withdrawn (replay guard)
    }

    // ------------------------------------------------------------------ storage
    address public owner; // deploys, manages scorer, owns the treasury sweep
    address public scorer; // authorized judge (mirrors AgentArena.scorer)
    address public treasury; // receives swept pot when a task has zero winners

    uint256 public taskCount;
    mapping(uint256 => Task) public tasks;
    // taskId => attemptId (1-based) => Attempt
    mapping(uint256 => mapping(uint256 => Attempt)) public attempts;
    // taskId => agent => attemptId (an agent may attempt a task at most once)
    mapping(uint256 => mapping(address => uint256)) public attemptOf;

    // pull-payment ledger: address => withdrawable native balance
    mapping(address => uint256) public pending;

    // reentrancy guard
    uint256 private _lock = 1;

    // ------------------------------------------------------------------ events
    event TaskCreated(
        uint256 indexed taskId, address indexed sponsor, uint256 bounty, uint256 stakeRequired, uint8 passThreshold
    );
    event Attempted(uint256 indexed taskId, uint256 indexed attemptId, address indexed agent, uint256 stake);
    event Scored(uint256 indexed taskId, uint256 indexed attemptId, uint8 score, bool passed, bytes32 evidenceHash);
    event Settled(uint256 indexed taskId, uint256 winners, uint256 pot);
    event Withdrawn(address indexed who, uint256 amount);
    event ScorerUpdated(address indexed scorer);
    event TreasuryUpdated(address indexed treasury);

    // ------------------------------------------------------------------ errors
    error NotOwner();
    error NotScorer();
    error NoSuchTask();
    error TaskNotOpen();
    error TaskAlreadySettled();
    error BadBounty();
    error BadThreshold();
    error WrongStake();
    error AlreadyAttempted();
    error NoSuchAttempt();
    error AlreadyScored();
    error NotScoredYet();
    error AttemptNotScored();
    error BadScore();
    error NotAttemptOwner();
    error AlreadyClaimed();
    error DidNotPass();
    error NothingToWithdraw();
    error ZeroAddress();
    error TransferFailed();

    // ------------------------------------------------------------------ modifiers
    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    modifier onlyScorer() {
        if (msg.sender != scorer) revert NotScorer();
        _;
    }

    modifier nonReentrant() {
        if (_lock != 1) revert TransferFailed();
        _lock = 2;
        _;
        _lock = 1;
    }

    // ------------------------------------------------------------------ admin
    /// @param _scorer authorized judge; defaults to deployer if zero.
    /// @param _treasury receives swept pot when no agent passes; defaults to deployer if zero.
    constructor(address _scorer, address _treasury) {
        owner = msg.sender;
        scorer = _scorer == address(0) ? msg.sender : _scorer;
        treasury = _treasury == address(0) ? msg.sender : _treasury;
        emit ScorerUpdated(scorer);
        emit TreasuryUpdated(treasury);
    }

    function setScorer(address _scorer) external onlyOwner {
        if (_scorer == address(0)) revert ZeroAddress();
        scorer = _scorer;
        emit ScorerUpdated(_scorer);
    }

    function setTreasury(address _treasury) external onlyOwner {
        if (_treasury == address(0)) revert ZeroAddress();
        treasury = _treasury;
        emit TreasuryUpdated(_treasury);
    }

    // ------------------------------------------------------------------ task lifecycle

    /// @notice Create & fund a benchmark task. `msg.value` is the bounty (must be > 0).
    /// @param stakeRequired exact native-token stake each attempt must post (may be 0 for free entry).
    /// @param passThreshold minimum score 1-100 to pass; scores >= threshold win.
    function createTask(uint96 stakeRequired, uint8 passThreshold) external payable returns (uint256 taskId) {
        if (msg.value == 0 || msg.value > type(uint96).max) revert BadBounty();
        if (passThreshold == 0 || passThreshold > 100) revert BadThreshold();
        taskId = ++taskCount;
        tasks[taskId] = Task({
            sponsor: msg.sender,
            bounty: uint96(msg.value),
            stakeRequired: stakeRequired,
            pot: uint96(msg.value),
            passThreshold: passThreshold,
            status: Status.Open,
            createdAt: uint64(block.timestamp),
            attemptCount: 0,
            winnerCount: 0,
            winnerStakeReturn: 0
        });
        emit TaskCreated(taskId, msg.sender, msg.value, stakeRequired, passThreshold);
    }

    /// @notice Stake to attempt an open task. `msg.value` must equal the task's stakeRequired.
    function attempt(uint256 taskId) external payable nonReentrant returns (uint256 attemptId) {
        Task storage t = tasks[taskId];
        if (t.status == Status.None) revert NoSuchTask();
        if (t.status != Status.Open) revert TaskNotOpen();
        if (msg.value != t.stakeRequired) revert WrongStake();
        if (attemptOf[taskId][msg.sender] != 0) revert AlreadyAttempted();

        attemptId = ++t.attemptCount; // effects before any interaction
        attempts[taskId][attemptId] =
            Attempt({agent: msg.sender, stake: uint96(msg.value), score: 0, scored: false, claimed: false});
        attemptOf[taskId][msg.sender] = attemptId;
        // staked value stays in the contract; it joins the pot at settlement (win → returned, lose → slashed).
        emit Attempted(taskId, attemptId, msg.sender, msg.value);
    }

    /// @notice Scorer records the judge's result for one attempt. Tallies pot effects:
    ///         passing stakes are earmarked for return; failing stakes are slashed into the pot.
    /// @param evidenceHash reproducibility receipt hash committed by the judge (see receipts).
    function score(uint256 taskId, uint256 attemptId, uint8 s, bytes32 evidenceHash) external onlyScorer {
        Task storage t = tasks[taskId];
        if (t.status == Status.None) revert NoSuchTask();
        if (t.status != Status.Open) revert TaskNotOpen();
        if (s > 100) revert BadScore();
        Attempt storage a = attempts[taskId][attemptId];
        if (a.agent == address(0)) revert NoSuchAttempt();
        if (a.scored) revert AlreadyScored();

        a.scored = true;
        a.score = s;

        bool passed = s >= t.passThreshold;
        if (passed) {
            t.winnerCount += 1;
            t.winnerStakeReturn += a.stake; // returned 1:1 to this winner at withdraw
        } else {
            t.pot += a.stake; // slash: forfeited stake grows the pot for winners/treasury
        }
        emit Scored(taskId, attemptId, s, passed, evidenceHash);
    }

    /// @notice Finalize a task once every attempt has been scored. Locks payouts in.
    /// @dev If there are winners, each winner withdraws (stake back + equal share of pot).
    ///      If there are no winners, the entire pot is credited to the treasury (pull-payment).
    function settle(uint256 taskId) external {
        Task storage t = tasks[taskId];
        if (t.status == Status.None) revert NoSuchTask();
        if (t.status == Status.Settled) revert TaskAlreadySettled();
        if (t.status != Status.Open) revert TaskNotOpen();

        // require all attempts scored before settlement (deterministic payout)
        uint256 n = t.attemptCount;
        for (uint256 i = 1; i <= n; i++) {
            if (!attempts[taskId][i].scored) revert AttemptNotScored();
        }

        t.status = Status.Settled; // effects before interaction

        if (t.winnerCount == 0) {
            // nobody passed: sweep the full pot (bounty + all slashed stakes) to treasury.
            uint256 swept = t.pot;
            t.pot = 0;
            if (swept > 0) {
                pending[treasury] += swept;
            }
        }
        emit Settled(taskId, t.winnerCount, t.pot);
    }

    /// @notice Winner pulls their payout for a settled task: stake returned + equal share of pot.
    /// @dev Pot (bounty + slashed stakes) is split equally among winners; integer remainder is
    ///      credited to the treasury so no wei is ever stranded.
    function withdraw(uint256 taskId, uint256 attemptId) external nonReentrant {
        Task storage t = tasks[taskId];
        if (t.status == Status.None) revert NoSuchTask();
        if (t.status != Status.Settled) revert NotScoredYet();
        Attempt storage a = attempts[taskId][attemptId];
        if (a.agent == address(0)) revert NoSuchAttempt();
        if (a.agent != msg.sender) revert NotAttemptOwner();
        if (a.claimed) revert AlreadyClaimed();
        if (a.score < t.passThreshold) revert DidNotPass();

        uint256 share = uint256(t.pot) / t.winnerCount;
        uint256 amount = uint256(a.stake) + share;

        a.claimed = true; // effects before interaction

        // last winner also clears any integer remainder to the treasury.
        // (computed deterministically; safe because all winners take the same `share`.)
        _payRemainderIfLast(t, taskId);

        pending[msg.sender] += amount;
        emit Withdrawn(msg.sender, amount); // credited to pull-ledger; agent calls claim() to pull
    }

    /// @dev Credits any non-divisible pot remainder to the treasury exactly once (when the final
    ///      winner withdraws), so the equal-share split never strands wei in the contract.
    function _payRemainderIfLast(Task storage t, uint256 taskId) private {
        uint256 claimedWinners = 0;
        uint256 n = t.attemptCount;
        for (uint256 i = 1; i <= n; i++) {
            Attempt storage x = attempts[taskId][i];
            if (x.score >= t.passThreshold && x.claimed) claimedWinners++;
        }
        if (claimedWinners == t.winnerCount) {
            uint256 remainder = uint256(t.pot) % t.winnerCount;
            if (remainder > 0) pending[treasury] += remainder;
        }
    }

    /// @notice Sponsor reclaims their bounty if the task got zero attempts (so it can't be stranded).
    function cancelEmptyTask(uint256 taskId) external nonReentrant {
        Task storage t = tasks[taskId];
        if (t.status == Status.None) revert NoSuchTask();
        if (t.status != Status.Open) revert TaskNotOpen();
        if (msg.sender != t.sponsor) revert NotAttemptOwner();
        if (t.attemptCount != 0) revert TaskNotOpen();

        uint256 refund = t.pot;
        t.pot = 0;
        t.status = Status.Settled; // effects before interaction
        if (refund > 0) pending[t.sponsor] += refund;
        emit Settled(taskId, 0, 0);
    }

    /// @notice Pull native-token winnings/refunds from the pull-payment ledger.
    function claim() external nonReentrant {
        uint256 amount = pending[msg.sender];
        if (amount == 0) revert NothingToWithdraw();
        pending[msg.sender] = 0; // effects before interaction (CEI)
        (bool ok,) = payable(msg.sender).call{value: amount}("");
        if (!ok) revert TransferFailed();
        emit Withdrawn(msg.sender, amount);
    }

    // ------------------------------------------------------------------ views

    function getTask(uint256 taskId) external view returns (Task memory) {
        return tasks[taskId];
    }

    function getAttempt(uint256 taskId, uint256 attemptId) external view returns (Attempt memory) {
        return attempts[taskId][attemptId];
    }

    /// @notice Preview a winner's payout for a settled task without mutating state.
    function payoutOf(uint256 taskId, uint256 attemptId) external view returns (uint256) {
        Task storage t = tasks[taskId];
        if (t.status != Status.Settled || t.winnerCount == 0) return 0;
        Attempt storage a = attempts[taskId][attemptId];
        if (a.score < t.passThreshold) return 0;
        return uint256(a.stake) + uint256(t.pot) / t.winnerCount;
    }
}
