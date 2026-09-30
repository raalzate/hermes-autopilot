---
name: harness-audit
description: Prueba de vida del arnés en este repo y en esta máquina. Para cada regla, qué comando falla si alguien la viola; qué está instalado y muerto; qué regla vive sólo en prosa. Usala al portar el arnés, después de actualizar Hermes, o cuando un freno "debería haber frenado" y no frenó.
version: 1.0.0
platforms: [macos, linux, windows]
metadata:
  hermes:
    tags: [harness, audit]
    category: harness
---

# /harness-audit

Corré, en orden, y reportá una tabla **regla → mecanismo → evidencia (comando + resultado)**:

1. **Self-test** (`scripts/selftest.py`): ¿cada regla del config muerde su `example` por el
   camino del plugin? ¿los inocentes pasan?
2. **Lint** (`scripts/lint.py --rules` y después sin flags): qué clases están activas y si el
   repo entero pasa.
3. **Doctor** (`scripts/doctor.py`): lo que el gate no ve porque vive en `~/.hermes/`:
   - plugin `repo-harness` instalado **y** en `plugins.enabled`;
   - skills del repo confiadas (`hermes skills trust`);
   - que Hermes cargue `AGENTS.md` y no un `.hermes.md` que lo tape;
   - memoria cerca del tope, o con algo que el arnés prohíbe guardado de antes.
4. **Hermes real**, si está instalado: `hermes plugins doctor <ruta-del-plugin> --ci` y
   `hermes hooks doctor` si el repo usa el shell hook.
5. **Prosa sin mecanismo**: leé `AGENTS.md` y marcá cada "siempre/nunca/hay que" que no tenga
   una regla del config o una señal del gate detrás. Cada una es un hallazgo: o se convierte en
   freno (skill `new-guardrail`) o se borra.

Un control encendido que nadie ejecuta es "instalado y muerto": reportalo como rojo, no como
verde con asterisco.
