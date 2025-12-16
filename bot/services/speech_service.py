from __future__ import annotations

import subprocess
import unicodedata
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Tuple

from faster_whisper import WhisperModel
from rapidfuzz import fuzz


class SpeechService:
    def __init__(self, model_name: str):
        self.model = WhisperModel(model_name, compute_type="int8")

    @staticmethod
    def normalize_text(text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text.lower())
        return " ".join(normalized.split())

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
            segments, _ = self.model.transcribe(str(wav_path), beam_size=1)
            transcript = " ".join(segment.text.strip() for segment in segments).strip()
            return transcript

    def evaluate(self, audio_bytes: bytes, expected_text: str, threshold: int = 85) -> Tuple[str, int, bool]:
        transcript = self.transcribe(audio_bytes)
        reference = self.normalize_text(expected_text)
        actual = self.normalize_text(transcript)
        score = fuzz.ratio(reference, actual)
        return transcript, score, score >= threshold
