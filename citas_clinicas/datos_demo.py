"""Datos de demostración: cuatro clínicas de tipos distintos, un paciente y citas.

    python datos_demo.py          # recrea datos/citas.db
Todas las cuentas usan la contraseña demo1234.
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from werkzeug.security import generate_password_hash

from app import BASE, iniciar_bd

CLAVE = "demo1234"

CLINICAS = [
    {
        "email": "podologia@demo.es", "responsable": "Laura Martín",
        "nombre": "Podología Pasos", "tipo": "podologia", "color": "#2a9d8f",
        "eslogan": "Tus pies, en manos expertas desde 2009",
        "descripcion": "Clínica podológica con estudio biomecánico de la pisada por vídeo, "
                       "tratamiento de uña encarnada sin dolor y plantillas a medida fabricadas en "
                       "nuestro propio taller. Atendemos a deportistas, personas mayores y pie diabético.",
        "direccion": "Calle de Fuencarral 112", "ciudad": "Madrid", "cp": "28010", "tel": "910000101",
        "lat": 40.4316, "lon": -3.7022,
        "web": "", "caract": "accesible,tarjeta,seguros", "hueco": 15, "auto": 0,
        "modo": "franjas", "cupos": [(3, 2), (2, 1), (4, 2), (1, 3), (3, 0)],  # (mañana, tarde) de lunes a viernes
        "horario": {d: [("09:00", "14:00"), ("16:00", "20:00")] for d in range(5)},
        "servicios": [
            ("Quiropodia (durezas, callos y uñas)", 30, 35, "Limpieza completa del pie."),
            ("Uña encarnada", 45, 50, "Tratamiento conservador o cirugía ungueal con anestesia local."),
            ("Estudio biomecánico de la pisada", 60, 70, "Análisis en cinta con vídeo y plataforma de presiones."),
            ("Plantillas personalizadas (toma de medidas)", 30, 40, "Precio de la consulta; plantillas aparte."),
            ("Pie diabético: revisión", 30, 30, "Exploración vascular y neurológica."),
        ],
    },
    {
        "email": "masaje@demo.es", "responsable": "Iker Etxeberria",
        "nombre": "Manos en Calma", "tipo": "masaje", "color": "#6a4c93",
        "eslogan": "Quiromasaje y masaje terapéutico, también a domicilio",
        "descripcion": "Centro de quiromasaje con cabinas tranquilas y música suave. Masaje "
                       "descontracturante para espalda y cervicales, relajante para el estrés, drenaje "
                       "linfático y masaje deportivo antes o después de competir. Confirmamos al instante.",
        "direccion": "Calle de Alcalá 45", "ciudad": "Madrid", "cp": "28014", "tel": "910000202",
        "lat": 40.4189, "lon": -3.6968,
        "web": "", "caract": "domicilio,tarjeta,ingles", "hueco": 30, "auto": 1, "modo": "agenda",
        "horario": {**{d: [("10:00", "14:00"), ("16:00", "21:00")] for d in range(5)}, 5: [("10:00", "14:00")]},
        "servicios": [
            ("Masaje descontracturante de espalda", 60, 45, "Espalda, cervicales y hombros."),
            ("Masaje relajante", 60, 40, "Para reducir estrés y tensión."),
            ("Drenaje linfático manual", 45, 40, "Piernas cansadas y retención de líquidos."),
            ("Masaje deportivo", 30, 30, "Precompetición o recuperación."),
        ],
    },
    {
        "email": "dental@demo.es", "responsable": "Dra. Carmen Ruiz",
        "nombre": "Clínica Dental Sonrisa Norte", "tipo": "odontologia", "color": "#1d70b8",
        "eslogan": "Odontología familiar con primera revisión gratuita",
        "descripcion": "Equipo de cinco odontólogos: odontología general, ortodoncia invisible, "
                       "implantes y odontopediatría. Reservamos huecos cada día para urgencias "
                       "(dolor de muelas, rotura de diente). Trabajamos con las principales aseguradoras.",
        "direccion": "Paseo de la Castellana 210", "ciudad": "Madrid", "cp": "28046", "tel": "910000303",
        "lat": 40.4639, "lon": -3.6898,
        "web": "", "caract": "accesible,parking,seguros,infantil,urgencias,tarjeta", "hueco": 30, "auto": 0,
        "modo": "franjas", "cupos": [(2, 3), (3, 2), (1, 1), (2, 2), (4, 0)],
        "horario": {d: [("09:00", "14:00"), ("15:30", "20:30")] for d in range(5)},
        "servicios": [
            ("Revisión y diagnóstico", 30, 0, "Primera visita gratuita con radiografía."),
            ("Limpieza dental", 45, 55, "Higiene bucodental completa."),
            ("Empaste", 45, 60, "Tratamiento de caries."),
            ("Urgencia dental", 30, 40, "Dolor de muelas, infección o diente roto."),
            ("Blanqueamiento", 90, 250, "Blanqueamiento en clínica."),
            ("Ortodoncia: primera consulta", 45, 0, "Estudio para ortodoncia invisible o brackets."),
        ],
    },
    {
        "email": "fisio@demo.es", "responsable": "Javier Ortega",
        "nombre": "FisioActiva Getafe", "tipo": "fisioterapia", "color": "#e76f51",
        "eslogan": "Recupera tu movimiento: lesiones, espalda y suelo pélvico",
        "descripcion": "Fisioterapia traumatológica y deportiva. Tratamos dolor de espalda, lumbalgia, "
                       "ciática, esguinces, tendinitis y rehabilitación tras cirugía de rodilla u hombro. "
                       "Unidad de suelo pélvico y punción seca. Sesiones individuales de verdad, sin aparatos "
                       "en cadena.",
        "direccion": "Calle Madrid 30", "ciudad": "Getafe", "cp": "28901", "tel": "910000404",
        "lat": 40.3082, "lon": -3.7318,
        "web": "", "caract": "accesible,parking,seguros,ingles", "hueco": 15, "auto": 0, "modo": "agenda",
        "horario": {**{d: [("08:00", "14:00"), ("16:00", "21:00")] for d in range(5)}, 5: [("09:00", "13:00")]},
        "servicios": [
            ("Sesión de fisioterapia", 45, 40, "Valoración y tratamiento manual."),
            ("Punción seca", 30, 35, "Para contracturas y puntos gatillo."),
            ("Rehabilitación de lesión deportiva", 60, 50, "Esguinces, roturas fibrilares, tendinitis."),
            ("Suelo pélvico", 60, 55, "Posparto, incontinencia y dolor pélvico."),
        ],
    },
]

ADMIN = {"email": "admin@demo.es", "nombre": "Administración"}

PACIENTE = {"email": "paciente@demo.es", "nombre": "Ana López", "tel": "600000001", "cp": "28010"}

# Pacientes ficticios para que las agendas no estén vacías.
OTROS = [("lucia@demo.es", "Lucía Gómez", "600000002", "28015"),
         ("pablo@demo.es", "Pablo Sanz", "600000003", "28029"),
         ("marta@demo.es", "Marta Díaz", "600000004", "28901")]


def proximo_laborable(desde, n):
    """El n-ésimo día laborable (L-V) a partir de mañana."""
    dia = desde
    while n > 0:
        dia += timedelta(days=1)
        if dia.weekday() < 5:
            n -= 1
    return dia


def sembrar(ruta, borrar=False):
    ruta = Path(ruta)
    if borrar and ruta.exists():
        ruta.unlink()
    db = iniciar_bd(ruta)
    ahora = datetime.now()
    hoy = ahora.date()
    hash_clave = generate_password_hash(CLAVE)

    def usuario(email, rol, nombre, tel, cp):
        return db.execute("INSERT INTO usuarios (email, clave, rol, nombre, telefono, codigo_postal, creado) "
                          "VALUES (?, ?, ?, ?, ?, ?, ?)",
                          (email, hash_clave, rol, nombre, tel, cp, ahora.isoformat())).lastrowid

    clinicas = []
    for c in CLINICAS:
        uid = usuario(c["email"], "clinica", c["responsable"], c["tel"], c["cp"])
        cid = db.execute(
            "INSERT INTO clinicas (usuario_id, nombre, tipo, eslogan, descripcion, direccion, ciudad, "
            "codigo_postal, telefono, web, color, caracteristicas, duracion_hueco, confirmacion_automatica, "
            "lat, lon, creado, modo) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (uid, c["nombre"], c["tipo"], c["eslogan"], c["descripcion"], c["direccion"], c["ciudad"], c["cp"],
             c["tel"], c["web"], c["color"], c["caract"], c["hueco"], c["auto"], c["lat"], c["lon"],
             (ahora - timedelta(days=60)).isoformat(), c["modo"])).lastrowid
        # Huecos publicados por franja para las dos próximas semanas (días laborables).
        # Desde el lunes de esta semana. La clínica dental solo ha publicado esta semana:
        # así aparece en el recordatorio semanal.
        lunes = hoy - timedelta(days=hoy.weekday())
        for n in range(21 if c["email"] != "dental@demo.es" else 7):
            dia = lunes + timedelta(days=n)
            if c.get("cupos") and dia.weekday() < 5:
                for franja, plazas in zip(("manana", "tarde"), c["cupos"][dia.weekday()]):
                    db.execute("INSERT INTO cupos (clinica_id, fecha, franja, plazas) VALUES (?, ?, ?, ?)",
                               (cid, dia.isoformat(), franja, plazas))
        for dia, tramos in c["horario"].items():
            for ini, fin in tramos:
                db.execute("INSERT INTO horarios (clinica_id, dia_semana, inicio, fin) VALUES (?, ?, ?, ?)",
                           (cid, dia, ini, fin))
        servicios = [db.execute("INSERT INTO servicios (clinica_id, nombre, duracion, precio, descripcion) "
                                "VALUES (?, ?, ?, ?, ?)", (cid, *s)).lastrowid for s in c["servicios"]]
        clinicas.append((cid, servicios, c))

    usuario(ADMIN["email"], "admin", ADMIN["nombre"], "", "")
    ana = usuario(PACIENTE["email"], "paciente", PACIENTE["nombre"], PACIENTE["tel"], PACIENTE["cp"])
    otros = [usuario(e, "paciente", n, t, cp) for e, n, t, cp in OTROS]

    def cita(cid, pid, sid, dia, hora, estado, mensaje="", respuesta="", visto=1, franja="", preferencia=""):
        """Con hora: cita de agenda exacta. Sin hora: solicitud por franja pendiente de hora."""
        franja = franja or ("manana" if hora < "14:00" else "tarde")
        dur = db.execute("SELECT duracion FROM servicios WHERE id = ?", (sid,)).fetchone()[0]
        return db.execute(
            "INSERT INTO citas (clinica_id, paciente_id, servicio_id, fecha, hora, duracion, estado, "
            "mensaje_paciente, respuesta_clinica, visto_paciente, franja, preferencia, creado) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (cid, pid, sid, dia.isoformat(), hora, dur, estado, mensaje, respuesta, visto, franja, preferencia,
             (ahora - timedelta(days=1)).isoformat())).lastrowid

    (pod, pod_s, _), (mas, mas_s, _), (den, den_s, _), (fis, fis_s, _) = clinicas
    d1, d2, d3 = (proximo_laborable(hoy, n) for n in (1, 2, 3))

    # Ana: una cita confirmada, una pendiente y una pasada para poder valorarla.
    cita(den, ana, den_s[1], d2, "10:00", "confirmada", "Hace un año de la última limpieza.",
         "¡Perfecto, te esperamos!", visto=0)
    cita(pod, ana, pod_s[1], d3, "", "pendiente", "Me duele bastante el dedo gordo del pie derecho.",
         franja="tarde", preferencia="17:00")
    pasada = cita(fis, ana, fis_s[0], hoy - timedelta(days=9), "18:00", "completada")
    db.execute("INSERT INTO valoraciones (cita_id, clinica_id, paciente_id, puntuacion, comentario, creado) "
               "VALUES (?, ?, ?, 5, 'Me quitaron el dolor lumbar en dos sesiones.', ?)",
               (pasada, fis, ana, ahora.isoformat()))
    cita(mas, ana, mas_s[0], hoy - timedelta(days=4), "19:00", "confirmada")  # pasada, sin valorar

    # Ocupación y solicitudes de otros pacientes.
    lucia, pablo, marta = otros
    cita(pod, lucia, pod_s[0], d1, "", "pendiente", "¿Atendéis a personas con diabetes?", franja="manana")
    cita(pod, pablo, pod_s[2], d1, "10:00", "confirmada")
    cita(pod, marta, pod_s[0], d2, "16:30", "confirmada")
    cita(mas, lucia, mas_s[1], d1, "18:00", "confirmada")
    cita(mas, pablo, mas_s[0], d2, "17:00", "confirmada")
    cita(den, marta, den_s[3], d1, "", "pendiente", "Me duele una muela desde ayer, ¿podéis antes?",
         franja="manana", preferencia="09:00")
    cita(den, lucia, den_s[0], d1, "11:00", "confirmada")
    cita(fis, pablo, fis_s[2], d1, "08:00", "confirmada")
    cita(fis, lucia, fis_s[3], d2, "18:00", "pendiente", "Es por posparto, 4 meses.")

    for (cid, pid, puntos, texto) in [(pod, pablo, 5, "Muy profesionales y puntuales."),
                                      (pod, marta, 4, "Buen trato, algo de espera."),
                                      (mas, lucia, 5, "Salí nueva. Repetiré."),
                                      (den, pablo, 4, "Me explicaron todo con calma."),
                                      (fis, marta, 5, "Recuperé el tobillo antes de lo previsto.")]:
        sid = db.execute("SELECT id FROM servicios WHERE clinica_id = ? LIMIT 1", (cid,)).fetchone()[0]
        cid_cita = cita(cid, pid, sid, hoy - timedelta(days=20 + puntos), "10:00", "completada")
        db.execute("INSERT INTO valoraciones (cita_id, clinica_id, paciente_id, puntuacion, comentario, creado) "
                   "VALUES (?, ?, ?, ?, ?, ?)", (cid_cita, cid, pid, puntos, texto, ahora.isoformat()))

    # Mensajes: uno respondido a Ana y uno nuevo en la clínica dental.
    db.execute("INSERT INTO mensajes (clinica_id, paciente_id, tipo, franja, texto, respuesta, estado, "
               "visto_paciente, creado) VALUES (?, ?, 'consulta', '', ?, ?, 'respondido', 0, ?)",
               (mas, ana, "¿Hacéis masaje a domicilio en Chamberí?",
                "¡Sí! Recargo de 10 €. Pide la cita y en el mensaje indica la dirección.", ahora.isoformat()))
    db.execute("INSERT INTO mensajes (clinica_id, paciente_id, tipo, franja, texto, creado) "
               "VALUES (?, ?, 'llamada', 'Tardes', ?, ?)",
               (den, pablo, "Quiero información de ortodoncia invisible para mi hija de 12 años.",
                ahora.isoformat()))

    # Vacaciones de ejemplo: la clínica podológica cierra un día la semana que viene.
    db.execute("INSERT INTO bloqueos (clinica_id, fecha, motivo) VALUES (?, ?, 'Formación del equipo')",
               (pod, proximo_laborable(hoy, 6).isoformat()))
    # Actividad del mes en las fichas (vistas y clics), repartida en días pasados.
    for (cid, _, _), (vistas, llamadas, mapa) in zip(clinicas, [(64, 9, 7), (41, 3, 5), (88, 14, 6), (37, 4, 2)]):
        for tipo, n in (("vista", vistas), ("llamar", llamadas), ("mapa", mapa)):
            for i in range(n):
                momento = ahora - timedelta(days=i % max(ahora.day - 1, 1), hours=i % 9, minutes=i)
                db.execute("INSERT INTO eventos (clinica_id, tipo, creado) VALUES (?, ?, ?)",
                           (cid, tipo, momento.isoformat()))
    db.commit()
    db.close()


if __name__ == "__main__":
    destino = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CITAS_BD", str(BASE / "datos" / "citas.db"))
    sembrar(destino, borrar=True)
    print(f"Datos de demostración en {destino}. Contraseña de todas las cuentas: {CLAVE}")
