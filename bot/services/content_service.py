from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


@dataclass
class LevelItem:
    prompt: str
    answer: str
    hint: Optional[str] = None


@dataclass
class PetAsset:
    path: Path | None
    is_placeholder: bool
    message: str = ""


class ContentService:
    def __init__(self, levels_dir: Path, assets_dir: Path | None = None):
        self.levels_dir = Path(levels_dir)
        self.assets_dir = Path(assets_dir) if assets_dir else Path("assets/pets/cat")

    def _level_path(self, level: int) -> Path:
        return self.levels_dir / f"level{level}.csv"

    def _asset_path(self, state: str) -> Path:
        return self.assets_dir / f"{state}.png"

    def get_level_items(self, level: int) -> List[LevelItem]:
        path = self._level_path(level)
        if not path.exists():
            raise FileNotFoundError(f"Контент рівня {level} відсутній за шляхом {path}")
        with open(path, "r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            items: Iterable[LevelItem] = (
                LevelItem(row.get("prompt", ""), row.get("answer", ""), row.get("hint"))
                for row in reader
            )
            return [item for item in items if item.prompt and item.answer]

    def resolve_pet_asset(self, state: str) -> PetAsset:
        """Return the asset path or a placeholder description for the requested pet state.

        The method never raises if an image is missing; instead it falls back to a
        ``.png.placeholder`` file or a descriptive message.
        """

        target_path = self._asset_path(state)
        placeholder_path = target_path.with_suffix(target_path.suffix + ".placeholder")

        if target_path.exists():
            return PetAsset(path=target_path, is_placeholder=False, message="")

        if placeholder_path.exists():
            note = placeholder_path.read_text(encoding="utf-8").strip()
            message = note or f"image missing: {target_path.name} (placeholder present)"
            return PetAsset(path=placeholder_path, is_placeholder=True, message=message)

        return PetAsset(path=None, is_placeholder=True, message=f"image missing: {target_path.name}")
