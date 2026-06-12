// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Test} from "forge-std/Test.sol";
import {ArenaStaking} from "../src/ArenaStaking.sol";

contract ArenaStakingTest is Test {
    ArenaStaking staking;

    address owner = address(this);
    address scorer = address(0xA11CE);
    address treasury = address(0x7EE);
    address sponsor = address(0x5004);
    address alice = address(0xA1);
    address bob = address(0xB0B);
    address carol = address(0xCA401);

    uint96 constant BOUNTY = 10 ether;
    uint96 constant STAKE = 1 ether;

    function setUp() public {
        staking = new ArenaStaking(scorer, treasury);
        vm.deal(sponsor, 100 ether);
        vm.deal(alice, 100 ether);
        vm.deal(bob, 100 ether);
        vm.deal(carol, 100 ether);
    }

    // ----------------------------------------------------------------- helpers
    function _createTask(uint8 threshold) internal returns (uint256 id) {
        vm.prank(sponsor);
        id = staking.createTask{value: BOUNTY}(STAKE, threshold);
    }

    // ----------------------------------------------------------------- admin
    function test_ConstructorDefaults() public {
        ArenaStaking s = new ArenaStaking(address(0), address(0));
        assertEq(s.scorer(), address(this));
        assertEq(s.treasury(), address(this));
        assertEq(s.owner(), address(this));
    }

    function test_SetScorerAndTreasury() public {
        staking.setScorer(bob);
        assertEq(staking.scorer(), bob);
        staking.setTreasury(carol);
        assertEq(staking.treasury(), carol);
    }

    function test_SetScorer_OnlyOwner() public {
        vm.prank(alice);
        vm.expectRevert(ArenaStaking.NotOwner.selector);
        staking.setScorer(alice);
    }

    function test_SetScorer_ZeroReverts() public {
        vm.expectRevert(ArenaStaking.ZeroAddress.selector);
        staking.setScorer(address(0));
    }

    // ----------------------------------------------------------------- createTask
    function test_CreateTask() public {
        uint256 id = _createTask(50);
        assertEq(id, 1);
        ArenaStaking.Task memory t = staking.getTask(id);
        assertEq(t.sponsor, sponsor);
        assertEq(t.bounty, BOUNTY);
        assertEq(t.pot, BOUNTY);
        assertEq(t.stakeRequired, STAKE);
        assertEq(t.passThreshold, 50);
        assertEq(uint8(t.status), uint8(ArenaStaking.Status.Open));
        assertEq(address(staking).balance, BOUNTY);
    }

    function test_CreateTask_ZeroBountyReverts() public {
        vm.prank(sponsor);
        vm.expectRevert(ArenaStaking.BadBounty.selector);
        staking.createTask{value: 0}(STAKE, 50);
    }

    function test_CreateTask_BadThresholdReverts() public {
        vm.prank(sponsor);
        vm.expectRevert(ArenaStaking.BadThreshold.selector);
        staking.createTask{value: BOUNTY}(STAKE, 0);
        vm.prank(sponsor);
        vm.expectRevert(ArenaStaking.BadThreshold.selector);
        staking.createTask{value: BOUNTY}(STAKE, 101);
    }

    // ----------------------------------------------------------------- attempt
    function test_Attempt() public {
        uint256 id = _createTask(50);
        vm.prank(alice);
        uint256 aid = staking.attempt{value: STAKE}(id);
        assertEq(aid, 1);
        ArenaStaking.Attempt memory a = staking.getAttempt(id, aid);
        assertEq(a.agent, alice);
        assertEq(a.stake, STAKE);
        assertEq(staking.attemptOf(id, alice), 1);
        assertEq(address(staking).balance, BOUNTY + STAKE);
    }

    function test_Attempt_WrongStakeReverts() public {
        uint256 id = _createTask(50);
        vm.prank(alice);
        vm.expectRevert(ArenaStaking.WrongStake.selector);
        staking.attempt{value: STAKE - 1}(id);
    }

    function test_Attempt_DoubleReverts() public {
        uint256 id = _createTask(50);
        vm.prank(alice);
        staking.attempt{value: STAKE}(id);
        vm.prank(alice);
        vm.expectRevert(ArenaStaking.AlreadyAttempted.selector);
        staking.attempt{value: STAKE}(id);
    }

    function test_Attempt_NoSuchTaskReverts() public {
        vm.prank(alice);
        vm.expectRevert(ArenaStaking.NoSuchTask.selector);
        staking.attempt{value: STAKE}(99);
    }

    // ----------------------------------------------------------------- score
    function test_Score_OnlyScorer() public {
        uint256 id = _createTask(50);
        vm.prank(alice);
        staking.attempt{value: STAKE}(id);
        vm.prank(alice);
        vm.expectRevert(ArenaStaking.NotScorer.selector);
        staking.score(id, 1, 80, bytes32(0));
    }

    function test_Score_BadScoreReverts() public {
        uint256 id = _createTask(50);
        vm.prank(alice);
        staking.attempt{value: STAKE}(id);
        vm.prank(scorer);
        vm.expectRevert(ArenaStaking.BadScore.selector);
        staking.score(id, 1, 101, bytes32(0));
    }

    function test_Score_DoubleReverts() public {
        uint256 id = _createTask(50);
        vm.prank(alice);
        staking.attempt{value: STAKE}(id);
        vm.startPrank(scorer);
        staking.score(id, 1, 80, bytes32(0));
        vm.expectRevert(ArenaStaking.AlreadyScored.selector);
        staking.score(id, 1, 80, bytes32(0));
        vm.stopPrank();
    }

    function test_Score_NoSuchAttemptReverts() public {
        uint256 id = _createTask(50);
        vm.prank(scorer);
        vm.expectRevert(ArenaStaking.NoSuchAttempt.selector);
        staking.score(id, 1, 80, bytes32(0));
    }

    function test_Score_PassEarmarksStake_FailSlashes() public {
        uint256 id = _createTask(50);
        vm.prank(alice);
        staking.attempt{value: STAKE}(id);
        vm.prank(bob);
        staking.attempt{value: STAKE}(id);

        vm.startPrank(scorer);
        staking.score(id, 1, 80, keccak256("evidence-a")); // alice passes
        staking.score(id, 2, 10, keccak256("evidence-b")); // bob fails -> slashed
        vm.stopPrank();

        ArenaStaking.Task memory t = staking.getTask(id);
        assertEq(t.winnerCount, 1);
        assertEq(t.winnerStakeReturn, STAKE);
        // pot grew by bob's slashed stake
        assertEq(t.pot, BOUNTY + STAKE);
    }

    // ----------------------------------------------------------------- settle + payout
    function test_FullFlow_SingleWinner_GetsBountyPlusSlashedStake() public {
        uint256 id = _createTask(50);
        vm.prank(alice);
        staking.attempt{value: STAKE}(id); // attemptId 1
        vm.prank(bob);
        staking.attempt{value: STAKE}(id); // attemptId 2

        vm.startPrank(scorer);
        staking.score(id, 1, 90, keccak256("a")); // alice wins
        staking.score(id, 2, 20, keccak256("b")); // bob slashed
        vm.stopPrank();

        staking.settle(id);

        // pot = bounty + bob's slashed stake = 11 ether, 1 winner => alice gets stake(1) + 11 = 12
        uint256 expected = uint256(STAKE) + (BOUNTY + STAKE);
        assertEq(staking.payoutOf(id, 1), expected);

        uint256 before = alice.balance;
        vm.prank(alice);
        staking.withdraw(id, 1);
        vm.prank(alice);
        staking.claim();
        assertEq(alice.balance - before, expected);

        // bob (slashed) cannot withdraw
        vm.prank(bob);
        vm.expectRevert(ArenaStaking.DidNotPass.selector);
        staking.withdraw(id, 2);

        // contract drained
        assertEq(address(staking).balance, 0);
    }

    function test_FullFlow_TwoWinners_SplitPot() public {
        uint256 id = _createTask(50);
        vm.prank(alice);
        staking.attempt{value: STAKE}(id); // 1
        vm.prank(bob);
        staking.attempt{value: STAKE}(id); // 2
        vm.prank(carol);
        staking.attempt{value: STAKE}(id); // 3

        vm.startPrank(scorer);
        staking.score(id, 1, 70, keccak256("a")); // win
        staking.score(id, 2, 60, keccak256("b")); // win
        staking.score(id, 3, 10, keccak256("c")); // slashed
        vm.stopPrank();

        staking.settle(id);

        // pot = bounty(10) + carol slashed(1) = 11; 2 winners => share 5.5 each + own stake 1 = 6.5
        uint256 share = (uint256(BOUNTY) + STAKE) / 2;
        uint256 expected = uint256(STAKE) + share;
        assertEq(staking.payoutOf(id, 1), expected);
        assertEq(staking.payoutOf(id, 2), expected);

        uint256 a0 = alice.balance;
        uint256 b0 = bob.balance;
        vm.prank(alice);
        staking.withdraw(id, 1);
        vm.prank(alice);
        staking.claim();
        vm.prank(bob);
        staking.withdraw(id, 2);
        vm.prank(bob);
        staking.claim();
        assertEq(alice.balance - a0, expected);
        assertEq(bob.balance - b0, expected);

        // 11 ether split evenly => no remainder; contract empty
        assertEq(address(staking).balance, 0);
    }

    function test_Settle_RemainderToTreasury() public {
        // bounty not divisible by winners => remainder swept to treasury
        vm.prank(sponsor);
        uint256 id = staking.createTask{value: 10 ether + 1 wei}(STAKE, 50);
        vm.prank(alice);
        staking.attempt{value: STAKE}(id);
        vm.prank(bob);
        staking.attempt{value: STAKE}(id);
        vm.startPrank(scorer);
        staking.score(id, 1, 70, bytes32(0));
        staking.score(id, 2, 70, bytes32(0));
        vm.stopPrank();
        staking.settle(id);

        // pot = 10 ether + 1 wei, 2 winners => 1 wei remainder
        vm.prank(alice);
        staking.withdraw(id, 1);
        vm.prank(bob);
        staking.withdraw(id, 2);
        assertEq(staking.pending(treasury), 1);
        // drain all
        vm.prank(alice);
        staking.claim();
        vm.prank(bob);
        staking.claim();
        vm.prank(treasury);
        staking.claim();
        assertEq(address(staking).balance, 0);
    }

    function test_Settle_NoWinners_PotToTreasury() public {
        uint256 id = _createTask(80);
        vm.prank(alice);
        staking.attempt{value: STAKE}(id);
        vm.prank(bob);
        staking.attempt{value: STAKE}(id);
        vm.startPrank(scorer);
        staking.score(id, 1, 40, bytes32(0));
        staking.score(id, 2, 10, bytes32(0));
        vm.stopPrank();
        staking.settle(id);

        // pot = bounty + 2 slashed stakes = 12 ether to treasury
        assertEq(staking.pending(treasury), uint256(BOUNTY) + 2 * uint256(STAKE));
        uint256 t0 = treasury.balance;
        vm.prank(treasury);
        staking.claim();
        assertEq(treasury.balance - t0, uint256(BOUNTY) + 2 * uint256(STAKE));
        assertEq(address(staking).balance, 0);
    }

    function test_Settle_RequiresAllScored() public {
        uint256 id = _createTask(50);
        vm.prank(alice);
        staking.attempt{value: STAKE}(id);
        vm.prank(bob);
        staking.attempt{value: STAKE}(id);
        vm.prank(scorer);
        staking.score(id, 1, 80, bytes32(0));
        vm.expectRevert(ArenaStaking.AttemptNotScored.selector);
        staking.settle(id);
    }

    function test_ScoreAfterSettleReverts() public {
        uint256 id = _createTask(50);
        vm.prank(alice);
        staking.attempt{value: STAKE}(id);
        vm.prank(scorer);
        staking.score(id, 1, 80, bytes32(0));
        staking.settle(id);
        vm.prank(scorer);
        vm.expectRevert(ArenaStaking.TaskNotOpen.selector);
        staking.score(id, 1, 90, bytes32(0));
    }

    function test_AttemptAfterSettleReverts() public {
        uint256 id = _createTask(50);
        vm.prank(alice);
        staking.attempt{value: STAKE}(id);
        vm.prank(scorer);
        staking.score(id, 1, 80, bytes32(0));
        staking.settle(id);
        vm.prank(bob);
        vm.expectRevert(ArenaStaking.TaskNotOpen.selector);
        staking.attempt{value: STAKE}(id);
    }

    function test_DoubleSettleReverts() public {
        uint256 id = _createTask(50);
        vm.prank(alice);
        staking.attempt{value: STAKE}(id);
        vm.prank(scorer);
        staking.score(id, 1, 80, bytes32(0));
        staking.settle(id);
        vm.expectRevert(ArenaStaking.TaskAlreadySettled.selector);
        staking.settle(id);
    }

    function test_DoubleWithdrawReverts() public {
        uint256 id = _createTask(50);
        vm.prank(alice);
        staking.attempt{value: STAKE}(id);
        vm.prank(scorer);
        staking.score(id, 1, 80, bytes32(0));
        staking.settle(id);
        vm.prank(alice);
        staking.withdraw(id, 1);
        vm.prank(alice);
        vm.expectRevert(ArenaStaking.AlreadyClaimed.selector);
        staking.withdraw(id, 1);
    }

    function test_WithdrawBeforeSettleReverts() public {
        uint256 id = _createTask(50);
        vm.prank(alice);
        staking.attempt{value: STAKE}(id);
        vm.prank(scorer);
        staking.score(id, 1, 80, bytes32(0));
        vm.prank(alice);
        vm.expectRevert(ArenaStaking.NotScoredYet.selector);
        staking.withdraw(id, 1);
    }

    function test_WithdrawNotOwnerReverts() public {
        uint256 id = _createTask(50);
        vm.prank(alice);
        staking.attempt{value: STAKE}(id);
        vm.prank(scorer);
        staking.score(id, 1, 80, bytes32(0));
        staking.settle(id);
        vm.prank(bob);
        vm.expectRevert(ArenaStaking.NotAttemptOwner.selector);
        staking.withdraw(id, 1);
    }

    function test_ClaimNothingReverts() public {
        vm.prank(alice);
        vm.expectRevert(ArenaStaking.NothingToWithdraw.selector);
        staking.claim();
    }

    function test_CancelEmptyTask() public {
        uint256 id = _createTask(50);
        uint256 before = sponsor.balance;
        vm.prank(sponsor);
        staking.cancelEmptyTask(id);
        vm.prank(sponsor);
        staking.claim();
        assertEq(sponsor.balance - before, BOUNTY);
        assertEq(address(staking).balance, 0);
    }

    function test_CancelEmptyTask_WithAttemptsReverts() public {
        uint256 id = _createTask(50);
        vm.prank(alice);
        staking.attempt{value: STAKE}(id);
        vm.prank(sponsor);
        vm.expectRevert(ArenaStaking.TaskNotOpen.selector);
        staking.cancelEmptyTask(id);
    }

    function test_CancelEmptyTask_NotSponsorReverts() public {
        uint256 id = _createTask(50);
        vm.prank(alice);
        vm.expectRevert(ArenaStaking.NotAttemptOwner.selector);
        staking.cancelEmptyTask(id);
    }

    function test_FreeEntryTask() public {
        // stakeRequired = 0 still works; failing agents have nothing to slash
        vm.prank(sponsor);
        uint256 id = staking.createTask{value: BOUNTY}(0, 50);
        vm.prank(alice);
        staking.attempt{value: 0}(id);
        vm.prank(scorer);
        staking.score(id, 1, 90, bytes32(0));
        staking.settle(id);
        uint256 before = alice.balance;
        vm.prank(alice);
        staking.withdraw(id, 1);
        vm.prank(alice);
        staking.claim();
        assertEq(alice.balance - before, BOUNTY); // whole bounty, no stake
    }

    // ----------------------------------------------------------------- reentrancy
    function test_Reentrancy_ClaimGuarded() public {
        Reenterer attacker = new Reenterer(staking);
        vm.deal(address(attacker), 10 ether);
        uint256 id = _createTask(50);
        attacker.doAttempt{value: STAKE}(id);
        vm.prank(scorer);
        staking.score(id, 1, 90, bytes32(0));
        staking.settle(id);
        attacker.doWithdraw(id, 1);
        // claim triggers reentry attempt in receive(); guard must make the nested call fail,
        // the bubbled failure reverts the whole claim.
        vm.expectRevert();
        attacker.doClaim();
    }

    // fuzz: payout never exceeds contract balance, no stranded wei after all claims
    function testFuzz_Conservation(uint96 bounty, uint8 threshold, uint8 sA, uint8 sB) public {
        bounty = uint96(bound(bounty, 1, 1_000 ether));
        threshold = uint8(bound(threshold, 1, 100));
        sA = uint8(bound(sA, 0, 100));
        sB = uint8(bound(sB, 0, 100));
        vm.deal(sponsor, uint256(bounty));
        vm.prank(sponsor);
        uint256 id = staking.createTask{value: bounty}(STAKE, threshold);
        vm.prank(alice);
        staking.attempt{value: STAKE}(id);
        vm.prank(bob);
        staking.attempt{value: STAKE}(id);
        vm.startPrank(scorer);
        staking.score(id, 1, sA, bytes32(0));
        staking.score(id, 2, sB, bytes32(0));
        vm.stopPrank();
        staking.settle(id);

        if (sA >= threshold) {
            vm.prank(alice);
            staking.withdraw(id, 1);
        }
        if (sB >= threshold) {
            vm.prank(bob);
            staking.withdraw(id, 2);
        }
        // drain pull ledger for everyone involved
        _drain(alice);
        _drain(bob);
        _drain(treasury);
        assertEq(address(staking).balance, 0, "wei stranded");
    }

    function _drain(address who) internal {
        if (staking.pending(who) > 0) {
            vm.prank(who);
            staking.claim();
        }
    }

    receive() external payable {}
}

/// Malicious contract that tries to re-enter claim() from its receive hook.
contract Reenterer {
    ArenaStaking public immutable staking;
    bool entered;

    constructor(ArenaStaking _s) {
        staking = _s;
    }

    function doAttempt(uint256 id) external payable {
        staking.attempt{value: msg.value}(id);
    }

    function doWithdraw(uint256 id, uint256 aid) external {
        staking.withdraw(id, aid);
    }

    function doClaim() external {
        staking.claim();
    }

    receive() external payable {
        if (!entered) {
            entered = true;
            // attempt re-entry; nonReentrant guard should make this revert
            staking.claim();
        }
    }
}
