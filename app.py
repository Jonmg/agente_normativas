#!/usr/bin/env python3
"""
app.py — herramienta local de conformidad de envases (Reglamento UE 2025/40).

Tres cosas:
  1. Preguntar al reglamento.
  2. Subir un documento (informe de proveedor, correo, ficha) y ver qué falta.
  3. Carpetas: agrupar preguntas y documentos de un mismo caso, con memoria
     del hilo entre turnos, como una conversación.

El "ground truth" son los ficheros markdown de ./reglamento/. No hay base de datos:
las consultas y los análisis se guardan como ficheros en ./salidas/.

    export ANTHROPIC_API_KEY=sk-ant-...
    python app.py            ->  http://<ip-de-la-pi>:8000
"""
import os
import re
import json
import html
import datetime
import unicodedata
from pathlib import Path

from flask import Flask, request, render_template_string, redirect, url_for
from markupsafe import Markup
import anthropic

RAIZ = Path(__file__).parent
REG = RAIZ / "reglamento"
SALIDAS = RAIZ / "salidas"
CARPETAS = SALIDAS / "carpetas"
SALIDAS.mkdir(exist_ok=True)
CARPETAS.mkdir(exist_ok=True, parents=True)

MODELO = os.getenv("PPWR_MODELO", "claude-sonnet-4-6")
cliente = anthropic.Anthropic()
app = Flask(__name__)


# --------------------------------------------------------------------------
# Contexto: el índice siempre, los artículos bajo demanda
# --------------------------------------------------------------------------
def indice() -> str:
    f = REG / "00-INDICE.md"
    if not f.exists():
        return ""
    return f.read_text(encoding="utf-8")


def catalogo() -> dict:
    """{'art-012': ruta, 'anexo-VII': ruta, ...}"""
    c = {}
    for f in sorted((REG / "articulos").glob("*.md")):
        c[f.stem] = f
    for f in sorted((REG / "anexos").glob("*.md")):
        c[f.stem] = f
    return c


ROMANOS = "I II III IV V VI VII VIII IX X XI XII XIII XIV XV XVI".split()


def normativa_lista() -> tuple:
    """Artículos y anexos con su título, ordenados, para la pestaña Normativa."""
    cat = catalogo()
    arts, anexos = [], []
    for k, f in cat.items():
        titulo = f.read_text(encoding="utf-8").split("\n", 1)[0].lstrip("# ").strip()
        item = {"clave": k, "titulo": titulo}
        (arts if k.startswith("art-") else anexos).append(item)
    arts.sort(key=lambda x: int(x["clave"].split("-")[1]))
    anexos.sort(key=lambda x: ROMANOS.index(x["clave"].split("-", 1)[1])
                if x["clave"].split("-", 1)[1] in ROMANOS else 999)
    return arts, anexos


def fecha_actualizacion() -> str:
    f = REG / "00-INDICE.md"
    if not f.exists():
        return ""
    return datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime("%d/%m/%Y")


# --------------------------------------------------------------------------
# Visualizador de markdown — solo el subconjunto que generamos nosotros
# mismos en preparar_reglamento.py (cabeceras, negrita, cursiva, código en
# línea, citas, listas). No es CommonMark completo: no hace falta, y así no
# se añade una dependencia nueva para renderizar contenido que ya controlamos.
# --------------------------------------------------------------------------
def _md_en_linea(texto: str) -> str:
    t = html.escape(texto)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", t)
    t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
    return t


def markdown_a_html(md: str) -> Markup:
    """Recorre línea a línea (no por bloques) para que una cabecera o cita
    seguida de una lista sin línea en blanco de por medio, como en
    00-INDICE.md, no se trague todo como un párrafo."""
    salida, parrafo, lista = [], [], []

    def cerrar_parrafo():
        if parrafo:
            salida.append(f"<p>{'<br>'.join(_md_en_linea(l) for l in parrafo)}</p>")
            parrafo.clear()

    def cerrar_lista():
        if lista:
            salida.append("<ul>" + "".join(f"<li>{_md_en_linea(l)}</li>" for l in lista) + "</ul>")
            lista.clear()

    for linea in md.strip().split("\n"):
        l = linea.strip()
        if not l:
            cerrar_parrafo(); cerrar_lista()
            continue
        m = re.match(r"^(#{1,3})\s+(.*)$", l)
        if m:
            cerrar_parrafo(); cerrar_lista()
            nivel = len(m.group(1))
            salida.append(f"<h{nivel}>{_md_en_linea(m.group(2))}</h{nivel}>")
            continue
        if l.startswith("> "):
            cerrar_parrafo(); cerrar_lista()
            salida.append(f"<blockquote>{_md_en_linea(l[2:].strip())}</blockquote>")
            continue
        if l.startswith("- "):
            cerrar_parrafo()
            lista.append(l[2:].strip())
            continue
        cerrar_lista()
        parrafo.append(l)

    cerrar_parrafo(); cerrar_lista()
    return Markup("\n".join(salida))


def elegir_fuentes(texto: str, extra_terminos: str = "") -> list:
    """
    Selecciona qué ficheros cargar. Dos vías, sin vectores:
      a) referencias explícitas: "artículo 12", "art. 5", "anexo VII"
      b) coincidencia de palabras del título del artículo en el texto
    """
    cat = catalogo()
    elegidos = []
    blob = (texto + " " + extra_terminos).lower()

    for m in re.finditer(r"art[íi]culos?\.?\s*(\d{1,3})", blob):
        k = f"art-{int(m.group(1)):03d}"
        if k in cat and k not in elegidos:
            elegidos.append(k)
    for m in re.finditer(r"anexos?\s+([ivx]{1,6})\b", blob):
        k = f"anexo-{m.group(1).upper()}"
        if k in cat and k not in elegidos:
            elegidos.append(k)

    PARO = set("de la el los las del y o en un una para por con que a se su sus al es "
               "sobre este esta como no ni entre desde hasta".split())
    palabras = {w for w in re.findall(r"[a-záéíóúñ]{5,}", blob)} - PARO

    puntuado = []
    for k, f in cat.items():
        if k in elegidos:
            continue
        titulo = f.read_text(encoding="utf-8").split("\n", 1)[0].lower()
        tw = {w for w in re.findall(r"[a-záéíóúñ]{5,}", titulo)} - PARO
        s = len(tw & palabras)
        if s:
            puntuado.append((s, k))
    puntuado.sort(reverse=True)
    elegidos += [k for _, k in puntuado[:8]]

    return elegidos[:12]


def montar_contexto(claves: list) -> str:
    cat = catalogo()
    trozos = ["<indice>\n" + indice() + "\n</indice>"]
    for k in claves:
        if k in cat:
            trozos.append(f'<fuente id="{k}">\n{cat[k].read_text(encoding="utf-8")}\n</fuente>')
    return "\n\n".join(trozos)


def llamar(system: str, prompt: str, max_tokens=3000) -> str:
    r = cliente.messages.create(
        model=MODELO, max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(b.text for b in r.content if b.type == "text")


REGLAS = """Eres el responsable de calidad de una empresa del sector óptico y de producto
sanitario. Verificas que los envases de los productos que la empresa comercializa cumplen
el Reglamento (UE) 2025/40 (PPWR).

Trabajas SOLO con el texto normativo que se te entrega entre etiquetas <fuente>. Reglas:

1. Cita siempre el artículo o anexo concreto: "Art. 12.1", "Anexo VII".
2. Si el texto que te han dado no cubre la pregunta, dilo y señala qué artículo del índice
   habría que cargar. No completes con conocimiento general ni inventes números.
3. Distingue lo exigible el 12/08/2026 de lo que vence más tarde. La fecha importa.
4. El rol legal (envasador, importador, adquirente intracomunitario, distribuidor) cambia
   las obligaciones. Si no consta, pregúntalo antes de concluir.
5. Ninguna afirmación de un proveedor cuenta como evidencia sin documento que la respalde.
   Una exención necesita justificación escrita.
6. Tú propones; la conformidad la declara una persona. No cierres nada por tu cuenta.

Escribe en español, directo y sin relleno."""


# --------------------------------------------------------------------------
# Lectura de lo que sube el usuario
# --------------------------------------------------------------------------
def leer_subida_bytes(datos: bytes, nombre: str) -> str:
    nombre = nombre.lower()
    if nombre.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            import io
            return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(datos)).pages)
        except Exception as e:
            return f"[No se pudo leer el PDF: {e}]"
    if nombre.endswith(".docx"):
        try:
            import io, zipfile
            with zipfile.ZipFile(io.BytesIO(datos)) as z:
                xml = z.read("word/document.xml").decode("utf-8", "ignore")
            return re.sub(r"<[^>]+>", " ", xml.replace("</w:p>", "\n"))
        except Exception as e:
            return f"[No se pudo leer el DOCX: {e}]"
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return datos.decode(enc)
        except UnicodeDecodeError:
            continue
    return datos.decode("utf-8", "replace")


def leer_subida(fs) -> str:
    return leer_subida_bytes(fs.read(), fs.filename)


def prompt_analizar(ctx: str, hilo: str, texto: str, nombre: str, rol: str, nota: str) -> str:
    return f"""{hilo}{ctx}

<documento nombre="{nombre}">
{texto}
</documento>

<contexto_empresa>
Rol legal para esta referencia: {rol}
Nota de quien lo sube: {nota or "ninguna"}
</contexto_empresa>

Analiza el documento contra el reglamento y devuelve, en este orden:

1. QUÉ ES — una línea: qué documento es y de quién.
2. QUÉ APORTA — evidencias que sí cubre, con el artículo que satisface cada una.
3. QUÉ FALTA — tabla: requisito | artículo | por qué falta | qué pedir exactamente.
4. QUÉ NO CUADRA — afirmaciones sin respaldo documental, contradicciones o exenciones
   invocadas sin justificación.
5. SIGUIENTE PASO — borrador de la respuesta al proveedor, listo para copiar, pidiendo
   solo lo del punto 3.
"""


def guardar(tipo: str, payload: dict) -> str:
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    ruta = SALIDAS / f"{ts}-{tipo}.json"
    ruta.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta.name


# --------------------------------------------------------------------------
# Carpetas — un caso o una duda con memoria de hilo entre turnos, como una
# conversación. Nombre libre, sin obligar a colgarlo de un proveedor: hay
# dudas normativas que no tienen proveedor detrás. El documento original que
# se sube se guarda dentro de la carpeta (nunca se versiona: salidas/ está
# en .gitignore), porque sin él no hay con qué respaldar después una
# afirmación de proveedor.
# --------------------------------------------------------------------------
def _slug_carpeta(nombre: str) -> str:
    s = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    s = re.sub(r"[\s_-]+", "-", s)[:50]
    return s or "carpeta"


def crear_carpeta(nombre: str) -> str:
    base = _slug_carpeta(nombre)
    slug, i = base, 2
    while (CARPETAS / slug).exists():
        slug = f"{base}-{i}"
        i += 1
    d = CARPETAS / slug
    d.mkdir(parents=True)
    (d / "_carpeta.json").write_text(
        json.dumps({"nombre": nombre,
                    "creada": datetime.datetime.now().isoformat(timespec="seconds")},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    return slug


def carpeta_dir(slug: str):
    if not slug or not re.match(r"^[a-z0-9-]+$", slug):
        return None
    d = CARPETAS / slug
    return d if (d / "_carpeta.json").exists() else None


def historial_carpeta(d: Path) -> list:
    turnos = []
    for f in sorted(d.glob("*.json")):
        if f.name == "_carpeta.json":
            continue
        try:
            turnos.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    return turnos


def contexto_previo(turnos: list) -> str:
    if not turnos:
        return ""
    piezas = []
    for t in turnos:
        if t.get("tipo") == "analisis":
            piezas.append(
                f'<turno_anterior tipo="documento" nombre="{t.get("documento", "")}">\n'
                f'Rol: {t.get("rol", "")}. Nota: {t.get("nota", "")}\n\n'
                f'{t.get("respuesta", "")}\n</turno_anterior>')
        else:
            piezas.append(
                f'<turno_anterior tipo="pregunta">\n{t.get("pregunta", "")}\n\n'
                f'{t.get("respuesta", "")}\n</turno_anterior>')
    return "<hilo_previo>\n" + "\n\n".join(piezas) + "\n</hilo_previo>\n\n"


def guardar_turno(d: Path, tipo: str, payload: dict) -> str:
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    payload = {"tipo": tipo, "fecha": datetime.datetime.now().isoformat(timespec="seconds"), **payload}
    (d / f"{ts}-{tipo}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return ts


def listar_carpetas() -> list:
    out = []
    for d in sorted(CARPETAS.iterdir()) if CARPETAS.exists() else []:
        meta_f = d / "_carpeta.json"
        if not d.is_dir() or not meta_f.exists():
            continue
        try:
            meta = json.loads(meta_f.read_text(encoding="utf-8"))
        except Exception:
            continue
        turnos = historial_carpeta(d)
        ultima = max([t.get("fecha", "") for t in turnos], default=meta.get("creada", ""))
        out.append({"slug": d.name, "nombre": meta.get("nombre", d.name),
                    "turnos": len(turnos), "ultima": ultima[:16].replace("T", " ")})
    out.sort(key=lambda x: x["ultima"], reverse=True)
    return out


# --------------------------------------------------------------------------
# Rutas
# --------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def home():
    return render_template_string(PAGINA, vista="consulta", res=None, activa="consulta",
                                  estado=estado_reglamento(), actualizado=fecha_actualizacion(),
                                  historial=historial())


@app.route("/preguntar", methods=["POST"])
def preguntar():
    pregunta = request.form.get("pregunta", "").strip()
    if not pregunta:
        return redirect(url_for("home"))
    claves = elegir_fuentes(pregunta)
    ctx = montar_contexto(claves)
    resp = llamar(REGLAS, f"{ctx}\n\n<pregunta>\n{pregunta}\n</pregunta>")
    guardar("consulta", {"pregunta": pregunta, "fuentes": claves, "respuesta": resp})
    return render_template_string(PAGINA, vista="consulta", activa="consulta",
                                  res={"titulo": pregunta, "cuerpo": resp, "fuentes": claves},
                                  estado=estado_reglamento(), actualizado=fecha_actualizacion(),
                                  historial=historial())


@app.route("/analizar", methods=["POST"])
def analizar():
    fs = request.files.get("documento")
    nota = request.form.get("nota", "").strip()
    rol = request.form.get("rol", "sin especificar")
    texto = leer_subida(fs) if fs and fs.filename else ""
    if not texto and not nota:
        return redirect(url_for("home"))
    texto = texto[:60000]

    claves = elegir_fuentes(texto[:8000], nota)
    ctx = montar_contexto(claves)
    prompt = prompt_analizar(ctx, "", texto, fs.filename if fs else "nota", rol, nota)
    resp = llamar(REGLAS, prompt, max_tokens=4000)
    guardar("analisis", {"documento": fs.filename if fs else "nota", "rol": rol,
                         "nota": nota, "fuentes": claves, "respuesta": resp})
    return render_template_string(PAGINA, vista="analisis", activa="consulta",
                                  res={"titulo": fs.filename if fs else "Nota suelta",
                                       "cuerpo": resp, "fuentes": claves},
                                  estado=estado_reglamento(), actualizado=fecha_actualizacion(),
                                  historial=historial())


@app.route("/normativa", methods=["GET"])
def normativa():
    arts, anexos = normativa_lista()
    return render_template_string(PAGINA_NORMATIVA, activa="normativa",
                                  estado=estado_reglamento(), actualizado=fecha_actualizacion(),
                                  arts=arts, anexos=anexos)


@app.route("/normativa/<clave>", methods=["GET"])
def normativa_articulo(clave):
    if clave == "considerandos":
        f = REG / "considerandos.md"
        if not f.exists():
            return redirect(url_for("normativa"))
        contenido = f.read_text(encoding="utf-8")
    else:
        cat = catalogo()
        if clave not in cat:
            return redirect(url_for("normativa"))
        contenido = cat[clave].read_text(encoding="utf-8")
    titulo = contenido.split("\n", 1)[0].lstrip("# ").strip()
    return render_template_string(PAGINA_ARTICULO, activa="normativa",
                                  estado=estado_reglamento(), actualizado=fecha_actualizacion(),
                                  clave=clave, titulo=titulo, contenido_html=markdown_a_html(contenido))


@app.route("/carpetas", methods=["GET"])
def carpetas():
    return render_template_string(PAGINA_CARPETAS, activa="carpetas",
                                  estado=estado_reglamento(), actualizado=fecha_actualizacion(),
                                  carpetas=listar_carpetas())


@app.route("/carpetas/nueva", methods=["POST"])
def carpeta_nueva():
    nombre = request.form.get("nombre", "").strip()
    if not nombre:
        return redirect(url_for("carpetas"))
    slug = crear_carpeta(nombre)
    return redirect(url_for("carpeta_ver", slug=slug))


@app.route("/carpetas/<slug>", methods=["GET"])
def carpeta_ver(slug):
    d = carpeta_dir(slug)
    if not d:
        return redirect(url_for("carpetas"))
    meta = json.loads((d / "_carpeta.json").read_text(encoding="utf-8"))
    return render_template_string(PAGINA_CARPETA, activa="carpetas",
                                  estado=estado_reglamento(), actualizado=fecha_actualizacion(),
                                  carpeta={"slug": slug, **meta}, turnos=historial_carpeta(d))


@app.route("/carpetas/<slug>/preguntar", methods=["POST"])
def carpeta_preguntar(slug):
    d = carpeta_dir(slug)
    if not d:
        return redirect(url_for("carpetas"))
    pregunta = request.form.get("pregunta", "").strip()
    if not pregunta:
        return redirect(url_for("carpeta_ver", slug=slug))
    hilo = contexto_previo(historial_carpeta(d))
    claves = elegir_fuentes(pregunta)
    ctx = montar_contexto(claves)
    resp = llamar(REGLAS, f"{hilo}{ctx}\n\n<pregunta>\n{pregunta}\n</pregunta>")
    guardar_turno(d, "pregunta", {"pregunta": pregunta, "fuentes": claves, "respuesta": resp})
    return redirect(url_for("carpeta_ver", slug=slug))


@app.route("/carpetas/<slug>/analizar", methods=["POST"])
def carpeta_analizar(slug):
    d = carpeta_dir(slug)
    if not d:
        return redirect(url_for("carpetas"))
    fs = request.files.get("documento")
    nota = request.form.get("nota", "").strip()
    rol = request.form.get("rol", "sin especificar")
    datos = fs.read() if fs and fs.filename else b""
    texto = leer_subida_bytes(datos, fs.filename) if datos else ""
    if not texto and not nota:
        return redirect(url_for("carpeta_ver", slug=slug))
    texto = texto[:60000]

    nombre_doc = None
    if datos:
        ts_fichero = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        nombre_doc = f"{ts_fichero}-{fs.filename}"
        (d / nombre_doc).write_bytes(datos)

    hilo = contexto_previo(historial_carpeta(d))
    claves = elegir_fuentes(texto[:8000], nota)
    ctx = montar_contexto(claves)
    prompt = prompt_analizar(ctx, hilo, texto, fs.filename if fs else "nota", rol, nota)
    resp = llamar(REGLAS, prompt, max_tokens=4000)
    guardar_turno(d, "analisis", {"documento": fs.filename if fs else "nota", "fichero": nombre_doc,
                                  "rol": rol, "nota": nota, "fuentes": claves, "respuesta": resp})
    return redirect(url_for("carpeta_ver", slug=slug))


def estado_reglamento():
    if not (REG / "00-INDICE.md").exists():
        return "SIN CARGAR — ejecuta: python preparar_reglamento.py"
    n = len(list((REG / "articulos").glob("*.md")))
    a = len(list((REG / "anexos").glob("*.md")))
    return f"{n} artículos · {a} anexos"


def historial():
    fs = sorted(SALIDAS.glob("*.json"), reverse=True)[:15]
    out = []
    for f in fs:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append({"fecha": f.stem[:15].replace("-", " "),
                    "tipo": "análisis" if "analisis" in f.stem else "consulta",
                    "que": d.get("pregunta") or d.get("documento", "")})
    return out


# --------------------------------------------------------------------------
BASE_HEAD = """<!doctype html><html lang="es"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Conformidad de envases · 2025/40</title>
<style>
 *{box-sizing:border-box}
 body{font:15px/1.55 system-ui,sans-serif;margin:0;background:#f4f5f6;color:#16181a}
 header{background:#16181a;color:#fff;padding:14px 20px;display:flex;
   justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}
 header .cab{display:flex;align-items:center;gap:18px;flex-wrap:wrap}
 header b{font-size:16px} header span{font-size:12px;color:#9aa4ad;font-family:ui-monospace,monospace}
 nav.nav{display:flex;gap:4px}
 nav.nav a{color:#c7ccd1;text-decoration:none;font-size:13px;padding:5px 10px;border-radius:3px}
 nav.nav a:hover{background:#2c3238;color:#fff}
 nav.nav a.act{background:#fff;color:#16181a;font-weight:600}
 main{max-width:900px;margin:0 auto;padding:20px 16px 60px;display:flex;flex-direction:column;gap:16px}
 .caja{background:#fff;border:1px solid #d8dcdf;border-radius:4px;padding:18px}
 h2{margin:0 0 4px;font-size:15px}
 p.ayuda{margin:0 0 12px;font-size:13px;color:#5a646c}
 textarea,input[type=text],select{width:100%;font:14px system-ui,sans-serif;padding:9px;
   border:1px solid #c8cfd4;border-radius:3px;background:#fff}
 textarea{min-height:80px;resize:vertical}
 label{display:block;font-size:12px;font-weight:600;margin:10px 0 4px}
 button{margin-top:12px;background:#16181a;color:#fff;border:0;border-radius:3px;
   padding:10px 18px;font:600 14px system-ui;cursor:pointer}
 button:hover{background:#2c3238}
 .fila{display:flex;gap:12px;flex-wrap:wrap} .fila>*{flex:1;min-width:180px}
 .res{white-space:pre-wrap;font:13.5px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;
   background:#fbfbfc;border:1px solid #e3e6e8;border-radius:3px;padding:14px;overflow-x:auto}
 .ref{display:inline-block;font:11px ui-monospace,monospace;background:#eceff1;
   color:#39434b;padding:2px 7px;border-radius:2px;margin:2px 3px 0 0}
 .hist{font-size:12.5px;color:#5a646c;border-top:1px solid #e3e6e8;padding:6px 0}
 .aviso{background:#fff6e5;border-left:3px solid #c98a12;padding:10px 12px;font-size:13px}
 .lista{display:flex;flex-direction:column;gap:2px}
 .itm{color:#16181a;text-decoration:none;font-size:13.5px;padding:5px 6px;border-radius:3px}
 .itm:hover{background:#eceff1}
 .md{background:#fbfbfc;border:1px solid #e3e6e8;border-radius:3px;padding:6px 18px;overflow-x:auto}
 .md h1{font-size:18px;margin:16px 0 8px} .md h2{font-size:15px;margin:16px 0 6px}
 .md h3{font-size:13.5px;margin:14px 0 6px}
 .md p{margin:0 0 12px;font-size:14px;line-height:1.6}
 .md strong{font-weight:700} .md em{font-style:italic}
 .md code{font:12.5px ui-monospace,monospace;background:#eceff1;padding:1px 5px;border-radius:2px}
 .md blockquote{margin:0 0 12px;padding:4px 12px;border-left:3px solid #c8cfd4;
   color:#5a646c;font-size:13.5px}
 .md ul{margin:0 0 12px;padding-left:20px} .md li{font-size:14px;margin:2px 0}
</style>
<header>
  <div class="cab">
    <b>Conformidad de envases · Reglamento (UE) 2025/40</b>
    <nav class="nav">
      <a href="{{ url_for('home') }}" class="{{ 'act' if activa=='consulta' else '' }}">Consultar</a>
      <a href="{{ url_for('normativa') }}" class="{{ 'act' if activa=='normativa' else '' }}">Normativa</a>
      <a href="{{ url_for('carpetas') }}" class="{{ 'act' if activa=='carpetas' else '' }}">Carpetas</a>
    </nav>
  </div>
  <span>{{ estado }}{% if actualizado %} · actualizado {{ actualizado }}{% endif %}</span>
</header>
"""

PAGINA = BASE_HEAD + """
<main>

{% if 'SIN CARGAR' in estado %}
<div class="caja aviso">El reglamento no está cargado. En la Pi: <code>python preparar_reglamento.py</code></div>
{% endif %}

{% if res %}
<div class="caja">
  <h2>{{ res.titulo }}</h2>
  <p class="ayuda">Fuentes usadas:
    {% for f in res.fuentes %}<span class="ref">{{ f }}</span>{% endfor %}</p>
  <div class="res">{{ res.cuerpo }}</div>
</div>
{% endif %}

<div class="caja">
  <h2>Preguntar al reglamento</h2>
  <p class="ayuda">Responde solo con el texto normativo cargado. Si no lo cubre, lo dice.</p>
  <form method="post" action="/preguntar">
    <textarea name="pregunta" placeholder="¿Qué documentación debo exigir a un fabricante de fuera de la UE antes de comercializar su envase?"></textarea>
    <button>Preguntar</button>
  </form>
</div>

<div class="caja">
  <h2>Revisar un documento</h2>
  <p class="ayuda">Informe de proveedor, correo, declaración, ficha técnica. PDF, DOCX o texto.</p>
  <form method="post" action="/analizar" enctype="multipart/form-data">
    <input type="file" name="documento" accept=".pdf,.docx,.txt,.md,.eml">
    <div class="fila">
      <div>
        <label>Rol legal en esta referencia</label>
        <select name="rol">
          <option>Importador (fabricante fuera de la UE)</option>
          <option>Adquirente intracomunitario</option>
          <option>Envasador propio</option>
          <option>Distribuidor</option>
          <option>Sin determinar</option>
        </select>
      </div>
      <div>
        <label>Contexto o duda concreta</label>
        <input type="text" name="nota" placeholder="Estuche de cartón, venta a consumidor">
      </div>
    </div>
    <button>Revisar</button>
  </form>
</div>

{% if historial %}
<div class="caja">
  <h2>Últimos trabajos</h2>
  {% for h in historial %}
  <div class="hist">{{ h.fecha }} · {{ h.tipo }} · {{ h.que[:90] }}</div>
  {% endfor %}
  <p class="ayuda" style="margin-top:10px">Guardados en <code>salidas/</code> como JSON.</p>
</div>
{% endif %}

</main></html>"""

PAGINA_NORMATIVA = BASE_HEAD + """
<main>

{% if 'SIN CARGAR' in estado %}
<div class="caja aviso">El reglamento no está cargado. En la Pi: <code>python preparar_reglamento.py</code></div>
{% endif %}

<div class="caja">
  <h2>Normativa cargada</h2>
  <p class="ayuda">Reglamento (UE) 2025/40 (PPWR), envases y residuos de envases.
    Aplicable desde el 12/08/2026.</p>
  <p class="ayuda"><a href="{{ url_for('normativa_articulo', clave='considerandos') }}">Ver considerandos</a>
    (interpretativos, no vinculantes)</p>
</div>

<div class="caja">
  <h2>Artículos</h2>
  <div class="lista">
    {% for a in arts %}
    <a class="itm" href="{{ url_for('normativa_articulo', clave=a.clave) }}">Art. {{ a.clave.split('-')[1]|int }} — {{ a.titulo }}</a>
    {% endfor %}
  </div>
</div>

<div class="caja">
  <h2>Anexos</h2>
  <div class="lista">
    {% for a in anexos %}
    <a class="itm" href="{{ url_for('normativa_articulo', clave=a.clave) }}">Anexo {{ a.clave.split('-')[1] }} — {{ a.titulo }}</a>
    {% endfor %}
  </div>
</div>

</main></html>"""

PAGINA_ARTICULO = BASE_HEAD + """
<main>

<div class="caja">
  <p class="ayuda"><a href="{{ url_for('normativa') }}">&larr; Normativa</a></p>
  <div class="md">{{ contenido_html }}</div>
</div>

</main></html>"""

PAGINA_CARPETAS = BASE_HEAD + """
<main>

<div class="caja">
  <h2>Nueva carpeta</h2>
  <p class="ayuda">Un caso, una duda, un proveedor concreto. Todo lo que preguntes o subas
    dentro se recuerda entre turnos, como una conversación.</p>
  <form method="post" action="{{ url_for('carpeta_nueva') }}">
    <input type="text" name="nombre" placeholder="Proveedor X — blíster PVC" required>
    <button>Crear carpeta</button>
  </form>
</div>

<div class="caja">
  <h2>Carpetas abiertas</h2>
  {% if carpetas %}
  <div class="lista">
    {% for c in carpetas %}
    <a class="itm" href="{{ url_for('carpeta_ver', slug=c.slug) }}">{{ c.nombre }}
      <span class="ref">{{ c.turnos }} turno{{ 's' if c.turnos != 1 else '' }}</span>
      <span class="ref">{{ c.ultima }}</span></a>
    {% endfor %}
  </div>
  {% else %}
  <p class="ayuda">Ninguna todavía.</p>
  {% endif %}
</div>

</main></html>"""

PAGINA_CARPETA = BASE_HEAD + """
<main>

<div class="caja">
  <p class="ayuda"><a href="{{ url_for('carpetas') }}">&larr; Carpetas</a></p>
  <h2>{{ carpeta.nombre }}</h2>
  <p class="ayuda">Creada {{ carpeta.creada[:16].replace('T', ' ') }}</p>
</div>

{% for t in turnos %}
<div class="caja">
  <h2>{{ t.pregunta if t.tipo == 'pregunta' else (t.documento or 'Nota suelta') }}</h2>
  {% if t.tipo == 'analisis' %}
  <p class="ayuda">Rol: {{ t.rol }}{% if t.nota %} · {{ t.nota }}{% endif %}</p>
  {% endif %}
  <p class="ayuda">Fuentes:
    {% for f in t.fuentes %}<span class="ref">{{ f }}</span>{% endfor %}</p>
  <div class="res">{{ t.respuesta }}</div>
  <p class="ayuda" style="margin-top:8px">{{ t.fecha[:16].replace('T', ' ') }}</p>
</div>
{% endfor %}

<div class="caja">
  <h2>Preguntar en esta carpeta</h2>
  <p class="ayuda">Recuerda todo lo hablado antes en esta misma carpeta.</p>
  <form method="post" action="{{ url_for('carpeta_preguntar', slug=carpeta.slug) }}">
    <textarea name="pregunta" placeholder="Sigue la conversación..."></textarea>
    <button>Preguntar</button>
  </form>
</div>

<div class="caja">
  <h2>Subir documento a esta carpeta</h2>
  <p class="ayuda">El documento original se guarda dentro de la carpeta, junto con el análisis.</p>
  <form method="post" action="{{ url_for('carpeta_analizar', slug=carpeta.slug) }}" enctype="multipart/form-data">
    <input type="file" name="documento" accept=".pdf,.docx,.txt,.md,.eml">
    <div class="fila">
      <div>
        <label>Rol legal en esta referencia</label>
        <select name="rol">
          <option>Importador (fabricante fuera de la UE)</option>
          <option>Adquirente intracomunitario</option>
          <option>Envasador propio</option>
          <option>Distribuidor</option>
          <option>Sin determinar</option>
        </select>
      </div>
      <div>
        <label>Contexto o duda concreta</label>
        <input type="text" name="nota" placeholder="Estuche de cartón, venta a consumidor">
      </div>
    </div>
    <button>Revisar</button>
  </form>
</div>

</main></html>"""


if __name__ == "__main__":
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("Falta ANTHROPIC_API_KEY")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
