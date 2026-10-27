"""
La autonomía se gana con evidencia (P27–P29).

Cuatro niveles, de menos a más: L0 observa, L1 recomienda, L2 cambia con aprobación, L3 trabaja
solo. Qué permite cada uno, qué evidencia hace falta para subir y qué lo hace bajar lo declara
`autonomia` en el config (P4): este módulo no conoce ni una herramienta ni un umbral.

  - El nivel vive en `autonomia.estado` (por defecto `.git/harness-autonomia.json`, en el gitdir
    COMÚN: los worktrees del loop ven el mismo nivel). Sin archivo, vale `autonomia.inicial`.
    Un archivo roto vale L0: un estado corrupto no puede regalar autonomía (la única excepción a
    «un arnés roto deja pasar», ADR 0012).
  - Subir es de a un nivel, con la evidencia del umbral cumplida y con la firma de un humano.
  - Bajar es automático (`revisar`) ante un disparador de `autonomia.descenso`, sin firma.
  - La evidencia se cuenta en el registro de eventos DESDE la última transición: bajar resetea
    la ventana. Una transición que no está en el registro no ocurrió (P29).

Las funciones de decisión son puras (`evidencia`, `disparador`, `decidir`): el self-test las
llama directo. Las de efecto (`subir`, `bajar`, `revisar`) escriben el estado y el evento.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from . import events
from .core import git_dir

NIVELES = ("L0", "L1", "L2", "L3")
# Las familias de `tools` que guardan lo aprendido (se gobiernan juntas con `aprender`).
APRENDER = frozenset({"memory", "skill", "cron"})
_CACHE: dict[str, tuple[bytes, dict]] = {}


def spec(config: dict | None) -> dict:
    a = (config or {}).get("autonomia")
    return a if isinstance(a, dict) and isinstance(a.get("niveles"), dict) else {}


def _comun(root: Path) -> Path | None:
    """El gitdir COMÚN: en un worktree, `.git` apunta a `.git/worktrees/<x>`, y ahí un `commondir`
    lleva al del repo principal. El nivel es del repo, no de cada worktree."""
    g = git_dir(root)
    if g is None:
        return None
    try:
        c = (g / "commondir").read_text(encoding="utf-8").strip()
        return (g / c).resolve() if c else g
    except OSError:
        return g


def ruta(config: dict | None, root: Path) -> Path | None:
    """`HARNESS_AUTONOMIA_FILE` (ruta absoluta) lo redirige, como `HARNESS_EVENTS_FILE` al registro: una
    imagen sin `.git` (producción) guarda el nivel en su volumen; sin eso no hay `desde` y los días no corren."""
    forzado = os.environ.get("HARNESS_AUTONOMIA_FILE")
    if forzado:
        return Path(forzado)
    rel = spec(config).get("estado") or ".git/harness-autonomia.json"
    if rel.startswith(".git/"):
        c = _comun(root)
        return (c / rel[len(".git/"):]) if c is not None else None
    return root / rel


def leer(config: dict | None, root: Path) -> dict:
    """{nivel, historial, desde, error}. Lo lee el freno en cada tool call: unos bytes, parseados una vez."""
    s = spec(config)
    inicial = s.get("inicial") if s.get("inicial") in NIVELES else "L0"
    prueba = os.environ.get("HARNESS_NIVEL_PRUEBA")
    if prueba in NIVELES:
        # Sólo para el self-test: probar los OTROS frenos sin el nivel encima. El agente no puede
        # ponerla en el proceso de Hermes, y la regla `nivel-prueba` de `terminal.deny` la veda en comandos.
        return {"nivel": prueba, "historial": [], "desde": 0.0, "error": "", "inicial": False, "prueba": True}
    p = ruta(config, root)
    try:
        crudo = p.read_bytes() if p is not None else None
    except FileNotFoundError:
        crudo = None
    except OSError as e:
        return {"nivel": "L0", "historial": [], "desde": 0.0, "inicial": False,
                "error": f"el estado de autonomía no se puede leer ({e}): vale L0 hasta que un humano lo arregle"}
    if crudo is None:
        return {"nivel": inicial, "historial": [], "desde": 0.0, "error": "", "inicial": True}
    # Caché por CONTENIDO, no por (mtime, tamaño): en Windows el mtime es grueso y `L2`→`L3` no
    # cambia el tamaño, así que un nivel recién firmado se leía viejo (lo cazó la matriz de CI).
    clave = str(p)
    hit = _CACHE.get(clave)
    if hit and hit[0] == crudo:
        return hit[1]
    huella = crudo
    try:
        dato = json.loads(crudo.decode("utf-8"))
        nivel = dato.get("nivel")
        historial = dato.get("historial") if isinstance(dato.get("historial"), list) else []
        if nivel not in NIVELES:
            raise ValueError(f"nivel inválido: {nivel!r}")
        out = {"nivel": nivel, "historial": historial, "error": "", "inicial": False,
               "desde": max([float(h.get("at") or 0) for h in historial if isinstance(h, dict)] or [0.0])}
    except (ValueError, TypeError, AttributeError) as e:
        out = {"nivel": "L0", "historial": [], "desde": 0.0, "inicial": False,
               "error": f"el estado de autonomía no se puede leer ({e}): vale L0 hasta que un humano lo arregle"}
    _CACHE[clave] = (huella, out)
    return out


def nivel(config: dict | None, root: Path) -> str:
    return leer(config, root)["nivel"]


def siguiente(n: str) -> str | None:
    i = NIVELES.index(n)
    return NIVELES[i + 1] if i + 1 < len(NIVELES) else None


def anterior(n: str) -> str | None:
    i = NIVELES.index(n)
    return NIVELES[i - 1] if i > 0 else None


# ── evidencia (pura) ──────────────────────────────────────────────────────────

def fuera_de_nivel(e: dict) -> bool:
    """Un bloqueo del freno de nivel que es del AGENTE. Uno con `origen` (una herramienta que el manifiesto no
    conoce) es del config: sigue bloqueado, pero no le resta evidencia (piloto doctiling-sre, 2026-10-27)."""
    return e.get("kind") == "block" and str(e.get("rule", "")).startswith("nivel-") and not e.get("origen")


def _sesiones(evs: list[dict]) -> tuple[set, set]:
    vistas = {e.get("session") for e in evs if e.get("kind") == "turno" and e.get("session")}
    sucias = {e.get("session") for e in evs if fuera_de_nivel(e)}
    return vistas, sucias


def _ratio(a: int, b: int) -> float | None:
    return (a / b) if b else None


def metricas(evs: list[dict], desde: float, ahora: float | None = None) -> dict:
    """Lo que el registro dice desde `desde`. Cada métrica es un número (o None si no hay base)."""
    evs = [e for e in evs if float(e.get("at") or 0) >= desde]
    vistas, sucias = _sesiones(evs)
    recs = [e for e in evs if e.get("kind") == "recomendacion"]
    hall = [e for e in evs if e.get("kind") == "hallazgo"]
    aprob = [e for e in evs if e.get("kind") == "aprobacion"]
    gates = [e for e in evs if e.get("kind") == "gate" and e.get("mode", "full") != "fast"]
    verdes = [g for g in gates if str(g.get("verdict", "")).startswith("verde")]
    return {
        "sesionesLimpias": len(vistas - sucias),
        "intentosFueraDeNivel": sum(1 for e in evs if fuera_de_nivel(e)),
        "recomendaciones": len(recs),
        "aceptadasMin": _ratio(sum(1 for e in recs if e.get("aceptada")), len(recs)),
        "cambiosAprobados": sum(1 for e in aprob if e.get("approved")),
        "denegadosMax": _ratio(sum(1 for e in aprob if not e.get("approved")), len(aprob)) if aprob else 0.0,
        "gatesMin": len(gates),
        "gateVerdeMin": _ratio(len(verdes), len(gates)),
        "tamperings": sum(1 for e in evs if e.get("kind") == "tampering"),
        # Competencia, no sólo obediencia: lo que el agente detectó y una persona juzgó (un agente que observa
        # y avisa se mide por cuántas de sus alertas eran reales).
        "hallazgosJuzgados": len(hall),
        "falsosPositivosMax": _ratio(sum(1 for e in hall if not e.get("valido")), len(hall)),
        # El porqué comprobable: de las propuestas juzgadas, cuántas traían un certificado que el verificador
        # del repo aceptó. Una sin certificado cuenta como no verificada (ADR 0014).
        "certificadosVerificadosMin": _ratio(sum(1 for e in recs if e.get("certificado") == "verificado"), len(recs)),
        "diasMin": max(0.0, ((ahora or time.time()) - desde) / 86400) if desde else 0.0,
    }


# Cómo se compara cada métrica con su umbral: "min" = al menos, "max" = como mucho.
COMPARA = {"sesionesLimpias": "min", "intentosFueraDeNivel": "max", "recomendaciones": "min", "aceptadasMin": "min",
           "cambiosAprobados": "min", "denegadosMax": "max", "gatesMin": "min", "gateVerdeMin": "min",
           "tamperings": "max", "diasMin": "min", "hallazgosJuzgados": "min", "falsosPositivosMax": "max",
           "certificadosVerificadosMin": "min"}
ETIQUETA = {"sesionesLimpias": "sesiones sin salirse del nivel", "intentosFueraDeNivel": "intentos fuera del nivel",
            "recomendaciones": "recomendaciones juzgadas", "aceptadasMin": "recomendaciones aceptadas",
            "cambiosAprobados": "cambios aprobados", "denegadosMax": "aprobaciones denegadas",
            "gatesMin": "gates corridos", "gateVerdeMin": "gates verdes", "tamperings": "intocables tocados",
            "diasMin": "días en el nivel", "hallazgosJuzgados": "hallazgos juzgados",
            "falsosPositivosMax": "falsos positivos", "certificadosVerificadosMin": "propuestas con certificado verificado"}

# Lo que puede decir el verificador de un certificado (lo corre la CLI al juzgar, nunca un freno).
CERTIFICADO = ("verificado", "rechazado", "ausente", "error")


def evidencia(config: dict | None, n: str, evs: list[dict], desde: float, ahora: float | None = None) -> list[dict]:
    """Las filas del umbral para subir de `n` al siguiente: [{clave, etiqueta, valor, umbral, ok}]."""
    sig = siguiente(n)
    if not sig:
        return []
    umbral = (spec(config).get("ascenso") or {}).get(f"{n}->{sig}") or {}
    m = metricas(evs, desde, ahora)
    filas = []
    for clave, u in umbral.items():
        if clave.startswith("$"):
            continue
        v = m.get(clave)
        modo = COMPARA.get(clave)
        if modo is None:  # una métrica que el arnés no sabe medir no se da por cumplida
            ok = False
        elif v is None:
            ok = False
        else:
            ok = v >= u if modo == "min" else v <= u
        filas.append({"clave": clave, "etiqueta": ETIQUETA.get(clave, clave), "valor": v, "umbral": u,
                      "modo": modo or "?", "ok": ok})
    return filas


def inicio(est: dict, evs: list[dict]) -> float:
    """Desde cuándo cuenta la evidencia: la última transición o, si nunca hubo una, el primer evento del
    registro (desde ahí el agente está en `inicial`). Sin ninguno de los dos, 0: los días no corren."""
    if est.get("desde"):
        return est["desde"]
    return min((float(e.get("at") or 0) for e in evs if e.get("at")), default=0.0)


def puede_subir(config: dict | None, n: str, evs: list[dict], desde: float, ahora: float | None = None) -> tuple[bool, list[dict]]:
    filas = evidencia(config, n, evs, desde, ahora)
    return (bool(siguiente(n)) and bool(filas) and all(f["ok"] for f in filas)), filas


def disparador(config: dict | None, evs: list[dict], desde: float) -> str | None:
    """El motivo para bajar de nivel que el registro muestra desde `desde`, o None."""
    d = spec(config).get("descenso") or {}
    evs = [e for e in evs if float(e.get("at") or 0) >= desde]
    if d.get("tampering", True):
        t = next((e for e in evs if e.get("kind") == "tampering"), None)
        if t:
            return f"el agente tocó lo que no podía durante una tarea ({', '.join((t.get('paths') or [])[:3])})"
    criticas = set(d.get("reglasCriticas") or [])
    b = next((e for e in evs if e.get("kind") == "block" and e.get("rule") in criticas), None)
    if b:
        return f"intentó algo que una regla crítica veda (`{b.get('rule')}`)"
    n = int(d.get("denegadasSeguidas") or 0)
    aprob = [e for e in evs if e.get("kind") == "aprobacion"]
    if n and len(aprob) >= n and not any(e.get("approved") for e in aprob[-n:]):
        return f"{n} aprobaciones denegadas seguidas: el humano no está de acuerdo con lo que propone"
    n = int(d.get("escaladasSeguidas") or 0)
    fins = [e for e in evs if e.get("kind") in ("loop-verde", "loop-escalar")]
    if n and len(fins) >= n and all(e.get("kind") == "loop-escalar" for e in fins[-n:]):
        return f"{n} tareas seguidas escaladas sin llegar a verde"
    return None


# ── el freno (puro: recibe el nivel ya leído) ────────────────────────────────

def partir(cmd: str) -> list[str]:
    """`a && b; c | d` → [a, b, c, d], respetando comillas: cada parte se evalúa sola, así
    `grep x; rm -r y` no pasa por `grep`."""
    partes, cur, q, i = [], "", None, 0
    while i < len(cmd):
        c = cmd[i]
        if q:
            cur += c
            q = None if c == q else q
        elif c in "'\"":
            q, cur = c, cur + c
        elif cmd.startswith(("&&", "||"), i):
            partes, cur, i = partes + [cur], "", i + 2
            continue
        elif c in ";|\n":
            partes, cur = partes + [cur], ""
        else:
            cur += c
        i += 1
    return [x.strip() for x in partes + [cur] if x.strip()]


def _casa(patrones, texto: str) -> bool:
    for p in patrones or []:
        try:
            if re.search(p, texto):
                return True
        except re.error:
            continue
    return False


def terminal_permitida(cmd: str, patrones) -> bool:
    """Cada subcomando casa con un patrón permitido, y ninguno esconde otro comando adentro."""
    if re.search(r"`|\$\(|<\(|>", cmd.replace("2>&1", "")):
        return False
    partes = partir(cmd)
    return bool(partes) and all(_casa(patrones, p) for p in partes)


def accion(config: dict, n: str, familia: str, ctx: dict) -> str:
    """'allow' | 'ask' | 'deny' para una familia de herramienta en el nivel `n`.

    `ctx` trae lo que hace falta para las excepciones: `rutas` (relativas al repo) para escribir,
    `comando` para la terminal, `clase` para una integración."""
    lv = (spec(config).get("niveles") or {}).get(n) or {}
    if familia == "read":
        return "allow"
    if familia == "write":
        rutas = ctx.get("rutas") or []
        if rutas and all(_casa(lv.get("escribirPermitido"), r) for r in rutas):
            return "allow"
        return lv.get("escribir", "deny")
    if familia == "shell":
        if terminal_permitida(ctx.get("comando", ""), lv.get("terminalPermitida")):
            return "allow"
        return lv.get("terminal", "deny")
    if familia == "code":
        return lv.get("codigo", "deny")
    if familia in APRENDER:
        return lv.get("aprender", "deny")
    if familia == "integracion":
        return "allow" if ctx.get("clase") == "read" else lv.get("integraciones", "deny")
    return "allow"


def mensaje(config: dict, n: str, familia: str, que: str, act: str) -> str:
    lv = (spec(config).get("niveles") or {}).get(n) or {}
    sig = siguiente(n)
    cmd = spec(config).get("comando") or "python3 scripts/cli.py nivel"
    if act == "ask":
        # El freno no corre el verificador (no lanza procesos): le dice al humano cómo comprobar el porqué.
        cert = ((spec(config).get("certificados") or {}).get("verificador")
                and f" Si ejecuta una propuesta, comprobá su porqué antes: `{cmd.replace(' nivel', ' recomendacion')} verificar <propuesta>`.")
        return (f"NIVEL {n} ({lv.get('nombre', n)}): {que} pide aprobación humana. En este nivel el agente puede "
                f"{lv.get('puede', 'cambiar el repo con aprobación')} Lo que el humano decida queda como evidencia"
                + (f" para {sig}." if sig else ".") + (cert or ""))
    return (f"NIVEL {n} ({lv.get('nombre', n)}): {que} no está permitido en este nivel.\n"
            f"Lo que sí podés hacer: {lv.get('puede', 'leer y reportar')}\n"
            f"La autonomía se gana con evidencia: " + (f"lo que falta para {sig} lo muestra `{cmd}`. " if sig else "")
            + "No busques otro camino para hacerlo: intentarlo fuera del nivel resta evidencia.")


# ── efectos ──────────────────────────────────────────────────────────────────

def _escribir(config: dict, root: Path, estado: dict) -> bool:
    p = ruta(config, root)
    if p is None:
        return False
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(estado, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)
        _CACHE.pop(str(p), None)
        return True
    except OSError:
        return False


def transicion(config: dict, root: Path, a: str, tipo: str, firma: str = "", motivo: str = "", evid: list | None = None,
               ref: str = "") -> bool:
    """Escribe el nivel nuevo, lo agrega al historial y lo deja en el registro (P29). `ref`: la entrada del
    registro firmado que la pidió (un despliegue la aplica una sola vez)."""
    est = leer(config, root)
    de = est["nivel"]
    h = {"at": round(time.time(), 3), "de": de, "a": a, "tipo": tipo, "firma": firma, "motivo": motivo}
    if ref:
        h["ref"] = ref
    if evid:
        h["evidencia"] = {f["clave"]: f["valor"] for f in evid}
    if not _escribir(config, root, {"nivel": a, "historial": (est["historial"] + [h])[-50:]}):
        return False
    kind = {"ganado": "nivel-sube", "declarado": "nivel-declarado"}.get(tipo, "nivel-baja")
    events.record(config, root, kind, de=de, a=a, firma=firma, motivo=motivo, tipo=tipo)
    return True


def subir(config: dict, root: Path, firma: str, evs: list[dict] | None = None,
          ahora: float | None = None, ref: str = "") -> tuple[bool, str, list[dict]]:
    """`ahora`: el reloj de la evaluación (por defecto, el real). Lo usa el self-test para `diasMin`."""
    if not firma.strip():
        return False, "subir de nivel lo firma un humano: falta --firma.", []
    est = leer(config, root)
    if est["error"]:
        return False, est["error"], []
    n = est["nivel"]
    sig = siguiente(n)
    if not sig:
        return False, f"ya está en {n}: no hay nivel más alto.", []
    evs = evs if evs is not None else events.tail(config, root, 20000)
    ok, filas = puede_subir(config, n, evs, inicio(est, evs), ahora)
    if not ok:
        return False, f"la evidencia no alcanza para pasar de {n} a {sig}.", filas
    transicion(config, root, sig, "ganado", firma=firma, motivo=f"evidencia cumplida para {n}->{sig}", evid=filas, ref=ref)
    return True, f"{n} → {sig}, firmado por {firma}.", filas


def bajar(config: dict, root: Path, motivo: str, firma: str = "", a: str | None = None) -> str | None:
    n = nivel(config, root)
    destino = a or anterior(n)
    if not destino or NIVELES.index(destino) >= NIVELES.index(n):
        return None
    transicion(config, root, destino, "bajado" if firma else "bajado-automatico", firma=firma, motivo=motivo)
    return destino


def declarar(config: dict, root: Path, a: str, firma: str, motivo: str, ref: str = "") -> tuple[bool, str]:
    """Fijar un nivel SIN evidencia: la excepción a P28 (un sandbox de aprendizaje, el repo del
    propio arnés). Exige firma y motivo, y el panel lo muestra como alerta mientras dure."""
    if a not in NIVELES:
        return False, f"nivel inválido: {a} (válidos: {', '.join(NIVELES)})"
    if not firma.strip() or not motivo.strip():
        return False, "declarar un nivel sin evidencia exige --firma y --motivo: queda a la vista."
    transicion(config, root, a, "declarado", firma=firma, motivo=motivo, ref=ref)
    return True, f"{a} declarado por {firma} ({motivo}). El panel lo muestra como no ganado."


JUICIOS = {"recomendacion": "aceptada", "hallazgo": "valido"}


def juzgar(config: dict, root: Path, kind: str, ref: str, ok: bool, firma: str, evs: list[dict] | None = None,
           certificado: str = "") -> tuple[bool, str]:
    """Un juicio humano que viene de AFUERA del repo (una etiqueta en el tablero, un botón en el chat): la
    propuesta (`recomendacion`) o la alerta (`hallazgo`) identificada por `ref`, una sola vez, con la firma de
    quien juzgó. Así producción junta evidencia sin una shell (piloto doctiling-sre: etiquetas `rec:*`).
    `certificado`: lo que dijo el verificador del porqué de la propuesta (`CERTIFICADO`), si se corrió."""
    campo = JUICIOS.get(kind)
    if not campo:
        return False, f"no se juzga `{kind}` (son {', '.join(JUICIOS)})"
    if not str(ref).strip() or not str(firma).strip():
        return False, "un juicio lleva `ref` (qué se juzgó) y la firma de quien lo juzgó."
    evs = evs if evs is not None else events.tail(config, root, 20000)
    if any(e.get("kind") == kind and str(e.get("ref")) == str(ref) for e in evs):
        return False, f"{ref} ya fue juzgada: cuenta una vez."
    extra = {"certificado": certificado} if certificado in CERTIFICADO and kind == "recomendacion" else {}
    events.record(config, root, kind, ref=str(ref), firma=firma, **{campo: bool(ok)}, **extra)
    return True, f"{ref}: {campo if ok else 'no ' + campo} · {firma}" + (f" · certificado {certificado}" if extra else "")


def aplicar_firmadas(config: dict, root: Path, entradas: list) -> list[tuple[str, bool, str]]:
    """Las transiciones de un registro firmado (`autonomia.firmadas`): un archivo versionado donde cada entrada
    la agrega un PR revisado. Mergear es firmar, así que producción (sin shell ni `.git`) cambia de nivel en el
    próximo arranque. Se aplican en orden y una vez cada una (su `id` queda como `ref` en el historial). `subir`
    sigue exigiendo la evidencia: si no alcanza, esa y las siguientes esperan. → [(id, aplicada, mensaje)]."""
    hechas = {h.get("ref") for h in leer(config, root)["historial"] if isinstance(h, dict)}
    out: list[tuple[str, bool, str]] = []
    for e in entradas if isinstance(entradas, list) else []:
        ref = str((e or {}).get("id") or "")
        if not ref or ref in hechas:
            continue
        accion_, firma = e.get("accion"), str(e.get("firma") or "")
        if accion_ == "declarar":
            ok, msg = declarar(config, root, str(e.get("a") or ""), firma, str(e.get("motivo") or ""), ref=ref)
        elif accion_ == "subir":
            ok, msg, _ = subir(config, root, firma, ref=ref)
        else:
            ok, msg = False, f"acción desconocida: {accion_!r} (son `declarar` y `subir`)"
        out.append((ref, ok, msg))
        if not ok:
            break  # en orden: una entrada nunca salta a otra que no se aplicó
    return out


def revisar(config: dict | None, root: Path, evs: list[dict] | None = None) -> str | None:
    """Si el registro muestra un disparador desde la última transición, baja un nivel. Nunca lanza."""
    try:
        if not spec(config) or os.environ.get("HARNESS_NO_EVENTS") or os.environ.get("HARNESS_NIVEL_PRUEBA"):
            return None  # sin registro no hay disparador: lo que no quedó escrito no ocurrió (P29)
        est = leer(config, root)
        if est["nivel"] == "L0" or est["error"]:
            return None
        evs = evs if evs is not None else events.tail(config, root, 5000)
        motivo = disparador(config, evs, est["desde"])
        return bajar(config, root, motivo) if motivo else None
    except Exception:  # noqa: BLE001 — revisar nunca tumba a quien lo llama (P5)
        return None


def resumen(config: dict | None, root: Path, evs: list[dict] | None = None) -> dict:
    """Lo que muestran el panel y `cli.py nivel`: la salud del agente."""
    s = spec(config)
    if not s:
        return {"activa": False}
    est = leer(config, root)
    n = est["nivel"]
    evs = evs if evs is not None else events.tail(config, root, 20000)
    desde = inicio(est, evs)
    ok, filas = puede_subir(config, n, evs, desde)
    niveles = s.get("niveles") or {}
    alertas = []
    if est["error"]:
        alertas.append(est["error"])
    ult = est["historial"][-1] if est["historial"] else None
    if ult and ult.get("tipo") == "bajado-automatico":
        alertas.append(f"bajó solo de {ult.get('de')} a {ult.get('a')}: {ult.get('motivo')}")
    if (ult and ult.get("tipo") == "declarado") or (est.get("inicial") and n != "L0"):
        # Visible siempre: un nivel declarado es una excepción a P28, no una forma de ganarlo.
        alertas.append(f"{n} fue declarado por un humano, no ganado con evidencia"
                       + (f" ({ult.get('motivo')})" if ult and ult.get("motivo") else " (`autonomia.inicial` del config)"))
    ajenos = sorted({str(e.get("tool")) for e in evs if e.get("kind") == "block" and e.get("origen")
                     and float(e.get("at") or 0) >= desde})
    if ajenos:
        alertas.append(f"bloqueos que no son del agente (herramientas fuera de `toolNames`: {', '.join(ajenos[:4])}): "
                       "clasificalas en su manifiesto")
    return {
        "activa": True, "nivel": n, "nombre": (niveles.get(n) or {}).get("nombre", n),
        "puede": (niveles.get(n) or {}).get("puede", ""), "noPuede": (niveles.get(n) or {}).get("noPuede", ""),
        "loop": bool((niveles.get(n) or {}).get("loop")), "siguiente": siguiente(n),
        "listoParaSubir": ok, "evidencia": filas, "desde": desde, "inicial": est.get("inicial", False),
        "historial": est["historial"][-8:], "alertas": [a for a in alertas if a],
        "niveles": [{"id": k, "nombre": (niveles.get(k) or {}).get("nombre", k)} for k in NIVELES],
        "comando": s.get("comando") or "python3 scripts/cli.py nivel",
    }
