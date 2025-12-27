// SPDX-License-Identifier: MIT
pragma solidity ^0.8.22;

/**
 * @title TeeOracle
 * @notice Request/fulfill oracle with TEE signature verification
 * @dev Uses DStack signature chain to verify oracle responses
 */
contract TeeOracle {
    address public immutable kmsRoot;
    bytes32 public immutable appId;

    struct Request {
        address requester;
        uint256 reward;
        uint256 timestamp;
        bool fulfilled;
    }

    mapping(uint256 => Request) public requests;
    uint256 public nextRequestId;

    event RequestCreated(uint256 indexed requestId, address indexed requester, uint256 reward);
    event RequestFulfilled(uint256 indexed requestId, uint256 price, address fulfiller);
    event OracleMessageVerified(bytes32 indexed messageHash, address signer);

    constructor(address _kmsRoot, bytes32 _appId) {
        kmsRoot = _kmsRoot;
        appId = _appId;
    }

    /// @notice Post a price request with ETH reward
    function request() external payable returns (uint256 requestId) {
        require(msg.value > 0, "need reward");
        requestId = nextRequestId++;
        requests[requestId] = Request({
            requester: msg.sender,
            reward: msg.value,
            timestamp: block.timestamp,
            fulfilled: false
        });
        emit RequestCreated(requestId, msg.sender, msg.value);
    }

    struct OracleProof {
        bytes32 messageHash;
        bytes messageSignature;
        bytes appSignature;
        bytes kmsSignature;
        bytes derivedCompressedPubkey;
        bytes appCompressedPubkey;
        string purpose;
    }

    /// @notice Fulfill a request with verified oracle response, claim reward
    function fulfill(
        uint256 requestId,
        uint256 price,
        uint256 priceTimestamp,
        OracleProof calldata proof
    ) external {
        Request storage req = requests[requestId];
        require(!req.fulfilled, "already fulfilled");
        require(req.reward > 0, "no request");

        // Verify message hash matches price data
        bytes32 expectedHash = keccak256(abi.encodePacked(price, priceTimestamp));
        require(proof.messageHash == expectedHash, "hash mismatch");

        // Verify signature chain
        require(
            verify(proof.messageHash, proof.messageSignature, proof.appSignature,
                   proof.kmsSignature, proof.derivedCompressedPubkey,
                   proof.appCompressedPubkey, proof.purpose),
            "invalid sig"
        );

        // Mark fulfilled and pay reward
        req.fulfilled = true;
        uint256 reward = req.reward;
        emit RequestFulfilled(requestId, price, msg.sender);
        (bool ok,) = msg.sender.call{value: reward}("");
        require(ok, "transfer failed");
    }

    /**
     * @notice Verify complete DStack signature chain + oracle message
     * @param messageHash Hash of oracle data (e.g., price statement)
     * @param messageSignature Oracle's signature over messageHash
     * @param appSignature App key's signature over derived key
     * @param kmsSignature KMS root's signature over app key
     * @param derivedCompressedPubkey Derived key's compressed SEC1 pubkey (33 bytes)
     * @param appCompressedPubkey App key's compressed SEC1 pubkey (33 bytes)
     * @param purpose Key derivation purpose (e.g., "ethereum")
     * @return isValid True if all signatures verify
     */
    function verify(
        bytes32 messageHash,
        bytes calldata messageSignature,
        bytes calldata appSignature,
        bytes calldata kmsSignature,
        bytes calldata derivedCompressedPubkey,
        bytes calldata appCompressedPubkey,
        string calldata purpose
    ) public view returns (bool isValid) {
        // Step 1: Verify app signature over derived key
        string memory derivedHex = _bytesToHex(derivedCompressedPubkey);
        string memory appMessage = string(abi.encodePacked(purpose, ":", derivedHex));
        bytes32 appMessageHash = keccak256(bytes(appMessage));
        address recoveredApp = _recoverSigner(appMessageHash, appSignature);

        // Step 2: Verify KMS signature over app key
        bytes memory kmsMessage = abi.encodePacked(
            "dstack-kms-issued:",
            bytes20(appId),
            appCompressedPubkey
        );
        bytes32 kmsMessageHash = keccak256(kmsMessage);
        address recoveredKms = _recoverSigner(kmsMessageHash, kmsSignature);

        if (recoveredKms != kmsRoot) return false;

        // Step 3: Verify oracle message signature
        // Uses EIP-191 personal sign format
        bytes32 ethHash = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", messageHash));
        address messageSigner = _recoverSigner(ethHash, messageSignature);

        // Verify message signer matches derived key
        address derivedAddress = _compressedPubkeyToAddress(derivedCompressedPubkey);
        if (messageSigner != derivedAddress) return false;

        // Verify app key matches recovered app signer
        address appAddress = _compressedPubkeyToAddress(appCompressedPubkey);
        if (recoveredApp != appAddress) return false;

        return true;
    }

    /**
     * @notice Verify and emit event (for on-chain record)
     */
    function verifyAndLog(
        bytes32 messageHash,
        bytes calldata messageSignature,
        bytes calldata appSignature,
        bytes calldata kmsSignature,
        bytes calldata derivedCompressedPubkey,
        bytes calldata appCompressedPubkey,
        string calldata purpose
    ) external returns (bool isValid) {
        isValid = verify(messageHash, messageSignature, appSignature, kmsSignature,
                        derivedCompressedPubkey, appCompressedPubkey, purpose);
        if (isValid) {
            address signer = _compressedPubkeyToAddress(derivedCompressedPubkey);
            emit OracleMessageVerified(messageHash, signer);
        }
    }

    function _recoverSigner(bytes32 hash, bytes calldata sig) internal pure returns (address) {
        require(sig.length == 65, "bad sig len");
        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := calldataload(sig.offset)
            s := calldataload(add(sig.offset, 32))
            v := byte(0, calldataload(add(sig.offset, 64)))
        }
        if (v < 27) v += 27;
        return ecrecover(hash, v, r, s);
    }

    function _compressedPubkeyToAddress(bytes calldata pubkey) internal view returns (address) {
        require(pubkey.length == 33, "need compressed pubkey");
        // Decompress SEC1 compressed public key
        uint8 prefix = uint8(pubkey[0]);
        require(prefix == 0x02 || prefix == 0x03, "invalid prefix");

        uint256 x;
        assembly {
            x := calldataload(add(pubkey.offset, 1))
        }

        // secp256k1 curve: y² = x³ + 7
        uint256 p = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F;
        uint256 y2 = addmod(mulmod(mulmod(x, x, p), x, p), 7, p);
        uint256 y = _modExp(y2, (p + 1) / 4, p);

        // Check parity
        if ((prefix == 0x02 && y % 2 != 0) || (prefix == 0x03 && y % 2 == 0)) {
            y = p - y;
        }

        // Hash uncompressed pubkey (without 0x04 prefix)
        bytes32 hash = keccak256(abi.encodePacked(x, y));
        return address(uint160(uint256(hash)));
    }

    function _modExp(uint256 base, uint256 exp, uint256 mod) internal view returns (uint256) {
        // Use precompile at 0x05 for modular exponentiation
        bytes memory input = abi.encodePacked(
            uint256(32), uint256(32), uint256(32),
            base, exp, mod
        );
        bytes memory output = new bytes(32);
        assembly {
            if iszero(staticcall(gas(), 0x05, add(input, 32), 192, add(output, 32), 32)) {
                revert(0, 0)
            }
        }
        return abi.decode(output, (uint256));
    }

    function _bytesToHex(bytes calldata data) internal pure returns (string memory) {
        bytes memory alphabet = "0123456789abcdef";
        bytes memory str = new bytes(data.length * 2);
        for (uint i = 0; i < data.length; i++) {
            str[i*2] = alphabet[uint8(data[i] >> 4)];
            str[i*2+1] = alphabet[uint8(data[i] & 0x0f)];
        }
        return string(str);
    }
}
