"""تمیزکاریِ ماسک دیوار تا نتیجه‌ی رنگ‌آمیزی طبیعی شود و رنگ روی سقف/گچبری/در سرریز نکند."""

from __future__ import annotations

import cv2
import numpy as np


def _has_guided() -> bool:
    return hasattr(cv2, "ximgproc") and hasattr(cv2.ximgproc, "guidedFilter")


def refine_mask(
    image_rgb: np.ndarray,
    mask: np.ndarray,
    min_area_frac: float = 0.001,
) -> np.ndarray:
    """ماسک را نرم می‌کند و لبه‌اش را به لبه‌ی واقعیِ تصویر می‌چسباند.

    مراحل:
    1. پر کردن حفره‌های ریز و حذف نویزِ خیلی کوچک.
    2. guided filter تا لبهٔ ماسک دقیقاً روی لبهٔ واقعی بنشیند.
    خروجی: float32 در [0, 1].

    توجه: این تابع دیگر «فقط چند تکه‌ی بزرگ را نگه دار» یا «دروازه‌ی روشنایی»
    ندارد — یک دیوار واقعی می‌تواند به‌خاطر مبلمان/لوستر/لامپ به چند تکه‌ی
    جداگانه تقسیم شده باشد که همه‌شان باید رنگ بگیرند، و مرزِ سقف/اشیا از قبل
    توسط کلاس‌های معنایی + MobileSAM در segmentation.py مشخص شده — تکرارِ آن
    کار اینجا با یک معیارِ خام‌ترِ روشنایی فقط باعثِ افتادنِ تکه‌های درستِ دیوار
    (مثلاً نزدیکِ نورِ لوستر) می‌شد.
    """
    h, w = mask.shape[:2]
    binary = (mask > 0.5).astype(np.uint8)
    if binary.sum() == 0:
        return binary.astype(np.float32)

    k = max(3, (min(h, w) // 200) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

    num, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if num > 1:
        min_area = min_area_frac * h * w
        keep = {i for i in range(1, num) if stats[i, cv2.CC_STAT_AREA] >= min_area}
        if keep:
            binary = np.isin(labels, list(keep)).astype(np.uint8)

    soft = binary.astype(np.float32)

    # چسباندن لبه به تصویر
    guide = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    radius = max(5, min(h, w) // 110)
    if _has_guided():
        try:
            soft = cv2.ximgproc.guidedFilter(guide, soft, radius, 2e-4)
        except cv2.error:
            soft = cv2.GaussianBlur(soft, (0, 0), radius / 2)
    else:
        soft = cv2.GaussianBlur(soft, (0, 0), radius / 2)
    soft = np.nan_to_num(np.clip(soft, 0.0, 1.0), nan=0.0)

    # جمع‌کردن لبه و نرم‌کردن نهایی
    soft = np.clip((soft - 0.18) / 0.64, 0.0, 1.0)
    soft = cv2.GaussianBlur(soft, (0, 0), 1.4)
    return soft.astype(np.float32)
