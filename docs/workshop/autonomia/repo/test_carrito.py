import unittest

from tienda.carrito import subtotal, total

ITEMS = [{"precio": 100, "cantidad": 2}, {"precio": 50, "cantidad": 1}]


class Carrito(unittest.TestCase):
    def test_subtotal(self):
        self.assertEqual(subtotal(ITEMS), 250)

    def test_total_sin_descuento(self):
        self.assertEqual(total(ITEMS), 250)

    def test_total_con_descuento_en_porcentaje(self):
        self.assertEqual(total(ITEMS, descuento=10), 225)


if __name__ == "__main__":
    unittest.main()
