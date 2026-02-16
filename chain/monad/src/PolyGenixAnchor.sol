// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title PolyGenixAnchor
/// @notice Minimal on-chain proof-of-deployment contract for hackathon submission.
contract PolyGenixAnchor {
    string public projectName;
    string public releaseTag;
    address public immutable deployer;
    uint256 public immutable deployedAt;

    constructor(string memory _projectName, string memory _releaseTag) {
        projectName = _projectName;
        releaseTag = _releaseTag;
        deployer = msg.sender;
        deployedAt = block.timestamp;
    }
}
