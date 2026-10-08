"""Pruebas offline de CitaCerca (unittest, sin red).

    python pruebas.py
"""

import re
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest import mock

import app as modulo
from datos_demo import sembrar

# Un lunes a las 08:00 fijo: los huecos no dependen del día en que se ejecuten las pruebas.
AHORA = datetime(2026, 10, 5, 8, 0)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        ruta = Path(self.tmp.name)
        self.parche = mock.patch.object(modulo, "ahora", lambda: AHORA)
        self.parche.start()
        with mock.patch("datos_demo.datetime") as dt:
            dt.now.return_value = AHORA
            sembrar(ruta / "c.db", borrar=True)
        self.app = modulo.crear_app({"BASE_DATOS": str(ruta / "c.db"), "SUBIDAS": str(ruta / "sub"),
                                     "SECRET_KEY": "x", "TESTING": True})
        self.cli = self.app.test_client()
        self.conexiones = []

    def tearDown(self):
        for db in self.conexiones:
            db.close()
        self.parche.stop()
        self.tmp.cleanup()

    def csrf(self):
        with self.cli.session_transaction() as s:
            s.setdefault("csrf", "tok")
            return s["csrf"]

    def post(self, url, **datos):
        datos["_csrf"] = self.csrf()
        return self.cli.post(url, data=datos, follow_redirects=True)

    def entrar(self, email):
        r = self.post("/entrar", email=email, clave="demo1234")
        self.assertEqual(r.status_code, 200)
        return r

    def db(self):
        db = modulo.conectar(self.app.config["BASE_DATOS"])
        self.conexiones.append(db)
        return db


class Utilidades(unittest.TestCase):
    def test_distancia(self):
        self.assertEqual(modulo.distancia_cp("28010", "28010")[0], 0)
        misma = modulo.distancia_cp("28010", "28901")[0]
        otra = modulo.distancia_cp("28010", "08012")[0]
        self.assertLess(misma, otra)
        self.assertTrue(400 < otra < 600)  # Madrid-Barcelona
        self.assertEqual(modulo.distancia_cp("abc", "28010")[0], 10**6)

    def test_necesidades(self):
        self.assertEqual(modulo.tipos_por_necesidad("Tengo una UÑA encarnada"), ["podologia"])
        self.assertIn("fisioterapia", modulo.tipos_por_necesidad("me duele la espalda"))
        self.assertEqual(modulo.tipos_por_necesidad("dolor de muelas"), ["odontologia"])
        self.assertEqual(modulo.tipos_por_necesidad("hola"), [])


class Huecos(Base):
    def clinica(self, nombre):
        db = self.db()
        return db, db.execute("SELECT * FROM clinicas WHERE nombre = ?", (nombre,)).fetchone()

    def test_citas_y_bloqueos_ocupan(self):
        db, c = self.clinica("Podología Pasos")
        semana = dict(modulo.huecos_libres(db, c, 30))
        martes = date(2026, 10, 6)
        # Lucía pidió quiropodia (30 min) a las 09:00 y Pablo tiene estudio de pisada (60 min) a las 10:00.
        for ocupada in ("09:00", "09:15", "10:00", "10:45"):
            self.assertNotIn(ocupada, semana[martes])
        self.assertIn("09:30", semana[martes])   # 09:30-10:00 cabe justo
        self.assertIn("11:00", semana[martes])
        self.assertNotIn("13:45", semana[martes])  # no cabe antes de cerrar a las 14:00
        lunes_siguiente = date(2026, 10, 13)       # bloqueo de formación
        self.assertEqual(semana.get(lunes_siguiente, []), [])
        domingo = date(2026, 10, 11)
        self.assertEqual(semana[domingo], [])

    def test_hoy_respeta_margen(self):
        db, c = self.clinica("FisioActiva Getafe")
        hoy = dict(modulo.huecos_libres(db, c, 45))[AHORA.date()]
        self.assertTrue(hoy)
        self.assertGreaterEqual(hoy[0], "09:00")  # abre a las 8, pero son las 8 y hay 60 min de margen


class Busqueda(Base):
    def test_por_necesidad_y_cercania(self):
        r = self.cli.get("/buscar?necesidad=me+duele+la+espalda&cp=28010")
        html = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("FisioActiva Getafe", html)
        self.assertIn("Manos en Calma", html)
        self.assertNotIn("Sonrisa Norte", html)

    def test_por_tipo_y_filtro(self):
        html = self.cli.get("/buscar?tipo=odontologia&cp=28010").get_data(as_text=True)
        self.assertIn("Sonrisa Norte", html)
        self.assertNotIn("Podología Pasos", html)
        html = self.cli.get("/buscar?req=domicilio").get_data(as_text=True)
        self.assertIn("Manos en Calma", html)
        self.assertNotIn("FisioActiva", html)

    def test_orden_por_distancia(self):
        db = self.db()
        res, _ = modulo.buscar_clinicas(db, cp="28010")
        self.assertEqual(res[0]["clinica"]["codigo_postal"], "28010")
        self.assertEqual(res[-1]["clinica"]["codigo_postal"], "28901")


class FlujoPaciente(Base):
    def test_registro_reserva_y_cancelacion(self):
        r = self.post("/registro", nombre="Jon Prueba", telefono="600111222", codigo_postal="28010",
                      email="jon@prueba.es", clave="secreta123", acepto="1")
        self.assertIn("Bienvenido", r.get_data(as_text=True))
        db = self.db()
        c = db.execute("SELECT * FROM clinicas WHERE nombre = 'Podología Pasos'").fetchone()
        s = db.execute("SELECT * FROM servicios WHERE clinica_id = ? AND nombre LIKE 'Quiropodia%'",
                       (c["id"],)).fetchone()
        r = self.cli.get(f"/clinica/{c['id']}/reservar?servicio={s['id']}&fecha=2026-10-07&hora=12:00")
        self.assertIn("Revisa tu cita", r.get_data(as_text=True))
        r = self.post(f"/clinica/{c['id']}/reservar", servicio=s["id"], fecha="2026-10-07", hora="12:00",
                      mensaje="Primera vez")
        self.assertIn("Solicitud enviada", r.get_data(as_text=True))
        cita = db.execute("SELECT * FROM citas WHERE mensaje_paciente = 'Primera vez'").fetchone()
        self.assertEqual(cita["estado"], "pendiente")
        # El mismo hueco ya no se puede volver a pedir.
        r = self.post(f"/clinica/{c['id']}/reservar", servicio=s["id"], fecha="2026-10-07", hora="12:00")
        self.assertIn("ya no está libre", r.get_data(as_text=True))
        r = self.post(f"/mi/cita/{cita['id']}/cancelar", motivo="No puedo")
        self.assertEqual(db.execute("SELECT estado FROM citas WHERE id = ?", (cita["id"],)).fetchone()[0],
                         "cancelada")

    def test_confirmacion_automatica(self):
        self.entrar("paciente@demo.es")
        db = self.db()
        c = db.execute("SELECT * FROM clinicas WHERE nombre = 'Manos en Calma'").fetchone()
        s = db.execute("SELECT * FROM servicios WHERE clinica_id = ? LIMIT 1", (c["id"],)).fetchone()
        r = self.post(f"/clinica/{c['id']}/reservar", servicio=s["id"], fecha="2026-10-08", hora="11:00")
        self.assertIn("Cita confirmada", r.get_data(as_text=True))

    def test_reserva_requiere_cuenta(self):
        r = self.cli.get("/clinica/1/reservar?servicio=1&fecha=2026-10-07&hora=12:00")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/entrar", r.headers["Location"])

    def test_valorar_cita_pasada(self):
        self.entrar("paciente@demo.es")
        db = self.db()
        cita = db.execute("SELECT ci.id FROM citas ci JOIN clinicas c ON c.id = ci.clinica_id "
                          "WHERE c.nombre = 'Manos en Calma' AND ci.paciente_id = "
                          "(SELECT id FROM usuarios WHERE email = 'paciente@demo.es')").fetchone()
        self.post(f"/mi/cita/{cita['id']}/valorar", puntuacion="4", comentario="Bien")
        self.assertEqual(db.execute("SELECT puntuacion FROM valoraciones WHERE cita_id = ?",
                                    (cita["id"],)).fetchone()[0], 4)

    def test_mensaje(self):
        self.entrar("paciente@demo.es")
        r = self.post("/clinica/3/mensaje", tipo="llamada", franja="Tardes", texto="¿Me llamáis?")
        self.assertIn("Mensaje enviado", r.get_data(as_text=True))

    def test_csrf(self):
        self.entrar("paciente@demo.es")
        r = self.cli.post("/clinica/3/mensaje", data={"texto": "x"})
        self.assertEqual(r.status_code, 400)


class FlujoClinica(Base):
    def test_registro_clinica_y_ficha(self):
        r = self.post("/registro/clinica", nombre="Osteo Norte", tipo="osteopatia", codigo_postal="48001",
                      telefono="944000000", email="osteo@prueba.es", clave="secreta123")
        self.assertIn("Clínica creada", r.get_data(as_text=True))
        self.post("/panel/servicios", nombre="Sesión de osteopatía", duracion="50", precio="55")
        self.post("/panel/perfil", nombre="Osteo Norte", tipo="osteopatia", codigo_postal="48001",
                  color="#d1495b", descripcion="Tratamos dolor cervical", activa="1", duracion_hueco="30")
        html = self.cli.get("/buscar?tipo=osteopatia").get_data(as_text=True)
        self.assertIn("Osteo Norte", html)
        self.assertIn("Sesión de osteopatía", html)

    def test_confirmar_solicitud(self):
        self.entrar("podologia@demo.es")
        html = self.cli.get("/panel").get_data(as_text=True)
        self.assertIn("Solicitudes pendientes", html)
        db = self.db()
        cita = db.execute("SELECT * FROM citas WHERE estado = 'pendiente' AND clinica_id = 1 LIMIT 1").fetchone()
        self.post(f"/panel/cita/{cita['id']}/confirmar", respuesta="Te esperamos")
        fila = db.execute("SELECT estado, visto_paciente FROM citas WHERE id = ?", (cita["id"],)).fetchone()
        self.assertEqual(tuple(fila), ("confirmada", 0))

    def test_no_toca_citas_ajenas(self):
        self.entrar("podologia@demo.es")
        db = self.db()
        ajena = db.execute("SELECT id FROM citas WHERE clinica_id = 3 AND estado = 'pendiente'").fetchone()
        r = self.post(f"/panel/cita/{ajena['id']}/confirmar")
        self.assertEqual(r.status_code, 404)

    def test_horario_y_bloqueo(self):
        self.entrar("fisio@demo.es")
        self.post("/panel/horario", d0_ini1="10:00", d0_fin1="12:00")
        db = self.db()
        c = db.execute("SELECT * FROM clinicas WHERE id = 4").fetchone()
        lunes = date(2026, 10, 12)
        semana = dict(modulo.huecos_libres(db, c, 60, desde=lunes))
        self.assertEqual(semana[lunes], ["10:00", "10:15", "10:30", "10:45", "11:00"])
        self.assertEqual(semana[date(2026, 10, 14)], [])
        self.post("/panel/bloqueos", desde="2026-10-12", inicio="10:00", fin="11:00")
        semana = dict(modulo.huecos_libres(db, c, 60, desde=lunes))
        self.assertEqual(semana[lunes], ["11:00"])

    def test_paciente_no_entra_al_panel(self):
        self.entrar("paciente@demo.es")
        r = self.cli.get("/panel")
        self.assertEqual(r.status_code, 302)


class Paginas(Base):
    def test_todas_cargan(self):
        for url in ("/", "/buscar", "/clinica/1", "/clinica/2?servicio=6&semana=1", "/registro",
                    "/registro/clinica", "/entrar"):
            self.assertEqual(self.cli.get(url).status_code, 200, url)
        self.entrar("paciente@demo.es")
        for url in ("/mi", "/mi/perfil"):
            self.assertEqual(self.cli.get(url).status_code, 200, url)
        self.post("/salir")
        self.entrar("dental@demo.es")
        for url in ("/panel", "/panel/perfil", "/panel/servicios", "/panel/horario"):
            self.assertEqual(self.cli.get(url).status_code, 200, url)

    def test_redireccion_abierta(self):
        r = self.post("/entrar", email="paciente@demo.es", clave="demo1234", siguiente="//malo.com")
        self.assertNotIn("malo.com", r.request.path)


if __name__ == "__main__":
    unittest.main(verbosity=1)
