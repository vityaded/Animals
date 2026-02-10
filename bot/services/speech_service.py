from __future__ import annotations

import asyncio
import re
import subprocess
import unicodedata
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Tuple

from faster_whisper import WhisperModel
from rapidfuzz import fuzz


class SpeechService:
    def __init__(self, model_name: str, load_model: bool = True):
        self.model = WhisperModel(model_name, compute_type="int8") if load_model else None

    @staticmethod
    def normalize_text(text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text.lower())
        normalized = re.sub(r"[^\w\s]", " ", normalized)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def transcribe(self, audio_bytes: bytes) -> str:
        with TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "input.ogg"
            wav_path = Path(tmp) / "converted.wav"
            input_path.write_bytes(audio_bytes)
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(input_path),
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    str(wav_path),
                ],
                check=True,
                capture_output=True,
            )
            if self.model is None:
                raise RuntimeError("Model is not loaded")
            segments, _ = self.model.transcribe(
                str(wav_path),
                beam_size=1,
                language="en",
                vad_filter=True,
            )
            transcript = " ".join(segment.text.strip() for segment in segments).strip()
            return transcript

    async def transcribe_async(self, audio_bytes: bytes) -> str:
        return await asyncio.to_thread(self.transcribe, audio_bytes)

    def evaluate(self, audio_bytes: bytes, expected_text: str, threshold: int = 80) -> Tuple[str, int, bool]:
        transcript = self.transcribe(audio_bytes)
        return self._evaluate_transcript(transcript, expected_text, threshold)

    async def evaluate_async(self, audio_bytes: bytes, expected_text: str, threshold: int = 80) -> Tuple[str, int, bool]:
        transcript = await self.transcribe_async(audio_bytes)
        return self._evaluate_transcript(transcript, expected_text, threshold)

    def _evaluate_transcript(self, transcript: str, expected_text: str, threshold: int) -> Tuple[str, int, bool]:
        reference_variants = [part.strip() for part in expected_text.split("||") if part.strip()]
        actual = self.normalize_text(transcript)
        scores: list[int] = []

        def effective_threshold(word_count: int) -> int:
            # Short prompts are harder for ASR; be more forgiving for 1–2 words.
            if word_count <= 0:
                return threshold
            if word_count <= 2:
                return max(55, threshold - 15)
            if word_count <= 4:
                return max(60, threshold - 8)
            return threshold

        def phonetic_key(text: str, loose: bool) -> str:
            # Phonetic-ish normalization: tolerate long/short vowels and close consonants.
            t = self.normalize_text(text)
            if not t:
                return ""
            out_words: list[str] = []
            for w in t.split():
                # common digraph/orthography reductions
                w = re.sub(r"ph", "f", w)
                w = re.sub(r"ght$", "t", w)
                w = re.sub(r"gh$", "", w)
                w = re.sub(r"kn", "n", w)
                w = re.sub(r"wr", "r", w)
                w = re.sub(r"wh", "w", w)
                w = re.sub(r"ck", "k", w)
                w = re.sub(r"qu", "kw", w)
                w = w.replace("x", "ks")
                # soft 'c' before e/i/y -> s, otherwise -> k
                w = re.sub(r"c(?=[eiy])", "s", w)
                w = w.replace("c", "k")
                # drop trailing silent 'e' in longer words (make vs mak)
                if len(w) > 3 and w.endswith("e"):
                    w = w[:-1]

                # vowel class mapping: a->A, e/i/y->E, o/u->O
                mapped: list[str] = []
                for ch in w:
                    if ch in "a":
                        mapped.append("A")
                    elif ch in "eiy":
                        mapped.append("E")
                    elif ch in "ou":
                        mapped.append("O")
                    elif ch in "aeiouy":
                        mapped.append("E")  # fallback (should not happen often)
                    else:
                        mapped.append(ch)

                w2 = "".join(mapped)

                if loose:
                    # close consonants (voicing) tolerance
                    w2 = re.sub(r"[bp]", "P", w2)
                    w2 = re.sub(r"[dt]", "T", w2)
                    w2 = re.sub(r"[gkq]", "K", w2)
                    w2 = re.sub(r"[vf]", "F", w2)
                    w2 = re.sub(r"[zs]", "S", w2)

                # collapse repeats (e.g., "EE" -> "E")
                collapsed: list[str] = []
                prev = ""
                for ch in w2:
                    if ch == prev:
                        continue
                    collapsed.append(ch)
                    prev = ch
                out_words.append("".join(collapsed))

            return " ".join(out_words)

        for ref in reference_variants:
            reference = self.normalize_text(ref)
            if not reference:
                continue

            # Baselines (current behavior)
            base = fuzz.token_set_ratio(reference, actual)
            tight = fuzz.ratio(reference, actual)
            partial = fuzz.partial_ratio(reference, actual)

            # Phonetic passes
            ref_ph = phonetic_key(reference, loose=False)
            act_ph = phonetic_key(actual, loose=False)
            phon = fuzz.token_set_ratio(ref_ph, act_ph) if ref_ph and act_ph else 0
            phon_tight = fuzz.ratio(ref_ph, act_ph) if ref_ph and act_ph else 0

            ref_ph_loose = phonetic_key(reference, loose=True)
            act_ph_loose = phonetic_key(actual, loose=True)
            phon_loose = (
                fuzz.token_set_ratio(ref_ph_loose, act_ph_loose) if ref_ph_loose and act_ph_loose else 0
            )

            scores.append(max(base, tight, partial, phon, phon_tight, phon_loose))
        max_score = max(scores) if scores else 0
        # Use the most permissive threshold among variants (based on their length).
        eff = threshold
        for ref in reference_variants:
            r = self.normalize_text(ref)
            if not r:
                continue
            eff = min(eff, effective_threshold(len(r.split())))
        return transcript, max_score, max_score >= eff
