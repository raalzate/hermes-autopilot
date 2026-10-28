# 0014 — Lo que enseñó el primer piloto en producción

**Estado:** aceptada · **Fecha:** 2026-10-27

## Contexto

`doctiling-sre` es el primer repo que instaló el arnés y salió a producción: un agente SRE de solo
lectura sobre Hermes, en Railway, que observa con una CLI de catálogo cerrado, abre incidentes con
reglas y avisa por Telegram. Corre desde el 2026-10-21, desatendido, sin shell estable en el
contenedor y sin `.git`. En una semana subió de L0 a L1 (declarado, no ganado) y dejó quince
gotchas.

El arnés estaba pensado para un agente que desarrolla, con `.git`, terminal y un humano al lado. El
piloto mostró cuatro supuestos que en producción no valen:

1. **El estado vive en `.git/`.** La imagen no lo tiene: el nivel no se guardaba y los días en el
   nivel quedaban en 0, así que L1 no se podía ganar aunque el agente se portara bien.
2. **Firmar es correr un comando.** `nivel subir` y `recomendacion aceptar` piden una terminal en
   el contenedor; en la red del operador, el puerto 22 estaba bloqueado.
3. **Todo bloqueo del freno de nivel es culpa del agente.** Los dos de la primera ventana fueron
   del arnés (una herramienta nueva sin clasificar) y de Hermes (su revisión de skills en segundo
   plano). Le costaron la ventana.
4. **El código del arnés no se toca en el repo.** El repo tuvo que parchar su copia para resolver
   (1), y `install.py --upgrade` la habría pisado sin avisar.

Además, tres hallazgos sobre Hermes que el arnés no veía: `MEDIA:<ruta>` en un texto adjunta el
archivo; `transform_llm_output` no se encadena (gana el primer plugin); y la marca de terceros vivía
en memoria y moría con cada deploy.

## Decisión

1. **Producción es un modo, no una excepción.** `HARNESS_AUTONOMIA_FILE` saca el estado de
   `.git/`; sin transición, la evidencia cuenta desde el primer evento del registro.
2. **Firmar es mergear.** `autonomia.firmadas` apunta a un archivo versionado de transiciones; un
   PR revisado agrega la entrada y `cli.py nivel aplicar` la aplica en el arranque, una vez y en
   orden. `subir` sigue exigiendo la evidencia: el PR firma, no regala. El agente no edita ese
   archivo (`autonomia-firmada`).
3. **Lo que se juzga afuera entra con su referencia.** `recomendacion juzgar` y `hallazgo juzgar`
   registran un juicio con `ref` (un issue, un mensaje) y firma, una vez por `ref`. Un adaptador
   (las etiquetas `rec:aceptada` del tablero, en el piloto) los llama.
4. **La competencia también es evidencia.** `hallazgosJuzgados` y `falsosPositivosMax`: un agente
   que observa y avisa se mide por cuántas de sus alertas eran reales, no sólo por no salirse.
5. **Cada bloqueo dice de quién es.** Una herramienta fuera de `toolNames` de su manifiesto se
   bloquea igual (vale `write`), pero con `origen: config`: no resta evidencia y el panel la
   muestra como alerta. Lo que Hermes hace por su cuenta lo avisa `doctor.py`.
6. **Un parche local no se borra en silencio.** `install.py` deja huellas de lo que instala;
   `--upgrade` frena lo que el repo cambió después, hasta que el arreglo sube o se pasa `--pisar`.
   Los manifiestos propios del repo viven en `.hermes/integraciones/<id>.json`, fuera del código del arnés.
7. **La salida rompe lo que el canal interpreta** (`output.defang`), y la marca de terceros
   sobrevive a un reinicio (se busca en el registro).
8. **Desde L2, el porqué se comprueba, no se cree.** Una propuesta puede traer un certificado
   (hechos, reglas, deducción) y `autonomia.certificados.verificador` declara el comando que lo
   comprueba sin compartir código con el agente. La CLI lo corre al juzgar y el resultado queda en
   el evento; `certificadosVerificadosMin` lo pide para subir. El piloto lo hace con `oo-horn` (Lean
   4, open-ontologies) sobre la causa raíz de cada incidente investigado. El arnés no elige la
   lógica: sólo exige un comando que salga 0 si verifica y 3 si no pudo verificar.

## Consecuencias

- Un repo que despliega puede ganar autonomía sin shell y con firma revisada en GitHub.
- El nivel declarado sigue siendo una alerta visible, también si lo declara un PR.
- `origen: config` abre una puerta: un manifiesto sin `toolNames` no atribuye nada (cuenta contra
  el agente, como antes). Atribuir exige declarar las herramientas.
- El certificado prueba que la conclusión se deduce de las reglas dadas, no que las reglas sean
  ciertas: siguen siendo conocimiento de quien las escribió, revisado como código. Y el freno no
  verifica (no lanza procesos): en L2 le dice al humano cómo hacerlo antes de aprobar.
- La plantilla no pide `certificadosVerificadosMin`: un repo sin verificador nunca llegaría a L3.
- Lo que no se cierra con código queda en [huecos](../huecos.md) (34–40) y en
  [hermes.md](../hermes.md#lo-que-enseñó-un-piloto-en-producción).
