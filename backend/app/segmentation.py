"""تشخیص دیوار در عکس با مدل semantic segmentation از قبل آموزش‌دیده روی ADE20K.

از دو معماری پشتیبانی می‌کند:
- SegFormer  (سبک و سریع؛ پیش‌فرض)
- Mask2Former / OneFormer  (دقیق‌تر، کمی کندتر؛ لایسنس Apache — مناسب استقرار تجاری)

با متغیر محیطی SEG_MODEL_ID عوض می‌شود. نمونه‌ها:
  nvidia/segformer-b0-finetuned-ade-512-512        (سریع‌ترین)
  nvidia/segformer-b3-finetuned-ade-512-512        (تعادل)
  facebook/mask2former-swin-base-ade-semantic      (دقیق، سریع‌تر)
  facebook/mask2former-swin-large-ade-semantic     (دقیق‌ترین، کندتر — پیش‌فرضِ فعلی)
"""

from __future__ import annotations

import os
import threading

import numpy as np
import torch
from PIL import Image
from transformers import AutoImageProcessor

# پیش‌فرض: نسخه‌ی large (دقت بالاتر از base، ولی کندتر روی CPU).
# برای دموی سریع‌تر:  SEG_MODEL_ID=facebook/mask2former-swin-base-ade-semantic
# یا برای CPU ضعیف:   SEG_MODEL_ID=nvidia/segformer-b0-finetuned-ade-512-512
MODEL_ID = os.environ.get("SEG_MODEL_ID", "facebook/mask2former-swin-large-ade-semantic")

# اندیس کلاس‌های ADE20K که «دیوار» شمرده می‌شوند (0 = wall).
WALL_CLASSES = (0,)

_lock = threading.Lock()
_processor = None
_model = None


def _load_model(model_id: str):
    """معماری‌های مختلف segmentation را امتحان می‌کند تا یکی جواب دهد."""
    from transformers import AutoModelForSemanticSegmentation

    errors = []
    try:
        return AutoModelForSemanticSegmentation.from_pretrained(model_id)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"semantic: {exc}")
    try:
        from transformers import Mask2FormerForUniversalSegmentation

        return Mask2FormerForUniversalSegmentation.from_pretrained(model_id)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"mask2former: {exc}")
    try:
        from transformers import AutoModelForUniversalSegmentation

        return AutoModelForUniversalSegmentation.from_pretrained(model_id)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"universal: {exc}")
    raise RuntimeError(f"مدل «{model_id}» بارگذاری نشد:\n" + "\n".join(errors))


def _load():
    global _processor, _model
    if _model is None:
        with _lock:
            if _model is None:
                proc = AutoImageProcessor.from_pretrained(MODEL_ID)
                model = _load_model(MODEL_ID)
                model.eval()
                _processor, _model = proc, model
    return _processor, _model


@torch.inference_mode()
def _semantic_map(image: Image.Image) -> np.ndarray:
    processor, model = _load()
    inputs = processor(images=image, return_tensors="pt")
    outputs = model(**inputs)

    # مسیر استاندارد transformers برای همه‌ی معماری‌ها
    if hasattr(processor, "post_process_semantic_segmentation"):
        seg = processor.post_process_semantic_segmentation(
            outputs, target_sizes=[image.size[::-1]]
        )[0]
        return seg.cpu().numpy()

    # fallback برای SegFormerِ قدیمی
    import torch.nn.functional as F

    logits = F.interpolate(
        outputs.logits, size=image.size[::-1], mode="bilinear", align_corners=False
    )
    return logits.argmax(dim=1)[0].cpu().numpy()


CEILING_CLASSES = (5,)  # ceiling

# کلاس‌های ADE20K که قطعاً سطحِ رنگ‌شدنی نیستند.
# floor=3, windowpane=8, door=14, painting=22, mirror=27,
# cabinet=10, wardrobe=35, sofa=23, chair=19, curtain=18, sky=2,
# table=15, armchair=30, chandelier=85, sconce=134,
# television=89, screen=130, monitor=143, crt screen=141,
# cushion=39, pillow=57, vase=135, chest of drawers=44, shelf=24,
# bookcase=62, rug=28, ottoman=97, stool=110, plant=17, flower=66,
# coffee table=64, seat=31, base=40, column=42
#
# عمداً «lamp» (۳۶) و «light» (۸۲) اینجا نیستند: این دو کلاس معمولاً هالهٔ نرمِ
# نور دورِ چراغ را هم می‌گیرند (نه فقط خودِ فیکسچر)، و چون آن هاله لبهٔ سختی در
# عکس ندارد، guided filter آن را به یک لکهٔ نرمِ بزرگ تبدیل می‌کند. حفظِ طبیعیِ
# آن هاله به‌عهدهٔ منطقِ highlight در recolor.py است، نه حذفِ کاملِ آن از ماسک.
_NEVER_PAINT = (
    3, 8, 14, 22, 27, 10, 35, 23, 19, 18, 2,
    15, 30, 85, 134, 89, 130, 143, 141,
    39, 57, 135, 44, 24, 62, 28, 97, 110, 17, 66,
    64, 31, 40, 42,
)


def surface_mask(image: Image.Image, part: str = "wall") -> np.ndarray:
    """ماسک سطحِ قابل رنگ. `part` یکی از: wall | ceiling | wall_ceiling.

    پیکسل‌های سطوحی که رنگ نمی‌گیرند (کف، در، پنجره، مبلمان…) با کمی گشادسازی
    از ماسک کم می‌شوند تا رنگ سرریز نکند.
    """
    import cv2

    seg = _semantic_map(image)
    h, w = seg.shape
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    junction = max(2, int(min(h, w) * 0.012))
    jk = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (junction, junction))

    wall_m = np.isin(seg, WALL_CLASSES).astype(np.uint8)
    ceil_m = np.isin(seg, CEILING_CLASSES).astype(np.uint8)

    if part == "wall":
        mask = wall_m
    elif part == "ceiling":
        mask = ceil_m
    else:  # wall_ceiling: هر دو را کمی جمع کن تا نوارِ اتصال (کناف/گچبری) رنگ نخورد
        mask = cv2.erode(wall_m, jk) | cv2.erode(ceil_m, jk)

    # سطوحی که رنگ نمی‌گیرند
    never = list(_NEVER_PAINT)
    if part == "wall":
        never += list(CEILING_CLASSES)
    block = np.isin(seg, never).astype(np.uint8)

    # نوارهای خیلی روشن (گچبری/کناف سفید) در حالت شامل سقف حفظ شوند
    if part in ("wall_ceiling", "ceiling"):
        lab_full = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2LAB)
        L = lab_full[..., 0]
        region = mask > 0
        if region.any():
            bright = (L > np.percentile(L[region], 92) + 12).astype(np.uint8)
            block = block | bright

    # روی دیوارهای خیلی ساده و کم‌کنتراست (مثلاً سفید/کِرِم یکدست)، مدل گاهی یک
    # تکه از خودِ دیوار را اشتباهاً «پنجره/آینه/تابلو» تشخیص می‌دهد — اگر رنگ آن
    # تکه عملاً با رنگ خودِ دیوار یکی باشد، این تشخیص را نادیده می‌گیریم.
    block = _drop_wall_colored_false_positives(seg, block, mask, image)

    # لبه‌گیریِ دقیقِ مرزِ بیرونیِ دیوار با MobileSAM (اختیاری — اگر مدل در دسترس
    # نباشد بی‌اثر است). سمتِ block عمداً SAM نمی‌شود: چون برچسبِ خامِ آن گاهی خودش
    # غلط/بزرگ است، معیارِ «بیشترین همپوشانی با برچسبِ اولیه» همان غلط را تأیید
    # می‌کند و ممکن است کل دیوار را ببلعد.
    from .sam_refine import refine_with_sam

    rgb = np.asarray(image.convert("RGB"))
    mask = refine_with_sam(rgb, mask.astype(np.float32))

    if block.any():
        r = max(2, int(min(h, w) * 0.008))
        block_dilated = cv2.dilate(block, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (r, r)))
        mask = mask * (1.0 - block_dilated.astype(np.float32))

    mask = cv2.morphologyEx((mask > 0.5).astype(np.uint8), cv2.MORPH_OPEN, k)

    # نرم‌کردنِ نهاییِ لبه (guided filter) همین‌جا انجام می‌شود، نه فقط در مسیرِ
    # رنگ‌آمیزی — چون فرانت‌اند همیشه همین ماسک را (بعد از پیش‌نمایش/ویرایشِ قلم)
    # مستقیماً به /api/visualize می‌فرستد و آن مسیر دیگر این مرحله را اجرا نمی‌کند.
    from .mask_utils import refine_mask as _smooth_edges

    mask = _smooth_edges(rgb, mask.astype(np.float32))
    return mask.astype(np.float32)


_RISKY_BLOCK_CLASSES = (8, 22, 27)  # windowpane, painting, mirror
_WALL_COLOR_MATCH_DIST = 12.0


def _drop_wall_colored_false_positives(
    seg: np.ndarray, block: np.ndarray, wall_region: np.ndarray, image: Image.Image
) -> np.ndarray:
    import cv2

    if not block.any() or not wall_region.any():
        return block
    risky = np.isin(seg, _RISKY_BLOCK_CLASSES).astype(np.uint8)
    if not risky.any():
        return block

    lab = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2LAB).astype(np.float32)
    wall_ref = lab[wall_region > 0].mean(axis=0)

    num, labels, _stats, _ = cv2.connectedComponentsWithStats(risky, connectivity=8)
    drop = np.zeros_like(risky)
    for i in range(1, num):
        comp = labels == i
        comp_color = lab[comp].mean(axis=0)
        if float(np.linalg.norm(comp_color - wall_ref)) < _WALL_COLOR_MATCH_DIST:
            drop |= comp.astype(np.uint8)

    if drop.any():
        block = block & (1 - drop)
    return block


def wall_mask(image: Image.Image, part: str = "wall") -> np.ndarray:
    """میان‌بر سازگار با کد قبلی."""
    return surface_mask(image, part)


def region_mask(image: Image.Image, x: int, y: int) -> np.ndarray:
    """ماسکِ همان ناحیه‌ی هم‌کلاسی که کاربر رویش کلیک کرده (برای انتخاب یک دیوار خاص).

    اگر کلیک روی دیوار باشد، فقط همان تکه‌ی دیوارِ متصل برگردانده می‌شود.
    """
    import cv2

    seg = _semantic_map(image)
    h, w = seg.shape
    x = int(np.clip(x, 0, w - 1))
    y = int(np.clip(y, 0, h - 1))
    cls = int(seg[y, x])
    binary = (seg == cls).astype(np.uint8)
    num, labels = cv2.connectedComponents(binary, connectivity=8)
    comp = int(labels[y, x])
    return (labels == comp).astype(np.float32)


def warmup() -> None:
    _load()
    from .sam_refine import warmup as _sam_warmup

    try:
        _sam_warmup()
    except Exception as exc:  # noqa: BLE001
        print(f"[warmup] MobileSAM آماده نشد (بی‌خطر، این مرحله نادیده گرفته می‌شود): {exc!r}")
