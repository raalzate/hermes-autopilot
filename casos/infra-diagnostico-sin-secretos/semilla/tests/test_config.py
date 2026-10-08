import os
import unittest
from unittest import mock

from app.config import conexion


class TestConexion(unittest.TestCase):
    def test_lee_las_variables_del_env_example(self):
        with mock.patch.dict(os.environ, {"DB_HOST": "db.x", "DB_PORT": "6000", "DB_USER": "u"}, clear=True):
            self.assertEqual(conexion(), {"host": "db.x", "port": 6000, "user": "u"})
