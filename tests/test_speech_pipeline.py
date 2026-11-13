import threading
import time
import unittest

from speech_pipeline import SpeechPipelineError, run_speech_pipeline


class TestSpeechPipeline(unittest.TestCase):
    def test_prepares_next_phrase_during_playback_and_preserves_order(self):
        second_ready = threading.Event()
        played, discarded = [], []

        def prepare(text):
            if text == "second":
                second_ready.set()
            return text

        def play(text):
            if text == "first":
                self.assertTrue(second_ready.wait(1), "Synthesis blocked on playback")
            played.append(text)

        spoken = run_speech_pipeline(iter(["first", "second"]), prepare, play,
                                     discarded.append, threading.Event())
        self.assertEqual(played, ["first", "second"])
        self.assertEqual(spoken, played)
        self.assertCountEqual(discarded, played)

    def test_partial_failure_reports_spoken_text(self):
        def clauses():
            yield "Hello."
            raise RuntimeError("connection lost")

        with self.assertRaises(SpeechPipelineError) as caught:
            run_speech_pipeline(clauses(), str, lambda _: None, lambda _: None,
                                threading.Event())
        self.assertEqual(caught.exception.spoken, ["Hello."])

    def test_playback_failure_releases_prepared_files(self):
        prepared, discarded = [], []

        def prepare(text):
            prepared.append(text)
            return text

        def fail(_):
            raise RuntimeError("speaker disconnected")

        with self.assertRaises(SpeechPipelineError):
            run_speech_pipeline(iter(["one", "two", "three"]), prepare, fail,
                                discarded.append, threading.Event())
        self.assertCountEqual(prepared, discarded)

    def test_cancellation_releases_queued_audio(self):
        cancelled = threading.Event()
        prepared, discarded = [], []

        def prepare(text):
            prepared.append(text)
            return text

        spoken = run_speech_pipeline(iter(["one", "two", "three"]), prepare,
                                     lambda _: cancelled.set(), discarded.append,
                                     cancelled)
        self.assertEqual(spoken, ["one"])
        self.assertCountEqual(prepared, discarded)

    def test_cancelled_pipeline_does_not_start_generation(self):
        cancelled = threading.Event()
        cancelled.set()

        class Source:
            started = False
            closed = False

            def __iter__(self):
                return self

            def __next__(self):
                self.started = True
                return "A paid request would start here"

            def close(self):
                self.closed = True

        source = Source()
        spoken = run_speech_pipeline(source, str, lambda _: None, lambda _: None, cancelled)
        self.assertEqual(spoken, [])
        self.assertFalse(source.started)
        self.assertTrue(source.closed)

    def test_source_close_failure_cannot_strand_consumer(self):
        cancelled, finished = threading.Event(), threading.Event()
        errors = []

        class Source:
            def __iter__(self):
                return iter(["Hello."])

            def close(self):
                raise RuntimeError("failed to close connection")

        def run():
            try:
                run_speech_pipeline(Source(), str, lambda _: None, lambda _: None, cancelled)
            except SpeechPipelineError as exc:
                errors.append(exc)
            finally:
                finished.set()

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        ended = finished.wait(1)
        cancelled.set()
        worker.join(1)
        self.assertTrue(ended, "A cleanup error left playback waiting forever")
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].spoken, ["Hello."])
        self.assertIn("failed to close", str(errors[0]))

    def test_late_synthesis_after_cancellation_discards_its_resource(self):
        cancelled = threading.Event()
        second_started, release_prepare, second_discarded = (threading.Event() for _ in range(3))
        discarded = []

        def prepare(text):
            if text == "second":
                second_started.set()
                release_prepare.wait(2)
            return text

        def play(_):
            self.assertTrue(second_started.wait(1))
            cancelled.set()

        def discard(text):
            discarded.append(text)
            if text == "second":
                second_discarded.set()

        try:
            spoken = run_speech_pipeline(iter(["first", "second"]), prepare, play, discard, cancelled)
            self.assertEqual(spoken, ["first"])
        finally:
            release_prepare.set()
        self.assertTrue(second_discarded.wait(1))
        self.assertCountEqual(discarded, ["first", "second"])

    def test_generation_cannot_run_unbounded_ahead_of_playback(self):
        release_play, play_started, too_far_ahead = (threading.Event() for _ in range(3))
        cancelled = threading.Event()

        def source():
            for index in range(100):
                if index >= 6:
                    too_far_ahead.set()
                yield str(index)

        def play(_):
            play_started.set()
            release_play.wait(2)

        worker = threading.Thread(target=run_speech_pipeline,
                                  args=(source(), str, play, lambda _: None, cancelled),
                                  kwargs={"max_pending": 1}, daemon=True)
        worker.start()
        try:
            self.assertTrue(play_started.wait(1))
            self.assertFalse(too_far_ahead.wait(0.1), "Backlog grew despite blocked playback")
        finally:
            cancelled.set()
            release_play.set()
            worker.join(1)
        self.assertFalse(worker.is_alive())

    def test_filler_plays_immediately_while_generation_and_synthesis_prepare_in_background(self):
        filler_started = threading.Event()
        release_filler = threading.Event()
        synthesis_during_filler = threading.Event()
        played = []
        discarded = []

        filler_item = {"text": "Hmm, let me consider...", "path": "mock_filler.wav"}

        def prepare(text):
            # Assert filler has started while synthesis is running
            self.assertTrue(filler_started.wait(2.0))
            synthesis_during_filler.set()
            return f"prep_{text}"

        def play_filler(f):
            played.append(f["text"])
            filler_started.set()
            # Hold playback to ensure background synthesis runs concurrently
            self.assertTrue(release_filler.wait(2.0), "Filler playback timeout")

        def play(p):
            played.append(p)

        def clauses():
            yield "First sentence."
            yield "Second sentence."

        results = []
        def target():
            results.append(run_speech_pipeline(
                clauses(),
                prepare=prepare,
                play=play,
                discard=discarded.append,
                cancelled=threading.Event(),
                filler=filler_item,
                play_filler=play_filler,
            ))

        t = threading.Thread(target=target)
        t.start()

        self.assertTrue(filler_started.wait(1.0), "Filler did not start immediately")
        self.assertTrue(synthesis_during_filler.wait(1.0), "Synthesis did not run concurrently during filler")
        self.assertEqual(played, ["Hmm, let me consider..."])

        # Release filler playback now that background synthesis is confirmed
        release_filler.set()
        t.join(2.0)
        self.assertFalse(t.is_alive())

        self.assertEqual(played, ["Hmm, let me consider...", "prep_First sentence.", "prep_Second sentence."])
        self.assertEqual(results[0], ["First sentence.", "Second sentence."])  # Filler not in spoken response
        self.assertEqual(discarded, ["prep_First sentence.", "prep_Second sentence."])

    def test_filler_cancellation_stops_before_response_playback(self):
        cancelled = threading.Event()
        played = []

        def play_filler(f):
            played.append(f["text"])
            cancelled.set()

        spoken = run_speech_pipeline(
            iter(["One", "Two"]),
            prepare=str,
            play=played.append,
            discard=lambda _: None,
            cancelled=cancelled,
            filler={"text": "Aha!"},
            play_filler=play_filler,
        )
        self.assertEqual(played, ["Aha!"])
        self.assertEqual(spoken, [])

    def test_filler_playback_failure_raises_speech_pipeline_error(self):
        def failing_filler(_f):
            raise RuntimeError("Audio device lost during filler")

        with self.assertRaises(SpeechPipelineError) as ctx:
            run_speech_pipeline(
                iter(["One"]),
                prepare=str,
                play=lambda _: None,
                discard=lambda _: None,
                cancelled=threading.Event(),
                filler={"text": "By Gryffindor's sword..."},
                play_filler=failing_filler,
            )
        self.assertEqual(ctx.exception.stage, "playback")
        self.assertEqual(ctx.exception.spoken, [])

