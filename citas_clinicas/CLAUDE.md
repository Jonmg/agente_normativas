# citas_clinicas (CitaCerca)

Proyecto independiente de `agente_normativas`: comparte repositorio, pero NO sus
reglas. Aquí sí hay base de datos (SQLite de la biblioteca estándar), porque
hay usuarios, citas y concurrencia de reservas.

- Código, comentarios y textos en castellano.
- Dependencias: flask (y gunicorn solo para desplegar). Plantillas Jinja en `templates/`, sin frameworks de frontend.
- Disponibilidad en dos modos por clínica (`clinicas.modo`): 'franjas' (cupos por mañana/
  tarde en la tabla `cupos`, la clínica fija la hora al confirmar) y 'agenda' (horas exactas).
  `disponibilidad()` unifica ambos para búsqueda y mapa; `cupos_libres()` y `huecos_libres()`
  son las piezas sensibles. Toda reserva se revalida contra ellas antes de guardarse.
  Una cita por franja pendiente tiene hora '' y no ocupa hora concreta en la agenda.
- `ahora()` es el único punto que lee el reloj; las pruebas lo fijan.
- Despliegue: `render.yaml` en la raíz del repo (Render, plan gratuito, `CITAS_DEMO=1`
  siembra datos de ejemplo si la base está vacía). Un solo worker de gunicorn.
- Cobro: `captaciones()` define qué es un paciente nuevo (primera cita confirmada/realizada
  por paciente y clínica). Es la pieza de la que sale la factura: cambiarla con pruebas.
- Mapa: Leaflet 1.9.4 por CDN + OpenStreetMap. Todo el JS de mapa vive en `static/mapa.js`
  y debe degradar sin error si `L` no existe.
- Recordatorio semanal: `enviar_recordatorios()` (necesita contexto de petición para las URL).
  Enlaces sin contraseña firmados con itsdangerous (`token_huecos`), salt propio y caducidad.
  La ruta `/tareas/recordatorios` no lleva CSRF: se autentica con `CITAS_TAREAS_CLAVE`.
- Esquema: los cambios se añaden también a `migrar()` para no romper bases existentes.
- Pruebas: `python pruebas.py` (offline, base de datos temporal).
