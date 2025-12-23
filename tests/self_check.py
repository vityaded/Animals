from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from bot.services.pet_service import PetService


def main() -> None:
    pet_dir = Path("assets/pets/panda")
    happy_assets = list(pet_dir.glob("happy.*"))
    if not happy_assets:
        print("SKIP: no happy asset for panda")
        return
    path = PetService.asset_path("assets/pets", "panda", "happy")
    if not path:
        raise SystemExit("PetService.asset_path did not find happy asset for panda")
    print(f"OK: {path}")


if __name__ == "__main__":
    main()
