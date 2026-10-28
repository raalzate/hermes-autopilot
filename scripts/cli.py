#!/usr/bin/env python3
"""
`cli.py` — la CLI del arnés: parametrizarlo sin editar JSON a mano, y una sola puerta a todo lo demás.

    python3 scripts/cli.py status [--json]          rama, gate, loop, frenos, últimos eventos
    python3 scripts/cli.py rule list [familia]
    python3 scripts/cli.py rule add <familia> --id x --pattern RX --example EJ --reason "…" [--apply]
    python3 scripts/cli.py rule rm <familia> <id> [--apply]
    python3 scripts/cli.py rule test <familia> "texto"    ¿qué regla lo frena?
    python3 scripts/cli.py config get [ruta.con.puntos]
    python3 scripts/cli.py config set <ruta> <valor> [--apply]   el valor se lee como JSON si se puede
    python3 scripts/cli.py signal list | signal add "nombre" --why "…" [--apply] -- cmd args… | signal rm "nombre" [--apply]
    python3 scripts/cli.py profile list
    python3 scripts/cli.py task add "texto" | task list           la cola del loop autónomo
    python3 scripts/cli.py nivel [--json]                         el nivel de autonomía y la evidencia para subir
    python3 scripts/cli.py nivel subir --firma "Nombre"           sube UN nivel, sólo si la evidencia alcanza (P28)
    python3 scripts/cli.py nivel bajar [--a L1] --motivo "…" --firma "Nombre"
    python3 scripts/cli.py nivel declarar L3 --motivo "…" --firma "Nombre"   sin evidencia: queda como alerta
    python3 scripts/cli.py nivel aplicar [--registro config/autonomia.json]  lo que firmó un PR (producción sin shell)
    python3 scripts/cli.py recomendacion juzgar <ref> aceptada|rechazada [--certificado <archivo>] --firma "Nombre"   juzgada afuera (tablero)
    python3 scripts/cli.py recomendacion verificar <propuesta.md>   ¿el porqué se deduce de los hechos? (el verificador del repo)
    python3 scripts/cli.py hallazgo juzgar <ref> valido|falso --firma "Nombre"   ¿la alerta del agente era real?
    python3 scripts/cli.py recomendacion list | aceptar|rechazar <archivo> [--firma "Nombre"]   las propuestas de L1
    python3 scripts/cli.py integ list|show|add|set|rm|test|deps|hermes|check   las integraciones (scripts/integ.py)
    python3 scripts/cli.py gate|selftest|lint|map|timing|doctor|drift|install|loop|panel|casos [args…]

Familias: terminal.deny · terminal.ask · protectedPaths · protectedReads · patterns · memory.deny ·
skills.deny · cron.deny · routes.

Lo que la CLI agrega sobre editar el JSON: una regla nueva se prueba ANTES de escribirse, por el
mismo `guards.evaluate` que usa el plugin —
  - P2: trae `example`, y el ejemplo frena (y lo frena ESTA regla, no otra que ya lo cubría);
  - P3: ningún inocente de su familia muerde, y el gate del repo no queda vedado (un freno que
    bloquea `python3 scripts/gate.py` deja al agente y al loop sin forma de terminar);
  - el config resultante pasa el lint (COHERENCIA: un `reason` que recomienda un comando vedado).
Escribir es `--apply`; sin eso muestra qué cambiaría (P9). Después, `harness selftest`.
"""
from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "plugin"))
sys.path.append(str(HERE))  # al final: `scripts/` no puede tapar al paquete `harness` del plugin
from harness import core, guards, rules, turn  # noqa: E402
from harness.core import CONFIG_PATH, HARNESS_HOME, REPO_ROOT  # noqa: E402

# familia → (tipo de herramienta en `tools`, qué decisión se espera, dónde están sus inocentes)
FAMILIAS: dict[str, tuple[str | None, str, str | None]] = {
    "terminal.deny": ("shell", "block", "terminal.innocent"),
    "terminal.ask": ("shell", "approve", "terminal.innocent"),
    "protectedPaths": ("write", "block", "protectedInnocent"),
    "protectedReads": ("read", "block", "protectedReadsInnocent"),
    "patterns": ("write", "block", None),
    "memory.deny": ("memory", "block", "memory.innocent"),
    "skills.deny": ("skill", "block", "skills.innocent"),
    "cron.deny": ("cron", "block", "cron.innocent"),
    "routes": (None, "hint", None),
}
PASAMANOS = ("gate", "selftest", "lint", "map", "timing", "doctor", "drift", "install", "loop", "panel", "mutations", "linkcheck",
             "casos", "integ")


# ── rutas con puntos sobre el config ─────────────────────────────────────────

def _partes(ruta: str) -> list:
    return [int(p) if p.isdigit() else p for p in ruta.split(".") if p != ""]


def get_ruta(config, ruta: str):
    nodo = config
    for p in _partes(ruta):
        if isinstance(nodo, dict):
            nodo = nodo.get(p)
        elif isinstance(nodo, list) and isinstance(p, int) and p < len(nodo):
            nodo = nodo[p]
        else:
            return None
    return nodo


def set_ruta(config: dict, ruta: str, valor) -> dict:
    nuevo = copy.deepcopy(config)
    partes = _partes(ruta)
    if not partes:
        raise ValueError("ruta vacía")
    nodo = nuevo
    for p in partes[:-1]:
        if isinstance(nodo, list):
            nodo = nodo[p]
        else:
            nodo = nodo.setdefault(p, {})
    nodo[partes[-1]] = valor
    return nuevo


def lista_de(config: dict, familia: str) -> list:
    v = get_ruta(config, familia)
    return v if isinstance(v, list) else []


# ── la prueba de una regla, por el camino del plugin ─────────────────────────

def caso(familia: str, regla: dict, texto: str) -> dict:
    """Los argumentos con que Hermes llamaría a la herramienta (las mismas formas que el self-test)."""
    if familia.startswith("terminal"):
        return {"command": texto}
    if familia == "protectedPaths":
        return {"path": texto, "content": "x"}
    if familia == "protectedReads":
        return {"path": texto}
    if familia == "patterns":
        return {"path": regla.get("examplePath", "x.py"), "content": "x = 1\n" + texto}
    if familia == "memory.deny":
        return {"action": "add", "target": "memory", "content": texto}
    if familia == "skills.deny":
        return {"operations": [{"action": "create", "name": "x", "content": f"---\nname: x\n---\n{texto}\n"}]}
    if familia == "cron.deny":
        return {"action": "create", "schedule": "every day at 9am", "prompt": texto}
    return {}


def decision(config: dict, root: Path, familia: str, regla: dict, texto: str) -> core.Decision | None:
    kind = FAMILIAS[familia][0]
    tool = ((config.get("tools") or {}).get(kind) or [None])[0] if kind else None
    if not tool:
        return None
    # Se prueba la REGLA, no el nivel del agente: en L0 todo se frena y ningún ejemplo probaría nada.
    sin_nivel = {k: v for k, v in config.items() if k != "autonomia"}
    return guards.evaluate(core.Event(tool=tool, args=caso(familia, regla, texto)), sin_nivel, root)


def validar(config: dict, familia: str, regla: dict, root: Path = REPO_ROOT) -> list[str]:
    """Los problemas de agregar `regla` a `familia`. Vacío = se puede escribir."""
    if familia not in FAMILIAS:
        return [f"familia desconocida `{familia}`. Son: {', '.join(FAMILIAS)}"]
    _, espera, donde_inocentes = FAMILIAS[familia]
    errores = []
    rid, patron, ej = regla.get("id"), regla.get("pattern"), regla.get("example")
    if not rid or not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", str(rid)):
        errores.append("`id` en minúsculas, dígitos y `-._` (lo usa el rule_key de las aprobaciones)")
    if any(r.get("id") == rid for r in lista_de(config, familia)):
        errores.append(f"ya hay una regla `{rid}` en {familia}")
    try:
        re.compile(patron or "")
        if not patron:
            errores.append("falta `pattern`")
    except re.error as e:
        errores.append(f"`pattern` no es una regex válida: {e}")
    if not ej:
        errores.append("falta `example`: una regla sin ejemplo es una regla sin prueba de vida (P2)")
    texto_motivo = regla.get("hint" if espera == "hint" else "reason")
    if not texto_motivo:
        errores.append(f"falta `{'hint' if espera == 'hint' else 'reason'}`: es lo único que el agente lee cuando lo frenás")
    if familia == "patterns" and not regla.get("examplePath"):
        errores.append("`patterns` necesita `examplePath`: el archivo donde el ejemplo tiene que frenar")
    if errores:
        return errores

    nuevo = copy.deepcopy(config)
    lista = lista_de(nuevo, familia)
    nuevo = set_ruta(nuevo, familia, lista + [regla])

    # P2: el ejemplo (y cada `moreExamples`) frena, y lo frena ESTA regla.
    for texto in [ej] + list(regla.get("moreExamples") or []):
        if espera == "hint":
            if f"**{rid}**" not in turn.route(nuevo, texto):
                errores.append(f"el ejemplo «{texto}» no dispara la ruta")
            continue
        d = decision(nuevo, root, familia, regla, texto)
        if d is None:
            errores.append(f"`tools` no declara herramientas para {familia}: la regla no vería nada")
            break
        hizo = "block" if d.block else ("approve" if d.approve else "allow")
        if hizo != espera:
            errores.append(f"el ejemplo «{texto}» no frena: el plugin decide `{hizo}`, se esperaba `{espera}`")
        elif (d.rule or {}).get("id") not in (rid, None):
            errores.append(f"el ejemplo «{texto}» ya lo frena `{d.rule.get('id')}`: la regla nueva no prueba nada propio")

    # `patterns` también lo mira el lint (y un patch V4A, que sólo trae las líneas agregadas):
    # los dos van línea por línea. Un patrón con `\n` frena un write_file y nunca el lint.
    if familia == "patterns" and not any(f"PATRON[{rid}]" in h for h in rules.lint_one(nuevo, regla["examplePath"], ej)):
        errores.append("el lint no caza el ejemplo en `examplePath`: `patterns` se evalúa línea por línea "
                       "(un `\\n` en el patrón frena un write_file pero nunca el lint ni un patch V4A)")

    # P3: ni los inocentes de la familia ni el gate del repo quedan frenados.
    inocentes = list(get_ruta(nuevo, donde_inocentes) or []) if donde_inocentes else []
    if familia.startswith("terminal"):
        g = nuevo.get("gate") or {}
        inocentes += [c for c in (g.get("command"), g.get("fastCommand"), g.get("installHooksCommand")) if c]
        inocentes += [" ".join(c) for c in [(nuevo.get("loop") or {}).get("gateCommand")] if c]
    for texto in dict.fromkeys(inocentes):
        d = decision(nuevo, root, familia, regla, texto)
        if d is not None and (d.block or d.approve) and (d.rule or {}).get("id") == rid:
            errores.append(f"muerde de más: frena «{texto}», que tiene que pasar (P3)")

    # El config resultante pasa el lint (COHERENCIA, entre otras).
    texto_cfg = json.dumps(nuevo, indent=2, ensure_ascii=False)
    for h in rules.lint_one(nuevo, ".hermes/harness.config.json", texto_cfg):
        errores.append(f"lint: {h}")
    return errores


# ── escritura ────────────────────────────────────────────────────────────────

def leer_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def escribir(nuevo: dict, apply: bool, que: str) -> int:
    if not apply:
        print(f"DRY-RUN — {que}. Nada se escribió: repetí con --apply.")
        return 0
    CONFIG_PATH.write_text(json.dumps(nuevo, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"✓ {que}\n  {CONFIG_PATH}\nSiguiente: `python3 {_rel(Path(__file__))} selftest` (¿muerde?) y `… lint` (¿no muerde de más?).")
    return 0


def _rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return str(p)


def _valor(texto: str):
    try:
        return json.loads(texto)
    except ValueError:
        return texto


# ── comandos ─────────────────────────────────────────────────────────────────

def cmd_status(args: list[str]) -> int:
    import panel

    s = panel.estado(core.load_config(REPO_ROOT), REPO_ROOT, n_eventos=10)
    if "--json" in args:
        print(json.dumps(s, indent=1, ensure_ascii=False, default=str))
        return 0
    if not s.get("configured"):
        print(f"{s['repo']}: sin `.hermes/harness.config.json` — el arnés no actúa acá.")
        return 1
    g = s["gate"]
    sig = g.get("signals") or {}
    veredicto = ("PENDIENTE" if g.get("pending") else "nunca corrió" if not sig else
                 "ROJO" if "roja" in sig.values() else "verde con omitidas" if "omitida" in sig.values() else "VERDE")
    print(f"{s['repo']} · rama {s['branch']}")
    print(f"  gate      {veredicto}" + (f" ({g.get('mode')})" if g.get("mode") else ""))
    for n, v in sig.items():
        print(f"    {'✓' if v == 'verde' else '·' if v == 'omitida' else '✗'} {n}")
    st = s["status"]
    print(f"  {st['file']:<9} veredicto de hace {st['ageDays']} día(s)" if st.get("ageDays") is not None else f"  {st['file']}: sin fecha")
    au = s.get("autonomia") or {}
    if au.get("activa"):
        print(f"  nivel     {au['nivel']} ({au['nombre']})"
              + (f" · listo para {au['siguiente']}: falta la firma" if au.get("listoParaSubir") else "")
              + "".join(f"\n            ⚠ {x}" for x in au.get("alertas") or []))
    print("  frenos    " + " · ".join(f"{k} {v}" for k, v in s["rules"].items() if v))
    integ = s.get("integrations") or []
    print("  integ.    " + (" · ".join(f"{i['id']} ({i['perfil']})" for i in integ) if integ else "ninguna habilitada (`cli.py integ list`)"))
    lp = s["loop"]
    if lp["configured"]:
        e = lp["state"] or {}
        t = lp["tasks"] or {}
        print(f"  loop      {e.get('phase', 'nunca corrió')}" + (f" · {e.get('task')}" if e.get("task") else "")
              + (" · ⏸ parada pedida" if lp["stopRequested"] else ""))
        if e.get("reason"):
            print(f"            {e['reason']}")
        print(f"  tareas    {len(t.get('pending') or [])} pendientes · {t.get('done', 0)} verdes · {len(t.get('escalated') or [])} escaladas")
    if s["events"]:
        print("  eventos")
        import time as _t
        for ev in s["events"][-10:]:
            print(f"    {_t.strftime('%H:%M:%S', _t.localtime(ev.get('at', 0)))} {ev.get('kind'):<14} "
                  f"{ev.get('rule') or ev.get('verdict') or ev.get('task') or ev.get('first') or ''}")
    print("Panel en vivo: cli.py panel")
    return 0


def _opcion(args: list[str], nombre: str) -> str:
    if nombre in args:
        i = args.index(nombre)
        return args[i + 1] if i + 1 < len(args) else ""
    return ""


def _firma_de(args: list[str]) -> str:
    f = _opcion(args, "--firma")
    if f:
        return f
    p = subprocess.run(["git", "config", "user.name"], cwd=REPO_ROOT, capture_output=True, text=True)
    return p.stdout.strip()


PROPORCION = {"aceptadasMin", "denegadosMax", "gateVerdeMin", "falsosPositivosMax"}  # el resto son conteos (o días)


def _fila(f: dict) -> str:
    v, u, prop = f["valor"], f["umbral"], f["clave"] in PROPORCION
    v = "—" if v is None else (f"{v:.0%}" if prop else (f"{v:.1f}" if isinstance(v, float) else str(v)))
    u = f"{u:.0%}" if prop and isinstance(u, (int, float)) else str(u)
    return f"    {'✓' if f['ok'] else '✗'} {f['etiqueta']:<34} {v:>6}  ({'al menos' if f['modo'] == 'min' else 'como mucho'} {u})"


def cmd_nivel(args: list[str]) -> int:
    """El nivel de autonomía (P27–P29): verlo, subirlo con evidencia y firma, bajarlo, declararlo."""
    from harness import autonomia

    config = leer_config()
    if not autonomia.spec(config):
        print("harness: el config no declara `autonomia`: este repo no gradúa la autonomía del agente.")
        return 1
    sub = args[0] if args and not args[0].startswith("-") else "ver"
    if sub == "subir":
        ok, msg, filas = autonomia.subir(config, REPO_ROOT, _firma_de(args) if "--firma" in args else "")
        print(("✓ " if ok else "✗ ") + msg)
        for f in filas:
            print(_fila(f))
        return 0 if ok else 2
    if sub == "bajar":
        motivo, firma = _opcion(args, "--motivo"), _firma_de(args)
        if not motivo or not firma:
            print("bajar a mano lleva --motivo y una firma (--firma o `git config user.name`).")
            return 1
        a = autonomia.bajar(config, REPO_ROOT, motivo, firma=firma, a=_opcion(args, "--a") or None)
        print(f"✓ bajó a {a}." if a else "✗ no hay un nivel más bajo que el actual (o --a no es más bajo).")
        return 0 if a else 2
    if sub == "declarar":
        a = args[1] if len(args) > 1 else ""
        ok, msg = autonomia.declarar(config, REPO_ROOT, a, _opcion(args, "--firma"), _opcion(args, "--motivo"))
        print(("✓ " if ok else "✗ ") + msg)
        return 0 if ok else 2
    if sub == "aplicar":
        # Producción sin shell: el arranque corre esto y aplica lo que un PR firmó (ADR 0012).
        rel = _opcion(args, "--registro") or autonomia.spec(config).get("firmadas") or ""
        if not rel:
            print("✗ no hay registro firmado: `autonomia.firmadas` del config o --registro <archivo>.")
            return 1
        f = Path(rel) if Path(rel).is_absolute() else REPO_ROOT / rel
        try:
            entradas = json.loads(f.read_text(encoding="utf-8")).get("transiciones")
        except (OSError, ValueError) as e:
            print(f"✗ {rel}: {e}")
            return 1
        hechas = autonomia.aplicar_firmadas(config, REPO_ROOT, entradas)
        for ref, ok, msg in hechas:
            print(f"{'✓' if ok else '✗'} {ref}: {msg}")
        if not hechas:
            print(f"nivel {autonomia.nivel(config, REPO_ROOT)}: sin transiciones nuevas en {rel}.")
        return 0 if all(ok for _, ok, _ in hechas) else 2
    r = autonomia.resumen(config, REPO_ROOT)
    if "--json" in args:
        print(json.dumps(r, indent=1, ensure_ascii=False, default=str))
        return 0
    import time as _t
    print(f"Nivel {r['nivel']} — {r['nombre']}" + (f"  (desde {_t.strftime('%Y-%m-%d %H:%M', _t.localtime(r['desde']))})" if r["desde"] else ""))
    print(f"  puede     {r['puede']}")
    if r.get("noPuede"):
        print(f"  no puede  {r['noPuede']}")
    print(f"  loop      {'sí, desatendido' if r['loop'] else 'no'}")
    for a in r["alertas"]:
        print(f"  ⚠ {a}")
    if r["siguiente"]:
        print(f"\nEvidencia para {r['siguiente']} (desde la última transición):")
        for f in r["evidencia"]:
            print(_fila(f))
        print("\n" + (f"Lista para subir: un humano firma con `{r['comando']} subir --firma \"Nombre\"`." if r["listoParaSubir"]
                      else "Todavía no: la evidencia no alcanza."))
    if r["historial"]:
        print("\nTransiciones:")
        for h in r["historial"]:
            quien = h.get("firma") or "automático"
            print(f"  {_t.strftime('%Y-%m-%d %H:%M', _t.localtime(h.get('at', 0)))}  {h.get('de')} → {h.get('a')}  "
                  f"{h.get('tipo')} · {quien}" + (f" · {h.get('motivo')}" if h.get("motivo") else ""))
    return 0


def cmd_hallazgo(args: list[str]) -> int:
    """¿La alerta del agente era real? Un humano lo juzga (afuera: el issue de la alerta) y la tasa de falsos
    positivos es evidencia de competencia (`falsosPositivosMax`), no sólo de obediencia."""
    from harness import autonomia

    if len(args) < 3 or args[0] != "juzgar" or args[2] not in ("valido", "falso"):
        print("uso: harness hallazgo juzgar <ref> valido|falso --firma \"Nombre\"")
        return 1
    ok, msg = autonomia.juzgar(leer_config(), REPO_ROOT, "hallazgo", args[1], args[2] == "valido", _firma_de(args))
    print(("✓ " if ok else "✗ ") + msg)
    return 0 if ok else 2


def verificar_certificado(config: dict, cert: Path | None) -> tuple[str, str]:
    """El porqué de una propuesta, comprobado por un programa que no es el agente (ADR 0014). Lo corre la CLI
    al juzgar, nunca un freno (los frenos no lanzan procesos). → (estado, detalle), estado en
    `autonomia.CERTIFICADO`. Sin verificador en el config: "" (el repo no certifica)."""
    spec = (config.get("autonomia") or {}).get("certificados") or {}
    cmd = spec.get("verificador") or []
    if not cmd:
        return "", ""
    if cert is None or not cert.is_file():
        return "ausente", "la propuesta no trae certificado"
    argv = [str(cert.resolve()) if a == "{certificado}" else a for a in cmd]
    try:
        p = subprocess.run(argv, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=float(spec.get("timeoutSegundos") or 30))
    except (OSError, subprocess.TimeoutExpired) as e:
        return "error", f"el verificador no corrió: {e}"
    ultima = next((l.strip() for l in reversed((p.stdout + p.stderr).splitlines()) if l.strip()), "")
    # Exit 3 = no pudo verificar (falta el verificador en esta máquina), como una señal OMITIDA del gate: no es un
    # certificado rechazado, y tampoco cuenta como verificado.
    return {0: "verificado", 3: "error"}.get(p.returncode, "rechazado"), ultima[:200]


def _cert_de(config: dict, propuesta: Path) -> Path:
    ext = ((config.get("autonomia") or {}).get("certificados") or {}).get("extension") or ".cert.json"
    return propuesta.with_name(propuesta.stem + ext)


def _decir_cert(estado: str, detalle: str) -> None:
    if estado:
        print(f"  certificado: {estado}" + (f" — {detalle}" if detalle else ""))


def cmd_recomendacion(args: list[str]) -> int:
    """Las propuestas que el agente deja en L1: un humano las juzga, y eso es evidencia (P27)."""
    from harness import events

    config = leer_config()
    d = REPO_ROOT / ".hermes" / "recomendaciones"
    sub = args[0] if args else "list"
    MARCA = "<!-- juicio:"
    if sub == "verificar":
        # Antes de aprobar: ¿el porqué se deduce de los hechos? Se mira, no se registra nada.
        if len(args) < 2:
            print("uso: harness recomendacion verificar <propuesta.md | certificado>")
            return 1
        p = (REPO_ROOT / args[1]) if not Path(args[1]).is_absolute() else Path(args[1])
        estado, detalle = verificar_certificado(config, p if p.suffix == ".json" else _cert_de(config, p))
        if not estado:
            print("✗ el repo no declara `autonomia.certificados.verificador`: no certifica propuestas.")
            return 1
        _decir_cert(estado, detalle)
        return 0 if estado == "verificado" else 2
    if sub == "juzgar":
        # Lo juzgado AFUERA (un issue etiquetado, un botón del chat): un adaptador lo registra con su ref.
        from harness import autonomia
        if len(args) < 3 or args[2] not in ("aceptada", "rechazada"):
            print("uso: harness recomendacion juzgar <ref> aceptada|rechazada [--certificado <archivo>] --firma \"Nombre\"")
            return 1
        c = _opcion(args, "--certificado")
        estado, detalle = verificar_certificado(config, (REPO_ROOT / c) if c else None)
        ok, msg = autonomia.juzgar(config, REPO_ROOT, "recomendacion", args[1], args[2] == "aceptada", _firma_de(args),
                                   certificado=estado)
        print(("✓ " if ok else "✗ ") + msg)
        if ok:
            _decir_cert(estado, detalle)
        return 0 if ok else 2
    if sub == "list":
        archivos = sorted(d.glob("*.md")) if d.is_dir() else []
        if not archivos:
            print(f"Sin recomendaciones en {d.relative_to(REPO_ROOT)}/.")
        for f in archivos:
            texto = f.read_text(encoding="utf-8", errors="replace")
            estado = re.search(r"<!-- juicio: (\w+)", texto)
            titulo = next((l.lstrip("# ").strip() for l in texto.splitlines() if l.strip()), f.name)
            cert = " 📜" if _cert_de(config, f).is_file() else ""
            print(f"  [{estado.group(1) if estado else 'pendiente':<9}] {f.relative_to(REPO_ROOT)}{cert} — {titulo[:80]}")
        return 0
    if sub not in ("aceptar", "rechazar") or len(args) < 2:
        print("uso: harness recomendacion list | aceptar|rechazar <archivo> [--firma \"Nombre\"]")
        return 1
    f = (REPO_ROOT / args[1]).resolve() if not Path(args[1]).is_absolute() else Path(args[1]).resolve()
    try:
        f.relative_to(d.resolve())
    except ValueError:
        print(f"✗ {args[1]} no está en {d.relative_to(REPO_ROOT)}/: sólo se juzgan recomendaciones del agente.")
        return 1
    if not f.is_file():
        print(f"✗ no existe {args[1]}.")
        return 1
    texto = f.read_text(encoding="utf-8", errors="replace")
    if MARCA in texto:
        print(f"✗ {f.name} ya fue juzgada: una recomendación cuenta una vez.")
        return 2
    firma = _firma_de(args)
    if not firma:
        print("✗ juzgar una recomendación lleva firma (--firma o `git config user.name`).")
        return 1
    aceptada = sub == "aceptar"
    estado, detalle = verificar_certificado(config, _cert_de(config, f))
    import time as _t
    f.write_text(texto.rstrip("\n") + f"\n\n{MARCA} {'aceptada' if aceptada else 'rechazada'} · {firma} · "
                 f"{_t.strftime('%Y-%m-%d %H:%M')}" + (f" · certificado {estado}" if estado else "") + " -->\n",
                 encoding="utf-8")
    events.record(config, REPO_ROOT, "recomendacion", archivo=f.relative_to(REPO_ROOT).as_posix(), aceptada=aceptada, firma=firma,
                  **({"certificado": estado} if estado else {}))
    print(f"✓ {f.name}: {'aceptada' if aceptada else 'rechazada'} por {firma}. Cuenta como evidencia para subir de L1.")
    _decir_cert(estado, detalle)
    return 0


def cmd_rule(args: list[str]) -> int:
    import argparse

    if not args or args[0] not in ("list", "add", "rm", "test"):
        print("uso: harness rule list [familia] | add <familia> … | rm <familia> <id> | test <familia> <texto>")
        return 1
    sub, resto = args[0], args[1:]
    config = leer_config()

    if sub == "list":
        for fam in ([resto[0]] if resto else FAMILIAS):
            reglas = lista_de(config, fam)
            print(f"{fam} ({len(reglas)})")
            for r in reglas:
                print(f"  {r.get('id', '?'):<24} {str(r.get('reason') or r.get('hint') or '')[:90]}")
        return 0

    if sub == "test":
        if len(resto) < 2 or resto[0] not in FAMILIAS:
            print(f"uso: harness rule test <familia> <texto>   familias: {', '.join(FAMILIAS)}")
            return 1
        fam, texto = resto[0], " ".join(resto[1:])
        if fam == "routes":
            print(turn.route(config, texto) or "ninguna ruta casa")
            return 0
        d = decision(config, REPO_ROOT, fam, {}, texto)
        if d is None or not (d.block or d.approve):
            print("pasa — ninguna regla lo frena")
            return 0
        print(f"{'BLOQUEA' if d.block else 'ESCALA A UN HUMANO'} — regla `{(d.rule or {}).get('id', '?')}`\n{d.message}")
        return 0

    if sub == "rm":
        if len(resto) < 2:
            print("uso: harness rule rm <familia> <id> [--apply]")
            return 1
        fam, rid = resto[0], resto[1]
        reglas = lista_de(config, fam)
        quedan = [r for r in reglas if r.get("id") != rid]
        if len(quedan) == len(reglas):
            print(f"no hay `{rid}` en {fam}")
            return 1
        print(json.dumps(next(r for r in reglas if r.get("id") == rid), indent=2, ensure_ascii=False))
        return escribir(set_ruta(config, fam, quedan), "--apply" in resto, f"quitar `{rid}` de {fam}")

    ap = argparse.ArgumentParser(prog="harness rule add")
    ap.add_argument("familia", choices=list(FAMILIAS))
    ap.add_argument("--id", required=True)
    ap.add_argument("--pattern", required=True)
    ap.add_argument("--example", required=True)
    ap.add_argument("--reason")
    ap.add_argument("--hint")
    ap.add_argument("--more", action="append", default=[], help="otra variante que tiene que frenar (repetible)")
    ap.add_argument("--path", action="append", default=[], help="patterns: regex de rutas donde aplica (repetible)")
    ap.add_argument("--example-path", help="patterns: dónde el ejemplo tiene que frenar")
    ap.add_argument("--agent-only", action="store_true", help="protectedPaths: sólo frena al agente, no al pre-commit")
    ap.add_argument("--outside-repo", action="store_true", help="protectedPaths: la regla mira rutas de fuera del repo")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(resto)
    regla = {"id": a.id, "pattern": a.pattern, "example": a.example}
    if a.more:
        regla["moreExamples"] = a.more
    if a.familia == "routes":
        regla["hint"] = a.hint or a.reason
    else:
        regla["reason"] = a.reason
    if a.path:
        regla["paths"] = a.path
    if a.example_path:
        regla["examplePath"] = a.example_path
    if a.agent_only:
        regla["agentOnly"] = True
    if a.outside_repo:
        regla["outsideRepo"] = True
    problemas = validar(config, a.familia, regla)
    print(json.dumps(regla, indent=2, ensure_ascii=False))
    if problemas:
        print("\n✗ la regla no entra:")
        for p in problemas:
            print(f"  - {p}")
        return 1
    print("✓ el ejemplo frena, ningún inocente muerde y el config pasa el lint.")
    return escribir(set_ruta(config, a.familia, lista_de(config, a.familia) + [regla]), a.apply, f"agregar `{a.id}` a {a.familia}")


def cmd_config(args: list[str]) -> int:
    if not args or args[0] not in ("get", "set"):
        print("uso: harness config get [ruta] | set <ruta> <valor> [--apply]")
        return 1
    config = leer_config()
    if args[0] == "get":
        v = get_ruta(config, args[1]) if len(args) > 1 else config
        print(json.dumps(v, indent=2, ensure_ascii=False) if not isinstance(v, str) else v)
        return 0 if v is not None else 1
    resto = [x for x in args[1:] if x != "--apply"]
    if len(resto) != 2:
        print("uso: harness config set <ruta> <valor> [--apply]")
        return 1
    ruta, valor = resto[0], _valor(resto[1])
    if any(ruta == f or ruta.startswith(f + ".") for f in FAMILIAS):
        print(f"`{ruta}` es una lista de reglas: usá `harness rule add|rm` (prueba el ejemplo antes de escribir).")
        return 1
    antes = get_ruta(config, ruta)
    try:
        nuevo = set_ruta(config, ruta, valor)
    except (ValueError, IndexError, TypeError, AttributeError) as e:
        print(f"no pude poner `{ruta}`: {e}")
        return 1
    hallazgos = rules.lint_one(nuevo, ".hermes/harness.config.json", json.dumps(nuevo, indent=2, ensure_ascii=False))
    print(f"{ruta}: {json.dumps(antes, ensure_ascii=False)} → {json.dumps(valor, ensure_ascii=False)}")
    if hallazgos:
        print("✗ el config resultante no pasa el lint:\n  " + "\n  ".join(hallazgos))
        return 1
    return escribir(nuevo, "--apply" in args, f"`{ruta}` actualizado")


def validar_senal(config: dict, senal: dict) -> list[str]:
    """Una señal del gate nueva: con `why` (P6), con argv y con un nombre que no se repite."""
    errores = []
    if not senal.get("name"):
        errores.append("falta el nombre")
    if any(s.get("name") == senal.get("name") for s in (config.get("gate") or {}).get("signals") or []):
        errores.append(f"ya hay una señal `{senal.get('name')}`")
    if not senal.get("why"):
        errores.append("falta `why`: qué error atrapa que ninguna otra señal ve (P6)")
    if not isinstance(senal.get("command"), list) or not senal["command"]:
        errores.append("falta el comando (después de `--`, como argv: sin shell)")
    return errores


def cmd_signal(args: list[str]) -> int:
    config = leer_config()
    senales = (config.get("gate") or {}).get("signals") or []
    if not args or args[0] == "list":
        for s in senales:
            print(f"  {s.get('name', '?'):<40} {' '.join(s.get('command') or [])}")
        return 0
    apply = "--apply" in args
    if args[0] == "rm" and len(args) > 1:
        quedan = [s for s in senales if s.get("name") != args[1]]
        if len(quedan) == len(senales):
            print(f"no hay una señal `{args[1]}`")
            return 1
        if not quedan:
            print("el gate quedaría sin señales: no verifica nada.")
            return 1
        return escribir(set_ruta(config, "gate.signals", quedan), apply, f"quitar la señal `{args[1]}`")
    if args[0] == "add" and "--" in args:
        corte = args.index("--")
        opciones, argv = [a for a in args[1:corte] if a != "--apply"], args[corte + 1:]
        senal = {"name": opciones[0] if opciones and not opciones[0].startswith("--") else ""}
        if "--why" in opciones and opciones.index("--why") + 1 < len(opciones):
            senal["why"] = opciones[opciones.index("--why") + 1]
        senal["command"] = argv
        if "--fast-skip" in opciones:
            senal["fastSkip"] = True
        problemas = validar_senal(config, senal)
        print(json.dumps(senal, indent=2, ensure_ascii=False))
        if problemas:
            print("\n✗ la señal no entra:\n  - " + "\n  - ".join(problemas))
            return 1
        return escribir(set_ruta(config, "gate.signals", senales + [senal]), apply, f"agregar la señal `{senal['name']}` al gate")
    print('uso: harness signal list | add "nombre" --why "…" [--fast-skip] [--apply] -- cmd args… | rm "nombre" [--apply]')
    return 1


def cmd_profile(args: list[str]) -> int:
    d = HARNESS_HOME / "plantillas" / "perfiles"
    for p in sorted(d.glob("*.json")):
        try:
            pf = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        print(f"  {p.stem:<12} {' '.join(pf.get('codeExtensions') or [])}"
              + (f"  · señales: {', '.join(s.get('name', '?') for s in pf.get('signals') or [])}" if pf.get("signals") else ""))
    print("Instalar con uno: python3 scripts/cli.py install <repo> --profile <nombre>")
    return 0


def cmd_task(args: list[str]) -> int:
    config = leer_config()
    spec = config.get("loop") or {}
    if not spec:
        print("el config no declara `loop`.")
        return 1
    f = REPO_ROOT / spec.get("tasksFile", ".hermes/loop/tasks.md")
    if not args or args[0] == "list":
        import panel

        t = panel._tareas(config, REPO_ROOT)
        print(f"{f.relative_to(REPO_ROOT)} — {len(t['pending'])} pendientes · {t['done']} verdes · {len(t['escalated'])} escaladas")
        for x in t["escalated"]:
            print(f"  [!] {x}")
        for x in t["pending"]:
            print(f"  [ ] {x}")
        return 0
    if args[0] == "add" and len(args) > 1:
        texto = " ".join(args[1:]).strip().replace("\n", " ")
        previo = f.read_text(encoding="utf-8") if f.is_file() else "# Tareas del loop autónomo\n\n"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(previo + ("" if previo.endswith("\n") else "\n") + f"- [ ] {texto}\n", encoding="utf-8")
        print(f"+ {texto}\n  → {f.relative_to(REPO_ROOT)}. Correla: python3 {_rel(Path(__file__))} loop --apply")
        return 0
    print('uso: harness task add "texto" | task list')
    return 1


def pasamanos(nombre: str, args: list[str]) -> int:
    script = HERE / ("selftest.py" if nombre == "selftest" else f"{nombre}.py")
    if not script.is_file():
        print(f"harness: no existe {script.name} en esta instalación.")
        return 1
    return subprocess.run([sys.executable, str(script), *args]).returncode


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0 if argv else 1
    cmd, resto = argv[0], argv[1:]
    if cmd in PASAMANOS:
        return pasamanos(cmd, resto)
    if not CONFIG_PATH.is_file():
        print(f"harness: no hay {CONFIG_PATH}. Instalalo primero (`harness install <repo>`).")
        return 1
    fn = {"status": cmd_status, "rule": cmd_rule, "config": cmd_config, "profile": cmd_profile, "task": cmd_task,
          "signal": cmd_signal, "nivel": cmd_nivel, "recomendacion": cmd_recomendacion,
          "hallazgo": cmd_hallazgo}.get(cmd)
    if fn is None:
        print(f"harness: comando desconocido `{cmd}`.\n")
        print(__doc__)
        return 1
    try:
        return fn(resto)
    except (OSError, ValueError) as e:
        print(f"harness: {e}")
        return 1


if __name__ == "__main__":
    # Windows: la consola y los pipes son cp1252 por defecto, y `▶ ✓ ✗` o una `ñ` revientan el
    # print ANTES de verificar nada — el gate no fallaba, desaparecía (lo cazó la matriz de CI).
    for _s in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main(sys.argv[1:]))
