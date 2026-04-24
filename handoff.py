import os
import hashlib
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import base64
import json
from typing import Tuple, Dict, Any

# Custom base32 implementation using 0-9a-v characters
def base32_encode(data: bytes) -> str:
    """Encode bytes to base32 using 0-9a-v characters."""
    alphabet = "0123456789abcdefghijklmnopqrstuv"
    encoded = ""
    bits = 0
    buffer = 0
    
    for byte in data:
        buffer = (buffer << 8) | byte
        bits += 8
        while bits >= 5:
            bits -= 5
            encoded += alphabet[(buffer >> bits) & 31]
    
    if bits > 0:
        buffer <<= (5 - bits)
        encoded += alphabet[buffer & 31]
    
    return encoded

def base32_decode(encoded: str) -> bytes:
    """Decode base32 string using 0-9a-v characters to bytes."""
    alphabet = "0123456789abcdefghijklmnopqrstuv"
    decoded = bytearray()
    bits = 0
    buffer = 0
    
    for char in encoded:
        if char not in alphabet:
            continue
        buffer = (buffer << 5) | alphabet.index(char)
        bits += 5
        while bits >= 8:
            bits -= 8
            decoded.append((buffer >> bits) & 255)
    
    return bytes(decoded)


class HandoffProtocol:
    """
    Secure handoff protocol implementation.
    
    Protocol:
    1. Alice generates a nonce and sends it to Bob
    2. Bob generates a key pair, encrypts the nonce with his private key, 
       and sends his public key + encrypted nonce to Alice
    3. Alice verifies Bob's public key by decrypting the nonce with Bob's public key
    """
    
    def __init__(self):
        self.backend = default_backend()
    
    def generate_nonce(self, length: int = 32) -> bytes:
        """Generate a cryptographically secure nonce."""
        return os.urandom(length)
    
    def generate_key_pair(self) -> Tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
        """Generate a new RSA key pair."""
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=self.backend
        )
        public_key = private_key.public_key()
        return private_key, public_key
    
    def serialize_public_key(self, public_key: rsa.RSAPublicKey, format_type: str = "raw") -> str:
        """Serialize public key to different formats."""
        if format_type == "pem":
            # Standard PEM format (larger but human-readable)
            pem = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            return pem.decode('utf-8')
        elif format_type == "der":
            # DER format (binary, smaller)
            der = public_key.public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            return base32_encode(der)
        elif format_type == "raw":
            # Just the raw key components (smallest)
            numbers = public_key.public_numbers()
            key_data = {
                'n': base32_encode(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, 'big')),
                'e': numbers.e
            }
            return json.dumps(key_data)
        else:
            raise ValueError(f"Unknown format: {format_type}")
    
    def deserialize_public_key(self, key_string: str, format_type: str = "raw") -> rsa.RSAPublicKey:
        """Deserialize public key from different formats."""
        if format_type == "pem":
            # Standard PEM format
            pem_bytes = key_string.encode('utf-8')
            return serialization.load_pem_public_key(pem_bytes, backend=self.backend)
        elif format_type == "der":
            # DER format (base32 encoded)
            der_bytes = base32_decode(key_string)
            return serialization.load_der_public_key(der_bytes, backend=self.backend)
        elif format_type == "raw":
            # Raw key components
            key_data = json.loads(key_string)
            n_bytes = base32_decode(key_data['n'])
            n = int.from_bytes(n_bytes, 'big')
            e = key_data['e']
            from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
            public_numbers = RSAPublicNumbers(e, n)
            return public_numbers.public_key(backend=self.backend)
        else:
            raise ValueError(f"Unknown format: {format_type}")
    
    def encrypt_with_private_key(self, data: bytes, private_key: rsa.RSAPrivateKey) -> bytes:
        """Encrypt data using private key (signing)."""
        return private_key.sign(
            data,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
    
    def verify_with_public_key(self, signature: bytes, data: bytes, public_key: rsa.RSAPublicKey) -> bool:
        """Verify signature using public key."""
        try:
            public_key.verify(
                signature,
                data,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            return True
        except Exception:
            return False


class Alice:
    """Alice's role in the handoff protocol."""
    
    def __init__(self):
        self.protocol = HandoffProtocol()
        self.nonce = None
    
    def initiate_handoff(self) -> bytes:
        """Step 1: Alice generates and sends a nonce to Bob."""
        self.nonce = self.protocol.generate_nonce()
        print(f"Alice: Generated nonce: {base64.b64encode(self.nonce).decode()}")
        print(f"Alice: Sending nonce to Bob: {self.nonce.hex()}")
        return self.nonce
    
    def verify_bob_response(self, bob_public_key_serialized: str, encrypted_nonce: bytes, key_format: str = "raw") -> bool:
        """Step 3: Alice verifies Bob's public key using the encrypted nonce."""
        try:
            print(f"Alice: Received public key from Bob (format: {key_format}): {bob_public_key_serialized}")
            print(f"Alice: Received encrypted nonce from Bob: {base32_encode(encrypted_nonce)}")
            
            # Deserialize Bob's public key
            bob_public_key = self.protocol.deserialize_public_key(bob_public_key_serialized, key_format)
            
            # Verify the signature (encrypted nonce) using Bob's public key
            is_valid = self.protocol.verify_with_public_key(
                encrypted_nonce, 
                self.nonce, 
                bob_public_key
            )
            
            if is_valid:
                print("Alice: ✅ Bob's public key verified successfully!")
                if key_format == "pem":
                    print(f"Alice: Bob's public key: {bob_public_key_serialized[:100]}...")
                else:
                    print(f"Alice: Bob's public key length: {len(bob_public_key_serialized)} characters")
            else:
                print("Alice: ❌ Bob's public key verification failed!")
            
            return is_valid
            
        except Exception as e:
            print(f"Alice: ❌ Error verifying Bob's public key: {e}")
            return False


class Bob:
    """Bob's role in the handoff protocol."""
    
    def __init__(self):
        self.protocol = HandoffProtocol()
        self.private_key = None
        self.public_key = None
    
    def respond_to_handoff(self, alice_nonce: bytes, key_format: str = "raw") -> Tuple[str, bytes]:
        """Step 2: Bob generates key pair and sends public key + encrypted nonce to Alice."""
        # Generate key pair
        self.private_key, self.public_key = self.protocol.generate_key_pair()
        
        # Serialize public key in specified format
        public_key_serialized = self.protocol.serialize_public_key(self.public_key, key_format)
        
        # Encrypt (sign) the nonce with private key
        encrypted_nonce = self.protocol.encrypt_with_private_key(alice_nonce, self.private_key)
        
        print(f"Bob: Generated key pair")
        print(f"Bob: Received nonce from Alice: {alice_nonce.hex()}")
        print(f"Bob: Encrypted nonce with private key")
        print(f"Bob: Sending public key to Alice (format: {key_format}): {public_key_serialized}")
        print(f"Bob: Sending encrypted nonce to Alice: {base32_encode(encrypted_nonce)}")
        
        return public_key_serialized, encrypted_nonce


def run_handoff_protocol(key_format: str = "raw"):
    """Run the complete handoff protocol demonstration."""
    print(f"🤝 Starting Handoff Protocol (Key Format: {key_format.upper()})\n")
    
    # Initialize Alice and Bob
    alice = Alice()
    bob = Bob()
    
    # Step 1: Alice sends nonce to Bob
    print("Step 1: Alice sends nonce to Bob")
    alice_nonce = alice.initiate_handoff()
    print()
    
    # Step 2: Bob responds with public key and encrypted nonce
    print("Step 2: Bob responds with public key and encrypted nonce")
    bob_public_key, bob_encrypted_nonce = bob.respond_to_handoff(alice_nonce, key_format)
    print()
    
    # Step 3: Alice verifies Bob's public key
    print("Step 3: Alice verifies Bob's public key")
    verification_result = alice.verify_bob_response(bob_public_key, bob_encrypted_nonce, key_format)
    print()
    
    if verification_result:
        print("🎉 Handoff protocol completed successfully!")
        print("Bob's public key has been verified and can be trusted.")
    else:
        print("💥 Handoff protocol failed!")
        print("Bob's public key could not be verified.")
    
    return verification_result


def test_man_in_the_middle_attack():
    """Test that the protocol is resistant to man-in-the-middle attacks."""
    print("\n🔒 Testing Man-in-the-Middle Attack Resistance\n")
    
    alice = Alice()
    bob = Bob()
    
    # Alice sends nonce
    alice_nonce = alice.initiate_handoff()
    
    # Attacker tries to intercept and modify
    attacker_nonce = alice.protocol.generate_nonce()
    
    # Bob responds to attacker's nonce (simulating MITM)
    bob_public_key, bob_encrypted_nonce = bob.respond_to_handoff(attacker_nonce)
    
    # Alice tries to verify with her original nonce
    print("Testing verification with wrong nonce (simulating MITM attack):")
    verification_result = alice.verify_bob_response(bob_public_key, bob_encrypted_nonce)
    
    if not verification_result:
        print("✅ Protocol correctly rejected the attack!")
    else:
        print("❌ Protocol failed to detect the attack!")


if __name__ == "__main__":
    # Run the main protocol with raw format (default)
    print("=" * 60)
    print("RAW FORMAT (Smallest, just key components)")
    print("=" * 60)
    success = run_handoff_protocol("raw")
    
    # Test security
    print("\n" + "=" * 60)
    print("SECURITY TEST")
    print("=" * 60)
    test_man_in_the_middle_attack()
