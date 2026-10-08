#!/usr/bin/env python3
"""
El panel en vivo: el estado del arnés y del loop autónomo, actualizado solo, en el navegador.

    python3 scripts/panel.py                 http://127.0.0.1:8765
    python3 scripts/panel.py --port 9000
    python3 scripts/panel.py --once          el estado como JSON, una vez (lo usa `harness status`)

Qué muestra: veredicto del último gate y cada señal, gate pendiente, rama, edad del STATUS,
cuántas reglas tiene cada familia de frenos, el loop (tarea, intento, fase, motivo de la última
escalada), la cola de tareas y el registro de eventos — cada bloqueo, escalada, hallazgo del
lint, gate y vuelta del loop — en el momento en que pasa.

Cómo se actualiza: Server-Sent Events. El servidor mira cada segundo las fechas de modificación
de lo que alimenta el panel (registro de eventos, resultado del gate, estado del loop, marcador,
STATUS, config) y empuja el estado nuevo cuando algo cambió. Sin dependencias, sin build, sin
websockets: `http.server` y un `EventSource`.

Sólo lectura y sólo local: escucha en 127.0.0.1. El estado incluye los motivos de los frenos y
fragmentos de la salida del gate; exponerlo a la red es decisión de un humano (`--host`), y el
panel lo avisa al arrancar.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugin"))
sys.path.append(str(Path(__file__).resolve().parent))  # al final: no tapa al paquete `harness`
from harness import events  # noqa: E402
from harness.core import CONFIG_PATH, REPO_ROOT, git_dir, load_config, marker_path  # noqa: E402
from harness.turn import branch_of  # noqa: E402

HOST = "127.0.0.1"
PORT = 8765
FAMILIAS = ("terminal.deny", "terminal.ask", "protectedPaths", "protectedReads", "patterns", "memory.deny", "skills.deny", "cron.deny", "routes")


def _get(config: dict, ruta: str):
    nodo = config
    for k in ruta.split("."):
        nodo = nodo.get(k) if isinstance(nodo, dict) else None
    return nodo


def _json(p: Path | None) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p and p.is_file() else {}
    except (OSError, ValueError):
        return {}


def _tareas(config: dict, root: Path) -> dict:
    spec = config.get("loop") or {}
    p = root / spec.get("tasksFile", ".hermes/loop/tasks.md")
    try:
        texto = p.read_text(encoding="utf-8")
    except OSError:
        return {"file": spec.get("tasksFile"), "pending": [], "done": 0, "escalated": []}
    pend, hechas, esc = [], 0, []
    for linea in texto.splitlines():
        m = re.match(r"^\s*[-*]\s+\[(.)\]\s+(.+?)\s*$", linea)
        if not m:
            continue
        if m.group(1) == " ":
            pend.append(m.group(2))
        elif m.group(1).lower() == "x":
            hechas += 1
        elif m.group(1) == "!":
            esc.append(m.group(2))
    return {"file": spec.get("tasksFile"), "pending": pend, "done": hechas, "escalated": esc}


def _status(config: dict, root: Path, hoy: dt.date) -> dict:
    archivo = (config.get("status") or {}).get("file", "STATUS.md")
    rx = (config.get("drift") or {}).get("statusDatePattern")
    try:
        texto = (root / archivo).read_text(encoding="utf-8")
    except OSError:
        return {"file": archivo, "date": None, "ageDays": None}
    m = re.search(rx, texto) if rx else None
    try:
        fecha = dt.date.fromisoformat(m.group(1)) if m else None
    except (ValueError, IndexError):
        fecha = None
    return {"file": archivo, "date": fecha.isoformat() if fecha else None, "ageDays": (hoy - fecha).days if fecha else None,
            "maxAgeDays": (config.get("drift") or {}).get("statusMaxAgeDays")}


def mas_mordieron(evs: list[dict], n: int = 8) -> list[dict]:
    """Qué reglas frenaron o escalaron más en el registro: la que muerde mucho es candidata a guía
    (el agente no la conoce) o a revisión (muerde de más). La que nunca muerde la ve `drift.py`."""
    cuenta: dict[str, dict] = {}
    for e in evs:
        if e.get("kind") in ("block", "ask") and e.get("rule"):
            c = cuenta.setdefault(e["rule"], {"rule": e["rule"], "block": 0, "ask": 0, "last": 0})
            c[e["kind"]] += 1
            c["last"] = max(c["last"], e.get("at", 0))
    return sorted(cuenta.values(), key=lambda c: (-(c["block"] + c["ask"]), -c["last"]))[:n]


def fuentes(config: dict | None, root: Path) -> list[Path]:
    """Lo que alimenta el panel: si cambia la fecha de alguno, hay estado nuevo que empujar."""
    config = config or {}
    g = git_dir(root)
    out = [root / ".hermes" / "harness.config.json", root / (config.get("status") or {}).get("file", "STATUS.md")]
    for p in (events.path(config, root), marker_path(config, root), (g / "harness-gate.json") if g else None):
        if p is not None:
            out.append(p)
    spec = config.get("loop") or {}
    import loop as loop_mod  # noqa: E402 — perezoso: el panel funciona igual sin el loop
    for rel in (spec.get("stateFile", ".git/harness-loop.json"), spec.get("stopFile", ".git/harness-loop.stop")):
        p = loop_mod.ruta_estado(root, rel)
        if p is not None:
            out.append(p)
    out.append(root / spec.get("tasksFile", ".hermes/loop/tasks.md"))
    return out


def huella(config: dict | None, root: Path) -> tuple:
    h = []
    for p in fuentes(config, root):
        try:
            st = p.stat()
            h.append((str(p), st.st_mtime_ns, st.st_size))
        except OSError:
            h.append((str(p), 0, 0))
    return tuple(h)


def estado(config: dict | None, root: Path, n_eventos: int = 60) -> dict:
    """El estado entero como DATO: lo sirve el panel y lo imprime `harness status`."""
    if not config:
        return {"repo": root.name, "root": str(root), "configured": False, "generatedAt": time.time()}
    import loop as loop_mod  # noqa: E402
    g = git_dir(root)
    gate = _json(g / "harness-gate.json" if g else None)
    m = marker_path(config, root)
    spec = config.get("loop") or {}
    loop_estado = loop_mod.leer_estado(spec, root) if spec else {}
    for i in loop_estado.get("attempts") or []:
        i.pop("tail", None)  # la cola del gate va al prompt del agente, no hace falta en el panel
    stop = loop_mod.ruta_estado(root, spec.get("stopFile", ".git/harness-loop.stop")) if spec else None
    try:
        import map as mapa_mod  # noqa: E402
        mapa = mapa_mod.construir(config, root)
    except Exception:  # noqa: BLE001 — el panel informa; un mapa roto lo dice el gate
        mapa = None
    return {
        "repo": root.name,
        "root": str(root),
        "configured": True,
        "generatedAt": time.time(),
        "branch": branch_of(root),
        "gate": {"command": (config.get("gate") or {}).get("command"), "pending": bool(m and m.exists()), **gate},
        "status": _status(config, root, dt.date.today()),
        "rules": {f: len(_get(config, f) or []) for f in FAMILIAS},
        "signals": [s.get("name") for s in (config.get("gate") or {}).get("signals") or []],
        "map": {"pieces": len(mapa["piezas"]), "gaps": mapa["huecos"], "unclassified": len(mapa["sinClasificar"])} if mapa else None,
        "loop": {"configured": bool(spec), "state": loop_estado, "stopRequested": bool(stop and stop.exists()),
                 "limits": {k: spec.get(k) for k in ("maxIterations", "sameFailureLimit", "maxMinutes")} if spec else {},
                 "tasks": _tareas(config, root) if spec else None},
        "events": events.tail(config, root, n_eventos),
        "topRules": mas_mordieron(events.tail(config, root, 2000)),
        "eventsEnabled": bool(events.spec(config)),
    }


# ── servidor ─────────────────────────────────────────────────────────────────

def handler_para(root: Path, intervalo: float = 1.0):
    class Panel(BaseHTTPRequestHandler):
        def log_message(self, *_):  # el panel no ensucia la terminal con cada GET
            return

        def _enviar(self, codigo: int, tipo: str, cuerpo: bytes):
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(cuerpo)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(cuerpo)

        def do_GET(self):  # noqa: N802 — nombre de http.server
            ruta = self.path.split("?", 1)[0]
            if ruta == "/":
                self._enviar(200, "text/html; charset=utf-8", HTML.encode("utf-8"))
            elif ruta == "/api/state":
                cuerpo = json.dumps(estado(load_config(root), root), ensure_ascii=False, default=str).encode("utf-8")
                self._enviar(200, "application/json; charset=utf-8", cuerpo)
            elif ruta == "/api/stream":
                self._stream()
            else:
                self._enviar(404, "text/plain; charset=utf-8", b"no existe")

        def _stream(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            ultima, latido = None, time.monotonic()
            try:
                while True:
                    config = load_config(root)
                    h = huella(config, root)
                    if h != ultima:
                        ultima = h
                        datos = json.dumps(estado(config, root), ensure_ascii=False, default=str)
                        self.wfile.write(f"event: state\ndata: {datos}\n\n".encode("utf-8"))
                        self.wfile.flush()
                        latido = time.monotonic()
                    elif time.monotonic() - latido > 15:
                        self.wfile.write(b": latido\n\n")  # proxies y navegadores cierran un stream mudo
                        self.wfile.flush()
                        latido = time.monotonic()
                    time.sleep(intervalo)
            except (BrokenPipeError, ConnectionResetError, OSError):
                return

    return Panel


def servidor(root: Path = REPO_ROOT, host: str = HOST, port: int = PORT, intervalo: float = 1.0) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer((host, port), handler_para(root, intervalo))
    srv.daemon_threads = True
    return srv


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Panel en vivo del arnés y del loop autónomo.")
    ap.add_argument("--host", default=HOST, help=f"interfaz (por defecto {HOST}: sólo esta máquina)")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--once", action="store_true", help="imprimir el estado como JSON y salir")
    a = ap.parse_args(argv)
    if a.once:
        print(json.dumps(estado(load_config(REPO_ROOT), REPO_ROOT), indent=1, ensure_ascii=False, default=str))
        return 0
    if not CONFIG_PATH.is_file():
        print(f"panel: no hay {CONFIG_PATH}; el panel no tiene nada que mostrar.")
        return 1
    if a.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"⚠️  panel escuchando en {a.host}: cualquiera en esa red ve los motivos de los frenos y la salida del gate.")
    try:
        srv = servidor(REPO_ROOT, a.host, a.port)
    except OSError as e:
        print(f"panel: no pude escuchar en {a.host}:{a.port} ({e}). Probá --port.")
        return 1
    print(f"Panel del arnés en http://{a.host}:{srv.server_address[1]}  ·  {REPO_ROOT}  ·  Ctrl+C para cortar")
    hilo = threading.Thread(target=srv.serve_forever, daemon=True)
    hilo.start()
    try:
        while hilo.is_alive():
            hilo.join(0.5)
    except KeyboardInterrupt:
        pass
    srv.shutdown()
    return 0


HTML = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Panel del arnés</title>
<style>
:root{--bg:#f6f5f1;--panel:#fff;--ink:#1d1d1b;--mute:#6b6a64;--line:#e3e1d9;--ok:#1f7a4d;--bad:#b3261e;--warn:#9a6700;--skip:#5b5bd6;--chip:#efede6;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
@media (prefers-color-scheme:dark){:root{--bg:#141413;--panel:#1d1d1b;--ink:#ecebe6;--mute:#9c9a92;--line:#2f2e2b;--ok:#4cc38a;--bad:#ff7b72;--warn:#e3b341;--skip:#a5a5ff;--chip:#262624}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif}
header{display:flex;flex-wrap:wrap;gap:.6rem 1.2rem;align-items:baseline;padding:1rem 16px;border-bottom:1px solid var(--line)}
h1{font-size:1.15rem;margin:0}h2{font-size:.8rem;text-transform:uppercase;letter-spacing:.06em;color:var(--mute);margin:0 0 .6rem}
.live{font-size:.8rem;color:var(--mute)}.live b{display:inline-block;width:.55rem;height:.55rem;border-radius:50%;background:var(--mute);margin-right:.35rem;vertical-align:middle}
.live.on b{background:var(--ok);animation:p 2s infinite}@keyframes p{50%{opacity:.35}}
main{display:grid;gap:12px;padding:12px 16px 24px;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));max-width:1400px;margin:0 auto}
section{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px}
.wide{grid-column:1/-1}
.big{font-size:1.6rem;font-weight:650}.ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--warn)}.skip{color:var(--skip)}.mute{color:var(--mute)}
ul{list-style:none;margin:0;padding:0}li{padding:.28rem 0;border-top:1px solid var(--line);display:flex;gap:.6rem;align-items:baseline}li:first-child{border-top:0}
.k{font-family:var(--mono);font-size:.82rem}.chip{background:var(--chip);border-radius:999px;padding:.05rem .55rem;font-size:.78rem;white-space:nowrap}
.grid2{display:grid;grid-template-columns:1fr auto;gap:.25rem .8rem}.n{font-variant-numeric:tabular-nums;text-align:right}
#ev li{font-size:.86rem}#ev .t{font-family:var(--mono);color:var(--mute);font-size:.78rem;white-space:nowrap}
#ev .msg{overflow-wrap:anywhere}.empty{color:var(--mute);font-size:.9rem}
.bar{height:6px;background:var(--chip);border-radius:3px;overflow:hidden;margin-top:.5rem}.bar i{display:block;height:100%;background:var(--ok)}
</style>
</head>
<body>
<header>
  <h1 id="repo">Panel del arnés</h1>
  <span class="chip k" id="branch">—</span>
  <span class="live" id="live"><b></b>conectando…</span>
</header>
<main>
  <section><h2>Gate</h2><div class="big" id="verdict">—</div><div class="mute" id="gatewhen"></div><ul id="signals" style="margin-top:.6rem"></ul></section>
  <section><h2>Loop autónomo</h2><div class="big" id="lphase">—</div><div id="ltask" class="mute"></div><div id="lreason"></div><ul id="attempts" style="margin-top:.6rem"></ul></section>
  <section><h2>Tareas</h2><div id="tasks"></div></section>
  <section><h2>Frenos activos</h2><div class="grid2" id="rules"></div><h2 style="margin-top:1rem">Los que más mordieron</h2><ul id="top"></ul></section>
  <section><h2>Salud</h2><div class="grid2" id="health"></div></section>
  <section class="wide"><h2>Eventos en vivo</h2><ul id="ev"></ul></section>
</main>
<script>
const $=id=>document.getElementById(id), esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const hora=t=>t?new Date(t*1000).toLocaleTimeString():"—", hace=t=>{if(!t)return"";const s=Math.round(Date.now()/1000-t);return s<60?`hace ${s}s`:s<3600?`hace ${Math.round(s/60)} min`:s<86400?`hace ${Math.round(s/3600)} h`:`hace ${Math.round(s/86400)} d`};
const CLS={verde:"ok",roja:"bad",omitida:"skip"};
const EV={block:["bad","freno"],ask:["warn","escala a humano"],lint:["warn","lint"],"verify-pending":["warn","gate pendiente"],gate:["","gate"],"loop-start":["","loop: tarea"],"loop-iter":["","loop: intento"],"loop-verde":["ok","loop: verde"],"loop-escalar":["bad","loop: escaló"],"loop-parado":["warn","loop: parado"]};
function evText(e){switch(e.kind){
 case"block":case"ask":return`<span class="k">${esc(e.rule)}</span> en <span class="k">${esc(e.tool)}</span>`;
 case"lint":return`${esc(e.findings)} hallazgo(s): ${esc(e.first)}`;
 case"gate":return`${esc(e.mode)} → <b class="${e.verdict==="roja"?"bad":"ok"}">${esc(e.verdict)}</b>${(e.failed||[]).length?" · rojas: "+esc(e.failed.join(", ")):""}`;
 case"loop-start":return esc(e.task);
 case"loop-iter":return`#${esc(e.n)} ${e.green?'<b class="ok">verde</b>':esc(e.signature)} · ${esc(e.task)}`;
 default:return`${esc(e.task||"")} ${e.reason?"— "+esc(e.reason):""}`}}
function render(s){
 $("repo").textContent=s.repo?`Panel del arnés · ${s.repo}`:"Panel del arnés";
 if(!s.configured){$("verdict").textContent="sin config";return}
 $("branch").textContent=s.branch;
 const g=s.gate||{}, sig=g.signals||{}, vals=Object.values(sig);
 const v=g.pending?["gate pendiente","warn"]:!vals.length?["nunca corrió","mute"]:vals.includes("roja")?["ROJO","bad"]:g.mode==="fast"?["fast (no entregable)","warn"]:vals.includes("omitida")?["verde con omitidas","ok"]:["VERDE","ok"];
 $("verdict").textContent=v[0];$("verdict").className="big "+v[1];
 $("gatewhen").textContent=g.at?`${g.mode||""} · ${hora(g.at)} (${hace(g.at)})`:(g.command||"");
 $("signals").innerHTML=(s.signals||[]).map(n=>`<li><span class="chip ${CLS[sig[n]]||"mute"}">${esc(sig[n]||"—")}</span><span>${esc(n)}</span></li>`).join("");
 const L=s.loop||{}, st=L.state||{};
 if(!L.configured){$("lphase").textContent="sin `loop`";$("ltask").textContent="";$("lreason").textContent="";$("attempts").innerHTML=""}
 else{const ph=st.phase||"nunca corrió";const cls={verde:"ok",escalar:"bad",parado:"warn",agente:"",gate:""}[ph]??"mute";
  $("lphase").textContent=(L.stopRequested?"⏸ parada pedida · ":"")+ph+(st.iteration&&!st.endedAt?` · intento ${st.iteration}`:"");$("lphase").className="big "+cls;
  $("ltask").textContent=st.task?`${st.task} · ${hace(st.startedAt)}`:"";
  $("lreason").innerHTML=st.reason?`<p class="${cls}">${esc(st.reason)}</p>`:`<p class="mute">topes: ${esc(L.limits.maxIterations)} intentos · mismo rojo ${esc(L.limits.sameFailureLimit)}× escala · ${esc(L.limits.maxMinutes)} min</p>`;
  $("attempts").innerHTML=(st.workers||[]).length?st.workers.map(w=>`<li><span class="chip ${{verde:"ok",escalar:"bad",parado:"warn"}[w.phase]||""}">${esc(w.phase)}</span><span>${esc(w.task)}</span></li>`).join(""):(st.attempts||[]).map(a=>`<li><span class="chip ${a.green?"ok":"bad"}">#${a.n}</span><span>${a.green?"verde":esc(a.signature)}</span><span class="mute n" style="margin-left:auto">${esc(a.secs)}s</span></li>`).join("")}
 const T=L.tasks;
 if(!T){$("tasks").innerHTML='<p class="empty">El repo no declara <span class="k">loop</span>.</p>'}
 else{const tot=T.pending.length+T.done+T.escalated.length;
  $("tasks").innerHTML=`<div class="grid2"><span>pendientes</span><b class="n">${T.pending.length}</b><span>verdes</span><b class="n ok">${T.done}</b><span>escaladas</span><b class="n bad">${T.escalated.length}</b></div>`
  +(tot?`<div class="bar"><i style="width:${Math.round(100*T.done/tot)}%"></i></div>`:"")
  +`<ul style="margin-top:.6rem">${T.escalated.map(t=>`<li><span class="chip bad">!</span>${esc(t)}</li>`).join("")}${T.pending.slice(0,6).map(t=>`<li><span class="chip">·</span>${esc(t)}</li>`).join("")}</ul>`
  +(tot?"":`<p class="empty">Sin tareas en <span class="k">${esc(T.file)}</span>.</p>`)}
 $("rules").innerHTML=Object.entries(s.rules||{}).map(([k,n])=>`<span class="k">${esc(k)}</span><b class="n">${n}</b>`).join("");
 $("top").innerHTML=(s.topRules||[]).length?s.topRules.map(r=>`<li><span class="k">${esc(r.rule)}</span><span class="mute" style="margin-left:auto">${hace(r.last)}</span><b class="n bad">${r.block}</b>${r.ask?`<b class="n warn">+${r.ask}</b>`:""}</li>`).join(""):'<li class="empty">Ninguna todavía.</li>';
 const S=s.status||{}, M=s.map;
 const age=S.ageDays==null?['<span class="bad">sin fecha</span>']:[`<span class="${S.maxAgeDays&&S.ageDays>S.maxAgeDays?"bad":"ok"}">${S.ageDays} día(s)</span>`];
 $("health").innerHTML=`<span>${esc(S.file)}: veredicto</span><b class="n">${age[0]}</b>`
  +(M?`<span>mapa: piezas</span><b class="n">${M.pieces}</b><span>sin clasificar</span><b class="n ${M.unclassified?"bad":"ok"}">${M.unclassified}</b><span>etapas sin control</span><b class="n">${M.gaps.length}</b>`:"")
  +`<span>registro de eventos</span><b class="n ${s.eventsEnabled?"ok":"warn"}">${s.eventsEnabled?"encendido":"apagado"}</b>`;
 const evs=(s.events||[]).slice().reverse();
 $("ev").innerHTML=evs.length?evs.map(e=>{const[c,l]=EV[e.kind]||["",e.kind];return`<li><span class="t">${hora(e.at)}</span><span class="chip ${c}">${esc(l)}</span><span class="msg">${evText(e)}</span></li>`}).join(""):'<li class="empty">Todavía nada. Cada freno, gate y vuelta del loop aparece acá apenas pasa.</li>';
}
function conectar(){
 const live=$("live");
 if(!window.EventSource){setInterval(()=>fetch("/api/state").then(r=>r.json()).then(render),2000);live.className="live on";live.lastChild.textContent="cada 2 s";return}
 const es=new EventSource("/api/stream");
 es.addEventListener("state",m=>{render(JSON.parse(m.data));live.className="live on";live.lastChild.textContent="en vivo · "+new Date().toLocaleTimeString()});
 es.onerror=()=>{live.className="live";live.lastChild.textContent="reconectando…"};
}
fetch("/api/state").then(r=>r.json()).then(render).finally(conectar);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    # Windows: la consola y los pipes son cp1252 por defecto, y `▶ ✓ ✗` o una `ñ` revientan el
    # print ANTES de verificar nada — el gate no fallaba, desaparecía (lo cazó la matriz de CI).
    for _s in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
