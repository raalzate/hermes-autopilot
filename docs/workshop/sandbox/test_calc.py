"""El criterio de salida de la tarea del workshop: el loop termina cuando esto pasa (vía el gate)."""
import unittest

from app.calc import suma


class TestSuma(unittest.TestCase):
    def test_suma(self):
        self.assertEqual(suma(2, 3), 5)


if __name__ == "__main__":
    unittest.main()
