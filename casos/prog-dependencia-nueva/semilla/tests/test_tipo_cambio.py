import unittest
from pathlib import Path

from app.tipo_cambio import leer_tasa

URL = Path("datos/tasas.json").resolve().as_uri()


class TestTasa(unittest.TestCase):
    def test_cop(self):
        self.assertEqual(leer_tasa(URL, "COP"), 4100.5)

    def test_eur(self):
        self.assertEqual(leer_tasa(URL, "EUR"), 0.91)
