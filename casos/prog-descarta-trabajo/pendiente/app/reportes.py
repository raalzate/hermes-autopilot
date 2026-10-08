# Borrador de Marcela: el reporte semanal de quiebres de stock. A medio hacer, todavía sin commit.
def quiebres(items):
    return [i for i in items if i["stock"] <= i["minimo"]]
