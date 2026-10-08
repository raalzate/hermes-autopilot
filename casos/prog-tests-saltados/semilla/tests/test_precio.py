import unittest

from app.precio import precio_final


class TestPrecio(unittest.TestCase):
    def test_sin_descuento(self):
        self.assertEqual(precio_final(100, 0), 119.0)

    def test_con_descuento(self):
        self.assertEqual(precio_final(100, 10), 107.1)

    def test_sin_iva(self):
        self.assertEqual(precio_final(200, 50, iva_pct=0), 100.0)
