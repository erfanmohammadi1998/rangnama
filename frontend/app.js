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
  tool: "none",
  brush: 34,
  layers: [],            // [{code,name,hex, maskURL}]
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
  if (S.mode === "scene") applySceneColor();
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
  S.layers = []; S.resultURL = null; S.svg = null; S.sceneName = null;
  enterEditor();
  await autoMask();
}

async function useScene(name) {
  const res = await fetch(`/scenes/${name}.svg`);
  const txt = await res.text();
  const holder = document.createElement("div");
  holder.innerHTML = txt;
  const svg = holder.querySelector("svg");
  svg.setAttribute("width", "1200");
  svg.setAttribute("height", "900");
  svg.removeAttribute("style");
  S.mode = "scene";
  S.svg = svg; S.sceneName = name;
  S.W = 1200; S.H = 900;
  S.layers = []; S.resultURL = null; S.mask = null;
  enterEditor();
  setTool("none");
  $("#toolbar").querySelectorAll(".tool, #btnAuto").forEach((b) => (b.style.display = "none"));
  await rasterizeScene();
  if (S.color) applySceneColor();
}

function svgToBlobURL(svg) {
  let xml = new XMLSerializer().serializeToString(svg);
  if (!xml.startsWith("<?xml")) xml = '<?xml version="1.0" encoding="UTF-8"?>' + xml;
  return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(xml);
}

function rasterizeSVG() {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const cv = document.createElement("canvas");
      cv.width = S.W; cv.height = S.H;
      const c = cv.getContext("2d");
      c.fillStyle = "#ffffff";
      c.fillRect(0, 0, S.W, S.H);
      c.drawImage(img, 0, 0, S.W, S.H);
      resolve(cv);
    };
    img.onerror = () => reject(new Error("خطا در بارگذاری فضای نمونه"));
    img.src = svgToBlobURL(S.svg);
  });
}

async function rasterizeScene() {
  const cv = await rasterizeSVG();
  S.orig = cv;
  draw(cv);
}

async function applySceneColor() {
  if (!S.svg || !S.color) return;
  S.svg.querySelectorAll(".wall").forEach((el) => el.setAttribute("fill", S.color.hex));
  try {
    const cv = await rasterizeSVG();
    setResultURL(cv.toDataURL("image/jpeg", 0.92));
    draw(cv);
    flashReveal();
    showBA(true);
    $("#resultActions").hidden = false;
  } catch (e) {
    toast(e.message, true);
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
  $("#btnAddWall").hidden = true;
  $("#appliedList").innerHTML = "";
  $("#resultActions").hidden = true;
  $("#stageControls").hidden = false;
  $$("#stageControls .sc-group:not(.grow)").forEach((g) => (g.hidden = S.mode === "scene"));
  renderQuickColors();
  showBA(false);
  ensureFsButton();
}

function sizeCanvases() {
  [photoCanvas, maskCanvas].forEach((c) => { c.width = S.W; c.height = S.H; });
  if (S.orig) draw(S.orig);
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
  const img = mctx.createImageData(S.W, S.H);
  for (let i = 0; i < S.mask.length; i++) {
    const v = S.mask[i];
    img.data[i * 4] = 214;
    img.data[i * 4 + 1] = 0;
    img.data[i * 4 + 2] = 28;
    img.data[i * 4 + 3] = v ? 90 : 0;
  }
  mctx.putImageData(img, 0, 0);
}

async function autoMask() {
  if (S.mode !== "photo") return;
  spin(true);
  try {
    const fd = new FormData();
    fd.append("image", await canvasBlob(S.orig));
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

function paintAt(x, y) {
  if (!S.mask) S.mask = new Uint8ClampedArray(S.W * S.H);
  const rad = (S.brush / maskCanvas.getBoundingClientRect().width) * S.W;
  const val = S.tool === "add" ? 1 : 0;
  const x0 = Math.max(0, (x - rad) | 0), x1 = Math.min(S.W, (x + rad) | 0);
  const y0 = Math.max(0, (y - rad) | 0), y1 = Math.min(S.H, (y + rad) | 0);
  const r2 = rad * rad;
  for (let yy = y0; yy < y1; yy++)
    for (let xx = x0; xx < x1; xx++) {
      const dx = xx - x, dy = yy - y;
      if (dx * dx + dy * dy <= r2) S.mask[yy * S.W + xx] = val;
    }
  redrawMask();
}

function startPaint(ev) {
  if (S.tool === "none") return;
  ev.preventDefault();
  painting = true;
  const { x, y } = canvasPos(ev);
  paintAt(x, y);
}
function movePaint(ev) {
  if (!painting) return;
  ev.preventDefault();
  const { x, y } = canvasPos(ev);
  paintAt(x, y);
}
let _brushApply = null;
function endPaint() {
  if (!painting) return;
  painting = false;
  // بعد از رها کردن قلم، اگر قبلاً رنگ اعمال شده، خودکار به‌روزرسانی کن
  if (S.mode === "photo" && S.color && (S.resultURL || S.layers.length)) {
    clearTimeout(_brushApply);
    _brushApply = setTimeout(() => {
      S.layers.length ? renderMulti() : applyColor({ keepTool: true });
    }, 500);
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
  if (hint) hint.textContent = S.mode === "scene" ? "" : TOOL_HINTS[t] || "";
  redrawMask();
}

/* ---------------- Apply color ---------------- */

async function applyColor(opts = {}) {
  if (S.mode === "scene") { applySceneColor(); return; }
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
    $("#btnAddWall").hidden = false;
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

function addWallLayer() {
  if (!S.color || !S.mask) return;
  const url = maskDataURL();
  S.layers.push({ ...S.color, maskURL: url });
  S.mask = new Uint8ClampedArray(S.W * S.H);
  renderLayers();
  setTool("add");
  toast("دیوار بعدی را با قلم مشخص کن و رنگش را انتخاب کن");
}

function renderLayers() {
  const box = $("#appliedList");
  box.innerHTML = "";
  S.layers.forEach((l, idx) => {
    const row = document.createElement("div");
    row.className = "layer";
    row.innerHTML = `<i style="background:${l.hex}"></i> ${l.name} — ${l.code}`;
    const del = document.createElement("button");
    del.className = "btn tiny ghost";
    del.textContent = "حذف";
    del.onclick = () => { S.layers.splice(idx, 1); renderLayers(); renderMulti(); };
    row.appendChild(del);
    box.appendChild(row);
  });
  renderMulti();
}

async function renderMulti() {
  if (!S.layers.length) { draw(S.orig); showBA(false); return; }
  spin(true);
  try {
    const layers = [...S.layers];
    if (S.color && S.mask && S.mask.some((v) => v)) {
      layers.push({ ...S.color, maskURL: maskDataURL() });
    }
    const body = {
      image: S.orig.toDataURL("image/jpeg", 0.92),
      lighting: S.lighting,
      layers: layers.map((l) => ({ code: l.code, mask: l.maskURL })),
    };
    const res = await fetch("/api/visualize-multi", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error("خطا در ترکیب دیوارها");
    const blob = await res.blob();
    setResultURL(URL.createObjectURL(blob));
    draw(await createImageBitmap(blob));
    flashReveal();
    showBA(true);
    $("#resultActions").hidden = false;
  } catch (e) {
    toast(e.message, true);
  } finally {
    spin(false);
  }
}

/* ---------------- Before / After ---------------- */

function showBA(on) {
  $("#baRow").hidden = !on;
  if (on) { $("#baRange").value = 55; updateBA(); }
  else { photoCanvas.style.clipPath = "none"; $("#baOrig")?.remove(); }
}

function updateBA() {
  const v = +$("#baRange").value;
  let orig = $("#baOrig");
  if (!orig) {
    orig = document.createElement("canvas");
    orig.id = "baOrig";
    orig.width = S.W; orig.height = S.H;
    orig.getContext("2d").drawImage(S.orig, 0, 0, S.W, S.H);
    photoCanvas.parentElement.insertBefore(orig, maskCanvas);
  } else {
    orig.width = S.W; orig.height = S.H;
    orig.getContext("2d").drawImage(S.orig, 0, 0, S.W, S.H);
  }
  // سمت راست تصویر = «قبل»
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
  $("#btnApply").disabled = !(S.color && (S.mode === "scene" || S.mask));
}

function ensureFsButton() {
  if ($("#fsBtn")) return;
  const b = document.createElement("button");
  b.id = "fsBtn";
  b.className = "fs-btn";
  b.title = "تمام‌صفحه";
  b.textContent = "⛶";
  b.onclick = () => {
    const el = $("#canvasWrap");
    if (document.fullscreenElement) document.exitFullscreen();
    else el.requestFullscreen?.();
  };
  $("#canvasWrap").appendChild(b);
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
  const used = [...S.layers];
  if (S.color) used.push(S.color);
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
  $("#btnAddWall").onclick = addWallLayer;
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
    if (S.resultURL && S.mode !== "scene") (S.layers.length ? renderMulti() : applyColor());
  }));

  const str = $("#strength");
  if (str) {
    const faNum = (n) => Number(n).toLocaleString("fa-IR");
    str.oninput = () => { $("#strengthVal").textContent = faNum(str.value) + "٪"; };
    str.onchange = () => {
      S.strength = +str.value / 100;
      if (S.resultURL && S.mode !== "scene" && !S.layers.length) applyColor();
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
