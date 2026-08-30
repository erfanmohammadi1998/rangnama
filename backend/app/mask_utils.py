"""تمیزکاریِ ماسک دیوار تا نتیجه‌ی رنگ‌آمیزی طبیعی شود و رنگ روی سقف/گچبری/در سرریز نکند."""

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
    """ماسک خام مدل را به یک ماسک نرم و چسبیده به لبه‌های واقعی دیوار تبدیل می‌کند.

    مراحل:
    1. پر کردن حفره‌ها و حذف جزیره‌های کوچک.
    2. نگه‌داشتن فقط بزرگ‌ترین ناحیه‌های متصل.
    3. کمی تو رفتن (erode) تا از لبه‌ها فاصله بگیریم.
    4. سرکوب نواحی‌ای که روشنایی‌شان خیلی با دیوار فرق دارد (سقف/گچبری/پنجرهٔ روشن،
       در/سایهٔ تیره) — علت اصلی سرریز رنگ.
    5. guided filter تا لبهٔ ماسک دقیقاً روی لبهٔ واقعی بنشیند.
    خروجی: float32 در [0, 1].
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
        areas = stats[1:, cv2.CC_STAT_AREA]
        order = np.argsort(areas)[::-1]
        min_area = min_area_frac * h * w
        keep = {
            idx + 1
            for rank, idx in enumerate(order)
            if rank < keep_components and areas[idx] >= min_area
        }
        if keep:
            binary = np.isin(labels, list(keep)).astype(np.uint8)

    # روشناییِ مرجعِ دیوار از داخلِ ناحیه (نه لبه‌ها)
    inner = cv2.erode(binary, kernel, iterations=2)
    lab = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2LAB)
    Lc = lab[..., 0].astype(np.float32)
    ref_region = inner if inner.sum() > 500 else binary
    wall_L = float(np.median(Lc[ref_region > 0]))
    wall_std = float(np.std(Lc[ref_region > 0])) + 1e-3

    # هرچه روشنایی از دیوار دورتر باشد، کمتر جزو دیوار است
    tol = max(22.0, 2.2 * wall_std)
    diff = np.abs(Lc - wall_L)
    lum_gate = np.clip(1.0 - (diff - tol) / (tol * 1.6), 0.0, 1.0)

    # کمی تو رفتن از لبه‌ی سختِ ماسک
    eroded = cv2.erode(binary, kernel, iterations=1).astype(np.float32)
    soft = np.minimum(eroded, lum_gate).astype(np.float32)

    # چسباندن لبه به تصویر
    guide = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    radius = max(6, min(h, w) // 90)
    if _has_guided():
        try:
            soft = cv2.ximgproc.guidedFilter(guide, soft, radius, 2e-4)
        except cv2.error:
            soft = cv2.GaussianBlur(soft, (0, 0), radius / 2)
    else:
        soft = cv2.GaussianBlur(soft, (0, 0), radius / 2)
    soft = np.nan_to_num(np.clip(soft, 0.0, 1.0), nan=0.0)

    # دروازه‌ی روشنایی را دوباره اعمال کن (guided filter کمی پخشش کرده)
    soft = soft * (0.35 + 0.65 * lum_gate)

    # جمع‌کردن لبه و نرم‌کردن نهایی
    soft = np.clip((soft - 0.18) / 0.64, 0.0, 1.0)
    soft = cv2.GaussianBlur(soft, (0, 0), 1.4)
    return soft.astype(np.float32)
