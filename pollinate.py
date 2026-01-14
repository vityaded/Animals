from __future__ import annotations

"""
Pollinations icon generator for CSV content (hard-coded settings).

What it does
- Reads one or many CSV files from INPUT_DIR (expects at least columns: id,text).
- For each row, generates a 128x128 PNG icon via https://image.pollinations.ai/prompt
- Skips rows that already have a valid PNG.
- If a PNG is missing/invalid, retries generation:
    * tries TRIES_PER_CONCEPT times per concept variant
    * tries multiple concept variants (safe disambiguations) for ambiguous / abstract words
- Runs multiple passes until every row has a valid PNG (MAX_PASSES=0).

Designed for your archive layout:
- CSVs: ./levels/level1.csv, ./levels/level2.csv, ./levels/level3.csv
- Output folders: ./level1/, ./level2/, ./level3/ (same as CSV stem)

Install:
  python3 -m pip install -U pip
  python3 -m pip install -U pillow requests

Run:
  python3 pollinate.py
"""

import csv
import hashlib
import json
import re
import sys
import time
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image, UnidentifiedImageError


# ----------------------------
# HARD-CODED SETTINGS
# ----------------------------
INPUT_DIR = Path("content/levels")       # where your CSVs are
OUTPUT_ROOT = Path("assets/unit_icons")  # where icons should be saved

BASE_URL = "https://image.pollinations.ai/prompt"
MODEL = "flux"
WIDTH = 128
HEIGHT = 128

SAFE = True
NOLOGO = True
PRIVATE = True
REFERRER = "animals_reading_bot"

REQUEST_DELAY_SECONDS = 30.0   # strict: 30 seconds between Pollinations requests (including retries)
TIMEOUT_SECONDS = 120

TRIES_PER_CONCEPT = 2          # EXACTLY 2 tries per concept variant
MIN_BYTES = 256                # reject obviously broken responses

WRITE_IMAGE_COLUMN = True      # update CSV "image" column to point to generated PNG path
MAX_PASSES = 0                 # 0 = loop until all valid, else stop after N passes
# ----------------------------

STYLE_ANCHOR = (
    "Cute kid-friendly flat vector icon, simple sticker style, clean bold outline, "
    "minimal details, centered composition, white background, soft shadow, "
    "high contrast, consistent style, no text, no letters, no watermark."
)

STOPWORDS = {
    "a", "an", "the", "i", "you", "he", "she", "we", "they", "it",
    "see", "sees", "saw", "have", "has", "had", "like", "likes", "liked",
    "am", "is", "are", "was", "were", "be",
    "on", "in", "at", "to", "from", "with", "of", "and", "or",
    "my", "your", "his", "her", "our", "their",
}

# Concept disambiguation / visualization helpers.
# IMPORTANT: order matters (first variant is tried first).
SAFE_SYNONYMS: dict[str, list[str]] = {
    # ambiguous short words
    "cap":   ["baseball cap (hat)", "hat", "headwear"],
    "bat":   ["bat (animal, flying mammal)", "baseball bat (sports)", "cricket bat (sports)"],
    "can":   ["tin can (metal container)", "soda can (drink)", "trash can (bin)"],
    "ham":   ["ham slice on plate (food)", "ham sandwich (food)", "cooked ham (food)"],
    "cup":   ["drinking cup (for water)", "coffee mug", "teacup"],
    "nut":   ["peanut (food)", "hazelnut (food)", "mixed nuts (food)"],
    "ring":  ["gold ring jewelry", "ringing bell (bell icon)", "toy ring (kids toy)"],
    "dot":   ["single dot on paper", "polka dot pattern (one dot)"],

    # verbs / abstract / function words that are hard to picture
    "get":   ["hand receiving a gift box", "hand picking up an object", "open hands holding a present"],
    "big":   ["big elephant (large animal)", "large balloon next to small balloon (size comparison)"],
    "best":  ["gold trophy with star", "gold medal with ribbon (no text)"],
    "melt":  ["ice cream melting", "ice cube melting into water"],
    "wind":  ["wind gust blowing a leaf", "windy cloud blowing air"],
    "wink":  ["smiling face winking (simple cartoon)", "winking emoji-style face (no text)"],
    "safe":  ["shield icon", "padlock icon"],
    "time":  ["clock icon", "hourglass icon"],
    "hide":  ["object hiding behind a curtain", "box with lid partly closed (hiding)"],
    "out":   ["open door with arrow pointing outward (no letters)", "arrow leaving a box (out)"],
    "shout": ["megaphone with sound waves", "loudspeaker with sound waves"],
    "loud":  ["speaker with big sound waves", "megaphone with strong sound waves"],
    "quit":  ["hand pressing stop button icon", "exit door icon with arrow (no letters)"],
    "flip":  ["flipping pancake in a pan", "coin flipping in the air"],

    # body/violence-adjacent words that sometimes get false-blocked in safe mode
    "lip":   ["lip balm stick (cosmetic)", "smiling mouth lips (simple cartoon)", "edge (lip) of a cup"],
    "chin":  ["cartoon face showing chin (friendly)", "beard under chin (cartoon)"],
    "chop":  ["chopping vegetables on a cutting board (kitchen)", "chopped carrot slices on board"],

    # function words (use “visual hint” rather than literal word)
    "this":  ["pointing finger at a nearby object", "arrow pointing to a nearby item (no letters)"],
    "that":  ["pointing finger toward a far object", "arrow pointing to a far item (no letters)"],
    "when":  ["calendar next to a clock", "clock over calendar page"],
    "what":  ["magnifying glass over a mystery object", "open box with a surprise glow (no text)"],
    "which": ["two objects with a check mark on one", "two items and a selection highlight (no text)"],

    # qu/wh cluster words (make them concrete)
    "quack": ["duck (animal)", "rubber duck toy"],
    "quick": ["fast cheetah running", "running rabbit (fast)"],
    "quilt": ["patchwork quilt blanket", "folded blanket quilt"],
    "whip":  ["whipped cream swirl on dessert", "kitchen whisk tool"],
}

AMBIGUOUS_WORDS = set(SAFE_SYNONYMS.keys())


def stable_seed(s: str) -> int:
    h = hashlib.sha256(s.encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def pick_key_concept(text: str) -> str:
    tokens = re.findall(r"[A-Za-z']+", text.lower())
    for tok in reversed(tokens):
        if tok not in STOPWORDS:
            return tok
    return (text.strip() or "icon")[:40]


def is_ambiguous(concept: str) -> bool:
    return concept in AMBIGUOUS_WORDS or len(concept) <= 3


def concept_variants(original_text: str) -> list[str]:
    c = pick_key_concept(original_text).strip().lower()

    if c in SAFE_SYNONYMS:
        variants = SAFE_SYNONYMS[c][:]
    else:
        variants = [c]
        if len(c) <= 3:
            variants.append(f"{c} (everyday object)")
            variants.append(f"{c} (simple icon)")

    seen: set[str] = set()
    out: list[str] = []
    for v in variants:
        v2 = v.strip()
        if v2 and v2 not in seen:
            out.append(v2)
            seen.add(v2)
    return out


def build_prompt(original_text: str, concept: str) -> str:
    disambig = ""
    if is_ambiguous(pick_key_concept(original_text).lower()):
        disambig = (
            "Important: depict ONLY the most obvious, common, everyday meaning for children. "
            "Avoid any adult/suggestive interpretation. "
        )

    safety = (
        "Family-friendly. Fully clothed characters if any. "
        "No nudity, no sexual content, no violence, no weapons, no blood. "
        "No text, no letters, no watermark."
    )

    return (
        f"{STYLE_ANCHOR} "
        f"{disambig}"
        f"Draw ONE clear icon of: {concept}. "
        f"Make it instantly recognizable for children. "
        f"Context (do NOT write it): '{original_text.strip()}'. "
        f"{safety}"
    )


def image_url(prompt: str) -> str:
    return f"{BASE_URL.rstrip('/')}/{quote(prompt, safe='')}"


def atomic_write_bytes(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def try_parse_json_bytes(b: bytes):
    try:
        return json.loads(b.decode("utf-8", errors="strict"))
    except Exception:
        return None


def is_valid_png(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        data = path.read_bytes()
        if len(data) < MIN_BYTES:
            return False
        with Image.open(BytesIO(data)) as im:
            im.verify()
        with Image.open(BytesIO(data)) as im2:
            w, h = im2.size
            return (w == WIDTH and h == HEIGHT)
    except Exception:
        return False


def save_debug_response(out_file: Path, body: bytes, suffix: str) -> Path:
    dbg = out_file.with_suffix(out_file.suffix + suffix)
    atomic_write_bytes(dbg, body)
    return dbg


def is_nsfw_safe_mode_block(status_code: int, body_bytes: bytes) -> bool:
    js = try_parse_json_bytes(body_bytes)
    if isinstance(js, dict):
        msg = str(js.get("message") or "").lower()
        safe = js.get("requestParameters", {}).get("safe")
        if "nsfw" in msg and safe is True:
            return True
    txt = body_bytes[:2000].decode("utf-8", errors="ignore").lower()
    return ("nsfw content detected" in txt) and ("safe mode" in txt or "safe" in txt)


def response_to_png_bytes(image_bytes: bytes) -> bytes:
    with Image.open(BytesIO(image_bytes)) as im:
        im = im.convert("RGBA")
        buf = BytesIO()
        im.save(buf, format="PNG", optimize=True)
        return buf.getvalue()


class RateLimiter:
    def __init__(self, min_interval_s: float):
        self.min_interval_s = float(min_interval_s)
        self._last_ts: float | None = None

    def wait(self):
        if self._last_ts is None:
            return
        elapsed = time.time() - self._last_ts
        need = self.min_interval_s - elapsed
        if need > 0:
            time.sleep(need)

    def mark(self):
        self._last_ts = time.time()


def read_csv_rows(p: Path) -> tuple[list[dict], list[str]]:
    with p.open("r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        if not r.fieldnames:
            raise ValueError(f"{p}: empty CSV/no header")
        need = {"id", "text"}
        if not need.issubset(set(r.fieldnames)):
            raise ValueError(f"{p}: expected columns id,text (found: {r.fieldnames})")
        rows = list(r)
        fieldnames = list(r.fieldnames)
    return rows, fieldnames


def write_csv_rows(p: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def iter_csv_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    return sorted([p for p in input_path.glob("*.csv") if p.is_file()])


def main() -> int:
    if not INPUT_DIR.exists():
        print(f"ERROR: input path does not exist: {INPUT_DIR}", file=sys.stderr)
        return 2

    csv_files = iter_csv_files(INPUT_DIR)
    if not csv_files:
        print(f"ERROR: no CSV files found in: {INPUT_DIR}", file=sys.stderr)
        return 2

    session = requests.Session()
    session.headers.update({"User-Agent": "AnimalsReadingBot/1.0"})
    limiter = RateLimiter(REQUEST_DELAY_SECONDS)

    csv_data: list[tuple[Path, list[dict], list[str]]] = []
    for csv_path in csv_files:
        rows, fieldnames = read_csv_rows(csv_path)
        if WRITE_IMAGE_COLUMN and "image" not in fieldnames:
            fieldnames.append("image")
        csv_data.append((csv_path, rows, fieldnames))

    pass_no = 0
    while True:
        pass_no += 1
        total = 0
        skipped_valid = 0
        generated = 0
        print(f"\n=== PASS {pass_no} ===")

        for csv_path, rows, fieldnames in csv_data:
            out_dir = OUTPUT_ROOT / csv_path.stem
            out_dir.mkdir(parents=True, exist_ok=True)

            changed_csv = False

            for row in rows:
                unit_id = (row.get("id") or "").strip()
                text = (row.get("text") or "").strip()
                if not unit_id or not text:
                    continue

                total += 1
                out_file = out_dir / f"{unit_id}.png"
                rel_path = str(out_file)

                if is_valid_png(out_file):
                    skipped_valid += 1
                    if WRITE_IMAGE_COLUMN and (row.get("image") or "").strip() != rel_path:
                        row["image"] = rel_path
                        changed_csv = True
                    continue

                if out_file.exists():
                    try:
                        out_file.unlink()
                    except Exception:
                        pass

                concepts = concept_variants(text)

                ok = False
                last_error: str | None = None

                for concept in concepts:
                    for t in range(1, TRIES_PER_CONCEPT + 1):
                        prompt = build_prompt(text, concept)
                        url = image_url(prompt)

                        # critical fix: vary seed per retry so you don't repeat the same blocked result
                        seed = stable_seed(f"{csv_path.stem}:{unit_id}:{text}:{concept}:{t}:pass{pass_no}")

                        params = {
                            "model": MODEL,
                            "width": WIDTH,
                            "height": HEIGHT,
                            "seed": seed,
                            "safe": str(SAFE).lower(),
                            "nologo": str(NOLOGO).lower(),
                            "private": str(PRIVATE).lower(),
                            "referrer": REFERRER,
                        }

                        try:
                            limiter.wait()
                            limiter.mark()

                            r = session.get(url, params=params, timeout=TIMEOUT_SECONDS)
                            body = r.content or b""
                            ctype = (r.headers.get("Content-Type") or "").lower()

                            if r.status_code == 429:
                                ra = r.headers.get("Retry-After")
                                try:
                                    wait_s = float(ra) if ra else REQUEST_DELAY_SECONDS
                                except Exception:
                                    wait_s = REQUEST_DELAY_SECONDS
                                print(f"[429] {csv_path.stem}:{unit_id} concept='{concept}' try {t}/{TRIES_PER_CONCEPT} -> sleep {wait_s}s")
                                time.sleep(wait_s)
                                last_error = "429"
                                continue

                            if len(body) < MIN_BYTES:
                                dbg = save_debug_response(out_file, body, ".too_small.bin")
                                raise RuntimeError(f"Too small response ({len(body)} bytes, debug: {dbg.name})")

                            if not ctype.startswith("image/"):
                                if SAFE and is_nsfw_safe_mode_block(r.status_code, body):
                                    dbg = save_debug_response(out_file, body[:20000], ".nsfw_block.json")
                                    print(f"[NSFW-BLOCK] {csv_path.stem}:{unit_id} concept='{concept}' try {t}/{TRIES_PER_CONCEPT} (debug: {dbg.name})")
                                    last_error = "nsfw_block"
                                    continue

                                suffix = ".bad.json" if "json" in ctype else ".bad.txt"
                                dbg = save_debug_response(out_file, body[:50000], suffix)
                                raise RuntimeError(f"Non-image response: HTTP {r.status_code}, type={ctype!r} (debug: {dbg.name})")

                            try:
                                png_bytes = response_to_png_bytes(body)
                            except UnidentifiedImageError:
                                dbg = save_debug_response(out_file, body[:50000], ".bad_image.bin")
                                raise RuntimeError(f"Undecodable image bytes (debug: {dbg.name})")

                            atomic_write_bytes(out_file, png_bytes)

                            if is_valid_png(out_file):
                                ok = True
                                # cleanup leftover debug markers after success
                                for suffix in [".nsfw_block.json", ".bad.json", ".bad.txt", ".too_small.bin", ".bad_image.bin"]:
                                    dbg = out_file.with_suffix(out_file.suffix + suffix)
                                    if dbg.exists():
                                        try:
                                            dbg.unlink()
                                        except Exception:
                                            pass
                                break

                            try:
                                out_file.unlink(missing_ok=True)
                            except Exception:
                                pass
                            raise RuntimeError("Saved PNG failed validation")

                        except Exception as e:
                            last_error = str(e)
                            backoff = min(30.0 * t, 180.0)
                            print(f"[ERR] {csv_path.stem}:{unit_id} concept='{concept}' try {t}/{TRIES_PER_CONCEPT} -> {e} (sleep {backoff}s)")
                            time.sleep(backoff)

                    if ok:
                        break

                if ok:
                    generated += 1
                    if WRITE_IMAGE_COLUMN:
                        row["image"] = rel_path
                        changed_csv = True
                    print(f"[OK]  {csv_path.stem}:{unit_id} -> {out_file.name}")
                else:
                    print(f"[FAIL] {csv_path.stem}:{unit_id} (last_error={last_error})")

            if WRITE_IMAGE_COLUMN and changed_csv:
                write_csv_rows(csv_path, rows, fieldnames)
                print(f"Updated CSV: {csv_path}")

        print(f"\nPASS {pass_no} summary: total={total} skipped_valid={skipped_valid} generated={generated}")

        all_ok = True
        for csv_path, rows, _fieldnames in csv_data:
            out_dir = OUTPUT_ROOT / csv_path.stem
            for row in rows:
                unit_id = (row.get("id") or "").strip()
                text = (row.get("text") or "").strip()
                if not unit_id or not text:
                    continue
                out_file = out_dir / f"{unit_id}.png"
                if not is_valid_png(out_file):
                    all_ok = False
                    break
            if not all_ok:
                break

        if all_ok:
            print("\nALL IMAGES ARE PRESENT AND VALID. Exiting.")
            return 0

        if MAX_PASSES > 0 and pass_no >= MAX_PASSES:
            print("\nReached MAX_PASSES; exiting with non-zero status.")
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
