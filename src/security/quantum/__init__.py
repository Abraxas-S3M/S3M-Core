"""
S3M Quantum Security Shell — Post-Quantum Cryptographic Core
Ring 1: NIST PQC primitives for the sovereign military AI stack.

Provides:
- Kyber-768 Key Encapsulation Mechanism (KEM)
- Dilithium-3 Digital Signatures
- AES-256-GCM authenticated encryption
- Hybrid classical+PQ key exchange
- Quantum-safe key lifecycle management
"""

from src.security.quantum.kem import QuantumKEM, KEMKeyPair, EncapsulatedKey
from src.security.quantum.signatures import QuantumSigner, SigningKeyPair
from src.security.quantum.symmetric import QuantumSymmetricCipher
from src.security.quantum.key_manager import QuantumKeyManager
from src.security.quantum.hybrid import HybridKeyExchange

__all__ = [
    "QuantumKEM",
    "KEMKeyPair",
    "EncapsulatedKey",
    "QuantumSigner",
    "SigningKeyPair",
    "QuantumSymmetricCipher",
    "QuantumKeyManager",
    "HybridKeyExchange",
]
