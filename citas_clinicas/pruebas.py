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
        # Pablo tiene estudio de pisada (60 min) a las 10:00. La solicitud de Lucía es por franja,
        # sin hora todavía: no bloquea ninguna hora concreta.
        for ocupada in ("10:00", "10:15", "10:45"):
            self.assertNotIn(ocupada, semana[martes])
        self.assertIn("09:00", semana[martes])
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
        # Podología publica huecos por franja: el miércoles por la mañana solo queda uno.
        db.execute("UPDATE cupos SET plazas = 1 WHERE clinica_id = ? AND fecha = '2026-10-07' AND franja = 'manana'",
                   (c["id"],))
        db.commit()
        r = self.cli.get(f"/clinica/{c['id']}/reservar?servicio={s['id']}&fecha=2026-10-07&franja=manana")
        html = r.get_data(as_text=True)
        self.assertIn("Revisa tu cita", html)
        self.assertIn("por la mañana", html)
        self.assertIn("Hacia las 11:00", html)
        r = self.post(f"/clinica/{c['id']}/reservar", servicio=s["id"], fecha="2026-10-07", franja="manana",
                      preferencia="11:00", mensaje="Primera vez")
        self.assertIn("te confirmará la hora exacta", r.get_data(as_text=True))
        cita = db.execute("SELECT * FROM citas WHERE mensaje_paciente = 'Primera vez'").fetchone()
        self.assertEqual((cita["estado"], cita["hora"], cita["franja"], cita["preferencia"]),
                         ("pendiente", "", "manana", "11:00"))
        # Agotado: el cupo ya no se puede volver a pedir.
        r = self.post(f"/clinica/{c['id']}/reservar", servicio=s["id"], fecha="2026-10-07", franja="manana")
        self.assertIn("ya no está libre", r.get_data(as_text=True))
        r = self.post(f"/mi/cita/{cita['id']}/cancelar", motivo="No puedo")
        self.assertEqual(db.execute("SELECT estado FROM citas WHERE id = ?", (cita["id"],)).fetchone()[0],
                         "cancelada")
        # Cancelar libera el hueco.
        self.assertTrue(modulo.cupo_disponible(db, c, date(2026, 10, 7), "manana"))

    def test_confirmacion_automatica(self):
        self.entrar("paciente@demo.es")
        db = self.db()
        c = db.execute("SELECT * FROM clinicas WHERE nombre = 'Manos en Calma'").fetchone()
        s = db.execute("SELECT * FROM servicios WHERE clinica_id = ? LIMIT 1", (c["id"],)).fetchone()
        r = self.post(f"/clinica/{c['id']}/reservar", servicio=s["id"], fecha="2026-10-08", hora="11:00")
        self.assertIn("Cita confirmada", r.get_data(as_text=True))
        # Agenda exacta: la misma hora no se puede reservar dos veces.
        r = self.post(f"/clinica/{c['id']}/reservar", servicio=s["id"], fecha="2026-10-08", hora="11:00")
        self.assertIn("ya no está libre", r.get_data(as_text=True))

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
        self.assertIn("Sin huecos online", html)  # aún no ha publicado huecos
        self.assertIn("Publica tus huecos", self.cli.get("/panel").get_data(as_text=True))
        # Las clínicas nuevas publican por franjas: martes 3 por la mañana.
        self.post("/panel/huecos", **{"2026-10-06_manana": "3", "2026-10-06_tarde": "0"})
        html = self.cli.get("/buscar?tipo=osteopatia").get_data(as_text=True)
        self.assertIn("Mar 6 · mañana (3)", html)

    def test_confirmar_solicitud(self):
        self.entrar("podologia@demo.es")
        html = self.cli.get("/panel").get_data(as_text=True)
        self.assertIn("Solicitudes pendientes", html)
        db = self.db()
        cita = db.execute("SELECT * FROM citas WHERE estado = 'pendiente' AND clinica_id = 1 LIMIT 1").fetchone()
        self.assertIn('type="time"', html)  # solicitud por franja: hay que poner la hora
        # Sin hora no se puede confirmar una solicitud por franja.
        r = self.post(f"/panel/cita/{cita['id']}/confirmar", respuesta="Te esperamos")
        self.assertIn("Indica la hora", r.get_data(as_text=True))
        self.post(f"/panel/cita/{cita['id']}/confirmar", respuesta="Te esperamos", hora="9:30")
        fila = db.execute("SELECT estado, visto_paciente, hora FROM citas WHERE id = ?", (cita["id"],)).fetchone()
        self.assertEqual(tuple(fila), ("confirmada", 0, "09:30"))

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


class ModoDemo(unittest.TestCase):
    def test_siembra_si_vacia_y_muestra_cuentas(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = modulo.crear_app({"BASE_DATOS": f"{tmp}/d.db", "SUBIDAS": f"{tmp}/s", "SECRET_KEY": "x",
                                    "DEMO": True})
            html = app.test_client().get("/entrar").get_data(as_text=True)
            self.assertIn("Cuentas de prueba", html)
            self.assertIn("fisio@demo.es", html)
            # Un segundo arranque no duplica los datos.
            modulo.crear_app({"BASE_DATOS": f"{tmp}/d.db", "SUBIDAS": f"{tmp}/s", "SECRET_KEY": "x", "DEMO": True})
            db = modulo.conectar(f"{tmp}/d.db")
            self.assertEqual(db.execute("SELECT COUNT(*) FROM clinicas").fetchone()[0], 4)
            db.close()


class Franjas(Base):
    def podologia(self):
        db = self.db()
        return db, db.execute("SELECT * FROM clinicas WHERE nombre = 'Podología Pasos'").fetchone()

    def test_huecos_menos_solicitudes(self):
        db, c = self.podologia()
        semana = dict(modulo.cupos_libres(db, c))
        martes = semana[date(2026, 10, 6)]
        # Publicó 2 por la mañana; Lucía pidió 1 (pendiente) y Pablo tiene 1 confirmada a las 10:00.
        self.assertEqual((martes["manana"]["plazas"], martes["manana"]["ocupadas"], martes["manana"]["libres"]),
                         (2, 2, 0))
        self.assertEqual(martes["tarde"]["libres"], 1)
        self.assertEqual(martes["manana"]["horario"], "09:00–14:00")
        self.assertFalse(semana[date(2026, 10, 10)]["manana"]["abierto"])  # sábado cerrado

    def test_hoy_franja_casi_cerrada(self):
        db, c = self.podologia()
        with mock.patch.object(modulo, "ahora", lambda: datetime(2026, 10, 5, 13, 30)):
            hoy = dict(modulo.cupos_libres(db, c))[date(2026, 10, 5)]
        self.assertFalse(hoy["manana"]["abierto"])  # cierra a las 14:00: ya no se ofrece
        self.assertTrue(hoy["tarde"]["abierto"])

    def test_dia_bloqueado(self):
        db, c = self.podologia()
        semana = dict(modulo.cupos_libres(db, c, dias=14))
        self.assertEqual(semana[date(2026, 10, 13)]["manana"]["libres"], 0)  # formación del equipo

    def test_filtro_franja_en_busqueda(self):
        db, c = self.podologia()
        tardes = modulo.disponibilidad(db, c, franja="tarde")
        self.assertTrue(tardes)
        self.assertTrue(all(o["franja"] == "tarde" and o["hora"] is None for o in tardes))
        html = self.cli.get("/buscar?tipo=podologia&franja=manana").get_data(as_text=True)
        self.assertIn("mañana (", html)
        self.assertNotIn("tarde (", html)

    def test_ficha_muestra_franjas(self):
        html = self.cli.get("/clinica/1?servicio=1").get_data(as_text=True)
        self.assertIn("Elige día y franja", html)
        self.assertIn("Completo", html)  # martes por la mañana
        self.assertIn("franja=tarde", html)

    def test_publicar_y_copiar(self):
        self.entrar("podologia@demo.es")
        self.post("/panel/huecos", **{"2026-10-09_manana": "5", "2026-10-09_tarde": "abc"})
        db, c = self.podologia()
        plazas = dict(db.execute("SELECT franja, plazas FROM cupos WHERE clinica_id = 1 AND fecha = '2026-10-09'"))
        self.assertEqual(plazas, {"manana": 5, "tarde": 0})  # un valor no numérico no cambia nada
        self.post("/panel/huecos", accion="copiar")
        fila = db.execute("SELECT plazas FROM cupos WHERE clinica_id = 1 AND fecha = '2026-10-16' "
                          "AND franja = 'manana'").fetchone()
        self.assertEqual(fila[0], 5)
        self.assertIn("¿Cuántos huecos libres tienes?", self.cli.get("/panel/huecos").get_data(as_text=True))

    def test_paciente_ve_franja_y_luego_hora(self):
        self.entrar("paciente@demo.es")
        html = self.cli.get("/mi").get_data(as_text=True)
        self.assertIn("tarde (prefiere hacia las 17:00)", html)
        self.assertIn("hora por confirmar", html)


class Captacion(Base):
    OCTUBRE = (date(2026, 10, 1), date(2026, 11, 1))

    def por_clinica(self):
        db = self.db()
        return {c["nombre"]: modulo.resumen_clinica(db, c, *self.OCTUBRE)
                for c in db.execute("SELECT * FROM clinicas")}

    def test_solo_primera_cita_por_paciente_y_clinica(self):
        r = self.por_clinica()
        # Dental: Ana y Lucía son nuevas. Podología: Pablo y Marta ya fueron en septiembre.
        self.assertEqual(r["Clínica Dental Sonrisa Norte"]["nuevos"], 2)
        self.assertEqual(r["Podología Pasos"]["nuevos"], 0)
        self.assertEqual(r["Manos en Calma"]["nuevos"], 2)
        self.assertEqual(r["FisioActiva Getafe"]["nuevos"], 1)
        self.assertEqual(sum(x["importe"] for x in r.values()), 5 * modulo.TARIFA_POR_DEFECTO)

    def test_ya_era_paciente_no_se_factura(self):
        self.entrar("dental@demo.es")
        db = self.db()
        cita = db.execute("SELECT id FROM citas WHERE clinica_id = 3 AND estado = 'pendiente'").fetchone()
        self.post(f"/panel/cita/{cita['id']}/confirmar", ya_paciente="1", hora="09:00")
        r = self.por_clinica()["Clínica Dental Sonrisa Norte"]
        self.assertEqual((r["nuevos"], r["facturables"]), (3, 2))

    def test_cancelada_no_cuenta_y_libera_la_siguiente(self):
        db = self.db()
        db.execute("UPDATE citas SET estado = 'cancelada' WHERE clinica_id = 3 AND estado = 'confirmada' "
                   "AND fecha = '2026-10-07'")
        db.commit()
        self.assertEqual(self.por_clinica()["Clínica Dental Sonrisa Norte"]["nuevos"], 1)

    def test_tarifa_propia_y_tope(self):
        self.entrar("admin@demo.es")
        self.post("/admin/clinica/3", tarifa="10", tope_mensual="15", activa="1")
        r = self.por_clinica()["Clínica Dental Sonrisa Norte"]
        self.assertEqual((r["tarifa"], r["importe"]), (10, 15))


class Administracion(Base):
    def test_solo_admin(self):
        self.entrar("paciente@demo.es")
        self.assertEqual(self.cli.get("/admin").status_code, 302)
        self.post("/salir")
        self.entrar("dental@demo.es")
        self.assertEqual(self.cli.get("/admin/captaciones.csv").status_code, 302)

    def test_panel_y_csv(self):
        r = self.entrar("admin@demo.es")
        self.assertIn("Administración · octubre 2026", r.get_data(as_text=True))  # entra directo al panel
        html = self.cli.get("/admin?mes=2026-10").get_data(as_text=True)
        self.assertIn("Sonrisa Norte", html)
        self.assertIn("40,00 €", html)
        self.assertEqual(self.cli.get("/admin/clinica/3?mes=2026-10").status_code, 200)
        csv = self.cli.get("/admin/captaciones.csv?mes=2026-10").get_data(as_text=True)
        self.assertIn("clinica;fecha;hora;paciente", csv)
        self.assertIn("Lucía Gómez", csv)
        self.assertEqual(csv.count("\n"), 6)  # cabecera + 5 captaciones

    def test_admin_por_entorno(self):
        ruta = self.app.config["BASE_DATOS"]
        modulo.asegurar_admin(ruta, "yo@ejemplo.es", "clave-larga")
        self.assertIn("Administración", self.entrar_con("yo@ejemplo.es", "clave-larga"))

    def entrar_con(self, email, clave):
        return self.post("/entrar", email=email, clave=clave).get_data(as_text=True)


class Mapa(Base):
    def test_distancia_real_con_ubicacion(self):
        db = self.db()
        res, _ = modulo.buscar_clinicas(db, cp="28010", lat=40.3100, lon=-3.7300)  # en Getafe
        self.assertEqual(res[0]["clinica"]["nombre"], "FisioActiva Getafe")
        self.assertIn("m", res[0]["distancia_texto"])
        self.assertIn("km", res[-1]["distancia_texto"])

    def test_clinica_sin_chincheta_va_detras(self):
        db = self.db()
        db.execute("UPDATE clinicas SET lat = NULL, lon = NULL WHERE nombre = 'Podología Pasos'")
        db.commit()
        res, _ = modulo.buscar_clinicas(db, cp="28010", lat=40.4316, lon=-3.7022)
        self.assertEqual(res[-1]["clinica"]["nombre"], "Podología Pasos")

    def test_busqueda_pinta_mapa(self):
        html = self.cli.get("/buscar?lat=40.42&lon=-3.70").get_data(as_text=True)
        self.assertIn("CitaMapa.resultados", html)
        self.assertIn("Usando tu ubicación", html)
        self.assertIn('"lat": 40.4639', html)

    def test_guardar_ubicacion(self):
        self.entrar("fisio@demo.es")
        self.post("/panel/perfil", nombre="FisioActiva Getafe", tipo="fisioterapia", codigo_postal="28901",
                  activa="1", duracion_hueco="15", lat="40.3", lon="-3.73")
        fila = self.db().execute("SELECT lat, lon FROM clinicas WHERE id = 4").fetchone()
        self.assertEqual(tuple(fila), (40.3, -3.73))
        # Coordenadas absurdas no se guardan: se conservan las anteriores.
        self.post("/panel/perfil", nombre="FisioActiva Getafe", tipo="fisioterapia", codigo_postal="28901",
                  activa="1", duracion_hueco="15", lat="999", lon="-3.73")
        fila = self.db().execute("SELECT lat FROM clinicas WHERE id = 4").fetchone()
        self.assertEqual(fila[0], 40.3)


class Eventos(Base):
    def contar(self, tipo):
        return self.db().execute("SELECT COUNT(*) FROM eventos WHERE clinica_id = 1 AND tipo = ?",
                                 (tipo,)).fetchone()[0]

    def test_vista_y_clic(self):
        vistas, llamadas = self.contar("vista"), self.contar("llamar")
        self.cli.get("/clinica/1")
        self.assertEqual(self.contar("vista"), vistas + 1)
        self.cli.post("/clinica/1/evento", data={"tipo": "llamar", "_csrf": self.csrf()})
        self.assertEqual(self.contar("llamar"), llamadas + 1)
        self.cli.post("/clinica/1/evento", data={"tipo": "inventado", "_csrf": self.csrf()})
        self.assertEqual(self.db().execute("SELECT COUNT(*) FROM eventos WHERE tipo = 'inventado'").fetchone()[0], 0)

    def test_la_propia_clinica_no_cuenta(self):
        self.entrar("podologia@demo.es")
        vistas = self.contar("vista")
        self.cli.get("/clinica/1")
        self.assertEqual(self.contar("vista"), vistas)


class Migracion(unittest.TestCase):
    def test_base_antigua(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = modulo.conectar(f"{tmp}/v.db")
            db.executescript("""
                CREATE TABLE usuarios (id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, clave TEXT NOT NULL,
                    rol TEXT NOT NULL CHECK (rol IN ('paciente', 'clinica')), nombre TEXT NOT NULL,
                    telefono TEXT DEFAULT '', codigo_postal TEXT DEFAULT '', creado TEXT NOT NULL);
                INSERT INTO usuarios VALUES (1, 'a@b.es', 'x', 'clinica', 'A', '', '28010', '2026');
                CREATE TABLE clinicas (id INTEGER PRIMARY KEY, usuario_id INTEGER NOT NULL UNIQUE REFERENCES usuarios(id),
                    nombre TEXT NOT NULL, tipo TEXT NOT NULL, codigo_postal TEXT NOT NULL);
                INSERT INTO clinicas VALUES (1, 1, 'Vieja', 'podologia', '28010');
            """)
            db.close()
            db = modulo.iniciar_bd(f"{tmp}/v.db")
            db.execute("INSERT INTO usuarios (email, clave, rol, nombre, creado) VALUES ('ad@b.es', 'x', 'admin', 'Ad', '')")
            fila = db.execute("SELECT nombre, lat, tarifa, modo FROM clinicas").fetchone()
            self.assertEqual(tuple(fila), ("Vieja", None, None, "agenda"))  # las existentes siguen igual
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            db.close()


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
        self.post("/salir")
        self.entrar("admin@demo.es")
        for url in ("/admin", "/admin?mes=2026-09", "/admin?mes=basura", "/admin/clinica/1", "/buscar"):
            self.assertEqual(self.cli.get(url).status_code, 200, url)

    def test_redireccion_abierta(self):
        r = self.post("/entrar", email="paciente@demo.es", clave="demo1234", siguiente="//malo.com")
        self.assertNotIn("malo.com", r.request.path)


if __name__ == "__main__":
    unittest.main(verbosity=1)
