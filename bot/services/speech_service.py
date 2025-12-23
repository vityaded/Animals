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
            segments, _ = self.model.transcribe(str(wav_path), beam_size=1)
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
        scores = []
        for ref in reference_variants:
            reference = self.normalize_text(ref)
            scores.append(fuzz.token_set_ratio(reference, actual))
        max_score = max(scores) if scores else 0
        return transcript, max_score, max_score >= threshold
