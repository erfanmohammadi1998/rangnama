"""روی همه‌ی عکس‌های پوشه‌ی samples/ ماسک و چند رنگ را اجرا و در out/ ذخیره می‌کند."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps

from app.recolor import mask_preview, recolor_walls
from app.segmentation import wall_mask

BASE = Path(__file__).parent
SAMPLES = BASE / "samples"
OUT = BASE / "out"
OUT.mkdir(exist_ok=True)

COLORS = {
    "green": "#7C8459",   # سبز زیتونی
    "blue": "#35566B",    # آبی نفتی
    "beige": "#D8C4A9",   # بژ گرم
}


def main() -> None:
    imgs = sorted(p for p in SAMPLES.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    print(f"{len(imgs)} عکس پیدا شد")
    for i, p in enumerate(imgs, 1):
        img = ImageOps.exif_transpose(Image.open(p)).convert("RGB")
        img.thumbnail((1024, 1024))
        mask = wall_mask(img)
        cover = float((mask > 0.5).mean()) * 100
        print(f"[{i}] {p.name}: {cover:.0f}% دیوار")
        mask_preview(img, mask).save(OUT / f"s{i}_mask.jpg")
        img.save(OUT / f"s{i}_before.jpg")
        for name, hexv in COLORS.items():
            recolor_walls(img, mask, hexv).save(OUT / f"s{i}_{name}.jpg")


if __name__ == "__main__":
    main()
