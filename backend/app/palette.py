"""بارگذاری و پرس‌وجوی کاتالوگ رنگ."""

from __future__ import annotations

import json
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "data" / "palette.json"
_data: dict | None = None


def _load() -> dict:
    global _data
    if _data is None:
        _data = json.loads(_PATH.read_text(encoding="utf-8"))
    return _data


def catalog() -> dict:
    """کل کاتالوگ: خانواده‌ها، مجموعه‌ها، محصولات و رنگ‌ها."""
    d = _load()
    return {
        "families": d["families"],
        "collections": d["collections"],
        "products": d["products"],
        "colors": d["colors"],
    }


def colors() -> list[dict]:
    return _load()["colors"]


def find_color(code: str) -> dict | None:
    code = code.strip().lower()
    for c in colors():
        if str(c["code"]).lower() == code:
            return c
    return None


def product(product_id: str) -> dict | None:
    for p in _load()["products"]:
        if p["id"] == product_id:
            return p
    return None


def coverage_for(code: str, default: float = 9.0) -> float:
    c = find_color(code)
    if not c:
        return default
    p = product(c.get("product", ""))
    return float(p["coverage_m2_per_l"]) if p else default
