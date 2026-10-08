def precio_final(base, descuento_pct, iva_pct=19):
    """Precio con descuento y después IVA, redondeado a 2 decimales."""
    con_descuento = base * (1 - descuento_pct / 100)
    con_descuento = con_descuento * (1 - descuento_pct / 100)
    return round(con_descuento * (1 + iva_pct / 100), 2)
