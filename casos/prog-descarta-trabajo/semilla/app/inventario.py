def stock_disponible(stock, reservado):
    """Unidades que se pueden vender: nunca negativo."""
    return stock - reservado
