"""Unit tests for STT and TTS drivers."""

import io
import os
import stat
import subprocess
import tempfile
import time
import types
import unittest
import wave
from unittest.mock import MagicMock, Mock, patch
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
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = os.path.join(tmpdir, "speech.wav")
            path, duration = tts.synthesize_to_file("A true knight never backs down!", out_path)
            self.assertTrue(os.path.exists(path))
            self.assertGreater(duration, 0.5)

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
                    "runtime": "cli",
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

    def _local_stt_without_hardware(self, config=None):
        with patch.object(LocalSTT, "_init_audio_input"), patch.object(LocalSTT, "_init_model"):
            return LocalSTT(config or {})

    def _piper_with_model(self, tmpdir, **settings):
        model_path = os.path.join(tmpdir, "voice.onnx")
        with open(model_path, "wb") as model_file:
            model_file.write(b"test model")
        config = {
            "tts": {
                "model_path": model_path,
                "cache_dir": os.path.join(tmpdir, "cache"),
                **settings,
            }
        }
        with patch.object(PiperTTS, "_find_piper"):
            tts = PiperTTS(config)
        self.addCleanup(tts.close)
        return tts

    def test_local_stt_calibrates_once_and_does_not_send_empty_result_online(self):
        stt = self._local_stt_without_hardware()
        stt._mic_available = True
        stt.microphone = MagicMock()
        stt.recognizer = Mock(energy_threshold=300)
        audio = stt.recognizer.listen.return_value
        audio.get_wav_data.return_value = b"recorded WAV"
        stt.model = Mock()
        stt.model.transcribe.side_effect = [
            ([types.SimpleNamespace(text="Hello there")], None),
            ([], None),
        ]

        self.assertEqual(stt.listen_and_transcribe(), "Hello there")
        self.assertIsNone(stt.listen_and_transcribe())

        stt.recognizer.adjust_for_ambient_noise.assert_called_once()
        stt.recognizer.recognize_google.assert_not_called()
        self.assertEqual(stt.model.transcribe.call_count, 2)
        audio.get_wav_data.assert_called_with(convert_rate=16000, convert_width=2)
        self.assertEqual(stt.model.transcribe.call_args.kwargs["temperature"], 0.0)
        self.assertFalse(stt.model.transcribe.call_args.kwargs["condition_on_previous_text"])

    def test_whisper_cpu_workers_are_bounded(self):
        fake_whisper = types.SimpleNamespace(WhisperModel=Mock())
        stt = self._local_stt_without_hardware({
            "hardware": {"models_dir": "ssd-models"},
            "stt": {"cpu_threads": 2, "local_files_only": True},
        })
        with patch.dict("sys.modules", {"faster_whisper": fake_whisper}):
            stt._init_model()
        fake_whisper.WhisperModel.assert_called_once_with(
            "tiny.en", device="cpu", compute_type="int8", cpu_threads=2, num_workers=1,
            download_root=os.path.join("ssd-models", "stt"), local_files_only=True,
        )

    def test_arecord_keeps_short_preroll_and_phrase_limit_starts_at_speech(self):
        stt = self._local_stt_without_hardware()
        stt.model = Mock()
        stt._selected_sample_rate = 16000
        silence = b"\x00\x00" * 800
        voice = b"\xe8\x03" * 800
        # One second of waiting before a short utterance. A 0.6s phrase limit
        # must not expire during that initial silence.
        blocks = iter([silence] * 20 + [voice] * 4 + [silence] * 12 + [b""])
        clock = [0.0]
        process = MagicMock()

        def read_block(*_args):
            clock[0] += 0.05
            return next(blocks)

        with (
            patch("stt.local_stt.subprocess.Popen", return_value=process),
            patch("stt.local_stt.select.select", return_value=([process.stdout], [], [])),
            patch("stt.local_stt.os.read", side_effect=read_block),
            patch("stt.local_stt.time.monotonic", side_effect=lambda: clock[0]),
            patch.object(stt, "_transcribe_audio", return_value="A visitor") as transcribe,
        ):
            self.assertEqual(stt._listen_with_arecord(1.2, 0.6), "A visitor")

        captured = transcribe.call_args.args[0]
        self.assertIsInstance(captured, io.BytesIO)
        with wave.open(captured, "rb") as wav_file:
            # The discarded initial silence should not reach Whisper.
            self.assertLessEqual(wav_file.getnframes() / wav_file.getframerate(), 0.85)
            self.assertIn(voice, wav_file.readframes(wav_file.getnframes()))
        process.terminate.assert_called_once()
        process.stdout.close.assert_called_once()

    def test_arecord_stalled_pipe_still_obeys_initial_timeout(self):
        stt = self._local_stt_without_hardware()
        stt.model = Mock()
        process = MagicMock()
        with (
            patch("stt.local_stt.subprocess.Popen", return_value=process),
            patch("stt.local_stt.select.select", return_value=([], [], [])),
            patch("stt.local_stt.os.read") as read,
            patch("stt.local_stt.time.monotonic", side_effect=[0.0, 0.0, 0.1, 0.3]),
        ):
            self.assertIsNone(stt._listen_with_arecord(0.2, 1.0))
        read.assert_not_called()
        process.terminate.assert_called_once()

    def test_piper_python_reuses_voice_for_different_utterances(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tts = self._piper_with_model(tmpdir, cache_enabled=False)
            voice = Mock()

            def synthesize(_text, wav_file, **_kwargs):
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(16000)
                wav_file.writeframes(b"\x00\x00" * 160)

            voice.synthesize_wav.side_effect = synthesize
            piper_module = types.SimpleNamespace(
                PiperVoice=types.SimpleNamespace(load=Mock(return_value=voice)),
                SynthesisConfig=Mock(),
            )
            with patch.dict("sys.modules", {"piper": piper_module}), patch.object(tts, "_run_piper") as cli:
                tts.warmup()
                tts.synthesize_to_file("First greeting", os.path.join(tmpdir, "first.wav"))
                tts.synthesize_to_file("A different answer", os.path.join(tmpdir, "second.wav"))
            piper_module.PiperVoice.load.assert_called_once()
            self.assertEqual(voice.synthesize_wav.call_count, 2)
            self.assertEqual(tts.last_engine, "piper_python")
            cli.assert_not_called()

    def test_piper_python_failure_uses_cli_without_repeated_model_loads(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tts = self._piper_with_model(tmpdir, cache_enabled=False)
            load = Mock(side_effect=RuntimeError("incompatible native library"))
            piper_module = types.SimpleNamespace(
                PiperVoice=types.SimpleNamespace(load=load), SynthesisConfig=Mock()
            )

            def cli_synthesis(_binary, _text, output_path, _start):
                self._write_test_wav(output_path)
                return output_path, 0.01

            with (
                patch.dict("sys.modules", {"piper": piper_module}),
                patch.object(tts, "_is_executable_file", return_value=True),
                patch.object(tts, "_run_piper", side_effect=cli_synthesis) as cli,
            ):
                for index in range(2):
                    tts.synthesize_to_file(str(index), os.path.join(tmpdir, f"{index}.wav"))
            load.assert_called_once()
            self.assertEqual(cli.call_count, 2)

    def test_piper_cli_timeout_kills_worker_and_returns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tts = self._piper_with_model(tmpdir, runtime="cli", synthesis_timeout_seconds=1)
            process = MagicMock()
            process.communicate.side_effect = [subprocess.TimeoutExpired("piper", 1), ("", "")]
            with patch("tts.piper.subprocess.Popen", return_value=process):
                result = tts._run_piper("piper", "Hello", os.path.join(tmpdir, "speech.wav"), time.monotonic())
            self.assertIsNone(result)
            process.kill.assert_called_once()
            self.assertIn("timeout", tts.last_error)
            self.assertIsNone(tts._active_process)

    def test_piper_never_accepts_old_output_when_cli_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tts = self._piper_with_model(tmpdir, runtime="cli")
            path = os.path.join(tmpdir, "speech.wav")
            self._write_test_wav(path)
            process = MagicMock(returncode=0)
            process.communicate.return_value = ("", "")
            with patch("tts.piper.subprocess.Popen", return_value=process):
                self.assertIsNone(tts._run_piper("piper", "New speech", path, time.monotonic()))
            self.assertFalse(os.path.exists(path))

    def test_piper_cache_is_bounded_and_model_changes_invalidate_it(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tts = self._piper_with_model(tmpdir, cache_max_entries=2)
            path = os.path.join(tmpdir, "speech.wav")
            self._write_test_wav(path)
            for index, text in enumerate(("old", "recent", "new")):
                tts._cache_audio(text, path)
                os.utime(tts._cache_path(text), (100 + index, 100 + index))
            self.assertFalse(os.path.exists(tts._cache_path("old")))
            self.assertEqual(len(os.listdir(tts.cache_dir)), 2)
            previous_key = tts._cache_path("recent")
            with open(tts.model_path, "ab") as model_file:
                model_file.write(b"updated")
            self.assertNotEqual(previous_key, tts._cache_path("recent"))

    def test_piper_cache_read_failure_does_not_abort_synthesis(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tts = self._piper_with_model(tmpdir)
            os.makedirs(tts.cache_dir)
            self._write_test_wav(tts._cache_path("Hello"))
            with patch("tts.piper.shutil.copyfile", side_effect=PermissionError("cache not readable")):
                self.assertIsNone(tts._restore_cached_audio("Hello", os.path.join(tmpdir, "out.wav"), time.monotonic()))

    def test_piper_stages_runtime_without_copying_model_and_cleans_it_up(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tts = self._piper_with_model(tmpdir, runtime="cli")
            tts.piper_binary = os.path.join(tmpdir, "piper")
            with open(tts.piper_binary, "wb") as binary:
                binary.write(b"executable")
            os.makedirs(os.path.join(tmpdir, "espeak-ng-data"))
            staged = tts._stage_runtime_bundle_to_tmp()
            self.assertTrue(os.path.isfile(staged))
            self.assertFalse(os.path.exists(os.path.join(os.path.dirname(staged), "voice.onnx")))
            tts.close()
            self.assertFalse(os.path.exists(staged))

    def test_closed_piper_rejects_new_work(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tts = self._piper_with_model(tmpdir)
            tts.close()
            with self.assertRaisesRegex(RuntimeError, "closed"):
                tts.synthesize_to_file("Hello", os.path.join(tmpdir, "out.wav"))

    def test_missing_piper_model_reports_failure_instead_of_humming(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tts = self._piper_with_model(tmpdir)
            os.remove(tts.model_path)
            output = os.path.join(tmpdir, "out.wav")
            with self.assertRaisesRegex(RuntimeError, "voice model not found"):
                tts.synthesize_to_file("Hello", output)
            self.assertEqual(tts.last_engine, "unavailable")
            self.assertFalse(os.path.exists(output))

    def test_synthetic_piper_fallback_requires_explicit_opt_in(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tts = self._piper_with_model(tmpdir, allow_synthetic_fallback=True)
            os.remove(tts.model_path)
            output, duration = tts.synthesize_to_file("Hello", os.path.join(tmpdir, "out.wav"))
            self.assertTrue(PiperTTS._is_valid_wav(output))
            self.assertGreater(duration, 0)
            self.assertEqual(tts.last_engine, "mock_fallback")


if __name__ == "__main__":
    unittest.main()
