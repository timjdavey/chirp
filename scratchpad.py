"""Experiments: play test chirps through the speakers to time them."""
import secrets
import string
import time
from chirp import Chirp, Audio

chirp = Chirp()
audio = Audio()


def generate_crypto_key(bits=256):
    # Generate a cryptographically secure random key using only valid chirp characters
    # Valid chirp characters: 0-9, a-v (32 total characters)
    valid_chars = string.digits + string.ascii_letters[0:22]
    
    # Calculate how many characters we need
    # Each character represents log2(32) = 5 bits
    chars_needed = bits // 5
    
    # Generate random characters from the valid set
    key = ''.join(secrets.choice(valid_chars) for _ in range(chars_needed))
    return key

def create_valid_chirp(data, prefix="hj"):
    """
    Create a valid chirp code with proper formatting.
    
    Args:
        data (str): The data to encode (will be truncated to fit)
        prefix (str): The frontdoor pair, defaults to "hj"
    
    Returns:
        str: A valid 20-character chirp code
    """
    return prefix + data

def call(code):
    print(f"Calling {code}")
    samples = chirp.encode(code.lower())
    audio.play(samples)

def call_valid_chirp(data, prefix="hj"):
    """
    Create and play a valid chirp.
    
    Args:
        data (str): The data to encode
        prefix (str): The frontdoor pair, defaults to "hj"
    """
    try:
        chirp_code = create_valid_chirp(data, prefix)
        print(f"Generated valid chirp: {chirp_code}")
        call(chirp_code)
        return chirp_code
    except ValueError as e:
        print(f"Error creating chirp: {e}")
        return None


def main():
    print("=== Testing Valid Chirp Creation ===")

    #long_key = generate_crypto_key()
    #print(len(long_key), long_key)
    #return
    
    # Test 1: Simple data
    print("\n1. Creating chirp with simple data:")
    start_time = time.time()
    call_valid_chirp("0123456789abcdefg")
    call_valid_chirp("hijklmnopqrstuv01")
    #call_valid_chirp("d41d8cd98f00b204e9800998ecf8427e")
    end_time = time.time()
    print(f"Audio playback took {end_time - start_time:.2f} seconds")
    return
    
    print("\n=== Original Crypto Key Tests ===")
    for k in (128, 256):
        PREFIX = "CHIRP"
        ALICE = 'ALICE' #generate_crypto_key(k)
        BOB = 'BOB' #generate_crypto_key(k)

        start_time = time.time()
        # Alice calls a wakeup code
        call(PREFIX+ALICE)
        # Bob replies
        call(PREFIX+BOB)
        end_time = time.time()
        print(f"Audio playback took {end_time - start_time:.2f} seconds")


if __name__ == "__main__":
    main()