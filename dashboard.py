"""Dashboard: health.db'yi okuyup tarayıcıda gösterir.
Çalıştır: python dashboard.py   ->   http://127.0.0.1:8000
"""
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import uvicorn
import yaml
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

CONFIG = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
with open(CONFIG, encoding="utf-8") as f:
    cfg = yaml.safe_load(f)
DB = cfg["db_path"]

app = FastAPI()


def q(sql, args=()):
    conn = sqlite3.connect(DB, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(sql, args)]
    except sqlite3.OperationalError:   # monitor henüz tabloları oluşturmadıysa
        return []
    finally:
        conn.close()


@app.get("/api/status")
def status():
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(timespec="seconds")
    out = []
    for s in cfg["services"]:
        name = s["name"]
        last = q("SELECT ts, ok, latency_ms, error FROM health_checks "
                 "WHERE service=? ORDER BY id DESC LIMIT 1", (name,))
        open_inc = q("SELECT started_at FROM incidents "
                     "WHERE service=? AND ended_at IS NULL", (name,))
        agg = q("SELECT COUNT(*) AS n, SUM(ok) AS ok FROM health_checks "
                "WHERE service=? AND ts >= ?", (name, cutoff))[0]

        if not last:
            state = "UNKNOWN"
        elif open_inc:
            state = "DOWN"
        elif not last[0]["ok"]:
            state = "DEGRADED"   # hata var ama henüz DOWN eşiğine ulaşmadı
        else:
            state = "UP"

        out.append({
            "name": name,
            "protocol": s["protocol"],
            "address": f"{s['host']}:{s['port']}",
            "state": state,
            "last_check": last[0]["ts"] if last else None,
            "latency_ms": round(last[0]["latency_ms"], 1) if last else None,
            "error": last[0]["error"] if last else None,
            "uptime_24h": round(100 * (agg["ok"] or 0) / agg["n"], 1) if agg["n"] else None,
        })
    return out


@app.get("/api/incidents")
def incidents():
    return q("SELECT service, started_at, ended_at, reason FROM incidents "
             "ORDER BY id DESC LIMIT 50")


PAGE = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Servis Sağlık Paneli</title>
<style>
  :root { --bg:#f5f6f8; --card:#fff; --text:#1d2129; --muted:#6b7280; --line:#e5e7eb;
          --up:#16a34a; --down:#dc2626; --warn:#d97706; --unk:#9ca3af; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#111418; --card:#1b1f26; --text:#e6e8eb; --muted:#9aa3af; --line:#2b313b; } }
  * { box-sizing:border-box; }
  body { margin:0; font-family:system-ui,Segoe UI,Roboto,sans-serif; background:var(--bg); color:var(--text); }
  main { max-width:1100px; margin:0 auto; padding:24px 16px 48px; }
  h1 { font-size:22px; margin:0 0 4px; } h2 { font-size:16px; margin:32px 0 12px; }
  .sub { color:var(--muted); font-size:13px; }
  .summary { display:flex; gap:12px; margin:20px 0; flex-wrap:wrap; }
  .pill { background:var(--card); border:1px solid var(--line); border-radius:10px; padding:10px 16px; font-size:14px; }
  .pill b { font-size:20px; margin-right:6px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(250px,1fr)); gap:12px; }
  .card { background:var(--card); border:1px solid var(--line); border-left:5px solid var(--unk);
          border-radius:10px; padding:14px 16px; }
  .card.UP { border-left-color:var(--up); } .card.DOWN { border-left-color:var(--down); }
  .card.DEGRADED { border-left-color:var(--warn); }
  .top { display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; }
  .name { font-weight:600; } .badge { font-size:12px; font-weight:700; padding:2px 8px; border-radius:99px; color:#fff; background:var(--unk); }
  .UP .badge { background:var(--up); } .DOWN .badge { background:var(--down); } .DEGRADED .badge { background:var(--warn); }
  .meta { color:var(--muted); font-size:13px; line-height:1.6; }
  .err { color:var(--down); font-size:12px; margin-top:4px; word-break:break-word; }
  table { width:100%; border-collapse:collapse; background:var(--card); border:1px solid var(--line);
          border-radius:10px; overflow:hidden; font-size:14px; }
  th, td { text-align:left; padding:10px 14px; border-bottom:1px solid var(--line); }
  th { color:var(--muted); font-weight:600; font-size:12px; text-transform:uppercase; }
  tr:last-child td { border-bottom:none; }
  .open { color:var(--down); font-weight:600; } .scroll { overflow-x:auto; }
</style></head>
<body><main>
  <h1>Servis Sağlık Paneli</h1>
  <div class="sub">Her 3 saniyede otomatik yenilenir &middot; son güncelleme: <span id="upd">-</span></div>
  <div class="summary" id="summary"></div>
  <div class="grid" id="cards"></div>
  <h2>Kesinti geçmişi</h2>
  <div class="scroll"><table>
    <thead><tr><th>Servis</th><th>Başlangıç</th><th>Bitiş</th><th>Süre</th><th>Sebep</th></tr></thead>
    <tbody id="incidents"></tbody>
  </table></div>
</main>
<script>
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fmt = t => t ? new Date(t).toLocaleString("tr-TR") : "-";
const ago = t => { if(!t) return "-"; const s = Math.max(0, Math.round((Date.now()-new Date(t))/1000));
  return s < 60 ? s+" sn önce" : Math.round(s/60)+" dk önce"; };
const dur = (a, b) => { const s = Math.round(((b ? new Date(b) : new Date()) - new Date(a))/1000);
  return s < 60 ? s+" sn" : s < 3600 ? Math.floor(s/60)+" dk "+(s%60)+" sn" : Math.floor(s/3600)+" sa "+Math.floor(s%3600/60)+" dk"; };
const LABEL = {UP:"UP", DOWN:"DOWN", DEGRADED:"HATALI", UNKNOWN:"?"};

async function refresh() {
  try {
    const [st, inc] = await Promise.all([
      fetch("/api/status").then(r => r.json()), fetch("/api/incidents").then(r => r.json())]);
    const n = k => st.filter(s => s.state === k).length;
    document.getElementById("summary").innerHTML =
      `<div class="pill"><b style="color:var(--up)">${n("UP")}</b>çalışıyor</div>` +
      `<div class="pill"><b style="color:var(--down)">${n("DOWN")}</b>kesinti</div>` +
      `<div class="pill"><b style="color:var(--warn)">${n("DEGRADED")}</b>hatalı</div>`;
    document.getElementById("cards").innerHTML = st.map(s => `
      <div class="card ${s.state}">
        <div class="top"><span class="name">${esc(s.name)}</span><span class="badge">${LABEL[s.state]}</span></div>
        <div class="meta">${esc(s.protocol)} &middot; ${esc(s.address)}<br>
          Yanıt süresi: ${s.latency_ms ?? "-"} ms<br>
          Uptime (24s): ${s.uptime_24h ?? "-"}%<br>
          Son kontrol: ${ago(s.last_check)}</div>
        ${s.state !== "UP" && s.error ? `<div class="err">${esc(s.error)}</div>` : ""}
      </div>`).join("");
    document.getElementById("incidents").innerHTML = inc.length ? inc.map(i => `
      <tr><td>${esc(i.service)}</td><td>${fmt(i.started_at)}</td>
          <td>${i.ended_at ? fmt(i.ended_at) : '<span class="open">devam ediyor</span>'}</td>
          <td>${dur(i.started_at, i.ended_at)}</td><td>${esc(i.reason)}</td></tr>`).join("")
      : '<tr><td colspan="5" class="sub">Henüz kesinti kaydı yok.</td></tr>';
    document.getElementById("upd").textContent = new Date().toLocaleTimeString("tr-TR");
  } catch (e) { document.getElementById("upd").textContent = "bağlantı hatası"; }
}
refresh(); setInterval(refresh, 3000);
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
