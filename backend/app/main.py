"""رنگ‌نما — API و رابط کاربری شبیه‌ساز رنگ ساختمانی."""

from __future__ import annotations

import base64
import io
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps
from pydantic import BaseModel

from . import db
from .calc import EstimateInput, estimate
from .palette import catalog, coverage_for, find_color
from .recolor import mask_preview, recolor_walls
from .segmentation import region_mask, wall_mask, warmup

APP_NAME = "رنگ‌نما"
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
MAX_SIDE = 1280


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        warmup()
        print("[warmup] segmentation model loaded")
    except Exception as exc:  # noqa: BLE001
        print(f"[warmup] model NOT loaded: {exc!r}")
    yield


app = FastAPI(title=APP_NAME, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


# ---------- کمک‌کارها ----------

def _load_image(data: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        raise HTTPException(400, "فایل تصویر معتبر نیست")
    img = ImageOps.exif_transpose(img).convert("RGB")
    if max(img.size) > MAX_SIDE:
        s = MAX_SIDE / max(img.size)
        img = img.resize((round(img.width * s), round(img.height * s)))
    return img


def _decode_mask(data: bytes, size: tuple[int, int]) -> np.ndarray:
    m = Image.open(io.BytesIO(data)).convert("L").resize(size)
    return (np.asarray(m, dtype=np.float32) / 255.0)


def _decode_mask_b64(s: str, size: tuple[int, int]) -> np.ndarray:
    if "," in s:
        s = s.split(",", 1)[1]
    return _decode_mask(base64.b64decode(s), size)


def _resolve_color(color: str | None, code: str | None) -> tuple[str, dict | None]:
    if code:
        entry = find_color(code)
        if entry:
            return entry["hex"], entry
        raise HTTPException(400, "کد رنگ در کاتالوگ نیست")
    if color and color.startswith("#") and len(color) == 7:
        return color, None
    raise HTTPException(400, "رنگ نامعتبر است")


def _jpeg(img: Image.Image, quality: int = 90) -> Response:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return Response(content=buf.getvalue(), media_type="image/jpeg")


def _png(img: Image.Image) -> Response:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


# ---------- عمومی ----------

@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "app": APP_NAME}


@app.get("/api/catalog")
def api_catalog() -> dict:
    return catalog()


@app.post("/api/mask")
async def api_mask(
    image: UploadFile = File(...),
    x: int | None = Form(None),
    y: int | None = Form(None),
    part: str = Form("wall"),
) -> Response:
    """ماسک سطح به صورت PNG (سفید = سطح). part: wall | ceiling | wall_ceiling.
    اگر x,y بدهی فقط همان ناحیه."""
    img = _load_image(await image.read())
    if x is not None and y is not None:
        m = region_mask(img, x, y)
    else:
        m = wall_mask(img, part if part in ("wall", "ceiling", "wall_ceiling") else "wall")
    db.log_event("upload")
    out = Image.fromarray((np.clip(m, 0, 1) * 255).astype(np.uint8), mode="L")
    return _png(out)


@app.post("/api/mask-preview")
async def api_mask_preview(image: UploadFile = File(...)) -> Response:
    img = _load_image(await image.read())
    return _jpeg(mask_preview(img, wall_mask(img)))


@app.post("/api/visualize")
async def api_visualize(
    image: UploadFile = File(...),
    color: str | None = Form(None),
    code: str | None = Form(None),
    lighting: str = Form("natural"),
    strength: float = Form(1.0),
    mask: UploadFile | None = File(None),
) -> Response:
    hex_color, entry = _resolve_color(color, code)
    img = _load_image(await image.read())

    if mask is not None:
        m = _decode_mask(await mask.read(), img.size)
        refine = False
    else:
        m = wall_mask(img)
        refine = True

    out = recolor_walls(
        img, m, hex_color, refine=refine, lighting=lighting,
        strength=float(np.clip(strength, 0.2, 1.0)),
    )
    db.log_event(
        "visualize",
        color_code=(entry or {}).get("code"),
        color_name=(entry or {}).get("name"),
        lighting=lighting,
    )
    return _jpeg(out)


class Layer(BaseModel):
    code: str | None = None
    color: str | None = None
    mask: str  # base64 PNG، سفید = این دیوار


class MultiRequest(BaseModel):
    image: str  # base64
    layers: list[Layer]
    lighting: str = "natural"


@app.post("/api/visualize-multi")
def api_visualize_multi(req: MultiRequest) -> Response:
    img = _load_image(base64.b64decode(req.image.split(",", 1)[-1]))
    out = img
    used = []
    for layer in req.layers:
        hex_color, entry = _resolve_color(layer.color, layer.code)
        m = _decode_mask_b64(layer.mask, img.size)
        out = recolor_walls(out, m, hex_color, refine=False, lighting=req.lighting)
        if entry:
            used.append(entry["code"])
    db.log_event("visualize", color_code=",".join(used) or None, walls=len(req.layers))
    return _jpeg(out)


# ---------- محاسبه‌ی رنگ ----------

class EstimateRequest(BaseModel):
    wall_area_m2: float | None = None
    room_width_m: float | None = None
    room_length_m: float | None = None
    room_height_m: float = 2.9
    openings_m2: float = 0.0
    coats: int = 2
    code: str | None = None
    coverage_m2_per_l: float | None = None
    price_per_l: float | None = None


@app.post("/api/estimate")
def api_estimate(req: EstimateRequest) -> dict:
    coverage = req.coverage_m2_per_l or (coverage_for(req.code) if req.code else 9.0)
    try:
        result = estimate(
            EstimateInput(
                wall_area_m2=req.wall_area_m2,
                room_width_m=req.room_width_m,
                room_length_m=req.room_length_m,
                room_height_m=req.room_height_m,
                openings_m2=req.openings_m2,
                coats=req.coats,
                coverage_m2_per_l=coverage,
                price_per_l=req.price_per_l,
            )
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.log_event("estimate", color_code=req.code)
    return result


# ---------- لید فروش ----------

class LeadRequest(BaseModel):
    name: str
    phone: str
    city: str = ""
    note: str = ""


@app.post("/api/lead")
def api_lead(req: LeadRequest) -> dict:
    if len(req.phone.strip()) < 7:
        raise HTTPException(400, "شماره تماس معتبر نیست")
    db.add_lead(req.name.strip(), req.phone.strip(), req.city.strip(), req.note.strip())
    db.log_event("lead")
    return {"ok": True}


# ---------- آمار (داشبورد مدیریت) ----------

@app.get("/api/stats")
def api_stats() -> dict:
    return db.stats()


# ---------- فایل‌های استاتیک ----------

@app.get("/admin")
def admin_page() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "admin.html")


if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
