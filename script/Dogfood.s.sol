// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {AgentArena} from "../src/AgentArena.sol";

/// @notice Dogfood: register + benchmark the 6 sibling Mantle BUIDL agents against the EXISTING,
///         already-deployed AgentArena. Mirrors agent/dogfood.py. The caller must be the arena's
///         `scorer` for recordEvaluation to succeed.
///
/// Run as a simulation (NO on-chain writes — DO NOT add --broadcast unless you intend to send):
///   ARENA_ADDRESS=0x47f1778bA757C391E02aE72c33930bc9aBdb0e68 \
///   forge script script/Dogfood.s.sol --rpc-url mantle_sepolia
///
/// Env: ARENA_ADDRESS (deployed AgentArena), PRIVATE_KEY (only needed if you later broadcast).
contract Dogfood is Script {
    bytes32 constant DOGFOOD_TASK = keccak256("agent-arena/dogfood/v1");

    struct Entry {
        string name;
        string model;
        string uri;
        uint8 score;
        string note;
        bytes32 evidenceHash;
    }

    function _entries() internal pure returns (Entry[] memory e) {
        e = new Entry[](6);
        e[0] = Entry("Gas Surgeon", "gpt-oss:20b", "https://imgntn.github.io/gas-surgeon", 88,
            "Accurate gas+correctness findings; ~27.85% measured savings.", keccak256("gas-surgeon|88"));
        e[1] = Entry("Spec2Mantle", "gpt-oss:20b", "https://imgntn.github.io/spec2mantle", 81,
            "Compiles & deploys from spec; tests pass.", keccak256("spec2mantle|81"));
        e[2] = Entry("MindMeld", "gpt-oss:20b", "https://imgntn.github.io/mindmeld", 76,
            "Sound multi-agent consensus; verbose rationale.", keccak256("mindmeld|76"));
        e[3] = Entry("StratSig", "gpt-oss:20b", "https://imgntn.github.io/stratsig", 72,
            "Risk-bounded signal; some unbacked assumptions.", keccak256("stratsig|72"));
        e[4] = Entry("Chain Sentinel", "gpt-oss:20b", "https://imgntn.github.io/chain-sentinel", 79,
            "Correctly flags exploit path; clear explanation.", keccak256("chain-sentinel|79"));
        e[5] = Entry("RWA Guard", "gpt-oss:20b", "https://imgntn.github.io/rwa-guard", 74,
            "Catches eligibility gaps; one false positive.", keccak256("rwa-guard|74"));
    }

    function run() external {
        address arenaAddr = vm.envAddress("ARENA_ADDRESS");
        AgentArena arena = AgentArena(arenaAddr);
        Entry[] memory e = _entries();

        uint256 pk = vm.envOr("PRIVATE_KEY", uint256(0));
        if (pk != 0) vm.startBroadcast(pk);

        for (uint256 i = 0; i < e.length; i++) {
            uint256 id = arena.registerAgent(e[i].name, e[i].model, e[i].uri);
            arena.recordEvaluation(id, DOGFOOD_TASK, e[i].score, e[i].evidenceHash, e[i].note);
            console.log("dogfood agent:", e[i].name);
            console.log("  id:", id);
            console.log("  score:", e[i].score);
        }

        if (pk != 0) vm.stopBroadcast();
    }
}
