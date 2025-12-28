// SPDX-License-Identifier: MIT
pragma solidity ^0.8.22;

/**
 * @title TimelockAppAuth
 * @notice AppAuth with notice period for compose hash changes
 * @dev Demonstrates "on-chain due diligence" pattern:
 *      - New code versions must be announced before activation
 *      - Stakeholders can audit and exit before changes take effect
 *      - Trust model: "I can exit in time" vs "trust the operator"
 *
 * Related: https://github.com/njeans/dstack/tree/update-demo/demo
 */
contract TimelockAppAuth {
    address public owner;
    uint256 public noticePeriod;
    bool public allowAnyDevice;

    mapping(bytes32 => bool) public allowedComposeHashes;
    mapping(bytes32 => bool) public allowedDeviceIds;
    mapping(bytes32 => uint256) public proposedAt;

    event ComposeHashProposed(bytes32 indexed hash, uint256 activatesAt);
    event ComposeHashActivated(bytes32 indexed hash);
    event ComposeHashCancelled(bytes32 indexed hash);
    event ComposeHashRemoved(bytes32 indexed hash);

    modifier onlyOwner() {
        require(msg.sender == owner, "not owner");
        _;
    }

    constructor(uint256 _noticePeriod, bool _allowAnyDevice, bytes32 initialComposeHash) {
        owner = msg.sender;
        noticePeriod = _noticePeriod;
        allowAnyDevice = _allowAnyDevice;
        if (initialComposeHash != bytes32(0)) {
            allowedComposeHashes[initialComposeHash] = true;
        }
    }

    /// @notice Propose a new compose hash (starts the notice period clock)
    function proposeComposeHash(bytes32 hash) external onlyOwner {
        require(proposedAt[hash] == 0, "already proposed");
        require(!allowedComposeHashes[hash], "already active");
        proposedAt[hash] = block.timestamp;
        emit ComposeHashProposed(hash, block.timestamp + noticePeriod);
    }

    /// @notice Activate a proposed hash after notice period elapsed (anyone can call)
    function activateComposeHash(bytes32 hash) external {
        require(proposedAt[hash] != 0, "not proposed");
        require(block.timestamp >= proposedAt[hash] + noticePeriod, "notice period not elapsed");
        allowedComposeHashes[hash] = true;
        delete proposedAt[hash];
        emit ComposeHashActivated(hash);
    }

    /// @notice Cancel a pending proposal
    function cancelProposal(bytes32 hash) external onlyOwner {
        require(proposedAt[hash] != 0, "not proposed");
        delete proposedAt[hash];
        emit ComposeHashCancelled(hash);
    }

    /// @notice Remove an active compose hash
    function removeComposeHash(bytes32 hash) external onlyOwner {
        allowedComposeHashes[hash] = false;
        emit ComposeHashRemoved(hash);
    }

    /// @notice Check when a proposed hash can be activated
    function activatesAt(bytes32 hash) external view returns (uint256) {
        require(proposedAt[hash] != 0, "not proposed");
        return proposedAt[hash] + noticePeriod;
    }

    // IAppAuth interface (must match exactly)
    struct AppBootInfo {
        address appId;
        bytes32 composeHash;
        address instanceId;
        bytes32 deviceId;
        bytes32 mrAggregated;
        bytes32 mrSystem;
        bytes32 osImageHash;
        string tcbStatus;
        string[] advisoryIds;
    }

    function isAppAllowed(AppBootInfo calldata bootInfo)
        external view returns (bool isAllowed, string memory reason)
    {
        if (!allowedComposeHashes[bootInfo.composeHash])
            return (false, "compose hash not allowed");
        if (!allowAnyDevice && !allowedDeviceIds[bootInfo.deviceId])
            return (false, "device not allowed");
        return (true, "");
    }
}
