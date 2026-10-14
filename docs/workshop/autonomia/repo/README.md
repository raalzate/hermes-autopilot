# Tienda de juguete

El repo que trabaja el agente desarrollador del workshop de autonomía de Hermes Autopilot. Tiene un
bug a propósito: `total()` resta el descuento como un monto, y el descuento es un porcentaje.

```bash
python3 -m unittest -q      # 1 falla: test_total_con_descuento_en_porcentaje
```
