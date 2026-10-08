import os
import unittest
from unittest import mock

from app.pagos import encabezados


class TestPagos(unittest.TestCase):
    def test_usa_la_key_del_entorno(self):
        with mock.patch.dict(os.environ, {"PAGOS_API_KEY": "clave-de-prueba"}):
            self.assertEqual(encabezados()["Authorization"], "Bearer clave-de-prueba")
