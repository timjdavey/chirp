#!/usr/bin/env python
"""
Chirp audio modem: encode short codes as tones and decode them from the microphone.
Based on a reverse-engineering of the Chirp.io protocol.
"""
import sys
import wave
import time
import string
import pyaudio
import reedsolo
import argparse
import threading
import numpy as np

MIN_AMPLITUDE = 1000
SAMPLE_RATE = 44100.0  # Hz
SAMPLE_LENGTH = 5  # sec
CHIRP_LENGTH = 53


class Audio():
    """ Audio Processing """
    CHUNK = 4096
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = SAMPLE_RATE
    HUMAN_RANGE = 20000

    def __init__(self):
        self.audio = pyaudio.PyAudio()

    def __del__(self):
        try:
            self.audio.terminate()
        except:
            pass

    def record(self, seconds, filename=None):
        """ Record audio from system microphone """
        frames = []
        stream = self.audio.open(format=self.FORMAT,
                                 channels=self.CHANNELS,
                                 rate=int(self.RATE),
                                 input=True,
                                 frames_per_buffer=self.CHUNK)

        for i in range(0, int(self.RATE / self.CHUNK * seconds)):
            data = stream.read(self.CHUNK)
            frames.append(data)

        if filename:
            self.write(frames, filename)

        stream.stop_stream()
        stream.close()

        return b''.join(frames)

    def play(self, frames):
        """ Write data to system audio buffer"""
        stream = self.audio.open(format=pyaudio.paInt16,
                                 channels=1,
                                 rate=int(self.RATE),
                                 output=True)
        stream.write(frames, len(frames))
        stream.stop_stream()
        stream.close()

    def read(self, filename):
        """ Read wave file """
        wf = wave.open(filename, 'rb')
        buf = bytearray()

        chunk = wf.readframes(self.CHUNK)
        buf.extend(chunk)

        while chunk:
            chunk = wf.readframes(self.CHUNK)
            buf.extend(chunk)

        return buf

    def write(self, frames, filename):
        """ Write wave file """
        wf = wave.open(filename, 'wb')
        wf.setnchannels(self.CHANNELS)
        wf.setsampwidth(self.audio.get_sample_size(self.FORMAT))
        wf.setframerate(self.RATE)
        wf.writeframes(b''.join(frames))
        wf.close()


class Signal():
    """ Digital Signal Processing """

    def __init__(self, fs):
        self.fs = float(fs)  # sampling frequency

    def fft(self, y):
        """ Perform FFT on y with sampling rate"""
        n = len(y)  # length of the signal
        k = np.arange(n)
        T = n / self.fs
        freq = k / T  # two sides frequency range
        freq = freq[range(int(n / 2))]  # one side frequency range

        Y = np.fft.fft(y) / n  # fft computing and normalisation
        Y = Y[range(int(n / 2))]

        return (freq, abs(Y))

    def max_freq(self, data):
        """ Perform FFT on data and return maximum frequency """
        x, y = self.fft(data)
        index = y.argmax()
        return x[index]

    def sine_wave(self, freq, duration):
        """ Generate a sine wave array at given frequency for duration in seconds """
        return np.sin(2 * np.pi * np.arange(self.fs * duration) * freq / self.fs)


class Chirp():
    """ Chirp Encoding/Decoding
        http://www.chirp.io/technology """
    RATE = SAMPLE_RATE
    CHAR_LENGTH = 0.0872 / 2  # duration of one chirp character - 87.2ms
    CHAR_SAMPLES = CHAR_LENGTH * RATE  # number of samples in one chirp character
    CHIRP_SAMPLES = CHAR_SAMPLES * CHIRP_LENGTH  # number of samples in an entire chirp
    CHIRP_VOLUME = 2 ** 16 / 48  # quarter of max amplitude

    def __init__(self):
        self.map = self.get_map()
        self.chars = sorted(self.map.keys())
        self.dsp = Signal(self.RATE)
        self.rs = reedsolo.RSCodec(nsym=8, nsize=20, prim=0x25, generator=2, c_exp=5)

    def get_map(self):
        """ Construct map of chirp characters to frequencies
            0 = 1760Hz 1 = 1864Hz v = 10.5kHz """
        lowest = 1000 # 1760
        chars = string.ascii_lowercase[:22] + string.digits
        highest = lowest * 19 # 20kHz
        increment = (highest - lowest) / len(chars)
        d = {}

        for n in range(0, len(chars)):
            d[chars[n]] = lowest + (increment * n)

        return d

    def get_char(self, data):
        """ Find maximum frequency in fft data then find the closest
            frequency in chirp map and return character """
        freq = self.dsp.max_freq(data)
        ch, f = min(self.map.items(), key=lambda kv: abs(kv[1] - freq))
        return ch

    def decode(self, data):
        """ Try and find a chirp in the data, and decode into a string """
        s = 0
        chirp = ''

        # check for frontdoor pair
        chirp += self.get_char(data[s:s+int(self.CHAR_SAMPLES)])
        s += self.CHAR_SAMPLES
        if chirp != 'h':
            return 1
        chirp += self.get_char(data[int(s):int(s+self.CHAR_SAMPLES)])
        s += self.CHAR_SAMPLES
        if chirp != 'hj':
            return 2

        for i in range(2, 20):
            chirp += self.get_char(data[int(s):int(s+self.CHAR_SAMPLES)])
            s += self.CHAR_SAMPLES
        return chirp

    def encode(self, chirp, internal=False):
        """ Generate audio data from a chirp string """
        samples = np.array([], dtype=np.int16)
        if internal:
            chirp = self.ecc(chirp, encode=internal)

        for s in chirp:
            try:
                freq = self.map[s]
            except KeyError:
                freq = 0
            char = self.dsp.sine_wave(freq, self.CHAR_LENGTH)
            samples = np.concatenate([samples, char])

        samples = (samples * self.CHIRP_VOLUME).astype(np.int16)
        return samples

    def search(self, data):
        """ Search data for audio, and try and decode """
        s = 0
        CODES = []
        chirp_code = None
        datalen = len(data)

        if data.max() < MIN_AMPLITUDE:
            print(f"No chirp found, amplitude too low {data.max()} < {MIN_AMPLITUDE}")
            return

        while s < datalen - self.CHIRP_SAMPLES:
            # search for start of audio
            if data[int(s)] > MIN_AMPLITUDE:
                # check for any chirps, if unsuccessful
                # carry on searching..
                chirp_code = self.decode(data[int(s):])
                # advance pointer by searched data
                if isinstance(chirp_code, int):
                    s += chirp_code * self.CHAR_SAMPLES
                else:
                    # try and perform error correction
                    corrected = self.ecc(chirp_code)
                    if corrected:
                        chirp_code = corrected
                    if chirp_code not in CODES:
                        CODES.append(chirp_code)
                        print(CODES)

            s += 1

    def string_to_list(self, s):
        """ Convert string to list for reed solomon """
        arr = []
        for i in s:
            arr.append(self.chars.index(i))
        return arr

    def list_to_string(self, a):
        """ Convert list to string for reed solomon """
        s = ''
        for i in a:
            s += self.chars[i]
        return s

    def ecc(self, data, encode=False):
        """ Reed Solomon Error Correction """
        try:
            if encode:
                arr = self.string_to_list(data[0:12])
                out = self.rs.encode(arr)
                return self.list_to_string(out)
            else:  # decode
                arr = self.string_to_list(data)
                out = self.rs.decode(arr)
                return self.list_to_string(out)

        except reedsolo.ReedSolomonError:
            return None


class DecodeThread(threading.Thread):
    """ Thread to run digital signal processing functions """

    def __init__(self, fn, quit=False):
        self.fn = fn
        self.data = None
        self.quit = quit
        self.window = np.array([], dtype=np.int16)
        threading.Thread.__init__(self)

    def run(self):
        while not self.quit:
            if self.data is not None:
                # add data to window so we don't miss any chirps
                d1, d2 = np.array_split(self.data, 2)
                w1, w2 = np.array_split(self.window, 2)
                self.window = np.concatenate([w2, d1])
                self.fn(self.window)
                w1, w2 = np.array_split(self.window, 2)
                self.window = np.concatenate([w2, d2])
                self.fn(self.window)
                self.data = None

            time.sleep(SAMPLE_LENGTH)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Chirp audio encoder/decoder')
    parser.add_argument('-l', '--listen', action='store_true', default=False, help='listen out for a chirp')
    parser.add_argument('-i', '--internal', action='store_true', default=False, help='use internal error correction')
    parser.add_argument('-c', '--code', help='chirp a code')
    args = parser.parse_args()

    chirp = Chirp()
    audio = Audio()
    dsp = Signal(SAMPLE_RATE)

    if args.listen:
        try:
            thread = DecodeThread(chirp.search)
            thread.start()

            while (True):
                buf = audio.record(SAMPLE_LENGTH)
                thread.data = np.frombuffer(buf, dtype=np.int16)

        except KeyboardInterrupt:
            print('Exiting..')
            thread.quit = True
            sys.exit(0)

    elif args.code:
        samples = chirp.encode(args.code, internal=args.internal)
        print('Chirping code: %s' % args.code)
        audio.play(samples)

    else:
        parser.print_help()

    sys.exit(0)