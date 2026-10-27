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

### GOTCHA — En producción la autonomía no se podía ganar

- **Síntoma:** en el piloto doctiling-sre (Railway, 2026-10-27), «días en el nivel» marcaba 0 para
  siempre y L1 era imposible aunque el agente tenía 30 sesiones limpias.
- **Causa:** el estado vivía en `.git/harness-autonomia.json` y la imagen no tiene `.git`: el nivel
  no se guardaba y `desde` quedaba en 0. Firmar pedía además una shell en el contenedor, y el puerto
  22 estaba bloqueado.
- **Regla:** el arnés no supone `.git` ni terminal donde corre el agente: el estado va a un volumen
  y la firma es un PR revisado.
- **Mecanismo:** `HARNESS_AUTONOMIA_FILE`, `autonomia.inicio` (desde el primer evento),
  `autonomia.firmadas` + `cli.py nivel aplicar`, freno `autonomia-firmada`; self-test §15 y la
  mutación «una transición firmada se aplica dos veces».

### GOTCHA — Dos bloqueos que no eran del agente le costaron la ventana de evidencia

- **Síntoma:** en la primera ventana del piloto, dos `nivel-L0-*` dejaron dos sesiones «sucias».
  Uno era una herramienta nueva del plugin (`sre_panel`) que el manifiesto no clasificaba; el otro,
  la revisión de skills en segundo plano de Hermes llamando a `skill_manage`.
- **Causa:** el freno de nivel le atribuía al agente todo lo que bloqueaba.
- **Regla:** un bloqueo dice de quién es. El del config se bloquea igual pero no resta evidencia;
  lo que Hermes hace por su cuenta se apaga en su config.
- **Mecanismo:** `integ.declarada` (fuera de `toolNames` → `origen: config`), `autonomia.fuera_de_nivel`,
  la alerta del panel; `doctor.py` avisa `skills.creation_nudge_interval` ≠ 0. Self-test §15 y la
  mutación «un bloqueo del config le resta evidencia al agente».

### GOTCHA — `MEDIA:` en un texto citado adjunta un archivo

- **Síntoma:** al revisar `hermes_cli/send_cmd.py` el piloto vio que `MEDIA:<ruta>`, en cualquier
  parte del texto, se manda como adjunto. Una línea de log con `MEDIA:/opt/data/.env` habría
  mandado los secretos al chat.
- **Causa:** las respuestas citan texto de terceros (logs, correos) y el canal interpreta ese
  marcador.
- **Regla:** la respuesta no lleva ningún marcador que el canal interprete sin romperlo.
- **Mecanismo:** `output.defang` (`media-adjunto`) en `turn.respuesta`; self-test §14 con su
  `example` y la mutación «la respuesta deja vivo un MEDIA: citado».

### GOTCHA — El aviso de terceros se perdía tras un reinicio o detrás de otro plugin

- **Síntoma:** en Telegram, respuestas basadas en logs salían sin el aviso: después de reiniciar el
  contenedor (cada deploy), y cada vez que el plugin propio del repo cambiaba la respuesta.
- **Causa:** la marca de la sesión vivía en la memoria del proceso; y Hermes no encadena
  `transform_llm_output` (gana el primer plugin que devuelve texto, en orden alfabético).
- **Regla:** la marca se reconstruye del registro; un plugin que carga antes que `repo-harness` y
  transforma la respuesta pone él el aviso.
- **Mecanismo:** `_contaminada` en `plugin/__init__.py` (una búsqueda por sesión y proceso en el
  registro); `doctor.py` avisa el plugin que carga antes y transforma; self-test §15 y la mutación
  «la marca de terceros no sobrevive un reinicio».

### GOTCHA — `--upgrade` habría borrado el arreglo del repo

- **Síntoma:** el piloto parchó `autonomia.py` y `selftest.py` en su copia del arnés; un
  `install.py --upgrade` los reemplazaba sin decir nada.
- **Causa:** el instalador no sabía qué había escrito él y qué había cambiado el repo después.
- **Regla:** un archivo del arnés que el repo cambió no se pisa sin que alguien lo mire.
- **Mecanismo:** `.hermes/harness/huellas.json`, la marca `!` y `--pisar`; self-test §11 y §16, y la
  mutación «install --upgrade borra un parche local».
