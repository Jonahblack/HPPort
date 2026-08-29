"""Unit tests for STT and TTS drivers."""

import os
import stat
import subprocess
import tempfile
import unittest
import wave
from unittest.mock import patch
from stt.keyboard_stt import KeyboardSTT
from stt.local_stt import LocalSTT
from tts.mock_tts import MockTTS
from tts.piper import PiperTTS


class TestSTTTTS(unittest.TestCase):

    @staticmethod
    def _write_test_wav(path):
        with wave.open(path, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(b"\x00\x00" * 160)

    def test_keyboard_stt(self):
        stt = KeyboardSTT()
        stt.inject_text("Halt and state your business!")
        transcribed = stt.listen_and_transcribe(timeout_seconds=0.5)
        self.assertEqual(transcribed, "Halt and state your business!")

    def test_mock_tts_synthesis(self):
        tts = MockTTS()
        out_path = "/tmp/test_speech.wav"
        path, duration = tts.synthesize_to_file("A true knight never backs down!", out_path)
        self.assertTrue(os.path.exists(path))
        self.assertGreater(duration, 0.5)

        if os.path.exists(path):
            os.remove(path)

    def test_microphone_selector_prefers_named_device(self):
        names = ["bcm2835 HDMI 1", "USB PnP Sound Device", "Monitor of Built-in Audio"]
        selected = LocalSTT._choose_microphone_index(names, configured_name="usb pnp")
        self.assertEqual(selected, 1)

    def test_microphone_selector_prefers_name_when_saved_index_is_stale(self):
        names = ["USB PnP Sound Device", "vc4-hdmi-0"]
        selected = LocalSTT._choose_microphone_index(
            names,
            configured_index=1,
            configured_name="USB PnP Sound Device",
        )
        self.assertEqual(selected, 0)

    def test_microphone_selector_skips_output_like_devices(self):
        names = ["bcm2835 HDMI 1", "Monitor of Built-in Audio", "USB Mic"]
        selected = LocalSTT._choose_microphone_index(names)
        self.assertEqual(selected, 2)

    def test_piper_finds_nested_executable_when_configured_path_is_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_dir = os.path.join(tmpdir, "piper")
            os.makedirs(bundle_dir, exist_ok=True)

            binary_path = os.path.join(bundle_dir, "piper")
            with open(binary_path, "w", encoding="utf-8") as handle:
                handle.write("#!/bin/sh\nexit 0\n")
            os.chmod(binary_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

            model_path = os.path.join(tmpdir, "voice.onnx")
            with open(model_path, "w", encoding="utf-8") as handle:
                handle.write("dummy")

            config = {
                "tts": {
                    "piper_binary_path": bundle_dir,
                    "model_path": model_path,
                    "model_config_path": os.path.join(tmpdir, "voice.onnx.json"),
                }
            }

            tts = PiperTTS(config)
            self.assertEqual(tts.piper_binary, binary_path)

    def test_piper_replaces_empty_text_before_synthesis(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            binary_path = os.path.join(tmpdir, "piper")
            model_path = os.path.join(tmpdir, "voice.onnx")
            open(binary_path, "w", encoding="utf-8").close()
            open(model_path, "w", encoding="utf-8").close()
            os.chmod(binary_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
            config = {
                "tts": {
                    "piper_binary_path": binary_path,
                    "model_path": model_path,
                    "cache_enabled": False,
                    "empty_text_fallback": "Speak this recovery.",
                }
            }
            tts = PiperTTS(config)
            output_path = os.path.join(tmpdir, "output.wav")

            def fake_run(_binary, text, wav_path, _start):
                self.assertEqual(text, "Speak this recovery.")
                self._write_test_wav(wav_path)
                return wav_path, 0.01

            with patch.object(tts, "_run_piper", side_effect=fake_run):
                tts.synthesize_to_file("", output_path)

    def test_piper_restores_cached_audio(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = os.path.join(tmpdir, "voice.onnx")
            open(model_path, "w", encoding="utf-8").close()
            tts = PiperTTS(
                {
                    "hardware": {"cache_dir": tmpdir},
                    "tts": {
                        "model_path": model_path,
                        "cache_dir": os.path.join(tmpdir, "cache"),
                    },
                }
            )
            text = "Cached greeting"
            os.makedirs(tts.cache_dir)
            self._write_test_wav(tts._cache_path(text))
            output_path = os.path.join(tmpdir, "output.wav")

            path, duration = tts.synthesize_to_file(text, output_path)

            self.assertEqual(path, output_path)
            self.assertGreater(duration, 0)
            self.assertEqual(tts.last_engine, "piper_cache")

    @patch("stt.local_stt.subprocess.run")
    def test_arecord_device_resolution_prefers_named_usb_mic(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=["arecord", "-l"],
            returncode=0,
            stdout=(
                "card 0: vc4hdmi0 [vc4-hdmi-0], device 0: MAI PCM i2s-hifi-0 [MAI PCM i2s-hifi-0]\n"
                "card 2: Device [USB PnP Sound Device], device 0: USB Audio [USB Audio]\n"
            ),
            stderr="",
        )

        stt = LocalSTT.__new__(LocalSTT)
        stt.arecord_device = ""
        stt.microphone_name = "USB PnP Sound Device"
        with patch("stt.local_stt.shutil.which", return_value="/usr/bin/arecord"):
            resolved = LocalSTT._resolve_arecord_device(stt)
        self.assertEqual(resolved, "plughw:2,0")


if __name__ == "__main__":
    unittest.main()
