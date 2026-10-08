# CitaCerca · citas en clínicas cercanas

Plataforma para que clínicas de podología, fisioterapia, masaje, odontología,
osteopatía, psicología y nutrición publiquen su ficha y sus huecos libres, y para
que los pacientes encuentren una clínica cercana con hueco esta semana.

## Arrancar

```bash
cd citas_clinicas
pip install -r requirements.txt
python app.py --demo      # crea datos/citas.db con datos de ejemplo y arranca
# después, sin --demo para conservar los datos
```

Abre http://127.0.0.1:5000. Para verla desde el móvil en la misma red:
`HOST=0.0.0.0 python app.py`.

## Cuentas de demostración (contraseña `demo1234`)

| Perfil | Email | Qué tiene de particular |
|---|---|---|
| 🦶 Podología Pasos (Madrid 28010) | podologia@demo.es | Confirma a mano, huecos cada 15 min, día bloqueado por formación |
| 💆 Manos en Calma (Madrid 28014) | masaje@demo.es | **Confirmación automática**, atiende a domicilio, abre sábados |
| 🦷 Sonrisa Norte (Madrid 28046) | dental@demo.es | Revisión gratis, urgencias, mensaje de llamada pendiente |
| 💪 FisioActiva Getafe (28901) | fisio@demo.es | Abre a las 8:00, suelo pélvico, punción seca |
| 👤 Paciente Ana López (28010) | paciente@demo.es | Citas confirmadas, pendientes y una pasada para valorar |

O regístrate tú como paciente en «Crear cuenta», o como clínica en «Registrar mi clínica».

## Qué hace

**Paciente**
- Busca por especialidad **o describiendo lo que le pasa** («me duele la espalda»,
  «uña encarnada»): se deduce qué especialidades encajan y qué servicio concreto.
- Resultados ordenados por cercanía (código postal), cita más pronta o valoración;
  filtros de mañana/tarde y de necesidades (accesible, a domicilio, aseguradoras…).
- Cada resultado enseña los próximos huecos reales: un clic y a confirmar.
- En la ficha: elige servicio y ve los huecos de la semana en los que **cabe ese servicio**
  (no es lo mismo 30 que 90 minutos), navega semanas, llama (`tel:`), abre el mapa
  o deja un mensaje pidiendo que le llamen en una franja.
- Panel «Mis citas»: estado (pendiente/confirmada/rechazada), respuesta de la clínica,
  cancelar (libera el hueco), repetir y valorar citas pasadas.

**Clínica**
- Ficha personalizable: foto o logo, color propio, frase destacada, descripción,
  características y servicios con duración y precio.
- Horario semanal con dos tramos por día; los huecos se generan solos.
- Bloqueos de días u horas (vacaciones, festivos, citas dadas por teléfono).
- Solicitudes: confirmar o rechazar con mensaje; o confirmación automática.
- Mensajes y peticiones de llamada; agenda de 14 días; marcar citas como realizadas.
- Solo pueden valorar pacientes con una cita real.

## Cómo está montado

```
app.py           Flask + SQLite (stdlib). Rutas, búsqueda y cálculo de huecos.
datos_demo.py    siembra las 4 clínicas, pacientes, citas y valoraciones.
templates/       plantillas Jinja.
static/          estilo.css (sin frameworks).
pruebas.py       batería offline (unittest).
datos/           base de datos, fotos subidas y clave de sesión. No versionado.
```

La cercanía se calcula sin servicios externos: entre provincias, distancia entre
capitales; dentro de la misma provincia, proximidad numérica del código postal.
Es una aproximación suficiente para ordenar.

Seguridad básica incluida: contraseñas con hash, protección CSRF en todos los
formularios, sin redirecciones abiertas, solo imágenes PNG/JPG/WEBP/GIF de hasta 4 MB.
Usa el servidor de desarrollo de Flask: para publicarlo en internet hace falta
HTTPS, un servidor WSGI (gunicorn) y revisar el RGPD (datos de salud).

## Siguientes pasos posibles

- Avisos por email/SMS/WhatsApp al confirmar, y recordatorio el día anterior.
- Varios profesionales por clínica, cada uno con su agenda.
- Geolocalización real (coordenadas por dirección) y mapa con las clínicas.
- Lista de espera: avisar si se libera un hueco antes.
- Recuperar contraseña y verificación del email/teléfono.
- Texto legal y consentimiento RGPD; revisión de qué datos de salud se guardan.
