# Huecos — auditoría del arnés

Un hueco es algo que un agente puede hacer y que el arnés dice que no pasa, o algo que el arnés
debería ver y no ve. Esta página es la auditoría del 2026-10-07: se buscaron armando los
[casos replicables](../casos/README.md). Cada caso es un agente que toma un atajo real, y un atajo
que pasaba sin que nada lo notara era un hueco.

Regla de la casa (P15): un hueco se cierra con el mecanismo más fuerte disponible y con su prueba
(un caso en el self-test, una mutación, un caso replicable). Lo que no se puede cerrar queda
**acá**, con su estado, para que nadie lo dé por cubierto.

## Cerrados

| # | Hueco | Cómo apareció | Mecanismo | Prueba |
|---|---|---|---|---|
| 1 | La terminal escribía o borraba rutas protegidas con `cp`, `mv`, `install`, `ln`, `rsync`, `rm`, `shred`, `truncate`, `unlink`, `sed -i`, `perl -i`: el freno sólo veía `>` y `tee` | deuda conocida en `STATUS.md` y `docs/arnes.md`; caso `infra-env-secretos` (`cp … .env`) | `terminal.redirectTargets` ampliado, y cada argumento de un grupo se evalúa por separado (`rm a .env`). `git rm --cached` sigue pasando: limpiar el índice no es escribir | self-test §3 (cuatro formas por regla protegida) y la mutación «rm con varios argumentos» |
| 2 | **Leer secretos**: `read_file .env`, `cat .env`, `grep X .env`, `source .env`, `< .env` o `cp .env /tmp` mandaban el valor al proveedor del modelo y lo dejaban en el historial. Sólo se protegía escribir | caso `infra-diagnostico-sin-secretos` | familia nueva `protectedReads` (con `outsideRepo` para `~/.ssh` y `~/.hermes`), `read_guard` sobre `tools.read`, y `terminal.readTargets` para los comandos que leen | self-test §3 (cada regla por la herramienta de lectura y por `cat`, `grep` y `<`; los inocentes, como `.env.example`, pasan) y 2 mutaciones |
| 3 | **Reward hacking en el loop**: el agente puede conseguir verde ablandando lo que decide «terminado» (el verificador, su config, la cola) o borrando el test | casos `prog-tests-saltados` (`borra`), `infra-terraform-destroy`, `prog-migracion-aplicada`, `datos-anonimizar` e `infra-env-secretos` (`atajo`) | el loop compara, antes y después de cada intento, los `protectedPaths` versionados y `loop.lockedPaths` (aunque estén ignorados por git, como `.env`). Si cambió alguno escala, ni siquiera corre el gate y aunque el gate diera verde no vale | self-test §13 (un agente que reescribe su verificador) y 2 mutaciones |
| 4 | El agente podía editar la cola del loop: asignarse, cerrarse o borrarse tareas | revisión del loop | `protectedPaths[cola-del-loop]` (sólo al agente) y `^\.hermes/loop/` en `lockedPaths` | self-test §3 (el `example` de la regla) |
| 5 | Dos loops en el mismo repo se pisaban el estado y la rama | revisión del loop | candado `.git/harness-loop.lock`. Uno viejo (un loop matado con -9) no traba: vence por tiempo y por pid | self-test §13 y la mutación «dos loops en el mismo repo» |
| 6 | La plantilla no frenaba descartar trabajo sin commitear de otra persona (`git checkout -- .`, `git restore .`, `git clean -f`, `git stash drop`) | caso `prog-descarta-trabajo` | regla `descartar-cambios` en la plantilla (y en este repo, junto a `clean-f`). `git stash` y `git checkout -b` siguen pasando | el self-test deriva los casos del `example` y los `moreExamples` |
| 7 | El freno de intervalo del cron no tenía id: el registro y el panel decían «`?`» | caso `infra-cron-deploy` | id `cron-intervalo-minimo` | el caso lo exige en sus frenos |
| 8 | El panel no decía qué reglas mordían más: el workshop (5.2) lo preguntaba y no se podía contestar | workshop | `topRules` en el estado y la tarjeta «Los que más mordieron» | self-test §13 |
| 9 | Una regla nueva podía morder justo lo que su propio caso necesitaba (un `find` de sólo lectura sobre `backups/`) | caso `ops-limpiar-disco` | `inocentes` por caso, cargados **antes** de validar sus reglas con `cli.validar` | self-test §13 (una regla que muerde un inocente del caso lo rompe) y una mutación |
| 10 | Los casos no eran portables, y lo cazó la matriz de CI: en Windows, archivos abiertos sin `encoding` (cp1252, «Julián» ≠ «Julián») y semillas convertidas a CRLF (cambiaba el hash de la migración «aplicada»). Además, GitGuardian marcó como secretos las credenciales de juguete de las semillas | CI del PR #2 | `.gitattributes` (`casos/** eol=lf`); el runner rechaza código de un caso que abra archivos sin `encoding`; las semillas llevan `{{falso}}` y el runner pone un valor aleatorio en cada sandbox | la forma de cada caso en el self-test §13 y en `casos.py`; reproducido con un locale ISO-8859-1 |
| 11 | Del ensayo del workshop (ronda anterior): gate rojo de entrada en todo repo instalado, pre-commit que no dejaba commitear la plantilla, `patterns` multilínea que el lint nunca ve, firma del rojo que cortaba nombres, `pdb` colgando el loop | `docs/decisions/0006-autonomia-loop-cli-panel.md` | ver la ADR | self-test §11 y §13 |

## Abiertos

| Hueco | Riesgo | Por qué sigue abierto | Mitigación hoy |
|---|---|---|---|
| Escrituras y lecturas **por dentro** de un programa (`python3 -c`, un script del repo, `make`) **fuera** del loop | un agente interactivo puede escribir o leer un secreto sin que el freno de terminal lo vea | un freno por regex no puede saber qué hace un programa. Hacerlo de verdad es aislar al agente (sandbox de archivos o contenedor), y eso es de Hermes, no del arnés | dentro del loop, los intocables (hueco 3). Afuera, el pre-commit (nada protegido entra al historial) y `approvals.deny` de Hermes |
| Secretos en el **entorno** del agente (`env`, `printenv`, `echo $DB_PASSWORD`) | si Hermes corre con secretos exportados, cualquier comando los ve | no se puede vedar `env` sin romper trabajo legítimo, y el riesgo nace al exportarlos | no exportar secretos al entorno de Hermes; `doctor.py` es el lugar para avisarlo (pendiente) |
| Otras herramientas de lectura de Hermes (búsqueda en archivos, lectura de imágenes) | leen secretos sin pasar por `read_guard` | `tools.read` declara sólo `read_file`, la única verificada. Sumar nombres sin verificarlos contra el código de Hermes es adivinar | verificar con Hermes instalado (`hermes_e2e.py`) y sumarlas a `tools.read` |
| **Exfiltración por red** (`curl -d @archivo https://…`) | lo leído sale sin pasar por el modelo | una allowlist de dominios es política de red, no del repo | `curl … \| bash` está vedado, y `protectedReads` frena subir un secreto que el comando nombra (`curl -d @.env`, `curl -T .env`). Lo que un programa lee y manda por dentro no se ve |
| **Inyección de prompt** en lo que el agente lee (tickets, correos, páginas) | el agente obedece instrucciones de un tercero | ningún freno puede decidir si un texto es dato o instrucción | los frenos no dependen del modelo (caso `soporte-ticket-inyeccion`): lo peligroso se frena igual. Lo que no es una acción vedada (una copia en un texto) depende de que el gate de la tarea lo verifique |
| Sensor **inferencial** con tasa de acierto (`harness-review`) | lo que el gate no puede verificar sigue siendo juicio sin medir | necesita un conjunto de evaluación etiquetado | declarado en `guias-y-sensores.md` §6 |
| El loop con **Hermes real** como agente | los casos prueban el arnés con un agente determinista, no cómo reacciona un modelo al motivo de un freno | esta máquina no tiene Hermes; CI tampoco | `casos.py preparar <id> <dir> --hermes`, a mano |
| Varias tareas **en paralelo** | un loop por repo, una tarea por vez | worktrees + un candado por worktree | el candado evita el daño; el paralelismo es trabajo futuro |
