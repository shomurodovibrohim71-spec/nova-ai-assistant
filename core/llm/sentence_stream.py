"""Buffer streamed text deltas and emit complete sentences for TTS."""
from __future__ import annotations

import re

# Common abbreviations whose trailing period should NOT end a sentence.
_ABBREV = {"mr", "mrs", "ms", "dr", "st", "sr", "jr", "vs", "etc", "e.g", "i.e"}

_END_PUNCT = re.compile(r"([.!?…])(\s+|$)")


class SentenceBuffer:
    """Feed deltas via `feed`; pull completed sentences via `flush_sentences`."""

    def __init__(self) -> None:
        self._buf: str = ""

    def feed(self, delta: str) -> list[str]:
        self._buf += delta
        return self._extract()

    def finalize(self) -> list[str]:
        out: list[str] = []
        out.extend(self._extract())
        tail = self._buf.strip()
        if tail:
            out.append(tail)
            self._buf = ""
        return out

    def _extract(self) -> list[str]:
        sentences: list[str] = []
        while True:
            m = _END_PUNCT.search(self._buf)
            if not m:
                break
            end = m.end()
            candidate = self._buf[:end].strip()
            # abbreviation guard: e.g. "Mr. Smith"
            preceding = candidate[:-1].rsplit(maxsplit=1)
            last_word = preceding[-1].lower().rstrip(".") if preceding else ""
            if last_word in _ABBREV and m.group(1) == ".":
                # not a sentence boundary; advance past this match and keep buffering
                # easiest: continue search after this match by trimming buffer state via slicing trick
                head, tail = self._buf[:end], self._buf[end:]
                self._buf = head + tail  # no-op, we'll instead break to avoid infinite loop
                # walk the regex past this point manually
                _next = _END_PUNCT.search(self._buf, end)
                if _next is None:
                    break
                m = _next
                end = m.end()
                candidate = self._buf[:end].strip()
            sentences.append(candidate)
            self._buf = self._buf[end:]
        return sentences
