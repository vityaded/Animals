from __future__ import annotations

import csv
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


@dataclass
class ContentItem:
    id: str
    text: str
    sound: Optional[str] = None
    image: Optional[str] = None
    sublevel: Optional[str] = None


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

    def available_levels(self) -> list[int]:
        levels: list[int] = []
        for path in self.levels_dir.glob("level*.csv"):
            name = path.stem.replace("level", "")
            if name.isdigit():
                levels.append(int(name))
        return sorted(set(levels))

    def get_level_items(self, level: int) -> List[ContentItem]:
        path = self._level_path(level)
        if not path.exists():
            raise FileNotFoundError(f"Контент рівня {level} відсутній за шляхом {path}")
        with open(path, "r", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            items: Iterable[ContentItem] = (
                ContentItem(
                    id=row.get("id", "").strip(),
                    text=row.get("text", "").strip(),
                    sound=row.get("sound") or None,
                    image=row.get("image") or None,
                    sublevel=row.get("sublevel") or None,
                )
                for row in reader
            )
            return [item for item in items if item.id and item.text]

    def get_item(self, level: int, content_id: str) -> ContentItem:
        items = self.get_level_items(level)
        for item in items:
            if item.id == content_id:
                return item
        raise KeyError(f"Content id {content_id} not found for level {level}")

    def list_items(self, level: int) -> list[ContentItem]:
        return self.get_level_items(level)

    def _load_progress_map(self, user_id: int, level: int, progress_path: Path) -> set[str]:
        if not progress_path.exists():
            return set()
        try:
            data = json.loads(progress_path.read_text(encoding="utf-8"))
            return set(data.get(str(user_id), {}).get(str(level), []))
        except Exception:
            return set()

    def _save_progress_map(self, user_id: int, level: int, passed: set[str], progress_path: Path) -> None:
        progress_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads(progress_path.read_text(encoding="utf-8")) if progress_path.exists() else {}
        except Exception:
            data = {}
        data.setdefault(str(user_id), {})[str(level)] = list(passed)
        progress_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def build_deck(self, user_id: int, level: int, size: int = 10, passed_ids: Optional[set[str]] = None) -> list[str]:
        items = self.get_level_items(level)
        if not items:
            return []

        # Optional persisted list of passed items (local file fallback if DB not available).
        progress_path = Path("data/content_progress.json")
        if passed_ids is None:
            passed_ids = self._load_progress_map(user_id, level, progress_path)

        candidates = items
        if level == 1:
            mono = [i for i in items if (i.sublevel or "").lower() == "mono"]
            di = [i for i in items if (i.sublevel or "").lower() == "di"]
            mono_unpassed = [i for i in mono if i.id not in passed_ids]
            if mono_unpassed:
                candidates = mono_unpassed
            else:
                di_unpassed = [i for i in di if i.id not in passed_ids]
                candidates = di_unpassed or di or mono
        else:
            unpassed = [i for i in items if i.id not in passed_ids]
            candidates = unpassed or items

        random.shuffle(candidates)
        deck = [item.id for item in candidates[:size]]
        return deck

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
