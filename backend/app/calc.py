"""محاسبه‌ی مقدار رنگ لازم برای یک پروژه."""

from __future__ import annotations

from dataclasses import dataclass

# اندازه‌ی ظرف‌های استاندارد رنگ (لیتر)
CAN_SIZES = [
    (20.0, "حلب ۲۰ لیتری"),
    (12.0, "حلب ۱۲ لیتری"),
    (4.0, "گالن ۴ لیتری"),
    (1.0, "قوطی ۱ لیتری"),
    (0.5, "ربع ۰٫۵ لیتری"),
]


@dataclass
class EstimateInput:
    wall_area_m2: float | None = None
    room_width_m: float | None = None
    room_length_m: float | None = None
    room_height_m: float = 2.9
    openings_m2: float = 0.0        # مجموع مساحت در و پنجره
    coats: int = 2
    coverage_m2_per_l: float = 9.0  # پوشش هر لیتر در یک دست
    loss_factor: float = 1.08       # پرت اجرا ~۸٪
    price_per_l: float | None = None


def _paintable_area(inp: EstimateInput) -> float:
    if inp.wall_area_m2 and inp.wall_area_m2 > 0:
        area = inp.wall_area_m2
    elif inp.room_width_m and inp.room_length_m:
        perimeter = 2 * (inp.room_width_m + inp.room_length_m)
        area = perimeter * inp.room_height_m
    else:
        raise ValueError("یا مساحت دیوار را بده یا ابعاد اتاق را")
    return max(0.0, area - max(0.0, inp.openings_m2))


def _pack_cans(liters: float) -> list[dict]:
    """کوچک‌ترین ترکیب ظرف که مقدار لازم را پوشش دهد."""
    remaining = liters
    result: list[dict] = []
    for size, label in CAN_SIZES:
        if remaining <= 0:
            break
        count = int(remaining // size)
        if count:
            result.append({"size_l": size, "label": label, "count": count})
            remaining -= count * size
    if remaining > 1e-6:
        smallest, label = CAN_SIZES[-1]
        # یک ظرف کوچک اضافه یا ارتقاء آخرین ظرف
        for size, lbl in reversed(CAN_SIZES):
            if size >= remaining:
                result.append({"size_l": size, "label": lbl, "count": 1})
                remaining = 0
                break
        else:
            result.append({"size_l": smallest, "label": label, "count": 1})
    # ادغام موارد تکراری
    merged: dict[float, dict] = {}
    for item in result:
        m = merged.setdefault(item["size_l"], {**item, "count": 0})
        m["count"] += item["count"]
    return sorted(merged.values(), key=lambda x: -x["size_l"])


def estimate(inp: EstimateInput) -> dict:
    area = _paintable_area(inp)
    coverage = max(1.0, inp.coverage_m2_per_l)
    liters_net = area * inp.coats / coverage
    liters = liters_net * inp.loss_factor
    cans = _pack_cans(liters)
    can_liters = sum(c["size_l"] * c["count"] for c in cans)

    out = {
        "paintable_area_m2": round(area, 1),
        "coats": inp.coats,
        "coverage_m2_per_l": coverage,
        "liters_needed": round(liters, 1),
        "cans": cans,
        "cans_total_liters": round(can_liters, 1),
    }
    if inp.price_per_l:
        out["price_estimate"] = round(can_liters * inp.price_per_l)
        out["price_per_l"] = inp.price_per_l
    return out
