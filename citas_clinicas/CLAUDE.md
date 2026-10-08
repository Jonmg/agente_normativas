# citas_clinicas (CitaCerca)

Proyecto independiente de `agente_normativas`: comparte repositorio, pero NO sus
reglas. Aquí sí hay base de datos (SQLite de la biblioteca estándar), porque
hay usuarios, citas y concurrencia de reservas.

- Código, comentarios y textos en castellano.
- Única dependencia: flask. Plantillas Jinja en `templates/`, sin frameworks de frontend.
- `huecos_libres()` en `app.py` es la pieza sensible: decide qué horas se ofrecen.
  Toda reserva se revalida contra ella en el servidor antes de guardarse.
- `ahora()` es el único punto que lee el reloj; las pruebas lo fijan.
- Pruebas: `python pruebas.py` (offline, base de datos temporal).
