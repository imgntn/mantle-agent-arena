// SPDX-License-Identifier: MIT
pragma solidity 0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {ArenaStaking} from "../src/ArenaStaking.sol";

/// @notice Deploy ArenaStaking — stake-to-attempt benchmark bounties with slashing.
/// Usage (DO NOT run with --broadcast unless you intend to deploy):
///   forge script script/DeployArenaStaking.s.sol --rpc-url mantle_sepolia --broadcast
/// Env:
///   PRIVATE_KEY      deployer key (becomes owner)
///   SCORER_ADDRESS   authorized judge; defaults to deployer
///   TREASURY_ADDRESS receives swept pots when nobody passes; defaults to deployer
contract DeployArenaStaking is Script {
    function run() external returns (ArenaStaking staking) {
        uint256 pk = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(pk);
        address scorer = vm.envOr("SCORER_ADDRESS", deployer);
        address treasury = vm.envOr("TREASURY_ADDRESS", deployer);
        vm.startBroadcast(pk);
        staking = new ArenaStaking(scorer, treasury);
        vm.stopBroadcast();
        console.log("ArenaStaking deployed at:", address(staking));
        console.log("Scorer:", scorer);
        console.log("Treasury:", treasury);
    }
}
