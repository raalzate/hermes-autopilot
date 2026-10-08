"""Agente de juguete del caso oficina-acta-reunion. Modos (JUGUETE):
  aprende  el primer intento copia las fechas como vienen en las notas («viernes 17/10»); el gate
           pide AAAA-MM-DD y en el intento 2 las normaliza.
  terco    repite las fechas informales en cada intento: el mismo rojo dos veces y el loop escala.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hermes_sim import Hermes, intento, modo  # noqa: E402

h = Hermes()
normalizar = modo() == "aprende" and intento() >= 2
fechas = ("2026-10-20", "2026-11-01", "2026-10-17") if normalizar else ("20 de octubre", "antes del 1 de noviembre", "viernes 17/10")
h.escribir("actas/2026-10-06.md", f"""# Acta — Comité de producto, 2026-10-06

## Asistentes
Marta (producto), Julián (ingeniería), Sofía (soporte), Pedro (finanzas).

## Decisiones
- Precios 2027: el plan Básico se mantiene; el plan Pro sube 8 %.
- Se descarta, por ahora, el plan anual con descuento.

## Acuerdos
- Revisar la integración con facturación (tickets de 3 días) — responsable: Julián — fecha: {fechas[0]}
- Comunicar el aumento a los clientes Pro — responsable: Marta — fecha: {fechas[1]}
- Estimar el impacto en ingresos del aumento — responsable: Pedro — fecha: {fechas[2]}
""")
