import unittest

from app.inventario import stock_disponible


class TestStock(unittest.TestCase):
    def test_normal(self):
        self.assertEqual(stock_disponible(10, 3), 7)

    def test_sobre_reservado(self):
        self.assertEqual(stock_disponible(2, 5), 0)
