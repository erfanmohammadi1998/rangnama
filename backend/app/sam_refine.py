"""لبه‌گیری دقیقِ ماسک‌ها با SAM (Segment Anything، نسخه‌ی کاملِ ViT-B — دقیق‌تر
از MobileSAM ولی کندتر روی CPU).

مدل تشخیصِ اصلی (Mask2Former) فقط می‌گوید «این ناحیه تقریباً دیوار است» یا «این
ناحیه یک شیء/سقف/گچبری است» — لبه‌اش دقیقاً روی گچبری، دور اشیای کوچک (آباژور،
دیوارکوب) و لبه‌ی واقعی دیوار نمی‌نشیند و اغلب شکلی بلابی/ابری دارد. اینجا هم
تکه‌های «دیوار» و هم تکه‌های «سوراخِ اشیا» را به MobileSAM می‌دهیم تا هر دو با
جعبه/نقاطِ راهنما به شکلِ واقعیِ لبه بچسبند — در نتیجه هم مرزِ بیرونیِ دیوار و هم
مرزِ دورِ هر شیء تمیز و بدون زیگزاگ می‌شود.

اگر مدل/چک‌پوینت در دسترس نباشد یا دانلود/بارگذاری شکست بخورد، بی‌سروصدا ماسکِ
ورودی را دست‌نخورده برمی‌گرداند — یعنی این مرحله هیچ‌وقت باعث کرش سرویس نمی‌شود.
"""

from __future__ import annotations

import os
import threading
import urllib.request
from pathlib import Path

import cv2
import numpy as np

CHECKPOINT_PATH = Path(__file__).resolve().parents[1] / "data" / "weights" / "sam_vit_b.pth"
CHECKPOINT_URL = "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth"
_DISABLED = os.environ.get("DISABLE_SAM_REFINE") == "1"

_lock = threading.Lock()
_predictor = None
_load_failed = False


def _download_checkpoint() -> bool:
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CHECKPOINT_PATH.with_suffix(".part")
    for _attempt in range(3):
        try:
            urllib.request.urlretrieve(CHECKPOINT_URL, tmp)
            if tmp.stat().st_size > 300_000_000:  # فایل سالم باید ~۳۷۵ مگابایت باشد
                tmp.replace(CHECKPOINT_PATH)
                return True
        except Exception:
            pass
    if tmp.exists():
        tmp.unlink(missing_ok=True)
    return False


def _load():
    global _predictor, _load_failed
    if _predictor is not None or _load_failed:
        return _predictor
    with _lock:
        if _predictor is not None or _load_failed:
            return _predictor
        try:
            if not CHECKPOINT_PATH.exists():
                if not _download_checkpoint():
                    raise RuntimeError("دانلود چک‌پوینتِ SAM ناموفق بود")
            from segment_anything import SamPredictor, sam_model_registry

            sam = sam_model_registry["vit_b"](checkpoint=str(CHECKPOINT_PATH))
            sam.eval()
            _predictor = SamPredictor(sam)
        except Exception as exc:  # noqa: BLE001
            print(f"[sam_refine] SAM بارگذاری نشد، از این مرحله صرف‌نظر می‌شود: {exc!r}")
            _load_failed = True
    return _predictor


def available() -> bool:
    return not _DISABLED and not _load_failed


def warmup() -> None:
    if available():
        _load()


def _fill_small_holes(mask: np.ndarray, max_area: int) -> np.ndarray:
    """پر کردن حفره‌های کوچکِ داخلِ ماسک.

    روی سطوحِ بزرگ و کم‌بافت (مثل دیوارِ تخت)، MobileSAM گاهی به‌جای یک ماسکِ
    یکدست، الگویی چهارخانه‌ایِ نویزی برمی‌گرداند (مشکلِ شناخته‌شده‌ی خروجیِ
    decoder روی نواحیِ مبهم). این تابع فقط حفره‌های کوچک را پر می‌کند —
    حفره‌های بزرگ (شکلِ واقعیِ تلویزیون/مبل/لامپ که از قبل داخلِ ماسکِ خام بوده)
    دست‌نخورده باقی می‌مانند.
    """
    h, w = mask.shape
    inv = (~mask).astype(np.uint8)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(inv, connectivity=8)
    out = mask.copy()
    for i in range(1, num):
        x, y, cw, ch, area = stats[i]
        touches_border = x == 0 or y == 0 or x + cw >= w or y + ch >= h
        if not touches_border and area <= max_area:
            out = out | (labels == i)
    return out


def _refine_components(
    predictor,
    source: np.ndarray,
    min_area_frac: float,
    min_iou: float,
    max_components: int,
    max_area_frac: float = 0.18,
) -> np.ndarray:
    """هر تکه‌ی متصلِ `source` را با جعبه/نقاطِ راهنما به MobileSAM می‌دهد و بهترین
    ماسکِ پیشنهادی (بیشترین همپوشانی با تکه‌ی معناییِ اصلی) را برمی‌گرداند.
    فرض بر این است که `predictor.set_image` از قبل صدا زده شده.

    تکه‌های خیلی بزرگ (بیش از `max_area_frac` از تصویر — یعنی معمولاً کلِ دیوار)
    عمداً به SAM داده نمی‌شوند: جعبه/نقاطِ راهنما برای چنین ناحیه‌ی بزرگ و
    بی‌شکلی مبهم است و SAM می‌تواند شکلی نامنظم و بریده‌بریده برگرداند؛ برای
    اشیای کوچک/متوسط (تلویزیون، لوستر، آباژور، کوسن) که مرزشان مشخص است، SAM
    همچنان اجرا می‌شود.
    """
    h, w = source.shape[:2]
    binary = (source > 0.5).astype(np.uint8)
    if binary.sum() < 60:
        return source

    num, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    min_area = max(min_area_frac * h * w, 40)
    max_area = max_area_frac * h * w
    order = sorted(range(1, num), key=lambda i: -stats[i, cv2.CC_STAT_AREA])[:max_components]

    out = np.zeros((h, w), dtype=np.float32)
    refined_any = False

    for i in order:
        area = stats[i, cv2.CC_STAT_AREA]
        if area < min_area:
            continue
        comp = labels == i
        if area > max_area:
            out = np.logical_or(out > 0, comp).astype(np.float32)
            continue
        x, y, cw, ch = stats[i, :4]
        box = np.array([x, y, x + cw, y + ch], dtype=np.float32)

        eroded = cv2.erode(comp.astype(np.uint8), np.ones((5, 5), np.uint8))
        ys, xs = np.where(eroded > 0) if eroded.sum() > 20 else np.where(comp)
        if len(xs) == 0:
            out = np.logical_or(out > 0, comp).astype(np.float32)
            continue

        n_pts = min(5, len(xs))
        idx = np.linspace(0, len(xs) - 1, n_pts).astype(int)
        pos_pts = np.stack([xs[idx], ys[idx]], axis=1).astype(np.float32)
        pos_lbls = np.ones(len(pos_pts), dtype=np.int32)

        try:
            masks, _scores, _ = predictor.predict(
                point_coords=pos_pts,
                point_labels=pos_lbls,
                box=box,
                multimask_output=True,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[sam_refine] predict شکست خورد: {exc!r}")
            out = np.logical_or(out > 0, comp).astype(np.float32)
            continue

        best, best_iou = None, -1.0
        for cand in masks:
            inter = np.logical_and(cand, comp).sum()
            union = np.logical_or(cand, comp).sum()
            iou = inter / union if union else 0.0
            if iou > best_iou:
                best_iou, best = iou, cand

        if best is not None and best_iou >= min_iou:
            max_hole = min(3000, max(400, int(0.02 * area)))
            best = _fill_small_holes(best.astype(bool), max_hole)
            out = np.logical_or(out > 0, best).astype(np.float32)
            refined_any = True
        else:
            out = np.logical_or(out > 0, comp).astype(np.float32)

    # تکه‌های کوچک‌تر از حدِ آستانه که رد شدند، دست‌نخورده باقی بمانند
    small_leftover = binary.astype(np.float32) * (1.0 - (out > 0).astype(np.float32))
    small_leftover_mask = np.isin(
        labels, [i for i in range(1, num) if i not in order or stats[i, cv2.CC_STAT_AREA] < min_area]
    ).astype(np.float32)
    out = np.clip(out + small_leftover_mask, 0.0, 1.0)

    return out if refined_any else source


def refine_masks_with_sam(
    image_rgb: np.ndarray,
    wall_mask: np.ndarray,
    block_mask: np.ndarray | None = None,
    wall_min_area_frac: float = 0.01,
    block_min_area_frac: float = 0.0012,
) -> tuple[np.ndarray, np.ndarray | None]:
    """با یک بار image-encode، هم ماسکِ دیوار و هم سوراخ‌های اشیا (block_mask) را
    دقیق می‌کند — تا هم مرزِ بیرونیِ دیوار و هم دورِ هر شیءِ کوچک تمیز شود.
    """
    predictor = _load()
    if predictor is None:
        return wall_mask, block_mask

    if (wall_mask > 0.5).sum() < 200:
        return wall_mask, block_mask

    try:
        predictor.set_image(image_rgb)
    except Exception as exc:  # noqa: BLE001
        print(f"[sam_refine] set_image شکست خورد: {exc!r}")
        return wall_mask, block_mask

    refined_wall = _refine_components(
        predictor, wall_mask, wall_min_area_frac, min_iou=0.3, max_components=4
    )
    refined_block = block_mask
    if block_mask is not None and block_mask.any():
        refined_block = _refine_components(
            predictor, block_mask, block_min_area_frac, min_iou=0.25, max_components=10
        )

    return refined_wall, refined_block


def refine_with_sam(image_rgb: np.ndarray, mask: np.ndarray, min_area_frac: float = 0.01) -> np.ndarray:
    """میان‌بر سازگار با کد قبلی — فقط یک ماسک را دقیق می‌کند."""
    refined, _ = refine_masks_with_sam(image_rgb, mask, None, wall_min_area_frac=min_area_frac)
    return refined
