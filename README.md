# Conformidad de envases · Reglamento (UE) 2025/40

Herramienta personal para verificar que los envases de nuestros productos, y la
documentación que envían los proveedores, cumplen el PPWR. Corre en local (Raspberry Pi).

No es un sistema del SGC. Es una ayuda de trabajo: propone, no declara conformidad.

## Cómo está montado

Sin base de datos y sin vectores. El "ground truth" son ficheros markdown:

```
reglamento/
  00-INDICE.md        índice tema -> artículo. Va SIEMPRE en el contexto.
  articulos/art-012.md
  anexos/anexo-VII.md
  considerandos.md    aparte: interpretativos, no vinculantes
```

El texto completo (~250.000 palabras) no cabe en una ventana de contexto. Por eso se
carga el índice, se detecta qué artículos hacen falta, y se cargan **esos artículos
enteros**. Un artículo es una unidad de sentido cerrada: cargarlo entero evita las
respuestas a medias que da el troceado por caracteres.

La selección de artículos usa dos vías, ambas legibles:

- referencias explícitas en el texto ("artículo 12", "anexo VII")
- coincidencia de palabras con los títulos de los artículos

Si un día falla la recuperación, se arregla editando `00-INDICE.md` a mano. Eso es
deliberado: prefiero un índice que puedo corregir a un espacio vectorial que no puedo
inspeccionar.

## Instalación en la Pi

```bash
sudo apt update && sudo apt install -y python3-venv git
git clone <tu-repo> ppwr && cd ppwr
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...
python preparar_reglamento.py     # una sola vez, ~1 min
python app.py
```

Desde cualquier equipo de la red: `http://<ip-de-la-pi>:8000`

Para que arranque sola, `/etc/systemd/system/ppwr.service`:

```ini
[Unit]
Description=Conformidad envases PPWR
After=network-online.target

[Service]
User=pi
WorkingDirectory=/home/pi/ppwr
EnvironmentFile=/home/pi/ppwr/.env
ExecStart=/home/pi/ppwr/.venv/bin/python app.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

`sudo systemctl enable --now ppwr`

## Uso

**Preguntar** — dudas sobre el reglamento. Responde citando artículo y distinguiendo
lo exigible el 12/08/2026 de lo que vence después.

**Revisar un documento** — subes el informe, correo o declaración del proveedor e
indicas el rol legal de esa referencia. Devuelve qué aporta, qué falta, qué no cuadra
y un borrador de respuesta al proveedor.

El rol legal importa: Medop es importador en unas referencias, adquirente
intracomunitario en otras y envasador propio en otras. Las obligaciones cambian.
Por eso se pide en cada revisión en lugar de fijarlo una vez.

**Triaje rápido** — antes de pedir nada a un proveedor: tipo de producto/envase,
destinatario final y material. Sin subir ningún documento, una primera pasada para
saber qué artículos aplican y si hay alguna exención conocida, útil para repasar
muchas referencias antes de abrir una carpeta por caso.

**Carpetas** — un caso o una duda con memoria de hilo entre turnos, como una
conversación. Nombre libre (no hace falta que cuelgue de un proveedor: hay dudas
puramente normativas), con proveedor y **estado** opcionales (Abierta, Pendiente
proveedor, En revisión interna, Conforme, No aplica) editables en cualquier momento.
Cada pregunta o documento nuevo dentro de la carpeta recibe como contexto todo lo
hablado antes en esa misma carpeta. El documento original que subas se guarda en
`salidas/carpetas/<carpeta>/`, no solo el texto extraído.

Se pueden subir **varios documentos a la vez** en una misma revisión (por ejemplo,
un correo y su ficha adjunta), y un **.eml** se separa automáticamente en cuerpo del
mensaje + un documento por cada adjunto, porque la evidencia suele estar en el
adjunto y no en el texto del correo.

El listado de carpetas (`/carpetas`) es el panel de seguimiento: se puede filtrar por
texto o por estado, las carpetas abiertas van primero, ordenadas por antigüedad desde
la última actividad (con aviso a partir de 3 días sin movimiento), y las cerradas
(Conforme / No aplica) quedan al final.

Cada respuesta lleva un botón "Copiar respuesta" para pegarla directamente en un
correo al proveedor.

Todo queda en `salidas/` como JSON con fecha, fuentes usadas y respuesta.
Ninguna carpeta ni salida se versiona (`salidas/` está en `.gitignore`).

## Pruebas

Batería offline (`unittest`, sin dependencias nuevas). No llama a la API de
Anthropic ni a EUR-Lex; corre contra el reglamento real ya cargado en
`./reglamento/`:

```bash
python -m unittest pruebas -v
```

Cubre: selección de fuentes (`elegir_fuentes`), orden y recuento de
artículos/anexos, el renderizador de markdown (incluida una prueba de que
escapa HTML para evitar XSS), las rutas de la web, estado/proveedor y filtrado
del panel de seguimiento de carpetas, el parseo de `.eml` con adjuntos, la
subida de varios documentos en una misma revisión, el triaje rápido, y el
troceado por artículo de `preparar_reglamento.py` (el regex que separa
"Artículo 12" como cabecera de una simple mención a "el artículo 12" dentro
de un párrafo).

## Límites conocidos

- El parser depende del HTML de EUR-Lex. Si cambian el formato, `preparar_reglamento.py`
  avisa si detecta menos de 60 artículos. El texto crudo queda en
  `reglamento/_texto-plano.txt` para revisarlo.
- Los anexos con tablas complejas (Anexo II, reciclabilidad) pierden parte del formato.
  Contrastar contra el PDF oficial antes de decidir nada sobre esos umbrales.
- La API de Anthropic requiere internet. Los datos de proveedor salen de la red local
  al enviarlos; no subir documentos con datos personales o precios sensibles sin pensarlo.
- No hay control de acceso. Solo red local; no exponer a internet sin poner delante
  autenticación.

## Siguiente

- [ ] Cargar la Guía de la Comisión (2026) como segunda fuente junto al reglamento
- [ ] Recordatorios de plazos de respuesta (más allá del aviso visual a partir de 3
      días sin actividad en el listado de carpetas)
- [ ] La extracción de texto de PDF (`pypdf`) no hace OCR: una ficha escaneada como
      imagen no da texto. Si empieza a pasar con proveedores reales, valorar OCR.
