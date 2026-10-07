# chirp

> **Status: abandoned.** This was a playground for one idea: authenticating someone over audio. It didn't work for the use case we cared about, so the idea is dead. The code is left here in case it's useful to anyone.

## The idea

You join a call with someone. How do you know the person on the other end is who they say they are, and not an impersonator or a deepfake?

Our idea was to give them a small hardware device, or an app on their phone, that holds a private key. When you challenge them, it plays a short burst of tones (a "chirp") into the call. Your side listens, checks the cryptographic answer, and confirms who they are.

QR codes or ordinary sign-in can solve the same problem. We wanted to test audio because it travels over the call itself, with no camera, screen or extra channel needed.

## How it works

### The handshake (`handoff.py`)

1. **Alice** (the verifier) generates a random 32-byte nonce and chirps it.
2. **Bob's** device signs the nonce with its private key, then chirps back its public key and the signature.
3. **Alice** verifies the signature. The nonce is new every time, so a recording of an earlier handshake can't be replayed.

Keys and signatures are encoded in a custom base32 alphabet (`0-9a-v`). Those 32 characters are exactly the modem's symbols, so any bytes can be played directly as tones.

### The audio modem (`chirp.py`)

This is a modified version of a reverse-engineered [Chirp.io](http://www.chirp.io) encoder and decoder.

| | |
|---|---|
| Symbols | 32 (`0-9`, `a-v`), 5 bits each |
| Tones | 1 kHz to ~19 kHz, spaced 562.5 Hz apart |
| Symbol length | 43.6 ms |
| One chirp | 20 symbols, about 0.87 s: `hj` start marker + 10 data + 8 error-correction |
| Error correction | Reed-Solomon over GF(2^5); fixes up to 4 misheard symbols |
| Decoding | FFT on each symbol slot, snapped to the nearest tone |

## Why it didn't work

### 1. It takes too long

Each chirp carries 10 data symbols (50 bits) in about 0.87 s of sound. A public key plus a signature is a lot of bits:

| Handshake | Challenge (nonce) | Response (key + signature) | Total airtime |
|---|---|---|---|
| RSA-2048 (what `handoff.py` uses) | 52 symbols, ~5 s | 820 symbols, ~72 s | **~77 s** |
| Ed25519 (explored in `lengths.py`) | 52 symbols, ~5 s | 155 symbols, ~14 s | **~19 s** |

Even the best case means about 20 seconds of tones.

### 2. Calls filter the audio, so it has to be audible

Phone and video-call audio is band-limited by high-pass and low-pass filters. Narrowband telephony, for example, passes roughly 300 to 3,400 Hz. The modem uses 1 to 19 kHz, so most of its tones never reach the other side.

Fitting the tones into the band that survives makes the chirp clearly audible. Both people would then sit through tens of seconds of loud beeping in the middle of a conversation.

An inaudible (near-ultrasonic) chirp could run in the background, and the length would matter much less. But calls strip out exactly those frequencies. Together, these two problems killed the idea.

## What's in the repo

| File | What it is |
|---|---|
| `chirp.py` | Audio modem: encode a code to tones, play it, listen and decode |
| `handoff.py` | Nonce / sign / verify handshake (RSA-2048, in memory only; not wired to audio) |
| `reedsolo.py` | Vendored pure-Python Reed-Solomon codec |
| `lengths.py` | Experiment: encoded length of an Ed25519 key and a nonce |
| `scratchpad.py` | Experiment: play test chirps and time them |
| `pyproject.toml` / `uv.lock` | Dependencies (`cryptography`, `numpy`, `pyaudio`) |

## Running it

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/). PyAudio also needs PortAudio (`brew install portaudio` on macOS).

```sh
uv sync

uv run python chirp.py --code hj0123456789 --internal   # play a chirp, with error correction added
uv run python chirp.py --listen                         # listen on the mic and print decoded chirps
uv run python handoff.py                                # run the crypto handshake in memory
```

## Limitations

This is prototype code that was never finished:

- `handoff.py` runs only in memory. It was never connected to the audio modem.
- `handoff.py` generates a new key pair on every run. That proves the response is live, but not *who* is responding. A real version needs Bob's key to be known and trusted in advance.

## Credits

- The audio scheme is based on the Chirp.io protocol.
- `reedsolo.py` is by Tomer Filiba, rotorgit and Stephen Larroque (see the file header).
