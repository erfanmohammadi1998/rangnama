# معماری رنگ‌نما — یادداشت فنی

## اجزا
| بخش | فایل‌ها | کار |
|---|---|---|
| موتور پردازش | `backend/app/segmentation.py`, `recolor.py`, `mask_utils.py` | تشخیص دیوار + رنگ‌آمیزی |
| وب‌سرویس | `backend/app/main.py` | همهٔ مسیرهای API + سرو فرانت |
| ماشین‌حساب | `backend/app/calc.py` | مقدار رنگ از ابعاد اتاق |
| آمار | `backend/app/db.py` | SQLite، لید فروش و رویدادها |
| کاتالوگ | `backend/app/palette.py` + `data/palette.json` | رنگ‌ها (نمونه — با کاتالوگ واقعیِ محصول عوض شود) |
| رابط | `frontend/` | برنامهٔ مشتری + `admin.html` داشبورد |
| ابری (اختیاری) | `backend/app/cloud_recolor.py` | رنگ‌آمیزی با OpenAI gpt-image-2 — پولی، فقط با `OPENAI_API_KEY` فعال می‌شود |

## مسیر پردازش تصویر
عکس → کوچک‌سازی (≤۱۲۸۰px) → Mask2Former (ماسک دیوار) → حذفِ کلاس‌های غیردیوار + محافظِ رنگیِ false-positive → لبه‌گیریِ دقیق با SAM (`sam_refine.py`، فقط تکه‌های معقول، نه کلِ کانتور) → پالایشِ نهاییِ لبه (guided filter، `mask_utils.refine_mask`) → [اصلاح دستی کاربر، اختیاری] → موتور رنگ Lab (`recolor.recolor_walls`: حفظ کانال L، جایگزینی a/b، ترکیب خطی نور) → JPEG.

## مدل
- پیش‌فرض تشخیصِ دیوار: `facebook/mask2former-swin-large-ade-semantic` — ~۸۰۰MB، ۴۵–۶۰ ثانیه/تصویر روی CPU.
- سریع‌تر: `SEG_MODEL_ID=facebook/mask2former-swin-base-ade-semantic` (~۴۳۰MB، ۵–۸ ثانیه).
- سریع‌ترین (فقط تست): `SEG_MODEL_ID=nvidia/segformer-b0-finetuned-ade-512-512`.
- لبه‌گیری: SAM ViT-B (`segment_anything`، ~۳۷۵MB) — قبلاً MobileSAM بود، روی نواحیِ بزرگ نامطمئن بود.
- کلاس «دیوار» در ADE20K اندیس ۰ است (`segmentation.WALL_CLASSES`).

## محدودیت‌ها
- **تعداد تصویر: بدون سقف.** هر درخواست مستقل، حافظه آزاد می‌شود.
- هم‌زمانی: مدل روی CPU پشت‌سرهم پردازش می‌کند؛ برای ترافیک بالا صف کار + چند کارگر یا GPU لازم است.
- RAM هنگام اجرا: ~۱٫۵GB.

## نکات محیط
- `PYTHONUTF8=1` روی ویندوز لازم است (متن فارسی در کنسول/لاگ).
- باگ OpenCV 5 ویندوز: `ximgproc.guidedFilter` با guide از نوع uint8 مقدار NaN می‌دهد → در `mask_utils.py` guide به float32 نرمال‌شده تبدیل می‌شود.
- Python 3.14 + torch 2.13 (venv در `backend/.venv`).

## قبل از تولیدی‌شدن
۱. کاتالوگ رنگ واقعی در `data/palette.json`.
۲. احراز هویت روی `/admin` و `/api/stats`.
۳. HTTPS (دوربین موبایل بدون آن کار نمی‌کند).
۴. بکاپ `data/analytics.sqlite` (شامل شماره مشتری‌ها).
۵. صف پردازش اگر کاربر هم‌زمان زیاد شد.

جزئیات کامل: دفترچهٔ فنی (artifact).
