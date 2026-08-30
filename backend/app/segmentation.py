"""تشخیص دیوار در عکس با مدل semantic segmentation از قبل آموزش‌دیده روی ADE20K.

از دو معماری پشتیبانی می‌کند:
- SegFormer  (سبک و سریع؛ پیش‌فرض)
- Mask2Former / OneFormer  (دقیق‌تر، کمی کندتر؛ لایسنس Apache — مناسب استقرار تجاری)

با متغیر محیطی SEG_MODEL_ID عوض می‌شود. نمونه‌ها:
  nvidia/segformer-b0-finetuned-ade-512-512        (سریع‌ترین)
  nvidia/segformer-b3-finetuned-ade-512-512        (تعادل)
  facebook/mask2former-swin-base-ade-semantic      (دقیق، Apache-2.0)
"""

from __future__ import annotations

import os
import threading

import numpy as np
import torch
from PIL import Image
from transformers import AutoImageProcessor

# پیش‌فرض: Mask2Former (لایسنس Apache-2.0، دقت بالا).
# برای دموی سریع‌تر روی CPU ضعیف:  SEG_MODEL_ID=nvidia/segformer-b0-finetuned-ade-512-512
MODEL_ID = os.environ.get("SEG_MODEL_ID", "facebook/mask2former-swin-base-ade-semantic")

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


def wall_mask(image: Image.Image) -> np.ndarray:
    """ماسک دیوار: آرایه‌ی float32 با ابعاد [H, W]، مقادیر ۰ یا ۱."""
    seg = _semantic_map(image)
    return np.isin(seg, WALL_CLASSES).astype(np.float32)


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
