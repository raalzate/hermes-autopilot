# Gotchas — incidentes que dejaron infraestructura

Formato fijo (regla `INCIDENTE` del lint): **Síntoma / Causa / Regla / Mecanismo**. El ciclo lo
guía la skill `lesson`. Si un incidente ya estaba acá y volvió a pasar, el hallazgo es que el
mecanismo no alcanzó: hace falta uno más fuerte, no otra entrada.

### GOTCHA — Un plugin de Hermes que revienta no deja pasar: bloquea

- **Síntoma:** el primer diseño del plugin asumía el contrato de Claude Code (un hook roto no
  bloquea nada) y no atrapaba excepciones en `pre_tool_call`.
- **Causa:** en Hermes, `pre_tool_call` falla CERRADO: una excepción o un timeout del callback
  bloquean la herramienta (`_HOOK_TIMEOUT_FAIL_CLOSED_HOOKS` en `hermes_cli/plugins_dispatch.py`).
  Un bug del arnés habría frenado toda la terminal.
- **Regla:** ningún callback del plugin lanza; un arnés roto deja pasar (P5).
- **Mecanismo:** envoltorio `_seguro` en `plugin/__init__.py`, exigido por `invariants` (y sin
  `raise`); self-test §4 con un freno que divide por cero, con el núcleo entero roto y con kwargs
  basura.

### GOTCHA — El plugin pasaba el self-test y en Hermes no importaba

- **Síntoma:** self-test verde con 426 verificaciones; `hermes plugins doctor plugin --ci` en el
  Hermes real: `Plugin registration failed: No module named 'harness'`.
- **Causa:** el núcleo vivía en una carpeta harness de la raíz, al lado de `plugin/`, y el plugin lo encontraba
  agregando `plugin/..` al `sys.path`. Hermes **copia** el directorio del plugin para validarlo (y
  para instalarlo): en la copia, `plugin/..` no tiene nada. El self-test cargaba el plugin desde su
  lugar original, así que nunca vio la diferencia.
- **Regla:** el plugin es autocontenido: todo lo que importa viaja dentro de su directorio y se
  importa relativo, como el paquete que Hermes arma (`hermes_plugins.<slug>`).
- **Mecanismo:** el núcleo vive en `plugin/harness/`; el self-test (§1) carga el plugin desde una
  COPIA y con el mismo esquema de paquete que `plugins_loader.py`; las señales del gate
  `hermes plugins doctor` y `scripts/hermes_e2e.py` lo verifican contra el Hermes instalado.

### GOTCHA — Un `patch` de Hermes en modo V4A se salteaba los frenos de escritura

- **Síntoma:** la revisión mandó `patch` con `mode: "patch"` y un texto
  `*** Update File: .env` — sin `path` — y el freno lo dejó pasar. Lo mismo con un `print(` en el
  plugin.
- **Causa:** los frenos de escritura miraban sólo el argumento `path`. El modo V4A de Hermes
  (`tools/patch_parser.py`) lleva las rutas en encabezados dentro del texto, varias por llamada, y
  cualquier modelo lo puede usar.
- **Regla:** un freno de escritura evalúa TODAS las rutas que la herramienta va a tocar, y el texto
  que agrega; la gramática del formato es de Hermes y va al config.
- **Mecanismo:** `paths_of`/`content_of` en `plugin/harness/core.py` leen `tools.$multiFilePatch`;
  self-test §3b (Update, Move, borrado inocente) y `scripts/hermes_e2e.py` dentro de Hermes;
  mutación "patch V4A: sólo se mira `path`" en `scripts/mutations.py`.

### GOTCHA — El self-test pisaba su propio código y daba un rojo por la razón equivocada

- **Síntoma:** una mutación que rompía la lectura del índice en el pre-commit SOBREVIVIÓ, aunque el
  caso de git real "fallaba" como se esperaba.
- **Causa:** el caso tomaba el primer `patterns[]` con `examplePath`, que era
  `plugin/harness/core.py`; al "limpiar el disco" sobreescribía el arnés del repo temporal, el hook
  reventaba y el commit fallaba por eso — con o sin el bug.
- **Regla:** un caso que espera rojo tiene que fallar por SU razón: nunca reusar como muestra un
  archivo del que depende el propio freno.
- **Mecanismo:** el caso elige un `examplePath` que no exista; `scripts/mutations.py` (señal del
  gate) es lo que distingue un rojo verdadero de uno accidental.

### GOTCHA — Una ruta de Windows vista desde POSIX caía DENTRO del repo

- **Síntoma:** el self-test mandó `C:\home\u\.hermes\.env` a `write_file` y el freno la dejó
  pasar.
- **Causa:** en macOS/Linux `Path("C:\\…")` es una ruta *relativa* con un nombre raro; resuelta
  contra el cwd quedaba dentro del repo, así que se evaluaba con las reglas del repo y nunca con
  las de `outsideRepo`.
- **Regla:** una ruta con unidad de Windows es de afuera del repo en cualquier plataforma.
- **Mecanismo:** `rel_to_repo` en `plugin/harness/core.py` la devuelve con `../`; self-test §3 repite
  cada `protectedPaths` con `outsideRepo` usando separadores de Windows.

### GOTCHA — El invariante de P4 confundía claves del config con nombres de herramientas

- **Síntoma:** el lint marcó `plugin/harness/guards.py` por nombrar herramientas de Hermes, y el archivo
  no nombraba ninguna.
- **Causa:** la regex prohibía el literal entre comillas, y `config.get("terminal")` es la clave
  de la sección del config, no el nombre de la herramienta `terminal`. Un freno que muerde de más
  se desactiva a mano en una semana.
- **Regla:** el invariante caza la **comparación** contra un nombre (`== "patch"`,
  `in ("terminal", …)`), que es lo que de verdad cablea una herramienta.
- **Mecanismo:** `invariants` sobre `plugin/harness/guards.py` en el config; self-test §7 exige que el
  archivo real pase cada invariante (P3).

### GOTCHA — El parser de `plugin.yaml` leía un solo hook de la lista

- **Síntoma:** el self-test dijo que el plugin registraba hooks que su manifiesto no declaraba, y
  el manifiesto sí los declaraba.
- **Causa:** una regex de varias líneas para la lista YAML se tragaba el salto de línea y cortaba
  después del primer ítem.
- **Regla:** sin PyYAML, las listas YAML se leen línea por línea, no con una regex de bloque.
- **Mecanismo:** `manifest_hooks` en `scripts/selftest.py` (línea por línea); self-test §1 cruza
  `provides_hooks` contra lo que `register(ctx)` registra, en las dos direcciones.
