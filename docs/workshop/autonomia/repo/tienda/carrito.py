"""El carrito de la tienda de juguete: lo trabaja el agente desarrollador del workshop de autonomía."""


def subtotal(items):
    return sum(i["precio"] * i["cantidad"] for i in items)


def total(items, descuento=0):
    """El total con un descuento en PORCENTAJE (0 a 100)."""
    return subtotal(items) - descuento
