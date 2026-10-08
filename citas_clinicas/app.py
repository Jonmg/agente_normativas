"""CitaCerca: reserva de citas en clínicas de salud y bienestar cercanas.

Dos tipos de cuenta:
- clínica: publica su ficha (foto, color, servicios, horario) y gestiona
  solicitudes de cita y mensajes.
- paciente: busca por tipo de clínica o por lo que le pasa, ve huecos libres
  de la semana en clínicas cercanas y pide cita, llama o deja un mensaje.

Arranque:
    python app.py --demo     # crea la base de datos con datos de ejemplo
    python app.py            # arranca en http://127.0.0.1:5000
"""

import csv
import io
import math
import os
import secrets
import sqlite3
import sys
import unicodedata
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   send_from_directory, session, url_for)
from markupsafe import Markup
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE = Path(__file__).resolve().parent

# --------------------------------------------------------------------------
# Catálogos
# --------------------------------------------------------------------------

TIPOS = {
    "podologia": ("Podología", "🦶"),
    "fisioterapia": ("Fisioterapia", "💪"),
    "masaje": ("Masaje y quiromasaje", "💆"),
    "odontologia": ("Odontología", "🦷"),
    "osteopatia": ("Osteopatía", "🦴"),
    "psicologia": ("Psicología", "🧠"),
    "nutricion": ("Nutrición", "🥗"),
}

CARACTERISTICAS = {
    "accesible": "Accesible en silla de ruedas",
    "parking": "Parking cercano",
    "domicilio": "Atención a domicilio",
    "urgencias": "Urgencias en el día",
    "tarjeta": "Pago con tarjeta",
    "seguros": "Trabaja con aseguradoras",
    "infantil": "Atención infantil",
    "ingles": "Se habla inglés",
}

# Qué tipo de clínica suele resolver cada necesidad. Sirve para que quien no
# sabe a quién acudir pueda escribir "me duele la espalda" y encontrar algo.
NECESIDADES = [
    (("una", "unas", "encarnada", "juanete", "pie", "pies", "plantilla", "plantillas",
      "dureza", "durezas", "callo", "callos", "talon", "fascitis", "pisada", "hongos",
      "verruga"), ("podologia",)),
    (("espalda", "lumbar", "lumbalgia", "cervical", "cervicales", "contractura",
      "lesion", "esguince", "rodilla", "rehabilitacion", "hombro", "tendinitis",
      "ciatica", "suelo pelvico", "punción", "puncion"), ("fisioterapia", "osteopatia", "masaje")),
    (("relajante", "relajar", "estres", "masaje", "descontracturante", "drenaje",
      "tension", "cansancio", "piernas cansadas"), ("masaje",)),
    (("muela", "muelas", "diente", "dientes", "encia", "encias", "ortodoncia", "dental",
      "blanqueamiento", "caries", "implante", "empaste", "boca"), ("odontologia",)),
    (("ansiedad", "depresion", "duelo", "terapia", "insomnio", "pareja"), ("psicologia",)),
    (("dieta", "peso", "adelgazar", "alimentacion", "nutricion", "intolerancia"), ("nutricion",)),
]

ESTADOS_CITA = {
    "pendiente": "Pendiente de confirmar",
    "confirmada": "Confirmada",
    "rechazada": "No disponible",
    "cancelada": "Cancelada",
    "completada": "Realizada",
}
ESTADOS_OCUPAN = ("pendiente", "confirmada")

# Mañana hasta las 14:00, tarde desde las 14:00. Basta para lo que publica una clínica pequeña.
FRANJAS = {"manana": ("Mañana", 0, 14 * 60), "tarde": ("Tarde", 14 * 60, 24 * 60)}
MODOS = {
    "franjas": "Huecos por franja: digo cuántos tengo cada mañana y tarde y confirmo la hora",
    "agenda": "Agenda exacta: se ofrecen las horas libres según mi horario",
}

DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
DIAS_CORTOS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
MESES_LARGOS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
                "octubre", "noviembre", "diciembre"]
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

COLORES = ["#2a9d8f", "#264653", "#e76f51", "#6a4c93", "#1d70b8", "#d1495b", "#3a7d44", "#c77d00"]

EXTENSIONES_FOTO = {"png", "jpg", "jpeg", "webp", "gif"}
MARGEN_MIN = 60  # no se ofrecen huecos que empiecen dentro de la próxima hora

# Centro aproximado (capital) de cada provincia por los dos primeros dígitos
# del código postal. Basta para ordenar por cercanía sin geocodificar.
PROVINCIAS = {
    "01": (42.85, -2.67), "02": (38.99, -1.86), "03": (38.35, -0.48), "04": (36.84, -2.46),
    "05": (40.66, -4.70), "06": (38.88, -6.97), "07": (39.57, 2.65), "08": (41.39, 2.17),
    "09": (42.34, -3.70), "10": (39.48, -6.37), "11": (36.53, -6.29), "12": (39.99, -0.05),
    "13": (38.99, -3.93), "14": (37.89, -4.78), "15": (43.36, -8.41), "16": (40.07, -2.13),
    "17": (41.98, 2.82), "18": (37.18, -3.60), "19": (40.63, -3.17), "20": (43.32, -1.98),
    "21": (37.26, -6.95), "22": (42.14, -0.41), "23": (37.77, -3.79), "24": (42.60, -5.57),
    "25": (41.62, 0.62), "26": (42.47, -2.45), "27": (43.01, -7.56), "28": (40.42, -3.70),
    "29": (36.72, -4.42), "30": (37.99, -1.13), "31": (42.81, -1.64), "32": (42.34, -7.86),
    "33": (43.36, -5.85), "34": (42.01, -4.53), "35": (28.12, -15.43), "36": (42.43, -8.64),
    "37": (40.97, -5.66), "38": (28.46, -16.25), "39": (43.46, -3.80), "40": (40.95, -4.12),
    "41": (37.39, -5.98), "42": (41.76, -2.46), "43": (41.12, 1.25), "44": (40.34, -1.11),
    "45": (39.86, -4.02), "46": (39.47, -0.38), "47": (41.65, -4.72), "48": (43.26, -2.93),
    "49": (41.50, -5.75), "50": (41.65, -0.88), "51": (35.89, -5.32), "52": (35.29, -2.94),
}

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    clave TEXT NOT NULL,
    rol TEXT NOT NULL CHECK (rol IN ('paciente', 'clinica', 'admin')),
    nombre TEXT NOT NULL,
    telefono TEXT DEFAULT '',
    codigo_postal TEXT DEFAULT '',
    creado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clinicas (
    id INTEGER PRIMARY KEY,
    usuario_id INTEGER NOT NULL UNIQUE REFERENCES usuarios(id),
    nombre TEXT NOT NULL,
    tipo TEXT NOT NULL,
    eslogan TEXT DEFAULT '',
    descripcion TEXT DEFAULT '',
    direccion TEXT DEFAULT '',
    ciudad TEXT DEFAULT '',
    codigo_postal TEXT NOT NULL,
    telefono TEXT DEFAULT '',
    web TEXT DEFAULT '',
    foto TEXT DEFAULT '',
    color TEXT DEFAULT '#2a9d8f',
    caracteristicas TEXT DEFAULT '',
    duracion_hueco INTEGER DEFAULT 30,
    confirmacion_automatica INTEGER DEFAULT 0,
    activa INTEGER DEFAULT 1,
    lat REAL,
    lon REAL,
    tarifa REAL,             -- € por paciente nuevo; NULL = tarifa general
    tope_mensual REAL,       -- máximo a facturar al mes; NULL = sin tope
    creado TEXT DEFAULT '',
    -- 'franjas': la clínica publica cuántos huecos tiene por mañana/tarde y confirma la hora.
    -- 'agenda': huecos exactos generados a partir del horario (permite confirmación automática).
    modo TEXT DEFAULT 'franjas'
);
-- Huecos publicados por franja: «el lunes 12 por la mañana tengo 3».
CREATE TABLE IF NOT EXISTS cupos (
    id INTEGER PRIMARY KEY,
    clinica_id INTEGER NOT NULL REFERENCES clinicas(id),
    fecha TEXT NOT NULL,
    franja TEXT NOT NULL CHECK (franja IN ('manana', 'tarde')),
    plazas INTEGER NOT NULL DEFAULT 0,
    UNIQUE (clinica_id, fecha, franja)
);
CREATE TABLE IF NOT EXISTS servicios (
    id INTEGER PRIMARY KEY,
    clinica_id INTEGER NOT NULL REFERENCES clinicas(id),
    nombre TEXT NOT NULL,
    duracion INTEGER NOT NULL,
    precio REAL,
    descripcion TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS horarios (
    id INTEGER PRIMARY KEY,
    clinica_id INTEGER NOT NULL REFERENCES clinicas(id),
    dia_semana INTEGER NOT NULL,
    inicio TEXT NOT NULL,
    fin TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS bloqueos (
    id INTEGER PRIMARY KEY,
    clinica_id INTEGER NOT NULL REFERENCES clinicas(id),
    fecha TEXT NOT NULL,
    inicio TEXT,
    fin TEXT,
    motivo TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS citas (
    id INTEGER PRIMARY KEY,
    clinica_id INTEGER NOT NULL REFERENCES clinicas(id),
    paciente_id INTEGER NOT NULL REFERENCES usuarios(id),
    servicio_id INTEGER REFERENCES servicios(id),
    fecha TEXT NOT NULL,
    hora TEXT NOT NULL,
    duracion INTEGER NOT NULL,
    estado TEXT NOT NULL,
    mensaje_paciente TEXT DEFAULT '',
    respuesta_clinica TEXT DEFAULT '',
    llamar_antes INTEGER DEFAULT 0,
    ya_paciente INTEGER DEFAULT 0,  -- la clínica indica que ya era paciente suyo: no se factura
    franja TEXT DEFAULT '',         -- 'manana' / 'tarde'; en modo franjas la hora queda '' hasta confirmar
    preferencia TEXT DEFAULT '',    -- hora aproximada que prefiere el paciente
    visto_paciente INTEGER DEFAULT 1,
    creado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mensajes (
    id INTEGER PRIMARY KEY,
    clinica_id INTEGER NOT NULL REFERENCES clinicas(id),
    paciente_id INTEGER NOT NULL REFERENCES usuarios(id),
    tipo TEXT NOT NULL,
    franja TEXT DEFAULT '',
    texto TEXT NOT NULL,
    respuesta TEXT DEFAULT '',
    estado TEXT NOT NULL DEFAULT 'nuevo',
    visto_paciente INTEGER DEFAULT 1,
    creado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS valoraciones (
    id INTEGER PRIMARY KEY,
    cita_id INTEGER NOT NULL UNIQUE REFERENCES citas(id),
    clinica_id INTEGER NOT NULL REFERENCES clinicas(id),
    paciente_id INTEGER NOT NULL REFERENCES usuarios(id),
    puntuacion INTEGER NOT NULL CHECK (puntuacion BETWEEN 1 AND 5),
    comentario TEXT DEFAULT '',
    creado TEXT NOT NULL
);
-- Interacciones con la ficha (vistas, clics en llamar o en el mapa). Sirven para
-- enseñar a cada clínica lo que le aporta la plataforma.
CREATE TABLE IF NOT EXISTS eventos (
    id INTEGER PRIMARY KEY,
    clinica_id INTEGER NOT NULL REFERENCES clinicas(id),
    tipo TEXT NOT NULL,
    usuario_id INTEGER,
    creado TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_citas_clinica_fecha ON citas(clinica_id, fecha);
CREATE INDEX IF NOT EXISTS idx_eventos_clinica ON eventos(clinica_id, creado);
"""

# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------


def a_minutos(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def a_hhmm(minutos):
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def normalizar(texto):
    texto = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


def palabras(texto):
    limpio = "".join(c if c.isalnum() else " " for c in normalizar(texto))
    return [p for p in limpio.split() if len(p) > 2]


def ahora():
    """Punto único para la hora actual (las pruebas lo sustituyen)."""
    return datetime.now()


def fecha_bonita(valor):
    d = valor if isinstance(valor, date) else date.fromisoformat(valor)
    return f"{DIAS[d.weekday()]} {d.day} {MESES[d.month - 1]}"


def fecha_corta(valor):
    d = valor if isinstance(valor, date) else date.fromisoformat(valor)
    return f"{DIAS_CORTOS[d.weekday()]} {d.day}"


def cuando(cita):
    """«Lunes 12 oct · 10:00», o la franja si la clínica aún no ha fijado la hora."""
    if cita["hora"]:
        return f"{fecha_bonita(cita['fecha'])} · {cita['hora']}"
    texto = f"{fecha_bonita(cita['fecha'])} · {FRANJAS[cita['franja']][0].lower()}"
    if cita["preferencia"]:
        texto += f" (prefiere hacia las {cita['preferencia']})"
    return texto


def cp_valido(cp):
    return len(cp) == 5 and cp.isdigit() and cp[:2] in PROVINCIAS


def distancia_cp(cp_a, cp_b):
    """Distancia aproximada entre dos códigos postales.

    Devuelve (clave_orden, texto). Entre provincias se mide entre capitales;
    dentro de la misma provincia, la cercanía numérica del código postal es
    una aproximación razonable de la cercanía real.
    """
    if not (cp_valido(cp_a) and cp_valido(cp_b)):
        return (10**6, "")
    if cp_a == cp_b:
        return (0, "En tu código postal")
    if cp_a[:2] == cp_b[:2]:
        return (abs(int(cp_a) - int(cp_b)) / 1000, "En tu provincia")
    km = km_entre(*PROVINCIAS[cp_a[:2]], *PROVINCIAS[cp_b[:2]])
    return (km, f"A unos {round(km / 10) * 10:.0f} km")


def km_entre(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def texto_km(km):
    if km < 1:
        return f"A {round(km * 1000 / 50) * 50:.0f} m"
    return f"A {km:.1f} km".replace(".", ",")


def coordenada(valor, limite):
    try:
        x = float(valor)
    except (TypeError, ValueError):
        return None
    return x if -limite <= x <= limite else None


def distancia(c, cp="", lat=None, lon=None):
    """Distancia del paciente a la clínica: real si hay coordenadas, si no por código postal."""
    if lat is not None and lon is not None:
        if c["lat"] is not None and c["lon"] is not None:
            km = km_entre(lat, lon, c["lat"], c["lon"])
            return (km, texto_km(km))
        # Sin chincheta no se puede medir: detrás de las que sí la tienen.
        clave, texto = distancia_cp(cp, c["codigo_postal"]) if cp else (0, "")
        return (10**5 + clave, texto)
    return distancia_cp(cp, c["codigo_postal"]) if cp else (0, "")


def tipos_por_necesidad(texto):
    norm = " " + " ".join(palabras(texto)) + " "
    tipos = []
    for claves, destino in NECESIDADES:
        if any(f" {normalizar(c)} " in norm for c in claves):
            for t in destino:
                if t not in tipos:
                    tipos.append(t)
    return tipos


# --------------------------------------------------------------------------
# Base de datos
# --------------------------------------------------------------------------


def conectar(ruta):
    db = sqlite3.connect(ruta)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def get_db():
    if "db" not in g:
        g.db = conectar(app_actual().config["BASE_DATOS"])
    return g.db


def app_actual():
    from flask import current_app
    return current_app


def iniciar_bd(ruta):
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    db = conectar(ruta)
    migrar(db)
    db.executescript(ESQUEMA)
    db.commit()
    return db


def migrar(db):
    """Pone al día bases creadas con versiones anteriores del esquema."""
    tablas = {r[0]: r[1] for r in db.execute("SELECT name, sql FROM sqlite_master WHERE type = 'table'")}
    if "usuarios" in tablas and "'admin'" not in tablas["usuarios"]:
        # SQLite no permite cambiar un CHECK: se reconstruye la tabla.
        db.execute("PRAGMA foreign_keys = OFF")
        db.executescript("""
            CREATE TABLE usuarios_nueva (
                id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, clave TEXT NOT NULL,
                rol TEXT NOT NULL CHECK (rol IN ('paciente', 'clinica', 'admin')),
                nombre TEXT NOT NULL, telefono TEXT DEFAULT '', codigo_postal TEXT DEFAULT '',
                creado TEXT NOT NULL);
            INSERT INTO usuarios_nueva SELECT * FROM usuarios;
            DROP TABLE usuarios;
            ALTER TABLE usuarios_nueva RENAME TO usuarios;
        """)
        db.execute("PRAGMA foreign_keys = ON")
    nuevas = {"clinicas": [("lat", "REAL"), ("lon", "REAL"), ("tarifa", "REAL"), ("tope_mensual", "REAL"),
                           ("creado", "TEXT DEFAULT ''"), ("modo", "TEXT DEFAULT 'agenda'")],
              "citas": [("ya_paciente", "INTEGER DEFAULT 0"), ("franja", "TEXT DEFAULT ''"),
                        ("preferencia", "TEXT DEFAULT ''")]}
    for tabla, columnas in nuevas.items():
        if tabla not in tablas:
            continue
        existentes = {r[1] for r in db.execute(f"PRAGMA table_info({tabla})")}
        for nombre, tipo in columnas:
            if nombre not in existentes:
                db.execute(f"ALTER TABLE {tabla} ADD COLUMN {nombre} {tipo}")
    db.commit()


def una(sql, *args):
    return get_db().execute(sql, args).fetchone()


def todas(sql, *args):
    return get_db().execute(sql, args).fetchall()


# --------------------------------------------------------------------------
# Huecos libres
# --------------------------------------------------------------------------


def huecos_libres(db, clinica, duracion=None, desde=None, dias=7):
    """Huecos en los que cabe un servicio de `duracion` minutos.

    Recorre el horario semanal de la clínica en pasos de `duracion_hueco`,
    descartando lo pasado, lo bloqueado y lo que se solapa con citas
    pendientes o confirmadas. Devuelve [(fecha, [horas...]), ...].
    """
    momento = ahora()
    inicio = desde or momento.date()
    paso = clinica["duracion_hueco"] or 30
    duracion = duracion or paso
    fin = inicio + timedelta(days=dias)

    horario = {}
    for h in db.execute("SELECT * FROM horarios WHERE clinica_id = ? ORDER BY inicio",
                        (clinica["id"],)):
        horario.setdefault(h["dia_semana"], []).append((a_minutos(h["inicio"]), a_minutos(h["fin"])))

    ocupado = {}
    citas = db.execute(
        "SELECT fecha, hora, duracion FROM citas WHERE clinica_id = ? AND fecha >= ? AND fecha < ? "
        f"AND estado IN ({','.join('?' * len(ESTADOS_OCUPAN))})",
        (clinica["id"], inicio.isoformat(), fin.isoformat(), *ESTADOS_OCUPAN))
    for c in citas:
        if not c["hora"]:  # solicitud por franja aún sin hora: no ocupa una hora concreta
            continue
        ini = a_minutos(c["hora"])
        ocupado.setdefault(c["fecha"], []).append((ini, ini + c["duracion"]))
    for b in db.execute("SELECT * FROM bloqueos WHERE clinica_id = ? AND fecha >= ? AND fecha < ?",
                        (clinica["id"], inicio.isoformat(), fin.isoformat())):
        if b["inicio"] and b["fin"]:
            ocupado.setdefault(b["fecha"], []).append((a_minutos(b["inicio"]), a_minutos(b["fin"])))
        else:
            ocupado.setdefault(b["fecha"], []).append((0, 24 * 60))

    resultado = []
    for n in range(dias):
        dia = inicio + timedelta(days=n)
        clave = dia.isoformat()
        minimo = -1
        if dia == momento.date():
            minimo = momento.hour * 60 + momento.minute + MARGEN_MIN
        elif dia < momento.date():
            resultado.append((dia, []))
            continue
        horas = []
        for abre, cierra in horario.get(dia.weekday(), []):
            t = abre
            while t + duracion <= cierra:
                if t >= minimo and not any(t < f and t + duracion > i for i, f in ocupado.get(clave, [])):
                    horas.append(a_hhmm(t))
                t += paso
        resultado.append((dia, horas))
    return resultado


def franja_de(hora):
    return "manana" if a_minutos(hora) < FRANJAS["tarde"][1] else "tarde"


def tramos_franja(tramos, franja):
    """Parte del horario de un día que cae en la franja: [(inicio, fin)] en minutos."""
    _, ini, fin = FRANJAS[franja]
    return [(max(a, ini), min(b, fin)) for a, b in tramos if min(b, fin) > max(a, ini)]


def cupos_libres(db, clinica, desde=None, dias=7):
    """Huecos publicados por franja menos las solicitudes que ya los ocupan.

    Devuelve [(fecha, {franja: {"libres", "plazas", "abierto", "horario"}})].
    Una franja de hoy deja de ofrecerse cuando falta menos de MARGEN_MIN para su cierre.
    """
    momento = ahora()
    inicio = desde or momento.date()
    fin = inicio + timedelta(days=dias)
    horario = {}
    for h in db.execute("SELECT * FROM horarios WHERE clinica_id = ? ORDER BY inicio", (clinica["id"],)):
        horario.setdefault(h["dia_semana"], []).append((a_minutos(h["inicio"]), a_minutos(h["fin"])))
    plazas = {(r["fecha"], r["franja"]): r["plazas"] for r in db.execute(
        "SELECT * FROM cupos WHERE clinica_id = ? AND fecha >= ? AND fecha < ?",
        (clinica["id"], inicio.isoformat(), fin.isoformat()))}
    pedidas = {(r[0], r[1]): r[2] for r in db.execute(
        "SELECT fecha, franja, COUNT(*) FROM citas WHERE clinica_id = ? AND fecha >= ? AND fecha < ? "
        f"AND franja != '' AND estado IN ({','.join('?' * len(ESTADOS_OCUPAN))}) GROUP BY fecha, franja",
        (clinica["id"], inicio.isoformat(), fin.isoformat(), *ESTADOS_OCUPAN))}
    cerrados = {r[0] for r in db.execute(
        "SELECT fecha FROM bloqueos WHERE clinica_id = ? AND inicio IS NULL AND fecha >= ? AND fecha < ?",
        (clinica["id"], inicio.isoformat(), fin.isoformat()))}
    resultado = []
    for n in range(dias):
        dia = inicio + timedelta(days=n)
        clave = dia.isoformat()
        franjas = {}
        for f in FRANJAS:
            tramos = tramos_franja(horario.get(dia.weekday(), []), f)
            abierto = bool(tramos) and clave not in cerrados and dia >= momento.date()
            if abierto and dia == momento.date():
                abierto = momento.hour * 60 + momento.minute + MARGEN_MIN < tramos[-1][1]
            total = plazas.get((clave, f), 0)
            ocupadas = pedidas.get((clave, f), 0)
            franjas[f] = {
                "plazas": total, "ocupadas": ocupadas, "abierto": abierto,
                "libres": max(total - ocupadas, 0) if abierto else 0,
                "horario": ", ".join(f"{a_hhmm(a)}–{a_hhmm(b)}" for a, b in tramos),
                "horas": [a_hhmm(m) for a, b in tramos for m in range(a, b, 60)],
            }
        resultado.append((dia, franjas))
    return resultado


def disponibilidad(db, clinica, duracion=None, franja="", desde=None, dias=7):
    """Lo que se ofrece al paciente, sea cual sea el modo de la clínica.

    Lista de {"dia", "hora" | None, "franja", "plazas", "texto"} ordenada en el tiempo.
    """
    ofertas = []
    if clinica["modo"] == "franjas":
        for dia, franjas in cupos_libres(db, clinica, desde, dias):
            for f, datos in franjas.items():
                if datos["libres"] and (not franja or franja == f):
                    ofertas.append({"dia": dia, "hora": None, "franja": f, "plazas": datos["libres"],
                                    "texto": f"{fecha_corta(dia)} · {FRANJAS[f][0].lower()} ({datos['libres']})"})
    else:
        for dia, horas in huecos_libres(db, clinica, duracion, desde, dias):
            for h in horas:
                if not franja or franja_de(h) == franja:
                    ofertas.append({"dia": dia, "hora": h, "franja": franja_de(h), "plazas": 1,
                                    "texto": f"{fecha_corta(dia)} · {h}"})
    return ofertas


def cupo_disponible(db, clinica, fecha, franja):
    for dia, franjas in cupos_libres(db, clinica, desde=fecha, dias=1):
        return franjas[franja]["libres"] > 0
    return False


def hueco_disponible(db, clinica, fecha, hora, duracion):
    for dia, horas in huecos_libres(db, clinica, duracion, desde=fecha, dias=1):
        return hora in horas
    return False


# --------------------------------------------------------------------------
# Búsqueda
# --------------------------------------------------------------------------


def buscar_clinicas(db, tipo="", necesidad="", cp="", franja="", requisitos=(), orden="distancia",
                    lat=None, lon=None):
    tipos_inferidos = tipos_por_necesidad(necesidad) if necesidad and not tipo else []
    terminos = palabras(necesidad)
    resultados = []
    for c in db.execute("SELECT * FROM clinicas WHERE activa = 1"):
        servicios = db.execute("SELECT * FROM servicios WHERE clinica_id = ? ORDER BY duracion",
                               (c["id"],)).fetchall()
        caract = set(filter(None, c["caracteristicas"].split(",")))
        if tipo and c["tipo"] != tipo:
            continue
        if requisitos and not set(requisitos) <= caract:
            continue

        # Relevancia: tipo deducido de la necesidad + coincidencias de texto.
        relevancia = 0
        servicio_sugerido = None
        if necesidad:
            if c["tipo"] in tipos_inferidos:
                relevancia += 10 - tipos_inferidos.index(c["tipo"])
            for s in servicios:
                texto = set(palabras(s["nombre"] + " " + s["descripcion"]))
                aciertos = sum(1 for t in terminos if t in texto)
                if aciertos:
                    relevancia += 3 * aciertos
                    if servicio_sugerido is None:
                        servicio_sugerido = s
            descripcion = set(palabras(c["descripcion"] + " " + c["eslogan"]))
            relevancia += sum(1 for t in terminos if t in descripcion)
            if not tipo and relevancia == 0:
                continue

        duracion = servicio_sugerido["duracion"] if servicio_sugerido else (
            servicios[0]["duracion"] if servicios else None)
        proximos = disponibilidad(db, c, duracion, franja)
        dist, dist_texto = distancia(c, cp, lat, lon)
        media = db.execute("SELECT AVG(puntuacion) m, COUNT(*) n FROM valoraciones WHERE clinica_id = ?",
                           (c["id"],)).fetchone()
        resultados.append({
            "clinica": c,
            "servicios": servicios,
            "servicio_sugerido": servicio_sugerido,
            "caracteristicas": caract,
            "proximos": proximos[:6],
            "total_huecos": sum(p["plazas"] for p in proximos),
            "distancia": dist,
            "distancia_texto": dist_texto,
            "relevancia": relevancia,
            "valoracion": (media["m"], media["n"]),
            "precio_desde": min((s["precio"] for s in servicios if s["precio"] is not None), default=None),
        })

    def primer_hueco(r):
        if not r["proximos"]:
            return (date.max, "99:99")
        p = r["proximos"][0]
        return (p["dia"], p["hora"] or a_hhmm(FRANJAS[p["franja"]][1]))

    sin_huecos = [r for r in resultados if not r["proximos"]]
    con_huecos = [r for r in resultados if r["proximos"]]
    if orden == "pronto":
        con_huecos.sort(key=lambda r: (primer_hueco(r), r["distancia"]))
    elif orden == "valoracion":
        con_huecos.sort(key=lambda r: (-(r["valoracion"][0] or 0), r["distancia"]))
    else:
        con_huecos.sort(key=lambda r: (r["distancia"], -r["relevancia"], primer_hueco(r)))
    sin_huecos.sort(key=lambda r: r["distancia"])
    return con_huecos + sin_huecos, tipos_inferidos


# --------------------------------------------------------------------------
# Captación y facturación
# --------------------------------------------------------------------------

TARIFA_POR_DEFECTO = float(os.environ.get("CITAS_TARIFA", "8"))
TIPOS_EVENTO = ("vista", "llamar", "mapa", "web")


def rango_mes(mes):
    """'2026-10' -> (date(2026,10,1), date(2026,11,1)). Mes no válido -> mes actual."""
    try:
        inicio = datetime.strptime(mes, "%Y-%m").date()
    except (TypeError, ValueError):
        inicio = ahora().date().replace(day=1)
    fin = (inicio.replace(day=28) + timedelta(days=4)).replace(day=1)
    return inicio, fin


def captaciones(db, desde, hasta, clinica_id=None):
    """Pacientes nuevos que la plataforma ha llevado a cada clínica.

    Cuenta la PRIMERA cita confirmada o realizada de cada paciente en cada
    clínica, cuya fecha cae en [desde, hasta). Las que la clínica marca como
    «ya era paciente» se devuelven con ya_paciente = 1 y no se facturan.
    """
    filtro = "AND ci.clinica_id = ?" if clinica_id else ""
    args = [desde.isoformat(), hasta.isoformat()] + ([clinica_id] if clinica_id else [])
    return db.execute(f"""
        SELECT ci.*, u.nombre paciente, u.email, u.telefono, cl.nombre clinica, s.nombre servicio
        FROM citas ci
        JOIN usuarios u ON u.id = ci.paciente_id
        JOIN clinicas cl ON cl.id = ci.clinica_id
        LEFT JOIN servicios s ON s.id = ci.servicio_id
        WHERE ci.estado IN ('confirmada', 'completada') AND ci.fecha >= ? AND ci.fecha < ? {filtro}
          AND NOT EXISTS (
            SELECT 1 FROM citas p
            WHERE p.paciente_id = ci.paciente_id AND p.clinica_id = ci.clinica_id
              AND p.estado IN ('confirmada', 'completada')
              AND (p.fecha || ' ' || p.hora || printf('%09d', p.id))
                  < (ci.fecha || ' ' || ci.hora || printf('%09d', ci.id)))
        ORDER BY ci.fecha, ci.hora""", args).fetchall()


def importe(clinica, nuevos_facturables):
    tarifa = clinica["tarifa"] if clinica["tarifa"] is not None else TARIFA_POR_DEFECTO
    total = nuevos_facturables * tarifa
    if clinica["tope_mensual"] is not None:
        total = min(total, clinica["tope_mensual"])
    return tarifa, total


def resumen_clinica(db, clinica, desde, hasta):
    """Embudo del mes para una clínica: de la vista de la ficha al paciente nuevo."""
    cid = clinica["id"]
    rango = (desde.isoformat(), hasta.isoformat())
    eventos = dict(db.execute("SELECT tipo, COUNT(*) FROM eventos WHERE clinica_id = ? AND creado >= ? "
                              "AND creado < ? GROUP BY tipo", (cid, *rango)).fetchall())
    solicitudes = db.execute("SELECT COUNT(*) FROM citas WHERE clinica_id = ? AND creado >= ? AND creado < ?",
                             (cid, *rango)).fetchone()[0]
    mensajes = db.execute("SELECT COUNT(*) FROM mensajes WHERE clinica_id = ? AND creado >= ? AND creado < ?",
                          (cid, *rango)).fetchone()[0]
    nuevos = captaciones(db, desde, hasta, cid)
    facturables = sum(1 for n in nuevos if not n["ya_paciente"])
    tarifa, total = importe(clinica, facturables)
    return {"clinica": clinica, "vistas": eventos.get("vista", 0), "llamadas": eventos.get("llamar", 0),
            "mapa": eventos.get("mapa", 0), "mensajes": mensajes, "solicitudes": solicitudes,
            "nuevos": len(nuevos), "facturables": facturables, "tarifa": tarifa, "importe": total,
            "detalle": nuevos}


def registrar_evento(db, clinica_id, tipo, usuario_id=None):
    db.execute("INSERT INTO eventos (clinica_id, tipo, usuario_id, creado) VALUES (?, ?, ?, ?)",
               (clinica_id, tipo, usuario_id, ahora().isoformat()))
    db.commit()


def asegurar_admin(ruta, email, clave):
    """Crea o actualiza la cuenta de administración indicada por variables de entorno."""
    db = conectar(ruta)
    hash_clave = generate_password_hash(clave)
    if db.execute("SELECT 1 FROM usuarios WHERE email = ?", (email,)).fetchone():
        db.execute("UPDATE usuarios SET clave = ?, rol = 'admin' WHERE email = ?", (hash_clave, email))
    else:
        db.execute("INSERT INTO usuarios (email, clave, rol, nombre, creado) VALUES (?, ?, 'admin', ?, ?)",
                   (email, hash_clave, "Administración", ahora().isoformat()))
    db.commit()
    db.close()


# --------------------------------------------------------------------------
# Aplicación
# --------------------------------------------------------------------------


def crear_app(config=None):
    app = Flask(__name__)
    app.config.update(
        BASE_DATOS=os.environ.get("CITAS_BD", str(BASE / "datos" / "citas.db")),
        SUBIDAS=os.environ.get("CITAS_SUBIDAS", str(BASE / "datos" / "subidas")),
        MAX_CONTENT_LENGTH=4 * 1024 * 1024,
        SECRET_KEY=os.environ.get("CITAS_SECRETO") or clave_secreta(),
        CSRF=True,
        # Modo demo pública: siembra datos de ejemplo si la base está vacía y
        # muestra las cuentas de prueba en «Entrar».
        DEMO=os.environ.get("CITAS_DEMO") == "1",
    )
    if config:
        app.config.update(config)
    Path(app.config["SUBIDAS"]).mkdir(parents=True, exist_ok=True)
    db = iniciar_bd(app.config["BASE_DATOS"])
    vacia = db.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0] == 0
    db.close()
    if app.config["DEMO"] and vacia:
        from datos_demo import sembrar
        sembrar(app.config["BASE_DATOS"])
    if os.environ.get("CITAS_ADMIN_EMAIL") and os.environ.get("CITAS_ADMIN_CLAVE"):
        asegurar_admin(app.config["BASE_DATOS"], os.environ["CITAS_ADMIN_EMAIL"].lower(),
                       os.environ["CITAS_ADMIN_CLAVE"])

    app.jinja_env.filters.update(fecha_bonita=fecha_bonita, fecha_corta=fecha_corta, cuando=cuando,
                                 euros=lambda x: f"{x:,.2f} €".replace(",", "X").replace(".", ",").replace("X", "."))
    app.jinja_env.globals.update(TIPOS=TIPOS, CARACTERISTICAS=CARACTERISTICAS,
                                 ESTADOS_CITA=ESTADOS_CITA, DIAS=DIAS, COLORES=COLORES,
                                 FRANJAS=FRANJAS, MODOS=MODOS,
                                 csrf=campo_csrf, token_csrf=token_csrf, puede_valorarse=puede_valorarse,
                                 demo=app.config["DEMO"], cuentas_demo=cuentas_demo)

    @app.teardown_appcontext
    def cerrar_db(_):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.before_request
    def antes():
        g.usuario = None
        g.clinica = None
        if "uid" in session:
            g.usuario = una("SELECT * FROM usuarios WHERE id = ?", session["uid"])
            if g.usuario and g.usuario["rol"] == "clinica":
                g.clinica = una("SELECT * FROM clinicas WHERE usuario_id = ?", g.usuario["id"])
        if request.method == "POST" and app.config["CSRF"]:
            if not session.get("csrf") or request.form.get("_csrf") != session["csrf"]:
                abort(400, "Formulario caducado. Vuelve atrás y recarga la página.")

    @app.context_processor
    def avisos():
        n = 0
        if g.get("clinica"):
            n = una("SELECT (SELECT COUNT(*) FROM citas WHERE clinica_id = ? AND estado = 'pendiente') + "
                    "(SELECT COUNT(*) FROM mensajes WHERE clinica_id = ? AND estado = 'nuevo') n",
                    g.clinica["id"], g.clinica["id"])["n"]
        elif g.get("usuario"):
            n = una("SELECT (SELECT COUNT(*) FROM citas WHERE paciente_id = ? AND visto_paciente = 0) + "
                    "(SELECT COUNT(*) FROM mensajes WHERE paciente_id = ? AND visto_paciente = 0) n",
                    g.usuario["id"], g.usuario["id"])["n"]
        return {"avisos": n}

    registrar_rutas(app)
    return app


def cuentas_demo():
    from datos_demo import ADMIN, CLINICAS, PACIENTE
    return ([("👤 Paciente · " + PACIENTE["nombre"], PACIENTE["email"])]
            + [(f"{TIPOS[c['tipo']][1]} {c['nombre']}", c["email"]) for c in CLINICAS]
            + [("🛠️ Administración de la plataforma", ADMIN["email"])])


def clave_secreta():
    ruta = BASE / "datos" / ".secreto"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if not ruta.exists():
        ruta.write_text(secrets.token_hex(32))
    return ruta.read_text().strip()


def token_csrf():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]


def campo_csrf():
    return Markup(f'<input type="hidden" name="_csrf" value="{token_csrf()}">')


def requiere(rol):
    def decorador(f):
        @wraps(f)
        def envoltura(*args, **kwargs):
            if not g.usuario:
                flash("Entra con tu cuenta para continuar.", "info")
                siguiente = request.full_path if request.method == "GET" else None
                return redirect(url_for("entrar", siguiente=siguiente))
            if g.usuario["rol"] != rol:
                flash("Esa sección es para cuentas de "
                      + {"paciente": "paciente", "clinica": "clínica", "admin": "administración"}[rol] + ".", "error")
                return redirect(url_for("inicio"))
            if rol == "clinica" and not g.clinica:
                abort(404)
            return f(*args, **kwargs)
        return envoltura
    return decorador


def guardar_foto(fichero, prefijo):
    if not fichero or not fichero.filename:
        return None
    ext = fichero.filename.rsplit(".", 1)[-1].lower() if "." in fichero.filename else ""
    if ext not in EXTENSIONES_FOTO:
        flash("La foto debe ser PNG, JPG, WEBP o GIF.", "error")
        return None
    nombre = secure_filename(f"{prefijo}-{secrets.token_hex(6)}.{ext}")
    fichero.save(Path(app_actual().config["SUBIDAS"]) / nombre)
    return nombre


def campo(nombre, maximo=500):
    return (request.form.get(nombre) or "").strip()[:maximo]


def validar_cuenta(email, clave, nombre, cp):
    errores = []
    if "@" not in email or "." not in email.split("@")[-1]:
        errores.append("El email no parece válido.")
    if len(clave) < 8:
        errores.append("La contraseña debe tener al menos 8 caracteres.")
    if not nombre:
        errores.append("Falta el nombre.")
    if not cp_valido(cp):
        errores.append("El código postal debe tener 5 cifras (España).")
    if email and una("SELECT 1 FROM usuarios WHERE email = ?", email):
        errores.append("Ya existe una cuenta con ese email.")
    return errores


def destino_seguro(valor):
    """Solo rutas internas: evita redirecciones abiertas a otros dominios."""
    valor = valor or ""
    return valor if valor.startswith("/") and not valor.startswith("//") else ""


def iniciar_sesion(uid):
    csrf = session.get("csrf")
    session.clear()
    session["uid"] = uid
    if csrf:
        session["csrf"] = csrf


def horario_por_defecto(db, clinica_id):
    for dia in range(5):
        db.execute("INSERT INTO horarios (clinica_id, dia_semana, inicio, fin) VALUES (?, ?, '09:00', '14:00')",
                   (clinica_id, dia))
        db.execute("INSERT INTO horarios (clinica_id, dia_semana, inicio, fin) VALUES (?, ?, '16:00', '20:00')",
                   (clinica_id, dia))


def registrar_rutas(app):

    # ---------------------------------------------------------------- público

    @app.route("/")
    def inicio():
        n = una("SELECT COUNT(*) n FROM clinicas WHERE activa = 1")["n"]
        return render_template("inicio.html", total_clinicas=n)

    @app.route("/buscar")
    def buscar():
        tipo = request.args.get("tipo", "")
        tipo = tipo if tipo in TIPOS else ""
        necesidad = request.args.get("necesidad", "").strip()[:200]
        cp = request.args.get("cp", "").strip()
        if not cp and g.usuario:
            cp = g.usuario["codigo_postal"]
        franja = request.args.get("franja", "")
        orden = request.args.get("orden", "distancia")
        requisitos = [r for r in request.args.getlist("req") if r in CARACTERISTICAS]
        lat, lon = coordenada(request.args.get("lat"), 90), coordenada(request.args.get("lon"), 180)
        if lat is None or lon is None:
            lat = lon = None
        resultados, inferidos = buscar_clinicas(get_db(), tipo, necesidad, cp, franja, requisitos, orden,
                                                lat, lon)
        puntos = []
        for r in resultados:
            c = r["clinica"]
            if c["lat"] is None:
                continue
            s = r["servicio_sugerido"] or (r["servicios"][0] if r["servicios"] else None)
            puntos.append({
                "nombre": c["nombre"], "lat": c["lat"], "lon": c["lon"], "color": c["color"],
                "tipo": TIPOS[c["tipo"]][0], "distancia": r["distancia_texto"],
                "proximo": r["proximos"][0]["texto"] if r["proximos"] else "Sin huecos esta semana",
                "url": url_for("clinica", cid=c["id"], servicio=s["id"] if s else None),
            })
        return render_template("buscar.html", resultados=resultados, inferidos=inferidos, tipo=tipo,
                               necesidad=necesidad, cp=cp, franja=franja, orden=orden,
                               requisitos=requisitos, cp_ok=cp_valido(cp), lat=lat, lon=lon,
                               puntos=puntos)

    @app.route("/clinica/<int:cid>")
    def clinica(cid):
        c = una("SELECT * FROM clinicas WHERE id = ?", cid)
        if not c or (not c["activa"] and not (g.clinica and g.clinica["id"] == cid)):
            abort(404)
        servicios = todas("SELECT * FROM servicios WHERE clinica_id = ? ORDER BY nombre", cid)
        sid = request.args.get("servicio", type=int)
        servicio = next((s for s in servicios if s["id"] == sid), None)
        if servicio is None and len(servicios) == 1:
            servicio = servicios[0]
        semana = max(0, min(request.args.get("semana", 0, type=int), 7))
        desde = ahora().date() + timedelta(days=7 * semana)
        if c["modo"] == "franjas":
            huecos = cupos_libres(get_db(), c, desde=desde)
        else:
            huecos = huecos_libres(get_db(), c, servicio["duracion"] if servicio else None, desde=desde)
        horario = {}
        for h in todas("SELECT * FROM horarios WHERE clinica_id = ? ORDER BY dia_semana, inicio", cid):
            horario.setdefault(h["dia_semana"], []).append(f"{h['inicio']}–{h['fin']}")
        valoraciones = todas(
            "SELECT v.*, u.nombre FROM valoraciones v JOIN usuarios u ON u.id = v.paciente_id "
            "WHERE v.clinica_id = ? ORDER BY v.creado DESC LIMIT 6", cid)
        media = una("SELECT AVG(puntuacion) m, COUNT(*) n FROM valoraciones WHERE clinica_id = ?", cid)
        dist_texto = ""
        if g.usuario and g.usuario["rol"] == "paciente":
            dist_texto = distancia_cp(g.usuario["codigo_postal"], c["codigo_postal"])[1]
        # Cuenta la visita salvo que mire la propia clínica o administración.
        es_propia = (g.clinica and g.clinica["id"] == cid) or (g.usuario and g.usuario["rol"] == "admin")
        if not es_propia and semana == 0 and not request.args.get("servicio"):
            registrar_evento(get_db(), cid, "vista", g.usuario["id"] if g.usuario else None)
        return render_template("clinica.html", c=c, servicios=servicios, servicio=servicio, huecos=huecos,
                               semana=semana, horario=horario, valoraciones=valoraciones, media=media,
                               caract=set(filter(None, c["caracteristicas"].split(","))),
                               distancia=dist_texto)

    @app.route("/clinica/<int:cid>/evento", methods=["POST"])
    def evento(cid):
        """Clic en llamar, cómo llegar o web (lo envía el navegador con sendBeacon)."""
        tipo = request.form.get("tipo")
        if tipo in TIPOS_EVENTO and tipo != "vista" and una("SELECT 1 FROM clinicas WHERE id = ?", cid):
            registrar_evento(get_db(), cid, tipo, g.usuario["id"] if g.usuario else None)
        return "", 204

    @app.route("/clinica/<int:cid>/reservar", methods=["GET", "POST"])
    @requiere("paciente")
    def reservar(cid):
        c = una("SELECT * FROM clinicas WHERE id = ? AND activa = 1", cid)
        if not c:
            abort(404)
        datos = request.form if request.method == "POST" else request.args
        servicio = una("SELECT * FROM servicios WHERE id = ? AND clinica_id = ?",
                       datos.get("servicio", type=int), cid)
        por_franja = c["modo"] == "franjas"
        try:
            fecha = date.fromisoformat(datos.get("fecha", ""))
            if por_franja:
                franja, hora = datos.get("franja", ""), ""
                if franja not in FRANJAS:
                    raise ValueError
            else:
                hora = a_hhmm(a_minutos(datos.get("hora", "")))
                franja = franja_de(hora)
        except (ValueError, AttributeError):
            flash("Elige un día y una " + ("franja" if por_franja else "hora") + " de la lista.", "error")
            return redirect(url_for("clinica", cid=cid))
        if not servicio:
            flash("Elige primero el servicio que necesitas.", "error")
            return redirect(url_for("clinica", cid=cid))
        libre = (cupo_disponible(get_db(), c, fecha, franja) if por_franja
                 else hueco_disponible(get_db(), c, fecha, hora, servicio["duracion"]))
        if not libre:
            flash("Ese hueco ya no está libre. Elige otro, por favor.", "error")
            return redirect(url_for("clinica", cid=cid, servicio=servicio["id"]))
        if request.method == "GET":
            datos_franja = cupos_libres(get_db(), c, desde=fecha, dias=1)[0][1][franja] if por_franja else None
            return render_template("reservar.html", c=c, servicio=servicio, fecha=fecha, hora=hora,
                                   franja=franja, datos_franja=datos_franja)

        preferencia = campo("preferencia", 5) if por_franja else ""
        estado = "confirmada" if c["confirmacion_automatica"] and not por_franja else "pendiente"
        db = get_db()
        db.execute(
            "INSERT INTO citas (clinica_id, paciente_id, servicio_id, fecha, hora, duracion, estado, "
            "mensaje_paciente, llamar_antes, franja, preferencia, creado) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (cid, g.usuario["id"], servicio["id"], fecha.isoformat(), hora, servicio["duracion"], estado,
             campo("mensaje", 1000), 1 if request.form.get("llamar_antes") else 0, franja, preferencia,
             ahora().isoformat()))
        db.commit()
        if estado == "confirmada":
            flash(f"¡Cita confirmada! {fecha_bonita(fecha)} a las {hora} en {c['nombre']}.", "ok")
        elif por_franja:
            flash(f"Solicitud enviada. {c['nombre']} te confirmará la hora exacta del {fecha_bonita(fecha)} "
                  f"por la {FRANJAS[franja][0].lower()}.", "ok")
        else:
            flash(f"Solicitud enviada. {c['nombre']} te confirmará la cita del {fecha_bonita(fecha)} "
                  f"a las {hora}.", "ok")
        return redirect(url_for("mi_panel"))

    @app.route("/clinica/<int:cid>/mensaje", methods=["POST"])
    @requiere("paciente")
    def dejar_mensaje(cid):
        c = una("SELECT * FROM clinicas WHERE id = ? AND activa = 1", cid)
        if not c:
            abort(404)
        texto = campo("texto", 1500)
        tipo = request.form.get("tipo") if request.form.get("tipo") in ("llamada", "consulta") else "consulta"
        if not texto:
            flash("Escribe brevemente qué necesitas.", "error")
            return redirect(url_for("clinica", cid=cid) + "#mensaje")
        db = get_db()
        db.execute("INSERT INTO mensajes (clinica_id, paciente_id, tipo, franja, texto, creado) "
                   "VALUES (?, ?, ?, ?, ?, ?)",
                   (cid, g.usuario["id"], tipo, campo("franja", 50), texto, ahora().isoformat()))
        db.commit()
        flash("Mensaje enviado. " + ("Te llamarán en la franja que has indicado." if tipo == "llamada"
                                     else "Verás la respuesta en tu panel."), "ok")
        return redirect(url_for("mi_panel"))

    @app.route("/subidas/<path:nombre>")
    def subida(nombre):
        return send_from_directory(app.config["SUBIDAS"], nombre)

    # ---------------------------------------------------------------- cuentas

    @app.route("/registro", methods=["GET", "POST"])
    def registro():
        if request.method == "POST":
            email, clave = campo("email", 200).lower(), request.form.get("clave", "")
            nombre, cp, tel = campo("nombre", 120), campo("codigo_postal", 5), campo("telefono", 30)
            errores = validar_cuenta(email, clave, nombre, cp)
            if not tel:
                errores.append("Deja un teléfono: la clínica lo necesita para confirmar o avisarte.")
            if not request.form.get("acepto"):
                errores.append("Debes aceptar que la clínica vea tus datos de contacto.")
            if not errores:
                db = get_db()
                cur = db.execute("INSERT INTO usuarios (email, clave, rol, nombre, telefono, codigo_postal, creado) "
                                 "VALUES (?, ?, 'paciente', ?, ?, ?, ?)",
                                 (email, generate_password_hash(clave), nombre, tel, cp, ahora().isoformat()))
                db.commit()
                iniciar_sesion(cur.lastrowid)
                flash(f"¡Bienvenido/a, {nombre}! Ya puedes buscar clínicas y pedir cita.", "ok")
                return redirect(destino_seguro(request.form.get("siguiente")) or url_for("inicio"))
            for e in errores:
                flash(e, "error")
        return render_template("registro.html", siguiente=destino_seguro(request.values.get("siguiente")))

    @app.route("/registro/clinica", methods=["GET", "POST"])
    def registro_clinica():
        if request.method == "POST":
            email, clave = campo("email", 200).lower(), request.form.get("clave", "")
            nombre, cp = campo("nombre", 120), campo("codigo_postal", 5)
            responsable, tipo, tel = campo("responsable", 120), request.form.get("tipo", ""), campo("telefono", 30)
            errores = validar_cuenta(email, clave, nombre, cp)
            if tipo not in TIPOS:
                errores.append("Elige el tipo de clínica.")
            if not tel:
                errores.append("El teléfono es obligatorio: los pacientes podrán llamarte desde tu ficha.")
            if not errores:
                db = get_db()
                cur = db.execute("INSERT INTO usuarios (email, clave, rol, nombre, telefono, codigo_postal, creado) "
                                 "VALUES (?, ?, 'clinica', ?, ?, ?, ?)",
                                 (email, generate_password_hash(clave), responsable or nombre, tel, cp,
                                  ahora().isoformat()))
                uid = cur.lastrowid
                cur = db.execute("INSERT INTO clinicas (usuario_id, nombre, tipo, codigo_postal, telefono, "
                                 "direccion, ciudad, color, creado, modo) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'franjas')",
                                 (uid, nombre, tipo, cp, tel, campo("direccion", 200), campo("ciudad", 80),
                                  secrets.choice(COLORES), ahora().isoformat()))
                horario_por_defecto(db, cur.lastrowid)
                db.commit()
                iniciar_sesion(uid)
                flash("Clínica creada con un horario de ejemplo (L-V 9-14 y 16-20). Completa tu ficha, añade "
                      "servicios y publica tus huecos de la semana para aparecer en las búsquedas.", "ok")
                return redirect(url_for("panel_perfil"))
            for e in errores:
                flash(e, "error")
        return render_template("registro_clinica.html")

    @app.route("/entrar", methods=["GET", "POST"])
    def entrar():
        siguiente = destino_seguro(request.values.get("siguiente"))
        if request.method == "POST":
            u = una("SELECT * FROM usuarios WHERE email = ?", campo("email", 200).lower())
            if u and check_password_hash(u["clave"], request.form.get("clave", "")):
                iniciar_sesion(u["id"])
                destino = siguiente or url_for({"clinica": "panel", "admin": "admin"}.get(u["rol"], "inicio"))
                return redirect(destino)
            flash("Email o contraseña incorrectos.", "error")
        return render_template("entrar.html", siguiente=siguiente)

    @app.route("/salir", methods=["POST"])
    def salir():
        session.clear()
        flash("Has cerrado sesión.", "info")
        return redirect(url_for("inicio"))

    # ---------------------------------------------------------------- paciente

    @app.route("/mi")
    @requiere("paciente")
    def mi_panel():
        uid = g.usuario["id"]
        citas = todas(
            "SELECT ci.*, cl.nombre clinica, cl.telefono tel_clinica, cl.color, cl.tipo, s.nombre servicio, "
            "v.puntuacion FROM citas ci JOIN clinicas cl ON cl.id = ci.clinica_id "
            "LEFT JOIN servicios s ON s.id = ci.servicio_id LEFT JOIN valoraciones v ON v.cita_id = ci.id "
            "WHERE ci.paciente_id = ? ORDER BY ci.fecha, ci.hora", uid)
        hoy = ahora().strftime("%Y-%m-%d %H:%M")
        proximas = [c for c in citas if f"{c['fecha']} {c['hora'] or '23:59'}" >= hoy
                    and c["estado"] in ESTADOS_OCUPAN]
        historial = [c for c in citas if c not in proximas][::-1]
        mensajes = todas("SELECT m.*, cl.nombre clinica, cl.telefono tel_clinica FROM mensajes m "
                         "JOIN clinicas cl ON cl.id = m.clinica_id WHERE m.paciente_id = ? "
                         "ORDER BY m.creado DESC", uid)
        novedades = {c["id"] for c in citas if not c["visto_paciente"]}
        mensajes_nuevos = {m["id"] for m in mensajes if not m["visto_paciente"]}
        db = get_db()
        db.execute("UPDATE citas SET visto_paciente = 1 WHERE paciente_id = ?", (uid,))
        db.execute("UPDATE mensajes SET visto_paciente = 1 WHERE paciente_id = ?", (uid,))
        db.commit()
        return render_template("mi_panel.html", proximas=proximas, historial=historial, mensajes=mensajes,
                               novedades=novedades, mensajes_nuevos=mensajes_nuevos, hoy=hoy)

    @app.route("/mi/cita/<int:id>/cancelar", methods=["POST"])
    @requiere("paciente")
    def cancelar_cita(id):
        c = una("SELECT * FROM citas WHERE id = ? AND paciente_id = ?", id, g.usuario["id"])
        if not c or c["estado"] not in ESTADOS_OCUPAN:
            abort(404)
        db = get_db()
        db.execute("UPDATE citas SET estado = 'cancelada', mensaje_paciente = mensaje_paciente || ? WHERE id = ?",
                   ("\n[Cancelada por el paciente] " + campo("motivo", 300), id))
        db.commit()
        flash("Cita cancelada. El hueco queda libre para otra persona.", "info")
        return redirect(url_for("mi_panel"))

    @app.route("/mi/cita/<int:id>/valorar", methods=["POST"])
    @requiere("paciente")
    def valorar_cita(id):
        c = una("SELECT * FROM citas WHERE id = ? AND paciente_id = ?", id, g.usuario["id"])
        if not c or not puede_valorarse(c):
            abort(404)
        puntos = request.form.get("puntuacion", type=int)
        if puntos not in range(1, 6):
            flash("Elige de 1 a 5 estrellas.", "error")
            return redirect(url_for("mi_panel"))
        db = get_db()
        db.execute("INSERT OR IGNORE INTO valoraciones (cita_id, clinica_id, paciente_id, puntuacion, comentario, "
                   "creado) VALUES (?, ?, ?, ?, ?, ?)",
                   (id, c["clinica_id"], g.usuario["id"], puntos, campo("comentario", 600), ahora().isoformat()))
        db.commit()
        flash("¡Gracias por tu valoración!", "ok")
        return redirect(url_for("mi_panel"))

    @app.route("/mi/perfil", methods=["GET", "POST"])
    @requiere("paciente")
    def mi_perfil():
        if request.method == "POST":
            nombre, tel, cp = campo("nombre", 120), campo("telefono", 30), campo("codigo_postal", 5)
            if not nombre or not tel or not cp_valido(cp):
                flash("Nombre, teléfono y un código postal válido son obligatorios.", "error")
            else:
                db = get_db()
                db.execute("UPDATE usuarios SET nombre = ?, telefono = ?, codigo_postal = ? WHERE id = ?",
                           (nombre, tel, cp, g.usuario["id"]))
                db.commit()
                flash("Perfil guardado.", "ok")
                return redirect(url_for("mi_perfil"))
        return render_template("mi_perfil.html")

    # ---------------------------------------------------------------- clínica

    @app.route("/panel")
    @requiere("clinica")
    def panel():
        cid = g.clinica["id"]
        hoy = ahora().date()
        pendientes = todas(
            "SELECT ci.*, u.nombre paciente, u.telefono, u.email, s.nombre servicio FROM citas ci "
            "JOIN usuarios u ON u.id = ci.paciente_id LEFT JOIN servicios s ON s.id = ci.servicio_id "
            "WHERE ci.clinica_id = ? AND ci.estado = 'pendiente' ORDER BY ci.fecha, ci.hora", cid)
        agenda = todas(
            "SELECT ci.*, u.nombre paciente, u.telefono, s.nombre servicio FROM citas ci "
            "JOIN usuarios u ON u.id = ci.paciente_id LEFT JOIN servicios s ON s.id = ci.servicio_id "
            "WHERE ci.clinica_id = ? AND ci.estado = 'confirmada' AND ci.fecha >= ? AND ci.fecha < ? "
            "ORDER BY ci.fecha, ci.hora", cid, hoy.isoformat(), (hoy + timedelta(days=14)).isoformat())
        por_completar = todas(
            "SELECT ci.*, u.nombre paciente, s.nombre servicio FROM citas ci "
            "JOIN usuarios u ON u.id = ci.paciente_id LEFT JOIN servicios s ON s.id = ci.servicio_id "
            "WHERE ci.clinica_id = ? AND ci.estado = 'confirmada' AND ci.fecha < ? ORDER BY ci.fecha DESC",
            cid, hoy.isoformat())
        mensajes = todas(
            "SELECT m.*, u.nombre paciente, u.telefono, u.email FROM mensajes m "
            "JOIN usuarios u ON u.id = m.paciente_id WHERE m.clinica_id = ? "
            "ORDER BY m.estado = 'nuevo' DESC, m.creado DESC LIMIT 30", cid)
        dias_agenda = {}
        for a in agenda:
            dias_agenda.setdefault(a["fecha"], []).append(a)
        if g.clinica["modo"] == "franjas":
            semana = cupos_libres(get_db(), g.clinica)
            libres = sum(f["libres"] for _, fr in semana for f in fr.values())
        else:
            libres = sum(len(h) for _, h in huecos_libres(get_db(), g.clinica))
        faltan = []
        if g.clinica["modo"] == "franjas" and not libres:
            faltan.append(("Publica tus huecos de esta semana", url_for("panel_huecos")))
        if not una("SELECT 1 FROM servicios WHERE clinica_id = ?", cid):
            faltan.append(("Añade al menos un servicio", url_for("panel_servicios")))
        if not g.clinica["descripcion"]:
            faltan.append(("Escribe una descripción de tu clínica", url_for("panel_perfil")))
        if not g.clinica["foto"]:
            faltan.append(("Sube una foto", url_for("panel_perfil")))
        if g.clinica["lat"] is None:
            faltan.append(("Sitúa tu clínica en el mapa", url_for("panel_perfil") + "#mapa"))
        desde, hasta = rango_mes("")
        rendimiento = resumen_clinica(get_db(), g.clinica, desde, hasta)
        return render_template("panel.html", pendientes=pendientes, dias_agenda=dias_agenda,
                               por_completar=por_completar, mensajes=mensajes, libres=libres, faltan=faltan,
                               rendimiento=rendimiento, mes=MESES_LARGOS[desde.month - 1])

    @app.route("/panel/cita/<int:id>/<accion>", methods=["POST"])
    @requiere("clinica")
    def accion_cita(id, accion):
        c = una("SELECT * FROM citas WHERE id = ? AND clinica_id = ?", id, g.clinica["id"])
        transiciones = {
            "confirmar": (("pendiente",), "confirmada"),
            "rechazar": (("pendiente",), "rechazada"),
            "cancelar": (("confirmada",), "cancelada"),
            "completar": (("confirmada",), "completada"),
        }
        if not c or accion not in transiciones or c["estado"] not in transiciones[accion][0]:
            abort(404)
        respuesta = campo("respuesta", 800)
        hora = c["hora"]
        if accion == "confirmar" and not hora:
            # Solicitud por franja: la clínica fija la hora al confirmar.
            try:
                hora = a_hhmm(a_minutos(campo("hora", 5)))
            except (ValueError, IndexError):
                flash("Indica la hora de la cita para confirmarla.", "error")
                return redirect(url_for("panel"))
        db = get_db()
        ya_paciente = 1 if request.form.get("ya_paciente") else c["ya_paciente"]
        db.execute("UPDATE citas SET estado = ?, respuesta_clinica = ?, visto_paciente = 0, ya_paciente = ?, "
                   "hora = ? WHERE id = ?",
                   (transiciones[accion][1], respuesta or c["respuesta_clinica"], ya_paciente, hora, id))
        db.commit()
        flash({"confirmar": "Cita confirmada.", "rechazar": "Solicitud rechazada; el paciente lo verá en su panel.",
               "cancelar": "Cita cancelada y paciente avisado en su panel.",
               "completar": "Cita marcada como realizada."}[accion], "ok")
        return redirect(url_for("panel"))

    @app.route("/panel/mensaje/<int:id>", methods=["POST"])
    @requiere("clinica")
    def responder_mensaje(id):
        m = una("SELECT * FROM mensajes WHERE id = ? AND clinica_id = ?", id, g.clinica["id"])
        if not m:
            abort(404)
        db = get_db()
        db.execute("UPDATE mensajes SET respuesta = ?, estado = 'respondido', visto_paciente = 0 WHERE id = ?",
                   (campo("respuesta", 1500) or "Atendido por teléfono.", id))
        db.commit()
        flash("Mensaje marcado como atendido.", "ok")
        return redirect(url_for("panel") + "#mensajes")

    @app.route("/panel/perfil", methods=["GET", "POST"])
    @requiere("clinica")
    def panel_perfil():
        if request.method == "POST":
            c = g.clinica
            nombre, cp, tipo = campo("nombre", 120), campo("codigo_postal", 5), request.form.get("tipo", "")
            color = request.form.get("color", "")
            if not nombre or not cp_valido(cp) or tipo not in TIPOS:
                flash("Nombre, tipo y código postal válido son obligatorios.", "error")
                return redirect(url_for("panel_perfil"))
            if not (len(color) == 7 and color.startswith("#")
                    and all(ch in "0123456789abcdefABCDEF" for ch in color[1:])):
                color = c["color"]
            foto = guardar_foto(request.files.get("foto"), f"clinica{c['id']}") or c["foto"]
            if request.form.get("quitar_foto"):
                foto = ""
            caract = ",".join(k for k in CARACTERISTICAS if request.form.get("c_" + k))
            duracion = request.form.get("duracion_hueco", type=int)
            duracion = duracion if duracion in (15, 20, 30, 45, 60) else c["duracion_hueco"]
            lat, lon = coordenada(request.form.get("lat"), 90), coordenada(request.form.get("lon"), 180)
            if lat is None or lon is None:
                lat, lon = c["lat"], c["lon"]
            db = get_db()
            db.execute(
                "UPDATE clinicas SET nombre=?, tipo=?, eslogan=?, descripcion=?, direccion=?, ciudad=?, "
                "codigo_postal=?, telefono=?, web=?, foto=?, color=?, caracteristicas=?, duracion_hueco=?, "
                "confirmacion_automatica=?, activa=?, lat=?, lon=?, modo=? WHERE id=?",
                (nombre, tipo, campo("eslogan", 140), campo("descripcion", 3000), campo("direccion", 200),
                 campo("ciudad", 80), cp, campo("telefono", 30), campo("web", 200), foto, color, caract,
                 duracion, 1 if request.form.get("confirmacion_automatica") else 0,
                 1 if request.form.get("activa") else 0, lat, lon,
                 request.form.get("modo") if request.form.get("modo") in MODOS else c["modo"], c["id"]))
            db.commit()
            flash("Ficha guardada.", "ok")
            return redirect(url_for("panel_perfil"))
        return render_template("panel_perfil.html", c=g.clinica,
                               caract=set(filter(None, g.clinica["caracteristicas"].split(","))))

    @app.route("/panel/huecos", methods=["GET", "POST"])
    @requiere("clinica")
    def panel_huecos():
        """Rejilla de dos semanas: cuántos huecos hay cada mañana y cada tarde."""
        c = g.clinica
        db = get_db()
        hoy = ahora().date()
        if request.method == "POST":
            if request.form.get("accion") == "copiar":
                # Repite en la semana siguiente lo publicado para los próximos 7 días.
                for r in db.execute("SELECT fecha, franja, plazas FROM cupos WHERE clinica_id = ? AND fecha >= ? "
                                    "AND fecha < ?", (c["id"], hoy.isoformat(),
                                                      (hoy + timedelta(days=7)).isoformat())).fetchall():
                    destino = (date.fromisoformat(r["fecha"]) + timedelta(days=7)).isoformat()
                    db.execute("INSERT INTO cupos (clinica_id, fecha, franja, plazas) VALUES (?, ?, ?, ?) "
                               "ON CONFLICT (clinica_id, fecha, franja) DO UPDATE SET plazas = excluded.plazas",
                               (c["id"], destino, r["franja"], r["plazas"]))
                flash("Copiado a la semana siguiente. Revisa y ajusta lo que cambie.", "ok")
            else:
                for n in range(14):
                    dia = (hoy + timedelta(days=n)).isoformat()
                    for f in FRANJAS:
                        valor = request.form.get(f"{dia}_{f}")
                        if valor is None:
                            continue
                        try:
                            plazas = max(0, min(int(valor or 0), 50))
                        except ValueError:
                            continue
                        db.execute("INSERT INTO cupos (clinica_id, fecha, franja, plazas) VALUES (?, ?, ?, ?) "
                                   "ON CONFLICT (clinica_id, fecha, franja) DO UPDATE SET plazas = excluded.plazas",
                                   (c["id"], dia, f, plazas))
                flash("Huecos publicados. Los pacientes ya los ven.", "ok")
            db.commit()
            return redirect(url_for("panel_huecos"))
        semanas = [cupos_libres(db, c, hoy, 7), cupos_libres(db, c, hoy + timedelta(days=7), 7)]
        return render_template("panel_huecos.html", semanas=semanas, hoy=hoy)

    @app.route("/panel/servicios", methods=["GET", "POST"])
    @requiere("clinica")
    def panel_servicios():
        cid = g.clinica["id"]
        if request.method == "POST":
            nombre = campo("nombre", 120)
            duracion = request.form.get("duracion", type=int)
            precio_txt = campo("precio", 12).replace(",", ".")
            try:
                precio = float(precio_txt) if precio_txt else None
            except ValueError:
                precio = None
            if not nombre or not duracion or not 5 <= duracion <= 480:
                flash("Indica nombre y duración (en minutos) del servicio.", "error")
            else:
                db = get_db()
                db.execute("INSERT INTO servicios (clinica_id, nombre, duracion, precio, descripcion) "
                           "VALUES (?, ?, ?, ?, ?)", (cid, nombre, duracion, precio, campo("descripcion", 400)))
                db.commit()
                flash("Servicio añadido.", "ok")
            return redirect(url_for("panel_servicios"))
        servicios = todas("SELECT * FROM servicios WHERE clinica_id = ? ORDER BY nombre", cid)
        return render_template("panel_servicios.html", servicios=servicios)

    @app.route("/panel/servicios/<int:id>/borrar", methods=["POST"])
    @requiere("clinica")
    def borrar_servicio(id):
        db = get_db()
        # Las citas antiguas conservan su duración; solo pierden el enlace al servicio.
        db.execute("UPDATE citas SET servicio_id = NULL WHERE servicio_id = ? AND clinica_id = ?",
                   (id, g.clinica["id"]))
        db.execute("DELETE FROM servicios WHERE id = ? AND clinica_id = ?", (id, g.clinica["id"]))
        db.commit()
        flash("Servicio eliminado.", "info")
        return redirect(url_for("panel_servicios"))

    @app.route("/panel/horario", methods=["GET", "POST"])
    @requiere("clinica")
    def panel_horario():
        cid = g.clinica["id"]
        db = get_db()
        if request.method == "POST":
            tramos, errores = [], []
            for dia in range(7):
                for n in (1, 2):
                    ini, fin = campo(f"d{dia}_ini{n}", 5), campo(f"d{dia}_fin{n}", 5)
                    if not ini and not fin:
                        continue
                    try:
                        if a_minutos(ini) >= a_minutos(fin):
                            raise ValueError
                        tramos.append((dia, a_hhmm(a_minutos(ini)), a_hhmm(a_minutos(fin))))
                    except (ValueError, IndexError):
                        errores.append(f"{DIAS[dia]}: el tramo {n} no es válido.")
            if errores:
                for e in errores:
                    flash(e, "error")
            else:
                db.execute("DELETE FROM horarios WHERE clinica_id = ?", (cid,))
                db.executemany("INSERT INTO horarios (clinica_id, dia_semana, inicio, fin) VALUES (?, ?, ?, ?)",
                               [(cid, *t) for t in tramos])
                db.commit()
                flash("Horario guardado.", "ok")
            return redirect(url_for("panel_horario"))
        horario = {}
        for h in todas("SELECT * FROM horarios WHERE clinica_id = ? ORDER BY dia_semana, inicio", cid):
            horario.setdefault(h["dia_semana"], []).append(h)
        bloqueos = todas("SELECT * FROM bloqueos WHERE clinica_id = ? AND fecha >= ? ORDER BY fecha, inicio",
                         cid, ahora().date().isoformat())
        return render_template("panel_horario.html", horario=horario, bloqueos=bloqueos,
                               hoy=ahora().date().isoformat())

    @app.route("/panel/bloqueos", methods=["POST"])
    @requiere("clinica")
    def nuevo_bloqueo():
        try:
            desde = date.fromisoformat(campo("desde", 10))
            hasta = date.fromisoformat(campo("hasta", 10) or campo("desde", 10))
        except ValueError:
            flash("Fecha no válida.", "error")
            return redirect(url_for("panel_horario"))
        ini, fin = campo("inicio", 5) or None, campo("fin", 5) or None
        if (ini or fin) and not (ini and fin and ini < fin):
            flash("Para bloquear solo unas horas indica inicio y fin; si no, se bloquea el día entero.", "error")
            return redirect(url_for("panel_horario"))
        if hasta < desde or (hasta - desde).days > 60:
            flash("El periodo debe ir hacia delante y durar como mucho 60 días.", "error")
            return redirect(url_for("panel_horario"))
        db = get_db()
        dia = desde
        while dia <= hasta:
            db.execute("INSERT INTO bloqueos (clinica_id, fecha, inicio, fin, motivo) VALUES (?, ?, ?, ?, ?)",
                       (g.clinica["id"], dia.isoformat(), ini, fin, campo("motivo", 120)))
            dia += timedelta(days=1)
        db.commit()
        flash("Bloqueo añadido: esos huecos ya no se ofrecen.", "ok")
        return redirect(url_for("panel_horario"))

    @app.route("/panel/bloqueos/<int:id>/borrar", methods=["POST"])
    @requiere("clinica")
    def borrar_bloqueo(id):
        db = get_db()
        db.execute("DELETE FROM bloqueos WHERE id = ? AND clinica_id = ?", (id, g.clinica["id"]))
        db.commit()
        return redirect(url_for("panel_horario"))

    # ---------------------------------------------------------------- administración

    def meses_disponibles():
        hoy = ahora().date().replace(day=1)
        meses = []
        for _ in range(12):
            meses.append((hoy.strftime("%Y-%m"), f"{MESES_LARGOS[hoy.month - 1]} {hoy.year}"))
            hoy = (hoy - timedelta(days=1)).replace(day=1)
        return meses

    @app.route("/admin")
    @requiere("admin")
    def admin():
        mes = request.args.get("mes", "")
        desde, hasta = rango_mes(mes)
        db = get_db()
        filas = [resumen_clinica(db, c, desde, hasta)
                 for c in db.execute("SELECT * FROM clinicas ORDER BY nombre")]
        filas.sort(key=lambda f: (-f["importe"], -f["nuevos"], f["clinica"]["nombre"]))
        rango = (desde.isoformat(), hasta.isoformat())
        totales = {
            "clinicas": sum(1 for f in filas if f["clinica"]["activa"]),
            "clinicas_nuevas": db.execute("SELECT COUNT(*) FROM clinicas WHERE creado >= ? AND creado < ?",
                                          rango).fetchone()[0],
            "pacientes": db.execute("SELECT COUNT(*) FROM usuarios WHERE rol = 'paciente'").fetchone()[0],
            "pacientes_nuevos": db.execute("SELECT COUNT(*) FROM usuarios WHERE rol = 'paciente' AND creado >= ? "
                                           "AND creado < ?", rango).fetchone()[0],
            **{k: sum(f[k] for f in filas) for k in ("vistas", "llamadas", "mensajes", "solicitudes", "nuevos",
                                                      "facturables", "importe")},
        }
        sin_actividad = [f for f in filas if f["clinica"]["activa"] and not f["vistas"] and not f["solicitudes"]]
        return render_template("admin.html", filas=filas, totales=totales, mes=desde.strftime("%Y-%m"),
                               meses=meses_disponibles(), titulo_mes=f"{MESES_LARGOS[desde.month - 1]} {desde.year}",
                               tarifa_general=TARIFA_POR_DEFECTO, sin_actividad=sin_actividad)

    @app.route("/admin/clinica/<int:cid>", methods=["GET", "POST"])
    @requiere("admin")
    def admin_clinica(cid):
        db = get_db()
        c = una("SELECT * FROM clinicas WHERE id = ?", cid)
        if not c:
            abort(404)
        mes = request.values.get("mes", "")
        if request.method == "POST":
            def importe_o_nada(nombre):
                texto = campo(nombre, 12).replace(",", ".")
                try:
                    return max(0.0, float(texto)) if texto else None
                except ValueError:
                    return None
            db.execute("UPDATE clinicas SET tarifa = ?, tope_mensual = ?, activa = ? WHERE id = ?",
                       (importe_o_nada("tarifa"), importe_o_nada("tope_mensual"),
                        1 if request.form.get("activa") else 0, cid))
            db.commit()
            flash("Condiciones de la clínica guardadas.", "ok")
            return redirect(url_for("admin_clinica", cid=cid, mes=mes))
        desde, hasta = rango_mes(mes)
        resumen = resumen_clinica(db, c, desde, hasta)
        responsable = una("SELECT * FROM usuarios WHERE id = ?", c["usuario_id"])
        return render_template("admin_clinica.html", c=c, r=resumen, responsable=responsable,
                               mes=desde.strftime("%Y-%m"), meses=meses_disponibles(),
                               titulo_mes=f"{MESES_LARGOS[desde.month - 1]} {desde.year}",
                               tarifa_general=TARIFA_POR_DEFECTO)

    @app.route("/admin/captaciones.csv")
    @requiere("admin")
    def admin_csv():
        desde, hasta = rango_mes(request.args.get("mes", ""))
        db = get_db()
        salida = io.StringIO()
        w = csv.writer(salida, delimiter=";")
        w.writerow(["clinica", "fecha", "hora", "paciente", "email", "servicio", "estado", "facturable"])
        for n in captaciones(db, desde, hasta):
            w.writerow([n["clinica"], n["fecha"], n["hora"], n["paciente"], n["email"], n["servicio"] or "",
                        n["estado"], "no (ya era paciente)" if n["ya_paciente"] else "sí"])
        nombre = f"captaciones-{desde.strftime('%Y-%m')}.csv"
        # BOM para que Excel abra bien los acentos.
        return app.response_class("\ufeff" + salida.getvalue(), mimetype="text/csv",
                                  headers={"Content-Disposition": f"attachment; filename={nombre}"})

    @app.errorhandler(404)
    def no_encontrado(_):
        return render_template("error.html", titulo="No encontrado",
                               texto="Esa página no existe o ya no está disponible."), 404

    @app.errorhandler(400)
    def peticion_mala(e):
        return render_template("error.html", titulo="No se pudo procesar", texto=e.description), 400

    @app.errorhandler(413)
    def demasiado_grande(_):
        return render_template("error.html", titulo="Archivo demasiado grande",
                               texto="La foto no puede superar 4 MB."), 413


def puede_valorarse(cita):
    if cita["estado"] == "completada":
        return True
    return (cita["estado"] == "confirmada"
            and f"{cita['fecha']} {cita['hora']}" < ahora().strftime("%Y-%m-%d %H:%M"))


if __name__ == "__main__":
    if "--demo" in sys.argv:
        from datos_demo import sembrar
        ruta = os.environ.get("CITAS_BD", str(BASE / "datos" / "citas.db"))
        sembrar(ruta, borrar=True)
        print("Base de datos de demostración creada. Cuentas en README.md (clave: demo1234).")
    app = crear_app()
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 5000)),
            debug=os.environ.get("DEBUG") == "1")
