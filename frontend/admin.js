"use strict";

const fa = (n) => Number(n || 0).toLocaleString("fa-IR");

async function load() {
  const res = await fetch("/api/stats");
  const d = await res.json();

  document.getElementById("kpis").innerHTML = [
    ["کل پیش‌نمایش‌ها", d.total_visualizations],
    ["۷ روز اخیر", d.visualizations_7d],
    ["عکس‌های بارگذاری‌شده", d.photos_uploaded],
    ["درخواست مشاوره", d.leads],
  ]
    .map(([label, v]) => `<div class="kpi"><b>${fa(v)}</b><span>${label}</span></div>`)
    .join("");

  const max = Math.max(1, ...d.timeline_14d);
  document.getElementById("timeline").innerHTML = d.timeline_14d
    .map((n, i) => {
      const day = new Date(Date.now() - (13 - i) * 86400000);
      const lbl = day.toLocaleDateString("fa-IR", { day: "numeric", month: "numeric" });
      return `<div class="bar" style="height:${(n / max) * 100}%" title="${lbl}: ${n}"><span>${n || ""}</span></div>`;
    })
    .join("");

  document.getElementById("topColors").innerHTML =
    d.top_colors.length
      ? d.top_colors
          .map(
            (c) =>
              `<div class="lrow"><span>${c.name || "—"} <small style="color:var(--muted)">${c.code || ""}</small></span><b>${fa(c.count)}</b></div>`
          )
          .join("")
      : '<p class="hint">هنوز داده‌ای ثبت نشده.</p>';

  document.getElementById("leads").innerHTML =
    d.recent_leads.length
      ? d.recent_leads
          .map(
            (l) =>
              `<div class="lrow"><span>${l.name || "—"} · ${l.city || ""}</span><span>${l.phone}</span></div>`
          )
          .join("")
      : '<p class="hint">هنوز درخواستی ثبت نشده.</p>';
}

load();
setInterval(load, 15000);
