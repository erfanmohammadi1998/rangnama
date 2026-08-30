"""تست سریع: بدون سرور، خط پردازش را روی یک عکس نمونه اجرا می‌کند.

اجرا:  .venv\\Scripts\\python.exe smoke_test.py [مسیر_عکس]
اگر عکسی داده نشود، یک تصویر مصنوعی ساخته می‌شود.
خروجی‌ها در پوشه‌ی out/ ذخیره می‌شوند.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

from app.recolor import recolor_walls

OUT = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)


def synthetic() -> Image.Image:
    h, w = 480, 640
    img = np.zeros((h, w, 3), dtype=np.uint8)
    # دیوار روشن با گرادیان نور
    grad = np.linspace(180, 235, w).astype(np.uint8)
    img[:, :] = np.stack([grad, grad, grad], axis=-1)
    # کف تیره‌تر
    img[int(h * 0.72) :, :] = (110, 95, 80)
    # یک پنجره‌ی روشن
    img[60:200, 420:560] = 250
    return Image.fromarray(img)


def main() -> None:
    if len(sys.argv) > 1:
        img = Image.open(sys.argv[1]).convert("RGB")
        img.thumbnail((1280, 1280))
    else:
        img = synthetic()
    img.save(OUT / "before.jpg")

    # تست رنگ‌آمیزی با ماسک ساختگی (نیمه‌ی بالای تصویر = دیوار)
    mask = np.zeros(img.size[::-1], dtype=np.float32)
    mask[: int(mask.shape[0] * 0.7), :] = 1.0
    recolor_walls(img, mask, "#35566B").save(OUT / "recolor_fake_mask.jpg")
    print("OK  recolor (ماسک ساختگی)  ->", OUT / "recolor_fake_mask.jpg")

    # تست خط کامل با مدل واقعی
    try:
        from app.segmentation import wall_mask

        real = wall_mask(img)
        cover = float((real > 0.5).mean()) * 100
        print(f"OK  segmentation  -> {cover:.1f}% از تصویر به‌عنوان دیوار تشخیص داده شد")
        recolor_walls(img, real, "#7C8459").save(OUT / "recolor_real_mask.jpg")
        print("OK  خط کامل  ->", OUT / "recolor_real_mask.jpg")
    except Exception as exc:  # noqa: BLE001
        print(f"SKIP segmentation ({type(exc).__name__}: {exc})")


if __name__ == "__main__":
    main()
