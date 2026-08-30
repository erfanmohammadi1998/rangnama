"""رنگ‌آمیزی واقع‌گرایانه‌ی دیوار با حفظ نور، سایه و بافت عکس اصلی.

روش:
- کار در فضای رنگی Lab.
- روشنایی (L): میانگینِ ناحیه به روشناییِ رنگ هدف منتقل می‌شود، ولی همه‌ی جزئیاتِ
  بافت (فرکانس بالا) و بیشترِ کنتراستِ سایه‌روشن حفظ می‌شود → رنگ‌های تیره واقعاً تیره
  و رنگ‌های روشن واقعاً روشن دیده می‌شوند، بدون تخت‌شدن.
- رنگ (a, b): روی رنگ هدف تنظیم می‌شود + کسر کوچکی از تغییراتِ رنگیِ اصلی نگه داشته
  می‌شود تا سطح «زنده» بماند و پوستریِ تخت نشود.
- انعکاس نور/آفتاب (highlight) و سایه‌های عمیق کم‌رنگ‌تر رنگ می‌گیرند.
- ترکیب نهایی در فضای خطی نور انجام می‌شود تا لبه‌ها طبیعی باشد.
"""

from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from .mask_utils import refine_mask


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _srgb_to_linear(x: np.ndarray) -> np.ndarray:
    x = x / 255.0
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * (x ** (1 / 2.4)) - 0.055) * 255.0


def recolor_walls(
    image: Image.Image,
    mask: np.ndarray,
    color: str,
    *,
    refine: bool = True,
    contrast_keep: float = 0.9,
    chroma_texture: float = 0.14,
    lighting: str = "natural",
    strength: float = 1.0,
) -> Image.Image:
    """تصویری با دیوارِ رنگ‌شده برمی‌گرداند. `color` باید هگز `#RRGGBB` باشد."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)

    m = np.clip(mask.astype(np.float32), 0.0, 1.0)
    if refine:
        m = refine_mask(rgb, m)
    if float((m > 0.5).sum()) < 50:
        return Image.fromarray(rgb)

    hard = m > 0.5

    target_rgb = np.array(hex_to_rgb(color), dtype=np.uint8).reshape(1, 1, 3)
    tL, tA, tB = cv2.cvtColor(target_rgb, cv2.COLOR_RGB2LAB)[0, 0].astype(np.float32)

    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    L, A, B = lab[..., 0], lab[..., 1], lab[..., 2]

    mean_L = float(L[hard].mean())
    mean_A = float(A[hard].mean())
    mean_B = float(B[hard].mean())

    # روشنایی: انتقال میانگین + حفظ کنتراست و جزئیات
    new_L = tL + (L - mean_L) * contrast_keep

    # حفظ انعکاس نور شدید (آفتاب روی دیوار، لامپ)
    highlight = np.clip((L - 232.0) / 23.0, 0.0, 1.0)
    new_L = new_L * (1.0 - highlight) + L * highlight
    new_L = np.clip(new_L, 4.0, 252.0)

    # رنگ: هدف + کمی بافت رنگیِ اصلی
    new_A = tA + (A - mean_A) * chroma_texture
    new_B = tB + (B - mean_B) * chroma_texture
    # سایه‌های عمیق و های‌لایت‌ها اشباع کمتری دارند
    deep = np.clip((30.0 - new_L) / 30.0, 0.0, 1.0)
    desat = np.clip(highlight + deep, 0.0, 1.0)[..., None]
    ab = np.stack([new_A, new_B], axis=-1)
    ab = ab * (1.0 - 0.55 * desat) + np.array([128.0, 128.0]) * (0.55 * desat)

    out_lab = np.stack([new_L, ab[..., 0], ab[..., 1]], axis=-1)
    recolored = cv2.cvtColor(np.clip(out_lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)

    recolored = _apply_lighting(recolored, lighting)

    # ترکیب در فضای خطی نور
    alpha = (m * strength)[..., None]
    alpha = alpha * (1.0 - 0.45 * highlight[..., None])
    base_lin = _srgb_to_linear(rgb.astype(np.float32))
    new_lin = _srgb_to_linear(recolored.astype(np.float32))
    out_lin = base_lin * (1.0 - alpha) + new_lin * alpha
    out = _linear_to_srgb(out_lin)

    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def _apply_lighting(rgb: np.ndarray, mode: str) -> np.ndarray:
    """شبیه‌سازی سادهٔ نور محیط روی ناحیهٔ رنگ‌شده."""
    if mode in ("natural", "day", None, ""):
        return rgb
    x = rgb.astype(np.float32)
    if mode == "warm":  # نور لامپ زرد / غروب
        x *= np.array([1.06, 1.0, 0.9])
    elif mode == "cool":  # نور مهتابی / روز ابری
        x *= np.array([0.95, 1.0, 1.08])
    elif mode == "evening":  # نور کم
        x = x * 0.82 + np.array([8, 4, 10])
    return np.clip(x, 0, 255).astype(np.uint8)


def recolor_multi(
    image: Image.Image,
    layers: list[tuple[np.ndarray, str]],
    **kwargs,
) -> Image.Image:
    """چند دیوار با رنگ‌های مختلف. هر لایه = (ماسک، هگز)."""
    out = image
    for mask, color in layers:
        out = recolor_walls(out, mask, color, **kwargs)
    return out


def mask_preview(image: Image.Image, mask: np.ndarray, refine: bool = True) -> Image.Image:
    """پیش‌نمایش ماسک: ناحیه‌ی دیوار نیمه‌شفاف قرمز می‌شود."""
    rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    m = np.clip(mask.astype(np.float32), 0, 1)
    if refine:
        m = refine_mask(rgb.astype(np.uint8), m)
    overlay = rgb.copy()
    overlay[..., 0] = 255
    overlay[..., 1] *= 0.3
    overlay[..., 2] *= 0.3
    a = (m * 0.5)[..., None]
    out = rgb * (1 - a) + overlay * a
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
