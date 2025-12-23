from __future__ import annotations

import hashlib
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class TTSUnavailableError(RuntimeError):
    """Raised when TTS backend is unavailable."""


class TTSService:
    def __init__(self, cache_dir: Path | str = "data/tts_cache") -> None:
        self.cache_dir = Path(cache_dir)

    def _hash_text(self, text: str) -> str:
        normalized = " ".join(text.split()).strip().lower()
        return hashlib.sha1(normalized.encode("utf-8")).hexdigest()

    def ensure_audio(self, text: str) -> Path:
        if not text.strip():
            raise ValueError("Text is empty, cannot generate audio")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{self._hash_text(text)}.wav"
        path = self.cache_dir / filename
        if path.exists():
            return path
        try:
            subprocess.run(
                [
                    "espeak-ng",
                    "-v",
                    "en",
                    "-s",
                    "150",
                    "-w",
                    str(path),
                    text,
                ],
                check=True,
                capture_output=True,
            )
        except FileNotFoundError as exc:  # noqa: BLE001
            logger.error("espeak-ng is not installed. Please install espeak-ng to enable TTS.")
            if path.exists():
                path.unlink(missing_ok=True)
            raise TTSUnavailableError("espeak-ng is not installed") from exc
        except subprocess.CalledProcessError as exc:  # noqa: BLE001
            logger.error("Failed to generate TTS: %s", exc.stderr.decode("utf-8", errors="ignore"))
            if path.exists():
                path.unlink(missing_ok=True)
            raise TTSUnavailableError("Failed to generate TTS audio") from exc
        return path
