"""Small speech chunks shared by cloud and local text generators."""

import re
from typing import Iterable, Iterator


_BOUNDARY = re.compile(r'[.!?]+["\u201d\u2019\')]*(?=\s)|\n|[,;:](?=\s)')
_WORD = re.compile(r"\S+\s+")


def speech_clauses(tokens: Iterable[str], max_words: int = 12) -> Iterator[str]:
    """Yield phrases in order, without waiting for the entire response.

    Keep short introductory commas with the following phrase. Bound long runs
    without punctuation at complete words; never split a word at a token edge.
    The input iterator is closed when playback cancels the consuming generator.
    """
    source = iter(tokens)
    buffer = ""
    word_limit = min(7, max(1, max_words))
    try:
        for token in source:
            if not token:
                continue
            buffer += token
            while buffer:
                end = None
                for boundary in _BOUNDARY.finditer(buffer):
                    if boundary.group()[0] in ",;:" and len(buffer[:boundary.end()].split()) < 3:
                        continue
                    end = boundary.end()
                    break
                words = list(_WORD.finditer(buffer))
                if len(words) >= word_limit:
                    word_end = words[word_limit - 1].end()
                    end = min(end, word_end) if end is not None else word_end
                if end is None:
                    break
                clause, buffer = buffer[:end].strip(), buffer[end:].lstrip()
                if clause:
                    # Start speaking early, then use longer phrases for prosody.
                    word_limit = max(1, max_words)
                    yield clause
        if buffer.strip():
            yield buffer.strip()
    finally:
        close = getattr(source, "close", None)
        if close:
            close()
