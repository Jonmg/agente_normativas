#!/usr/bin/env python3
"""
pruebas.py — batería de pruebas para validar app.py y preparar_reglamento.py.

Todas offline: no llaman a la API de Anthropic ni a EUR-Lex. Corren contra el
reglamento real ya cargado en ./reglamento/ (el "ground truth" del proyecto,
no una copia sintética). Las rutas /preguntar y /analizar solo se prueban con
entrada vacía, que redirige sin invocar el modelo.

    python -m unittest pruebas -v
"""
import os
import unittest
from pathlib import Path

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-pruebas-sin-red")

import app
import preparar_reglamento as prep


class TestCatalogoYFuentes(unittest.TestCase):
    def test_reglamento_cargado(self):
        self.assertIn("artículos", app.estado_reglamento())

    def test_catalogo_incluye_articulo_y_anexo_conocidos(self):
        cat = app.catalogo()
        self.assertIn("art-001", cat)
        self.assertIn("anexo-I", cat)

    def test_elegir_fuentes_referencia_explicita_articulo(self):
        claves = app.elegir_fuentes("¿Qué exige el artículo 12 sobre etiquetado?")
        self.assertIn("art-012", claves)

    def test_elegir_fuentes_referencia_explicita_anexo(self):
        claves = app.elegir_fuentes("Necesito el anexo VII de documentación técnica")
        self.assertIn("anexo-VII", claves)

    def test_elegir_fuentes_no_supera_doce(self):
        claves = app.elegir_fuentes(
            "reciclado envases sostenibilidad requisitos residuos etiquetado reutilización")
        self.assertLessEqual(len(claves), 12)

    def test_montar_contexto_incluye_indice_y_fuente_pedida(self):
        ctx = app.montar_contexto(["art-001"])
        self.assertIn("<indice>", ctx)
        self.assertIn('id="art-001"', ctx)


class TestNormativaLista(unittest.TestCase):
    def test_articulos_en_orden_numerico(self):
        arts, _ = app.normativa_lista()
        numeros = [int(a["clave"].split("-")[1]) for a in arts]
        self.assertEqual(numeros, sorted(numeros))

    def test_anexos_en_orden_romano(self):
        _, anexos = app.normativa_lista()
        claves = [a["clave"] for a in anexos]
        posiciones = [app.ROMANOS.index(c.split("-", 1)[1]) for c in claves]
        self.assertEqual(posiciones, sorted(posiciones))

    def test_cuenta_coincide_con_ficheros_en_disco(self):
        arts, anexos = app.normativa_lista()
        self.assertEqual(len(arts), len(list((app.REG / "articulos").glob("*.md"))))
        self.assertEqual(len(anexos), len(list((app.REG / "anexos").glob("*.md"))))


class TestFechaActualizacion(unittest.TestCase):
    def test_formato_fecha(self):
        self.assertRegex(app.fecha_actualizacion(), r"^\d{2}/\d{2}/\d{4}$")


class TestMarkdown(unittest.TestCase):
    def test_cabecera(self):
        self.assertIn("<h1>Título</h1>", app.markdown_a_html("# Título"))

    def test_negrita_y_cursiva(self):
        out = app.markdown_a_html("Texto **fuerte** y *cursiva*.")
        self.assertIn("<strong>fuerte</strong>", out)
        self.assertIn("<em>cursiva</em>", out)

    def test_codigo_en_linea(self):
        self.assertIn("<code>app.py</code>", app.markdown_a_html("Mira `app.py`"))

    def test_cita(self):
        self.assertIn("<blockquote>", app.markdown_a_html("> No vinculante."))

    def test_lista(self):
        out = app.markdown_a_html("- uno\n- dos")
        self.assertEqual(out.count("<li>"), 2)

    def test_cabecera_seguida_de_lista_sin_linea_en_blanco(self):
        # el caso real de 00-INDICE.md: "### Tema" pegado a la lista de artículos
        out = app.markdown_a_html("### Tema\n- Art. 1 — Objeto\n- Art. 2 — Ámbito")
        self.assertIn("<h3>Tema</h3>", out)
        self.assertEqual(out.count("<li>"), 2)

    def test_parrafos_separados_por_linea_en_blanco(self):
        out = app.markdown_a_html("Primero.\n\nSegundo.")
        self.assertEqual(out.count("<p>"), 2)

    def test_escapa_html_para_evitar_xss(self):
        out = app.markdown_a_html("<script>alert(1)</script>")
        self.assertNotIn("<script>", out)
        self.assertIn("&lt;script&gt;", out)

    def test_marca_como_seguro_para_jinja(self):
        from markupsafe import Markup
        self.assertIsInstance(app.markdown_a_html("texto"), Markup)


class TestRutasWeb(unittest.TestCase):
    def setUp(self):
        app.app.testing = True
        self.c = app.app.test_client()

    def test_home_200(self):
        self.assertEqual(self.c.get("/").status_code, 200)

    def test_normativa_200(self):
        self.assertEqual(self.c.get("/normativa").status_code, 200)

    def test_normativa_articulo_existente(self):
        self.assertEqual(self.c.get("/normativa/art-001").status_code, 200)

    def test_normativa_anexo_existente(self):
        self.assertEqual(self.c.get("/normativa/anexo-I").status_code, 200)

    def test_normativa_considerandos(self):
        self.assertEqual(self.c.get("/normativa/considerandos").status_code, 200)

    def test_normativa_clave_inexistente_redirige(self):
        self.assertEqual(self.c.get("/normativa/no-existe").status_code, 302)

    def test_normativa_no_deja_pasar_html_crudo(self):
        r = self.c.get("/normativa/art-001")
        self.assertNotIn(b"<script>", r.data)

    def test_preguntar_vacio_redirige_sin_llamar_api(self):
        r = self.c.post("/preguntar", data={"pregunta": ""})
        self.assertEqual(r.status_code, 302)

    def test_analizar_vacio_redirige_sin_llamar_api(self):
        r = self.c.post("/analizar", data={})
        self.assertEqual(r.status_code, 302)


class TestCarpetas(unittest.TestCase):
    """No llaman a la API real: sustituyen app.llamar por una función que
    devuelve texto fijo y registra el prompt recibido, para poder comprobar
    que el hilo previo se pasa como contexto sin gastar tokens."""

    def setUp(self):
        import tempfile
        app.app.testing = True
        self.c = app.app.test_client()
        self.prompts = []
        self._llamar_original = app.llamar
        app.llamar = lambda system, prompt, max_tokens=3000: (
            self.prompts.append(prompt) or f"respuesta simulada #{len(self.prompts)}")
        # aislar del salidas/carpetas/ real: no ensuciar carpetas de verdad
        self._carpetas_original = app.CARPETAS
        self._tmp = tempfile.mkdtemp()
        app.CARPETAS = Path(self._tmp)

    def tearDown(self):
        import shutil
        app.llamar = self._llamar_original
        app.CARPETAS = self._carpetas_original
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _crear_carpeta(self, nombre="Carpeta de prueba"):
        r = self.c.post("/carpetas/nueva", data={"nombre": nombre})
        return r.headers["Location"].rsplit("/", 1)[-1]

    def test_crear_carpeta_redirige_a_su_vista(self):
        slug = self._crear_carpeta()
        r = self.c.get(f"/carpetas/{slug}")
        self.assertEqual(r.status_code, 200)

    def test_crear_carpeta_sin_nombre_no_crea_nada(self):
        antes = len(app.listar_carpetas())
        self.c.post("/carpetas/nueva", data={"nombre": ""})
        self.assertEqual(len(app.listar_carpetas()), antes)

    def test_nombres_repetidos_generan_slugs_distintos(self):
        s1 = self._crear_carpeta("Duda repetida")
        s2 = self._crear_carpeta("Duda repetida")
        self.assertNotEqual(s1, s2)

    def test_segundo_turno_incluye_el_hilo_previo_en_el_prompt(self):
        slug = self._crear_carpeta()
        self.c.post(f"/carpetas/{slug}/preguntar", data={"pregunta": "Primera pregunta"})
        self.c.post(f"/carpetas/{slug}/preguntar", data={"pregunta": "Segunda pregunta"})
        self.assertNotIn("<hilo_previo>", self.prompts[0])
        self.assertIn("<hilo_previo>", self.prompts[1])
        self.assertIn("Primera pregunta", self.prompts[1])

    def test_documento_subido_se_guarda_en_la_carpeta(self):
        import io
        slug = self._crear_carpeta()
        self.c.post(f"/carpetas/{slug}/analizar", data={
            "documento": (io.BytesIO(b"contenido de prueba"), "declaracion.txt"),
            "rol": "Envasador propio", "nota": "",
        })
        guardados = list(app.carpeta_dir(slug).glob("*.txt"))
        self.assertEqual(len(guardados), 1)
        self.assertEqual(guardados[0].read_bytes(), b"contenido de prueba")

    def test_pregunta_vacia_no_llama_al_modelo(self):
        slug = self._crear_carpeta()
        self.c.post(f"/carpetas/{slug}/preguntar", data={"pregunta": ""})
        self.assertEqual(self.prompts, [])

    def test_carpeta_inexistente_redirige_al_listado(self):
        r = self.c.get("/carpetas/no-existe-esta-carpeta")
        self.assertEqual(r.status_code, 302)

    def test_slug_con_caracteres_invalidos_no_se_acepta(self):
        self.assertIsNone(app.carpeta_dir("../../etc"))
        self.assertIsNone(app.carpeta_dir("con espacios"))


class TestTroceadoReglamento(unittest.TestCase):
    """preparar_reglamento.py opera sobre texto ya extraído, sin red."""

    def test_regex_articulo_reconoce_formato_estandar(self):
        self.assertTrue(prep.RE_ART.search("\nArtículo 12\n"))

    def test_regex_articulo_no_confunde_referencia_dentro_de_parrafo(self):
        # una mención a "artículo 12" en medio de una frase no debe leerse
        # como el inicio de un artículo nuevo — es la base de por qué el
        # troceado saca ~71 artículos reales y no cientos de fragmentos falsos
        self.assertFalse(prep.RE_ART.search("de conformidad con el artículo 12, apartado 3"))

    def test_cortar_separa_por_marcador(self):
        texto = "\nArtículo 1\nCuerpo uno.\nArtículo 2\nCuerpo dos.\n"
        trozos = dict(prep.cortar(texto, prep.RE_ART))
        self.assertEqual(set(trozos), {"1", "2"})
        self.assertIn("Cuerpo uno.", trozos["1"])
        self.assertIn("Cuerpo dos.", trozos["2"])

    def test_primer_renglon_ignora_apartados_numerados(self):
        cuerpo = "1. Esto es un apartado, no un título.\nTítulo real\nMás texto."
        self.assertEqual(prep.primer_renglon(cuerpo), "Título real")

    def test_slug_normaliza_acentos_y_espacios(self):
        self.assertEqual(
            prep.slug("Envasador propio, sustancias químicas"),
            "envasador-propio-sustancias-quimicas")

    def test_descargar_desde_fichero_local(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".html", mode="w",
                                          encoding="utf-8", delete=False) as f:
            f.write("<html>contenido de prueba</html>")
            ruta = f.name
        try:
            self.assertIn("contenido de prueba", prep.descargar(ruta))
        finally:
            os.unlink(ruta)

    def test_descargar_sin_bytes_falla_con_mensaje_claro(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            ruta = f.name
        try:
            with self.assertRaises(SystemExit):
                prep.descargar(ruta)
        finally:
            os.unlink(ruta)


if __name__ == "__main__":
    unittest.main()
