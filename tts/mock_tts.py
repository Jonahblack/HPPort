"""Mock TTS driver for synthetic audio generation without external binaries."""

import os
import math
import struct
import wave
from typing import Tuple, Optional, Dict, Any
from tts.base import BaseTTS


class MockTTS(BaseTTS):
    """Generates synthetic multi-harmonic chime WAV audio with natural speech duration."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        pass

    def synthesize_to_file(self, text: str, output_wav_path: str) -> Tuple[str, float]:
        os.makedirs(os.path.dirname(os.path.abspath(output_wav_path)), exist_ok=True)

        # Estimate duration based on word count (~140 words per minute -> ~2.3 words/sec)
        words = max(1, len(text.split()))
        duration = max(1.2, words * 0.38)

        sample_rate = 22050
        total_samples = int(sample_rate * duration)

        with wave.open(output_wav_path, "w") as wf:
            wf.setnchannels(1)  # Mono
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(sample_rate)

            # Generate cadence modulating wave to give dynamic mouth amplitude flapping
            frames = bytearray()
            for i in range(total_samples):
                t = float(i) / sample_rate
                # Base speech frequency 180Hz modulated with speech syllables
                syllable_env = 0.5 + 0.5 * math.sin(2 * math.pi * 3.5 * t)
                wave_val = math.sin(2 * math.pi * 180 * t) * 0.6 + math.sin(2 * math.pi * 360 * t) * 0.3
                # Fade in and out
                fade = min(1.0, t * 10) * min(1.0, (duration - t) * 10)
                sample = int(wave_val * syllable_env * fade * 16000)
                sample = max(-32768, min(32767, sample))
                frames.extend(struct.pack("<h", sample))

            wf.writeframes(frames)

        return output_wav_path, duration
