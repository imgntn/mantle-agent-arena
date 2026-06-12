// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {AgentArena} from "../src/AgentArena.sol";

contract AgentArenaTest is Test {
    AgentArena arena;
    address scorer = address(0xA11CE);
    address dev = address(0xB0B);

    function setUp() public {
        arena = new AgentArena(scorer);
    }

    function test_RegisterAndIdentity() public {
        vm.prank(dev);
        vm.expectEmit(true, true, false, true);
        emit AgentArena.AgentRegistered(1, dev, "Gas Surgeon", "claude-opus-4-8", "ipfs://card");
        uint256 id = arena.registerAgent("Gas Surgeon", "claude-opus-4-8", "ipfs://card");
        assertEq(id, 1);
        AgentArena.Agent memory a = arena.getAgent(1);
        assertEq(a.owner, dev);
        assertEq(a.model, "claude-opus-4-8");
    }

    function test_ReputationAccrues() public {
        vm.prank(dev);
        uint256 id = arena.registerAgent("A", "qwen2.5", "");
        vm.startPrank(scorer);
        arena.recordEvaluation(id, keccak256("task1"), 80, bytes32(0), "good audit");
        arena.recordEvaluation(id, keccak256("task2"), 90, bytes32(0), "great");
        vm.stopPrank();
        (uint256 avg, uint64 n) = arena.reputation(id);
        assertEq(n, 2);
        assertEq(avg, 8500); // (80+90)/2 * 100
    }

    function test_OnlyScorer() public {
        vm.prank(dev);
        uint256 id = arena.registerAgent("A", "m", "");
        vm.prank(dev);
        vm.expectRevert(AgentArena.NotScorer.selector);
        arena.recordEvaluation(id, bytes32(0), 50, bytes32(0), "");
    }

    function test_BadScoreReverts() public {
        vm.prank(dev);
        uint256 id = arena.registerAgent("A", "m", "");
        vm.prank(scorer);
        vm.expectRevert(AgentArena.BadScore.selector);
        arena.recordEvaluation(id, bytes32(0), 101, bytes32(0), "");
    }

    function test_EvalUnknownAgentReverts() public {
        vm.prank(scorer);
        vm.expectRevert(AgentArena.NoSuchAgent.selector);
        arena.recordEvaluation(99, bytes32(0), 50, bytes32(0), "");
    }
}
