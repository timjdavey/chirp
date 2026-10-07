"""Experiment: how long an Ed25519 public key and a 32-byte nonce are once base64-encoded."""
import os
import base64

def to_base64(data: str | bytes) -> str:
    """Convert string or bytes to base64 encoding."""
    # Convert string to bytes if needed
    if isinstance(data, str):
        data = data.encode()
    
    # Use standard base64 encoding
    return base64.b64encode(data).decode()

# Convert test values to base64
PUBLIC = "AAAAC3NzaC1lZDI1NTE5AAAAIG/CygRy4SvjRE9xDajLnlFkBL5LwfJNOQ0cGzX30TU"
PUBLIC_B64 = to_base64(PUBLIC)
NONCE = os.urandom(32)
NONCE_B64 = to_base64(NONCE)

print(len(PUBLIC_B64))
print(len(NONCE_B64))

print(PUBLIC_B64)
print(NONCE_B64)