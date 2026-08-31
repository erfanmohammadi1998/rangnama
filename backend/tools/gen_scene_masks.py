"""ساخت عکس + ماسکِ آمادهٔ فضاهای نمونه.

برای هر فضا سه ماسک تولید می‌شود: دیوار / دیوار+سقف / فقط سقف.
ماسک‌ها با ترکیبِ «تشخیص مدل + محدودهٔ دستی (polygon)» ساخته می‌شوند تا رنگ روی
سقف/گچبری/مبلمان/هالهٔ نور سرریز نکند.

اجرا (از پوشهٔ backend):
    .venv\\Scripts\\python.exe tools\\gen_scene_masks.py

عکس‌های ورودی را در tools/scene_src/ بگذار و JOBS را ویرایش کن.
خروجی در frontend/scenes/ نوشته می‌شود.
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.segmentation import _semantic_map  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "frontend" / "scenes"
SRC = Path(__file__).resolve().parent / "scene_src"

# اندیس‌های ADE20K که سطحِ رنگ‌شدنی نیستند (کف، در، پنجره، مبلمان، تخت، تابلو، …)
NONWALL = {
    2, 3, 7, 8, 10, 12, 14, 15, 17, 18, 19, 22, 23, 24, 27, 28, 30, 31, 33, 36,
    39, 44, 47, 57, 62, 64, 65, 66, 67, 69, 70, 73, 75, 89, 92, 98, 108, 110,
    112, 115, 119, 124, 131, 132, 135, 143, 144,
}

# name: (فایل ورودی در scene_src/, (نسبت بالای دیوار, نسبت پایین دیوار))
JOBS = {
    "living": ("living.jpg", (0.07, 0.90)),
    "bedroom": ("bedroom.jpg", (0.02, 0.88)),
    "kitchen": ("kitchen.jpg", (0.015, 0.86)),
}


def _clean(m: np.ndarray, w: int, h: int, erode: int = 4) -> np.ndarray:
    m = m.astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, 8)
    if n > 1:
        keep = [i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] > 0.006 * w * h]
        m = np.isin(lab, keep).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)))
    if erode:
        m = cv2.erode(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (erode, erode)))
    return np.clip(cv2.GaussianBlur(m.astype(np.float32), (0, 0), 1.8), 0, 1)


def build(name: str, src_file: str, y0f: float, y1f: float) -> None:
    img = ImageOps.exif_transpose(Image.open(SRC / src_file)).convert("RGB")
    if max(img.size) > 1200:
        s = 1200 / max(img.size)
        img = img.resize((round(img.width * s), round(img.height * s)))
    w, h = img.size
    seg = _semantic_map(img)
    L = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2LAB)[..., 0]

    poly = np.zeros((h, w), np.uint8)
    poly[int(h * y0f):int(h * y1f), :] = 1
    nw_raw = np.isin(seg, list(NONWALL)).astype(np.uint8)
    r = max(3, int(min(w, h) * 0.010))
    nw = cv2.dilate(nw_raw, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (r, r)))

    wall = ((seg == 0).astype(np.uint8) | poly) & (1 - nw)
    ceil = (seg == 5).astype(np.uint8) & (1 - nw_raw)

    region = (wall | ceil) > 0
    thr = np.percentile(L[region], 88) + 10 if region.any() else 255
    bright = cv2.dilate((L > thr).astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))

    masks = {
        "wall": _clean(wall, w, h, erode=4),
        "ceiling": _clean(ceil & (1 - bright), w, h, erode=3),
        "wall_ceiling": _clean((wall | ceil) & (1 - bright), w, h, erode=3),
    }

    img.save(OUT / f"{name}.jpg", quality=88)
    for kind, m in masks.items():
        fn = f"{name}.mask.png" if kind == "wall" else f"{name}.{kind}.mask.png"
        Image.fromarray((m * 255).astype("uint8"), "L").save(OUT / fn)
    print(name, {k: f"{(v > .5).mean() * 100:.0f}%" for k, v in masks.items()})


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for n, (f, ys) in JOBS.items():
        if (SRC / f).exists():
            build(n, f, *ys)
        else:
            print(f"skip {n}: {SRC / f} پیدا نشد")
