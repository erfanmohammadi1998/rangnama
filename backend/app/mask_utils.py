"""تمیزکاری و لبه‌گیریِ ماسک دیوار تا نتیجه‌ی رنگ‌آمیزی طبیعی شود."""

from __future__ import annotations

import cv2
import numpy as np


def _has_guided() -> bool:
    return hasattr(cv2, "ximgproc") and hasattr(cv2.ximgproc, "guidedFilter")


def refine_mask(
    image_rgb: np.ndarray,
    mask: np.ndarray,
    keep_components: int = 3,
    min_area_frac: float = 0.004,
) -> np.ndarray:
    """ماسک خام مدل را به یک ماسک نرم و چسبیده به لبه‌های واقعی تصویر تبدیل می‌کند.

    - جزیره‌های کوچک حذف و حفره‌ها پر می‌شوند.
    - با guided filter لبه‌ی ماسک روی لبه‌ی واقعی دیوار (گچبری، قاب در، مبل) می‌نشیند.
    خروجی: float32 در بازه‌ی [0, 1].
    """
    h, w = mask.shape[:2]
    binary = (mask > 0.5).astype(np.uint8)

    # پر کردن حفره‌های کوچک و حذف نویز
    k = max(3, (min(h, w) // 200) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

    # نگه‌داشتن فقط بزرگ‌ترین ناحیه‌های متصل (دیوارهای اصلی)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if num > 1:
        areas = stats[1:, cv2.CC_STAT_AREA]
        order = np.argsort(areas)[::-1]
        min_area = min_area_frac * h * w
        keep = {
            idx + 1
            for rank, idx in enumerate(order)
            if rank < keep_components and areas[idx] >= min_area
        }
        binary = np.isin(labels, list(keep)).astype(np.uint8) if keep else binary

    soft = binary.astype(np.float32)

    # چسباندن لبه به تصویر
    guide = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    radius = max(4, min(h, w) // 120)
    if _has_guided():
        try:
            soft = cv2.ximgproc.guidedFilter(guide, soft, radius, 1e-4)
        except cv2.error:
            soft = cv2.GaussianBlur(soft, (0, 0), radius / 2)
    else:
        soft = cv2.GaussianBlur(soft, (0, 0), radius / 2)
    soft = np.nan_to_num(np.clip(soft, 0.0, 1.0), nan=0.0)

    # کمی جمع‌کردن لبه تا رنگ روی گچبری/قاب سرریز نکند
    soft = np.clip((soft - 0.15) / 0.7, 0.0, 1.0)
    soft = cv2.GaussianBlur(soft, (0, 0), 1.5)
    return soft.astype(np.float32)
