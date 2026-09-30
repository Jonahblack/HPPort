"""Bounded generation -> synthesis -> playback pipeline.

Only one synthesizer runs at a time. It can prepare the next phrase while the
current phrase plays, without holding up the model's network stream.
"""

import queue
import threading


class SpeechPipelineError(RuntimeError):
    def __init__(self, cause, spoken, stage="generation"):
        super().__init__(str(cause))
        self.spoken = spoken
        self.stage = stage
        self.__cause__ = cause


def run_speech_pipeline(clauses, prepare, play, discard, cancelled, max_pending=2):
    """Play prepared clauses in order; discard every unplayed resource on exit.

An exception carries the already-spoken clauses so a caller can avoid repeating
an answer through a fallback model after a partially successful stream.
"""
    pending = queue.Queue(maxsize=max(1, max_pending))
    ready = queue.Queue(maxsize=max(1, max_pending))
    done = object()
    stopped = threading.Event()
    spoken = []

    def active():
        return not stopped.is_set() and not cancelled.is_set()

    def put(target, item):
        while active():
            try:
                target.put(item, timeout=0.05)
                return True
            except queue.Full:
                pass
        return False

    def take(source):
        while active():
            try:
                return source.get(timeout=0.05)
            except queue.Empty:
                pass
        return done

    def generate():
        try:
            if not active():
                return
            for clause in clauses:
                if clause and clause.strip() and not put(pending, clause.strip()):
                    break
        except Exception as exc:
            put(pending, SpeechPipelineError(exc, [], "generation"))
        finally:
            close = getattr(clauses, "close", None)
            try:
                if close:
                    close()
            except Exception as exc:
                put(pending, SpeechPipelineError(exc, [], "generation"))
            put(pending, done)

    def synthesize():
        try:
            while active():
                clause = take(pending)
                if clause is done:
                    break
                if isinstance(clause, Exception):
                    put(ready, clause)
                    break
                prepared = prepare(clause)
                if not put(ready, (clause, prepared)):
                    discard(prepared)
                    break
        except Exception as exc:
            put(ready, SpeechPipelineError(exc, [], "synthesis"))
        finally:
            put(ready, done)

    workers = [threading.Thread(target=generate, daemon=True, name="portrait-generate"),
               threading.Thread(target=synthesize, daemon=True, name="portrait-synthesize")]
    for worker in workers:
        worker.start()
    try:
        while active():
            item = take(ready)
            if item is done:
                break
            if isinstance(item, Exception):
                raise item
            clause, prepared = item
            try:
                try:
                    play(prepared)
                except Exception as exc:
                    raise SpeechPipelineError(exc, spoken.copy(), "playback") from exc
                spoken.append(clause)
            finally:
                discard(prepared)
    except Exception as exc:
        raise SpeechPipelineError(exc, spoken.copy(), getattr(exc, "stage", "playback")) from exc
    finally:
        stopped.set()
        for worker in workers:
            worker.join(timeout=0.2)
        while True:
            try:
                item = ready.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, tuple):
                discard(item[1])
    return spoken
