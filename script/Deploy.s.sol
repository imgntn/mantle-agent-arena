// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {AgentArena} from "../src/AgentArena.sol";

/// forge script script/Deploy.s.sol --rpc-url mantle_sepolia --broadcast
/// Env: PRIVATE_KEY, SCORER_ADDRESS (the judge; defaults to deployer)
contract Deploy is Script {
    function run() external returns (AgentArena arena) {
        uint256 pk = vm.envUint("PRIVATE_KEY");
        address scorer = vm.envOr("SCORER_ADDRESS", vm.addr(pk));
        vm.startBroadcast(pk);
        arena = new AgentArena(scorer);
        vm.stopBroadcast();
        console.log("AgentArena deployed at:", address(arena));
        console.log("Scorer:", scorer);
    }
}
