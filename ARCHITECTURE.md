# معماری رنگ‌نما — یادداشت فنی

## اجزا
| بخش | فایل‌ها | کار |
|---|---|---|
| موتور پردازش | `backend/app/segmentation.py`, `recolor.py`, `mask_utils.py` | تشخیص دیوار + رنگ‌آمیزی |
| وب‌سرویس | `backend/app/main.py` | همهٔ مسیرهای API + سرو فرانت |
| ماشین‌حساب | `backend/app/calc.py` | مقدار رنگ از ابعاد اتاق |
| آمار | `backend/app/db.py` | SQLite، لید فروش و رویدادها |
| کاتالوگ | `backend/app/palette.py` + `data/palette.json` | رنگ‌ها (نمونه — با داده واقعی عوض شود) |
| رابط | `frontend/` | برنامهٔ مشتری + `admin.html` داشبورد |

## مسیر پردازش تصویر
عکس → کوچک‌سازی (≤۱۲۸۰px) → Mask2Former (ماسک دیوار) → پالایش ماسک (guided filter، `mask_utils.refine_mask`) → [اصلاح دستی کاربر، اختیاری] → موتور رنگ Lab (`recolor.recolor_walls`: حفظ کانال L، جایگزینی a/b، ترکیب خطی نور) → JPEG.

## مدل
- پیش‌فرض: `facebook/mask2former-swin-base-ade-semantic` — Apache-2.0، ~۴۳۰MB، ۵–۸ ثانیه/تصویر روی CPU.
- سریع (فقط تست): `SEG_MODEL_ID=nvidia/segformer-b0-finetuned-ade-512-512`.
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
