"""رنگ‌آمیزیِ دیوار با یک مدلِ چندوجهیِ ابری (OpenAI gpt-image-2).

برخلاف پایپ‌لاینِ لوکال (تشخیصِ ماسک + رنگ‌آمیزیِ الگوریتمی در فضای Lab)، اینجا
کل تصویر را به مدل می‌دهیم و از او می‌خواهیم فقط دیوار را رنگ کند و همه‌چیزِ
دیگر (مبلمان، نور، زاویه‌ی دوربین) را دقیقاً دست‌نخورده نگه دارد. مدل صحنه را
واقعاً «می‌فهمد» — پس روی گوشه‌های پیچیده یا دیوارهای کم‌کنتراست که مدلِ
سگمنتیشنِ لوکال روی آن‌ها می‌لغزد، معمولاً نتیجه‌ی بهتری می‌دهد.

نکته: Gemini/Google از این شبکه در دسترس نیست (مسدودیتِ جغرافیایی، مستقل از
اعتبارِ کلید) — برای همین از OpenAI استفاده می‌شود.

هزینه: هر درخواست چند سِنت (سرویسِ ابریِ پولی)؛ نیاز به اینترنت و OPENAI_API_KEY.
عکس برای پردازش به سرورهای OpenAI فرستاده می‌شود — برخلاف پایپ‌لاینِ لوکال که
هیچ داده‌ای از سیستم خارج نمی‌شود.
"""

from __future__ import annotations

import base64
import io
import os

import httpx
from PIL import Image

OPENAI_MODEL = "gpt-image-2"
OPENAI_URL = "https://api.openai.com/v1/images/edits"


class CloudRecolorError(RuntimeError):
    pass


def available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def _build_prompt(color_hex: str, color_name: str | None) -> str:
    name_part = f" (نامِ فارسی: «{color_name}»)" if color_name else ""
    return (
        "This is a real photo of a room. Change ONLY the wall paint color to "
        f"hex {color_hex}{name_part}. "
        "Strict rules: "
        "1) Do not change anything else — furniture, rugs, curtains, chandeliers, "
        "TVs, frames, ceiling, floor, lighting and shadows must stay exactly as they are. "
        "2) Keep the wall's original texture and lighting contrast, only the hue changes. "
        "3) Do not paint the ceiling, frames, mirrors, windows, or furniture touching the wall. "
        "4) Camera angle, framing and photo quality must exactly match the input — "
        "only the wall color changes, nothing else. "
        "Return only the final photo."
    )


def recolor_with_openai(image: Image.Image, color_hex: str, color_name: str | None = None) -> Image.Image:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise CloudRecolorError("OPENAI_API_KEY تنظیم نشده است")

    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="PNG")
    buf.seek(0)

    files = {"image": ("photo.png", buf.getvalue(), "image/png")}
    data = {
        "model": OPENAI_MODEL,
        "prompt": _build_prompt(color_hex, color_name),
        "size": "1024x1024",
        "quality": "high",
    }

    try:
        resp = httpx.post(
            OPENAI_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            data=data,
            files=files,
            timeout=120.0,
        )
    except httpx.HTTPError as exc:
        raise CloudRecolorError(f"اتصال به سرویسِ ابری ناموفق بود: {exc!r}") from exc

    if resp.status_code != 200:
        raise CloudRecolorError(f"سرویسِ ابری خطا داد ({resp.status_code}): {resp.text[:400]}")

    payload = resp.json()
    try:
        item = payload["data"][0]
    except (KeyError, IndexError) as exc:
        raise CloudRecolorError(f"پاسخِ غیرمنتظره از سرویسِ ابری: {payload!r}") from exc

    if item.get("b64_json"):
        out_bytes = base64.b64decode(item["b64_json"])
        return Image.open(io.BytesIO(out_bytes)).convert("RGB")

    if item.get("url"):
        img_resp = httpx.get(item["url"], timeout=60.0)
        img_resp.raise_for_status()
        return Image.open(io.BytesIO(img_resp.content)).convert("RGB")

    raise CloudRecolorError("سرویسِ ابری تصویری برنگرداند")


# نامِ سازگار با main.py
recolor_with_gemini = recolor_with_openai
