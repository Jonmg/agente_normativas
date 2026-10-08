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

## Demo pública en Render (gratis, desde GitHub)

El fichero `render.yaml` de la raíz del repositorio describe el despliegue:

1. Crea una cuenta en https://render.com entrando con GitHub.
2. **New → Blueprint** y elige el repositorio `agente_normativas`.
   Si no aparece, pulsa «Configure account» y dale acceso a ese repositorio.
3. Render lee `render.yaml`: pulsa **Apply**. En 2-3 minutos tendrás una URL
   `https://citacerca-demo-XXXX.onrender.com` que puedes abrir desde el móvil.

Cada `git push` a la rama `claude/health-clinics-booking-platform-uo0ckk` se
vuelve a desplegar solo. En modo demo (`CITAS_DEMO=1`) se cargan los datos de
ejemplo si la base está vacía y «Entrar» muestra las cuentas de prueba con
acceso en un clic.

Limitaciones del plan gratuito: el servicio se duerme tras 15 minutos sin
visitas (la primera carga después tarda unos 30-60 s) y el disco no es
persistente: al reiniciarse o redesplegar se pierden las cuentas y fotos nuevas
y vuelven los datos de ejemplo. Para una demo es justo lo que interesa; para uso
real haría falta un disco persistente o una base de datos gestionada.

## Cuentas de demostración (contraseña `demo1234`)

| Perfil | Email | Qué tiene de particular |
|---|---|---|
| 🦶 Podología Pasos (Madrid 28010) | podologia@demo.es | Confirma a mano, huecos cada 15 min, día bloqueado por formación |
| 💆 Manos en Calma (Madrid 28014) | masaje@demo.es | **Confirmación automática**, atiende a domicilio, abre sábados |
| 🦷 Sonrisa Norte (Madrid 28046) | dental@demo.es | Revisión gratis, urgencias, mensaje de llamada pendiente |
| 💪 FisioActiva Getafe (28901) | fisio@demo.es | Abre a las 8:00, suelo pélvico, punción seca |
| 👤 Paciente Ana López (28010) | paciente@demo.es | Citas confirmadas, pendientes y una pasada para valorar |
| 🛠️ Administración | admin@demo.es | Panel de captación y facturación de toda la plataforma |

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

**Mapa**
- Búsqueda con mapa de las clínicas (chincheta del color de cada una, próximo hueco al tocarla).
- «📍 Usar mi ubicación»: distancia real en metros/km y orden por cercanía de verdad.
  Sin ubicación se sigue aproximando por código postal.
- La clínica se sitúa en su «Ficha»: botón «Situar por la dirección» o clic en el mapa.
- OpenStreetMap + Leaflet: sin claves ni coste. Si el mapa no carga, la página sigue funcionando.

**Administración y modelo de cobro** (`/admin`)
- Se cobra por **paciente nuevo**: la primera cita confirmada o realizada de un paciente
  con una clínica. Repetir con la misma clínica no cuenta; cancelar sí lo descuenta.
- Al confirmar, la clínica puede marcar «Ya era paciente mío» y esa cita no se factura.
- Tarifa general con `CITAS_TARIFA` (8 € por defecto); por clínica se puede fijar tarifa
  propia (0 = piloto gratis) y un tope mensual.
- Embudo por mes: visitas a la ficha → clics en «Llamar» / «Cómo llegar» → mensajes →
  solicitudes → pacientes nuevos. La clínica ve su propio embudo en su panel: es el
  argumento de venta («este mes te hemos traído X»).
- CSV mensual de captaciones (justificante para facturar) y lista de clínicas sin actividad.
- Cuenta de administración en producción: variables `CITAS_ADMIN_EMAIL` y `CITAS_ADMIN_CLAVE`
  (se crea o actualiza al arrancar).

Las llamadas directas no se pueden atribuir con certeza: solo se cuenta quien pulsa
«Llamar» en la ficha. Antes de cobrar por paciente en profesiones sanitarias, conviene
confirmar con un abogado que es compatible con sus códigos deontológicos.

## Cómo está montado

```
app.py           Flask + SQLite (stdlib). Rutas, búsqueda y cálculo de huecos.
datos_demo.py    siembra las 4 clínicas, pacientes, citas y valoraciones.
templates/       plantillas Jinja.
static/          estilo.css y mapa.js (sin frameworks; Leaflet desde CDN para el mapa).
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
