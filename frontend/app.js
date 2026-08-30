"use strict";

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);
const MAX_SIDE = 1280;

const S = {
  mode: null,            // 'photo' | 'scene'
  orig: null,            // ImageBitmap | HTMLCanvasElement (منبع اصلی)
  W: 0, H: 0,
  mask: null,            // Uint8ClampedArray (0/255) هم‌اندازه‌ی نمایش
  svg: null,             // SVGElement صحنه
  sceneName: null,
  color: null,           // { code, name, hex, product }
  lighting: "natural",
  strength: 1.0,
  surface: "wall",       // wall | wall_ceiling | ceiling
  tool: "none",
  brush: 34,
  zoom: 1, panX: 0, panY: 0,
  origData: null,
  baShown: false,
  resultURL: null,
  catalog: null,
  filterFamily: null,
  filterCollection: null,
};

/* ---------------- Catalog ---------------- */

async function loadCatalog() {
  const res = await fetch("/api/catalog");
  S.catalog = await res.json();
  renderCollections();
  renderFamilies();
  renderSwatches();
}

function renderCollections() {
  const wrap = $("#collections");
  wrap.innerHTML = "";
  const all = document.createElement("button");
  all.textContent = "همه رنگ‌ها";
  all.className = S.filterCollection ? "" : "active";
  all.onclick = () => { S.filterCollection = null; renderCollections(); renderSwatches(); };
  wrap.appendChild(all);
  S.catalog.collections.forEach((c) => {
    const b = document.createElement("button");
    b.textContent = c.name;
    b.className = S.filterCollection === c.id ? "active" : "";
    b.onclick = () => {
      S.filterCollection = S.filterCollection === c.id ? null : c.id;
      S.filterFamily = null;
      renderCollections(); renderFamilies(); renderSwatches();
    };
    wrap.appendChild(b);
  });
}

function renderFamilies() {
  const wrap = $("#families");
  wrap.innerHTML = "";
  S.catalog.families.forEach((f) => {
    const b = document.createElement("button");
    b.textContent = f.name;
    b.className = S.filterFamily === f.id ? "active" : "";
    b.onclick = () => {
      S.filterFamily = S.filterFamily === f.id ? null : f.id;
      renderFamilies(); renderSwatches();
    };
    wrap.appendChild(b);
  });
}

function visibleColors() {
  let list = S.catalog.colors;
  const q = $("#search").value.trim().toLowerCase();
  if (S.filterCollection) {
    const col = S.catalog.collections.find((c) => c.id === S.filterCollection);
    list = list.filter((c) => col.codes.includes(c.code));
  }
  if (S.filterFamily) list = list.filter((c) => c.family === S.filterFamily);
  if (q) list = list.filter((c) => c.code.toLowerCase().includes(q) || c.name.toLowerCase().includes(q));
  return list;
}

function renderSwatches() {
  const wrap = $("#swatches");
  wrap.innerHTML = "";
  visibleColors().forEach((c) => {
    const el = document.createElement("button");
    el.className = "swatch" + (S.color && S.color.code === c.code ? " active" : "");
    el.style.background = c.hex;
    el.title = `${c.name} — ${c.code}`;
    el.onclick = () => selectColor(c);
    wrap.appendChild(el);
  });
  renderQuickColors();
}

function renderQuickColors() {
  const wrap = $("#quickColors");
  if (!wrap || !S.catalog) return;
  wrap.innerHTML = "";
  visibleColors().slice(0, 16).forEach((c) => {
    const b = document.createElement("button");
    b.style.background = c.hex;
    b.title = `${c.name} — ${c.code}`;
    b.className = S.color && S.color.code === c.code ? "active" : "";
    b.onclick = () => { selectColor(c); applyColor(); };
    wrap.appendChild(b);
  });
}

function selectColor(c) {
  S.color = c;
  renderSwatches();
  renderQuickColors();
  $("#selected").hidden = false;
  $("#selChip").style.background = c.hex;
  $("#selName").textContent = c.name;
  const prod = (S.catalog.products.find((p) => p.id === c.product) || {}).name || "";
  $("#selCode").textContent = `${c.code}${prod ? " · " + prod : ""}`;
  refreshApply();
}

/* ---------------- منبع تصویر ---------------- */

async function useFile(file) {
  if (!file || !file.type.startsWith("image/")) return;
  const bmp = await createImageBitmap(file);
  let { width: w, height: h } = bmp;
  if (Math.max(w, h) > MAX_SIDE) {
    const s = MAX_SIDE / Math.max(w, h);
    w = Math.round(w * s); h = Math.round(h * s);
  }
  const cv = document.createElement("canvas");
  cv.width = w; cv.height = h;
  cv.getContext("2d").drawImage(bmp, 0, 0, w, h);
  S.mode = "photo";
  S.orig = cv; S.W = w; S.H = h;
  S.resultURL = null; S.svg = null; S.sceneName = null; S.baShown = false;
  enterEditor();
  await autoMask();
}

// فضاهای نمونه = عکس واقعیِ لوکس + ماسک از پیش‌محاسبه‌شده (سریع و دقیق).
async function useScene(name) {
  spin(true);
  try {
    const bmp = await createImageBitmap(await (await fetch(`/scenes/${name}.jpg`)).blob());
    const cv = document.createElement("canvas");
    cv.width = bmp.width; cv.height = bmp.height;
    cv.getContext("2d").drawImage(bmp, 0, 0);
    S.mode = "photo";
    S.orig = cv; S.W = bmp.width; S.H = bmp.height;
    S.svg = null; S.sceneName = name;
    S.resultURL = null; S.baShown = false; S.surface = "wall";
    enterEditor();

    const mbmp = await createImageBitmap(await (await fetch(`/scenes/${name}.mask.png`)).blob());
    const t = document.createElement("canvas");
    t.width = S.W; t.height = S.H;
    const tc = t.getContext("2d");
    tc.drawImage(mbmp, 0, 0, S.W, S.H);
    const md = tc.getImageData(0, 0, S.W, S.H).data;
    S.mask = new Uint8ClampedArray(S.W * S.H);
    for (let i = 0; i < S.mask.length; i++) S.mask[i] = md[i * 4] > 128 ? 1 : 0;
    setTool("none");
    if (S.color) applyColor();
  } catch (e) {
    toast("بارگذاری فضای نمونه ناموفق بود", true);
  } finally {
    spin(false);
  }
}

/* ---------------- Editor / Canvas ---------------- */

const photoCanvas = $("#photoCanvas");
const maskCanvas = $("#maskCanvas");
const pctx = photoCanvas.getContext("2d");
const mctx = maskCanvas.getContext("2d");

function enterEditor() {
  $("#start").hidden = true;
  $("#editor").hidden = false;
  $("#toolbar").querySelectorAll(".tool, #btnAuto").forEach((b) => (b.style.display = ""));
  sizeCanvases();
  $("#resultActions").hidden = true;
  $("#stageControls").hidden = false;
  
  renderQuickColors();
  showBA(false);
  ensureFsButton();
}

function sizeCanvases() {
  [photoCanvas, maskCanvas].forEach((c) => { c.width = S.W; c.height = S.H; });
  if (S.orig) {
    draw(S.orig);
    const t = document.createElement("canvas");
    t.width = S.W; t.height = S.H;
    const tc = t.getContext("2d");
    tc.drawImage(S.orig, 0, 0);
    S.origData = tc.getImageData(0, 0, S.W, S.H).data;
  }
  setZoom(1);
  redrawMask();
}

function draw(src) {
  pctx.clearRect(0, 0, S.W, S.H);
  pctx.drawImage(src, 0, 0, S.W, S.H);
}

function flashReveal() {
  photoCanvas.classList.remove("reveal");
  void photoCanvas.offsetWidth;
  photoCanvas.classList.add("reveal");
}

function setResultURL(url) {
  if (S.resultURL && S.resultURL.startsWith("blob:")) URL.revokeObjectURL(S.resultURL);
  S.resultURL = url;
}

function redrawMask() {
  mctx.clearRect(0, 0, S.W, S.H);
  if (!S.mask || S.tool === "none") return;
  // ناحیهٔ ماسک با رنگِ انتخابی پیش‌نمایش می‌شود تا کاربر دقیقاً ببیند کجا رنگ می‌خورد
  const hex = (S.color && S.color.hex) || "#3aa0ff";
  const cr = parseInt(hex.slice(1, 3), 16);
  const cg = parseInt(hex.slice(3, 5), 16);
  const cb = parseInt(hex.slice(5, 7), 16);
  const img = mctx.createImageData(S.W, S.H);
  const d = img.data;
  const W = S.W;
  for (let i = 0; i < S.mask.length; i++) {
    if (!S.mask[i]) continue;
    // لبهٔ ماسک را پررنگ‌تر نشان بده
    const x = i % W, y = (i / W) | 0;
    const edge =
      x === 0 || y === 0 || x === W - 1 ||
      !S.mask[i - 1] || !S.mask[i + 1] || !S.mask[i - W] || !S.mask[i + W];
    d[i * 4] = cr; d[i * 4 + 1] = cg; d[i * 4 + 2] = cb;
    d[i * 4 + 3] = edge ? 235 : 120;
  }
  mctx.putImageData(img, 0, 0);
}

async function autoMask() {
  if (S.mode !== "photo") return;
  spin(true);
  try {
    const fd = new FormData();
    fd.append("image", await canvasBlob(S.orig));
    fd.append("part", S.surface);
    const res = await fetch("/api/mask", { method: "POST", body: fd });
    if (!res.ok) throw new Error("تشخیص دیوار ناموفق بود");
    const bmp = await createImageBitmap(await res.blob());
    const tmp = document.createElement("canvas");
    tmp.width = S.W; tmp.height = S.H;
    const tctx = tmp.getContext("2d");
    tctx.drawImage(bmp, 0, 0, S.W, S.H);
    const d = tctx.getImageData(0, 0, S.W, S.H).data;
    S.mask = new Uint8ClampedArray(S.W * S.H);
    for (let i = 0; i < S.mask.length; i++) S.mask[i] = d[i * 4] > 128 ? 1 : 0;
    setTool("none");
    redrawMask();
  } catch (e) {
    toast(e.message, true);
  } finally {
    spin(false);
  }
}

/* ---- Brush ---- */

let painting = false;

function canvasPos(ev) {
  const r = maskCanvas.getBoundingClientRect();
  const p = ev.touches ? ev.touches[0] : ev;
  return {
    x: ((p.clientX - r.left) / r.width) * S.W,
    y: ((p.clientY - r.top) / r.height) * S.H,
  };
}

const COLOR_TOL2 = 44 * 44; // شعاع شباهت رنگ برای قلم هوشمند

function _cdist2(idx, seed) {
  const d = S.origData, o = idx * 4;
  const r = d[o] - seed[0], g = d[o + 1] - seed[1], b = d[o + 2] - seed[2];
  return r * r + g * g + b * b;
}

// قلم هوشمند: فقط پیکسل‌هایی را تغییر می‌دهد که رنگشان به نقطهٔ مرکز شبیه است،
// پس روی لبهٔ کمد/قاب/مبل بکشی، فقط همان جسم انتخاب می‌شود نه دیوار کنارش.
function paintAt(x, y) {
  if (!S.mask) S.mask = new Uint8ClampedArray(S.W * S.H);
  x |= 0; y |= 0;
  const W = S.W, H = S.H;
  if (x < 0 || y < 0 || x >= W || y >= H) return;
  const rad = (S.brush / maskCanvas.getBoundingClientRect().width) * S.W;
  const val = S.tool === "add" ? 1 : 0;
  const seed = S.origData ? [S.origData[(y * W + x) * 4], S.origData[(y * W + x) * 4 + 1], S.origData[(y * W + x) * 4 + 2]] : null;
  const r2 = rad * rad;
  const x0 = Math.max(0, x - rad | 0), x1 = Math.min(W, x + rad | 0);
  const y0 = Math.max(0, y - rad | 0), y1 = Math.min(H, y + rad | 0);
  for (let yy = y0; yy < y1; yy++)
    for (let xx = x0; xx < x1; xx++) {
      const dx = xx - x, dy = yy - y;
      if (dx * dx + dy * dy > r2) continue;
      const idx = yy * W + xx;
      if (seed && _cdist2(idx, seed) > COLOR_TOL2) continue;
      S.mask[idx] = val;
    }
  redrawMask();
}

// یک کلیک (بدون کشیدن) = انتخاب هوشمندِ کلِ آن تکه: از نقطهٔ کلیک، ناحیهٔ هم‌رنگِ
// متصل را دنبال می‌کند و دقیقاً همان جسم/لکه را خط‌کشی می‌کند. محدود به اطراف کلیک.
function smartFill(x, y) {
  if (!S.origData) { return; }
  if (!S.mask) S.mask = new Uint8ClampedArray(S.W * S.H);
  x |= 0; y |= 0;
  const W = S.W, H = S.H;
  if (x < 0 || y < 0 || x >= W || y >= H) return;
  const seed = [S.origData[(y * W + x) * 4], S.origData[(y * W + x) * 4 + 1], S.origData[(y * W + x) * 4 + 2]];
  const val = S.tool === "add" ? 1 : 0;
  const reach = Math.max(70, (S.brush / maskCanvas.getBoundingClientRect().width) * S.W * 3.5);
  const reach2 = reach * reach;
  const seen = new Uint8Array(W * H);
  const stack = [y * W + x];
  let guard = 0, maxGuard = W * H;
  while (stack.length && guard++ < maxGuard) {
    const idx = stack.pop();
    if (seen[idx]) continue;
    seen[idx] = 1;
    const ix = idx % W, iy = (idx / W) | 0;
    const dx = ix - x, dy = iy - y;
    if (dx * dx + dy * dy > reach2) continue;
    if (_cdist2(idx, seed) > COLOR_TOL2 * 1.3) continue;
    S.mask[idx] = val;
    if (ix > 0) stack.push(idx - 1);
    if (ix < W - 1) stack.push(idx + 1);
    if (iy > 0) stack.push(idx - W);
    if (iy < H - 1) stack.push(idx + W);
  }
  redrawMask();
}

let _downXY = null, _moved = false;
function startPaint(ev) {
  if (S.tool === "none") return;
  ev.preventDefault();
  painting = true; _moved = false;
  const { x, y } = canvasPos(ev);
  _downXY = { x, y };
  paintAt(x, y);
}
function movePaint(ev) {
  if (!painting) return;
  ev.preventDefault();
  const { x, y } = canvasPos(ev);
  if (_downXY && Math.hypot(x - _downXY.x, y - _downXY.y) > 5) _moved = true;
  paintAt(x, y);
}
let _brushApply = null;
function endPaint() {
  if (!painting) return;
  painting = false;
  if (!_moved && _downXY) smartFill(_downXY.x, _downXY.y);
  if (S.mode === "photo" && S.color && S.resultURL) {
    clearTimeout(_brushApply);
    _brushApply = setTimeout(() => applyColor({ keepTool: true }), 450);
  }
}

maskCanvas.addEventListener("mousedown", startPaint);
maskCanvas.addEventListener("mousemove", movePaint);
window.addEventListener("mouseup", endPaint);
maskCanvas.addEventListener("touchstart", startPaint, { passive: false });
maskCanvas.addEventListener("touchmove", movePaint, { passive: false });
window.addEventListener("touchend", endPaint);

const TOOL_HINTS = {
  none: "قلم خاموش است. برای اصلاح، «افزودن دیوار» یا «پاک‌کردن» را بزن.",
  add: "🖌 روی دیواری که رنگ نخورده بکش. وقتی قلم را رها کنی، خودکار اعمال می‌شود.",
  erase: "🩹 روی جایی که اشتباهی رنگ خورده بکش. وقتی قلم را رها کنی، خودکار اعمال می‌شود.",
};

function setTool(t) {
  S.tool = t;
  $$(".tool").forEach((b) => b.classList.toggle("active", b.dataset.tool === t));
  maskCanvas.style.cursor = t === "none" ? "default" : "crosshair";
  maskCanvas.style.pointerEvents = t === "none" ? "none" : "auto";
  const hint = $("#toolHint");
  if (hint) hint.textContent = TOOL_HINTS[t] || "";
  redrawMask();
}

/* ---------------- Apply color ---------------- */

async function applyColor(opts = {}) {
  if (!S.color || !S.mask) return;
  spin(true);
  try {
    const fd = new FormData();
    fd.append("image", await canvasBlob(S.orig));
    fd.append("code", S.color.code);
    fd.append("lighting", S.lighting);
    fd.append("strength", String(S.strength));
    fd.append("mask", await maskBlob());
    const res = await fetch("/api/visualize", { method: "POST", body: fd });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "خطا در پردازش");
    const blob = await res.blob();
    setResultURL(URL.createObjectURL(blob));
    const bmp = await createImageBitmap(blob);
    draw(bmp);
    flashReveal();
    showBA(true);
    $("#resultActions").hidden = false;
    if (opts.keepTool && S.tool !== "none") {
      redrawMask();
      toast("به‌روزرسانی شد — می‌توانی باز هم اصلاح کنی");
    } else {
      setTool("none");
      toast("انجام شد — نوار زیر تصویر را بکش تا قبل و بعد را ببینی");
    }
  } catch (e) {
    toast(e.message, true);
  } finally {
    spin(false);
  }
}

/* ---------------- Before / After ---------------- */

function showBA(on) {
  $("#baRow").hidden = !on;
  if (!on) { $("#baOrig")?.remove(); S.baShown = false; return; }
  if (!S.baShown) { $("#baRange").value = 50; S.baShown = true; }
  updateBA();
}

function updateBA() {
  const v = +$("#baRange").value;
  let orig = $("#baOrig");
  if (!orig) {
    orig = document.createElement("canvas");
    orig.id = "baOrig";
    photoCanvas.parentElement.insertBefore(orig, maskCanvas);
  }
  orig.width = S.W; orig.height = S.H;
  orig.getContext("2d").drawImage(S.orig, 0, 0, S.W, S.H);
  // v=100 → فقط نتیجه؛ v=0 → فقط تصویر اصلی. سمت چپ = قبل.
  orig.style.clipPath = `inset(0 0 0 ${v}%)`;
}
$("#baRange").addEventListener("input", updateBA);

/* ---------------- Helpers ---------------- */

function canvasBlob(cv) {
  return new Promise((r) => cv.toBlob(r, "image/jpeg", 0.92));
}
function maskCanvasEl() {
  const cv = document.createElement("canvas");
  cv.width = S.W; cv.height = S.H;
  const c = cv.getContext("2d");
  const img = c.createImageData(S.W, S.H);
  for (let i = 0; i < S.mask.length; i++) {
    const v = S.mask[i] ? 255 : 0;
    img.data[i * 4] = img.data[i * 4 + 1] = img.data[i * 4 + 2] = v;
    img.data[i * 4 + 3] = 255;
  }
  c.putImageData(img, 0, 0);
  return cv;
}
function maskBlob() { return new Promise((r) => maskCanvasEl().toBlob(r, "image/png")); }
function maskDataURL() { return maskCanvasEl().toDataURL("image/png"); }

const MAGIC_STEPS = [
  "اتصال به موتور هوش مصنوعی",
  "تشخیص دیوارها در تصویر",
  "شبیه‌سازی رنگ روی سطح",
  "نهایی‌سازی نور و سایه",
];
let _magicTimer = null, _sparkTimer = null;

function magic(on) {
  const box = $("#magic");
  if (!on) {
    box.hidden = true;
    clearInterval(_magicTimer); clearInterval(_sparkTimer);
    return;
  }
  box.hidden = false;
  let i = 0;
  const status = $("#magicStatus");
  const steps = $$("#magicSteps i");
  const tick = () => {
    status.textContent = MAGIC_STEPS[Math.min(i, MAGIC_STEPS.length - 1)];
    steps.forEach((s, k) => s.classList.toggle("on", k <= i));
    i++;
  };
  tick();
  clearInterval(_magicTimer);
  _magicTimer = setInterval(tick, 1400);

  const sparks = $("#sparks");
  clearInterval(_sparkTimer);
  _sparkTimer = setInterval(() => {
    const s = document.createElement("span");
    s.className = "spark";
    s.style.left = 20 + Math.random() * 60 + "%";
    s.style.top = 40 + Math.random() * 30 + "%";
    sparks.appendChild(s);
    setTimeout(() => s.remove(), 1500);
  }, 180);
}
function spin(on) { magic(on); }
function toast(msg, err) {
  const el = $("#leadMsg");
  // پیام کوتاه در نوار پایین صحنه
  let t = $("#sceneToast");
  if (!t) {
    t = document.createElement("div");
    t.id = "sceneToast";
    t.style.cssText =
      "position:absolute;bottom:10px;right:10px;left:10px;background:rgba(0,0,0,.72);color:#fff;padding:8px 12px;border-radius:9px;font-size:12.5px;text-align:center;z-index:9";
    $("#canvasWrap").appendChild(t);
  }
  t.textContent = msg;
  t.style.background = err ? "rgba(214,0,28,.85)" : "rgba(0,0,0,.72)";
  t.hidden = false;
  clearTimeout(t._to);
  t._to = setTimeout(() => (t.hidden = true), 3800);
}

function refreshApply() {
  $("#btnApply").disabled = !(S.color && S.mask);
}

function setZoom(z, cx, cy) {
  S.zoom = Math.min(4, Math.max(1, Math.round(z * 20) / 20));
  const wrap = $("#canvasWrap");
  wrap.style.setProperty("--zoom", S.zoom);
  if (S.zoom === 1) { S.panX = 0; S.panY = 0; }
  wrap.style.setProperty("--panx", (S.panX || 0) + "px");
  wrap.style.setProperty("--pany", (S.panY || 0) + "px");
  const zr = $("#zoomRange");
  if (zr) zr.value = Math.round(S.zoom * 100);
}

function ensureFsButton() {
  if ($("#stageTools")) return;
  const wrap = $("#canvasWrap");
  const box = document.createElement("div");
  box.id = "stageTools";
  box.className = "stage-tools";
  box.innerHTML = `
    <button id="fsBtn" title="تمام‌صفحه">⛶</button>
    <button id="zoomOut" title="کوچک‌نمایی">−</button>
    <input type="range" id="zoomRange" min="100" max="400" value="100" title="بزرگ‌نمایی" />
    <button id="zoomIn" title="بزرگ‌نمایی">+</button>`;
  wrap.appendChild(box);

  $("#fsBtn").onclick = () => {
    if (document.fullscreenElement) document.exitFullscreen();
    else wrap.requestFullscreen?.();
  };
  $("#zoomRange").oninput = (e) => setZoom(+e.target.value / 100);
  $("#zoomIn").onclick = () => setZoom((S.zoom || 1) + 0.25);
  $("#zoomOut").onclick = () => setZoom((S.zoom || 1) - 0.25);

  wrap.addEventListener("wheel", (e) => {
    if (!S.orig) return;
    e.preventDefault();
    setZoom((S.zoom || 1) + (e.deltaY < 0 ? 0.2 : -0.2));
  }, { passive: false });

  // کشیدن برای جابه‌جایی وقتی بزرگ‌نمایی فعال است و قلم خاموش است
  let dragging = false, sx = 0, sy = 0;
  wrap.addEventListener("mousedown", (e) => {
    if (S.tool !== "none" || (S.zoom || 1) === 1) return;
    dragging = true; sx = e.clientX; sy = e.clientY;
  });
  window.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    S.panX = (S.panX || 0) + (e.clientX - sx);
    S.panY = (S.panY || 0) + (e.clientY - sy);
    sx = e.clientX; sy = e.clientY;
    setZoom(S.zoom);
  });
  window.addEventListener("mouseup", () => (dragging = false));
}

/* ---------------- Proposal card ---------------- */

async function makeCard() {
  const cv = $("#cardCanvas");
  cv.width = 1080; cv.height = 1350;
  const c = cv.getContext("2d");
  c.fillStyle = "#ffffff";
  c.fillRect(0, 0, 1080, 1350);

  // هدر
  c.fillStyle = "#d6001c";
  c.fillRect(0, 0, 1080, 120);
  c.fillStyle = "#fff";
  c.font = "800 44px Vazirmatn, sans-serif";
  c.textAlign = "right";
  c.fillText("رنگ‌نما", 1040, 76);
  c.font = "500 22px Vazirmatn, sans-serif";
  c.fillText("پیش‌نمای هوشمند رنگ ساختمانی", 1040, 104);

  // تصویر نتیجه
  const resImg = await loadImg(S.resultURL || S.orig.toDataURL());
  const iw = 1000, ih = Math.round((iw * S.H) / S.W);
  c.drawImage(resImg, 40, 150, iw, Math.min(ih, 720));

  let y = 150 + Math.min(ih, 720) + 50;

  // رنگ‌های استفاده‌شده
  c.fillStyle = "#1b1b1e";
  c.font = "700 28px Vazirmatn, sans-serif";
  c.fillText("رنگ‌های انتخابی", 1040, y);
  y += 20;
  const used = S.color ? [S.color] : [];
  const uniq = [...new Map(used.map((u) => [u.code, u])).values()];
  uniq.forEach((u) => {
    y += 46;
    c.fillStyle = u.hex;
    c.fillRect(1000 - 40, y - 30, 40, 40);
    c.strokeStyle = "#ddd";
    c.strokeRect(1000 - 40, y - 30, 40, 40);
    c.fillStyle = "#1b1b1e";
    c.font = "600 24px Vazirmatn, sans-serif";
    c.fillText(`${u.name}`, 940, y);
    c.fillStyle = "#6c7078";
    c.font = "400 20px Vazirmatn, sans-serif";
    c.fillText(`${u.code}`, 940, y + 26);
  });

  // برآورد رنگ
  if (S.lastEstimate) {
    y += 70;
    c.fillStyle = "#1b1b1e";
    c.font = "700 26px Vazirmatn, sans-serif";
    c.fillText(
      `برآورد رنگ: حدود ${S.lastEstimate.liters_needed} لیتر (${S.lastEstimate.coats} دست)`,
      1040, y
    );
  }

  // فوتر
  c.fillStyle = "#f2f2f3";
  c.fillRect(0, 1270, 1080, 80);
  c.fillStyle = "#6c7078";
  c.font = "400 20px Vazirmatn, sans-serif";
  c.fillText("مشاوره و خرید: نمایندگی‌های مجاز — رنگ نمایش‌داده‌شده تقریبی است", 1040, 1316);

  const a = document.createElement("a");
  a.href = cv.toDataURL("image/png");
  a.download = "rangnama-proposal.png";
  a.click();
}

function loadImg(src) {
  return new Promise((res) => {
    const i = new Image();
    i.crossOrigin = "anonymous";
    i.onload = () => res(i);
    i.src = src;
  });
}

/* ---------------- Calculator ---------------- */

async function calc() {
  const body = {
    room_width_m: parseFloat($("#cW").value) || null,
    room_length_m: parseFloat($("#cL").value) || null,
    room_height_m: parseFloat($("#cH").value) || 2.9,
    openings_m2: parseFloat($("#cO").value) || 0,
    coats: parseInt($("#cCoats").value) || 2,
    code: S.color ? S.color.code : null,
    price_per_l: parseFloat($("#cPrice").value) || null,
  };
  const res = await fetch("/api/estimate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const box = $("#calcResult");
  if (!res.ok) {
    box.hidden = false;
    box.innerHTML = `<span style="color:#d6001c">${(await res.json()).detail}</span>`;
    return;
  }
  const d = await res.json();
  S.lastEstimate = d;
  const cans = d.cans
    .map((x) => `<div class="calc-row"><span>${x.label}</span><span>${x.count} عدد</span></div>`)
    .join("");
  box.hidden = false;
  box.innerHTML = `
    <div class="calc-big">${d.liters_needed} لیتر</div>
    <div class="calc-row"><span>سطح قابل رنگ</span><span>${d.paintable_area_m2} م²</span></div>
    <div class="calc-row"><span>تعداد دست</span><span>${d.coats}</span></div>
    <div class="calc-row"><span>پوشش هر لیتر</span><span>${d.coverage_m2_per_l} م²</span></div>
    ${cans}
    <div class="calc-row"><span>مجموع بسته‌بندی</span><span>${d.cans_total_liters} لیتر</span></div>
    ${d.price_estimate ? `<div class="calc-row"><b>برآورد هزینه</b><b>${d.price_estimate.toLocaleString("fa-IR")} تومان</b></div>` : ""}
  `;
}

/* ---------------- Lead ---------------- */

async function submitLead() {
  const body = {
    name: $("#lName").value.trim(),
    phone: $("#lPhone").value.trim(),
    city: $("#lCity").value.trim(),
    note: $("#lNote").value.trim(),
  };
  const msg = $("#leadMsg");
  const res = await fetch("/api/lead", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  msg.hidden = false;
  if (res.ok) {
    msg.className = "lead-msg";
    msg.textContent = "درخواست ثبت شد. همکاران ما با شما تماس می‌گیرند.";
    ["lName", "lPhone", "lCity", "lNote"].forEach((id) => ($("#" + id).value = ""));
  } else {
    msg.className = "lead-msg err";
    msg.textContent = (await res.json()).detail || "خطا در ثبت";
  }
}

/* ---------------- Wiring ---------------- */

function wire() {
  $("#btnPick").onclick = (e) => { e.stopPropagation(); $("#fileInput").click(); };
  $("#btnCam").onclick = (e) => { e.stopPropagation(); $("#camInput").click(); };
  $("#dropzone").onclick = () => $("#fileInput").click();
  $$(".scene-card").forEach((b) => (b.onclick = (e) => {
    e.stopPropagation();
    useScene(b.dataset.scene);
  }));
  $("#fileInput").onchange = (e) => useFile(e.target.files[0]);
  $("#camInput").onchange = (e) => useFile(e.target.files[0]);

  ["dragenter", "dragover"].forEach((ev) =>
    $("#dropzone").addEventListener(ev, (e) => { e.preventDefault(); $("#dropzone").classList.add("over"); })
  );
  ["dragleave", "drop"].forEach((ev) =>
    $("#dropzone").addEventListener(ev, (e) => { e.preventDefault(); $("#dropzone").classList.remove("over"); })
  );
  $("#dropzone").addEventListener("drop", (e) => useFile(e.dataTransfer.files[0]));

  $$(".tool").forEach((b) => (b.onclick = () => setTool(b.dataset.tool)));
  $("#brushSize").oninput = (e) => (S.brush = +e.target.value);
  $("#btnAuto").onclick = autoMask;
  $("#btnNew").onclick = () => location.reload();

  $("#search").oninput = renderSwatches;
  $("#btnApply").onclick = applyColor;
  $("#btnDownload").onclick = () => {
    const a = document.createElement("a");
    a.href = S.resultURL || S.orig.toDataURL();
    a.download = "rangnama-preview.jpg";
    a.click();
  };
  $("#btnCard").onclick = makeCard;

  $$("#lighting button").forEach((b) => (b.onclick = () => {
    S.lighting = b.dataset.l;
    $$("#lighting button").forEach((x) => x.classList.toggle("active", x === b));
    if (S.resultURL) applyColor({ keepTool: true });
  }));

  $$("#surface button").forEach((b) => (b.onclick = async () => {
    S.surface = b.dataset.p;
    $$("#surface button").forEach((x) => x.classList.toggle("active", x === b));
    if (S.mode !== "photo") return;
    await autoMask();               // ماسک متناسب با سطح انتخابی
    if (S.color) applyColor({ keepTool: true });
  }));

  const str = $("#strength");
  if (str) {
    const faNum = (n) => Number(n).toLocaleString("fa-IR");
    str.oninput = () => { $("#strengthVal").textContent = faNum(str.value) + "٪"; };
    str.onchange = () => {
      S.strength = +str.value / 100;
      if (S.resultURL) applyColor({ keepTool: true });
    };
  }

  $$(".tab").forEach((t) => (t.onclick = () => {
    $$(".tab").forEach((x) => x.classList.toggle("active", x === t));
    $$(".tabpane").forEach((p) => (p.hidden = p.dataset.pane !== t.dataset.tab));
  }));

  $("#btnCalc").onclick = calc;
  $("#btnLead").onclick = submitLead;

  const tt = $("#themeToggle");
  try {
    const saved = localStorage.getItem("rangnama-theme");
    if (saved) document.documentElement.dataset.theme = saved;
  } catch (e) {}
  if (tt) tt.onclick = () => {
    const cur = document.documentElement.dataset.theme === "light" ? "light" : "dark";
    const next = cur === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("rangnama-theme", next); } catch (e) {}
  };
}

wire();
loadCatalog();
setTool("none");
