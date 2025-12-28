// SPDX-License-Identifier: MIT
pragma solidity ^0.8.22;

import "forge-std/Test.sol";
import "./TimelockAppAuth.sol";

contract TimelockAppAuthTest is Test {
    TimelockAppAuth auth;
    uint256 constant NOTICE_PERIOD = 2 minutes;
    bytes32 constant INITIAL_HASH = bytes32(uint256(1));
    bytes32 constant NEW_HASH = bytes32(uint256(2));

    function setUp() public {
        auth = new TimelockAppAuth(NOTICE_PERIOD, true, INITIAL_HASH);
    }

    function test_initialHashIsActive() public view {
        assertTrue(auth.allowedComposeHashes(INITIAL_HASH));
    }

    function test_proposeNewHash() public {
        auth.proposeComposeHash(NEW_HASH);
        assertEq(auth.proposedAt(NEW_HASH), block.timestamp);
        assertFalse(auth.allowedComposeHashes(NEW_HASH));
    }

    function test_cannotActivateBeforeNoticePeriod() public {
        auth.proposeComposeHash(NEW_HASH);
        vm.expectRevert("notice period not elapsed");
        auth.activateComposeHash(NEW_HASH);
    }

    function test_canActivateAfterNoticePeriod() public {
        auth.proposeComposeHash(NEW_HASH);
        vm.warp(block.timestamp + NOTICE_PERIOD);
        auth.activateComposeHash(NEW_HASH);
        assertTrue(auth.allowedComposeHashes(NEW_HASH));
    }

    function test_anyoneCanActivate() public {
        auth.proposeComposeHash(NEW_HASH);
        vm.warp(block.timestamp + NOTICE_PERIOD);
        vm.prank(address(0xdead));
        auth.activateComposeHash(NEW_HASH);
        assertTrue(auth.allowedComposeHashes(NEW_HASH));
    }

    function test_ownerCanCancel() public {
        auth.proposeComposeHash(NEW_HASH);
        auth.cancelProposal(NEW_HASH);
        assertEq(auth.proposedAt(NEW_HASH), 0);
    }

    function test_cannotActivateCancelled() public {
        auth.proposeComposeHash(NEW_HASH);
        auth.cancelProposal(NEW_HASH);
        vm.warp(block.timestamp + NOTICE_PERIOD);
        vm.expectRevert("not proposed");
        auth.activateComposeHash(NEW_HASH);
    }

    function test_cannotProposeAlreadyActive() public {
        vm.expectRevert("already active");
        auth.proposeComposeHash(INITIAL_HASH);
    }

    function test_cannotProposeTwice() public {
        auth.proposeComposeHash(NEW_HASH);
        vm.expectRevert("already proposed");
        auth.proposeComposeHash(NEW_HASH);
    }

    function test_activatesAtReturnsCorrectTime() public {
        auth.proposeComposeHash(NEW_HASH);
        assertEq(auth.activatesAt(NEW_HASH), block.timestamp + NOTICE_PERIOD);
    }

    function test_isAppAllowed() public view {
        TimelockAppAuth.AppBootInfo memory info;
        info.composeHash = INITIAL_HASH;
        (bool allowed, ) = auth.isAppAllowed(info);
        assertTrue(allowed);
    }

    function test_isAppNotAllowed() public view {
        TimelockAppAuth.AppBootInfo memory info;
        info.composeHash = NEW_HASH;
        (bool allowed, string memory reason) = auth.isAppAllowed(info);
        assertFalse(allowed);
        assertEq(reason, "compose hash not allowed");
    }
}
