# agente_normativas

Herramienta personal de vigilancia normativa y verificación de proveedores.
Primer alcance: Reglamento (UE) 2025/40 (PPWR), envases y residuos de envases.

Sector: óptica y producto sanitario. Uso interno, no forma parte del SGC.
Corre en local sobre una Raspberry Pi. Repositorio: Jonmg/agente_normativas.

## Qué NO hacer

Estas decisiones ya se tomaron y descartarlas silenciosamente rompe el diseño.

- **No introducir base de datos.** El ground truth son ficheros markdown en
  `reglamento/`. Si algo parece necesitar SQLite o Postgres, casi siempre es que
  el índice está mal escrito. Arréglese el índice.
- **No introducir embeddings ni vectores.** Se descartaron a propósito: PyTorch
  en ARM es inviable en la Pi y el reglamento está bien estructurado por
  artículos. La recuperación se hace por referencias explícitas y coincidencia
  con títulos, y es inspeccionable a mano.
- **No trocear por caracteres o tokens.** La unidad mínima es el artículo o el
  anexo completo. Media obligación es peor que ninguna.
- **No hacer que la herramienta declare conformidad.** Propone y señala. La
  decisión la firma una persona.

## Arquitectura

```
preparar_reglamento.py   descarga EUR-Lex -> markdown troceado. Se ejecuta a mano.
app.py                   Flask. Preguntar / triaje rápido / revisar documento / carpetas.
reglamento/00-INDICE.md  mapa tema -> artículo. SIEMPRE en contexto. Editable a mano.
reglamento/articulos/    un .md por artículo
reglamento/anexos/       un .md por anexo
reglamento/considerandos.md  aparte. Interpretativos, no vinculantes.
salidas/                 JSON de cada consulta y análisis suelto. No versionado.
salidas/carpetas/<slug>/ un caso: _carpeta.json (nombre, proveedor, estado) +
                         un JSON por turno + los documentos originales subidos.
pruebas.py               batería offline (unittest), sin red ni API real.
```

`elegir_fuentes()` en `app.py` decide qué ficheros entran en contexto. Es la
pieza sensible: si una respuesta sale coja, mirar ahí antes que en el prompt.

`extraer_documentos()` convierte lo subido en un formulario en una lista de
documentos de texto: separa un `.eml` en cuerpo + un documento por cada adjunto
(la evidencia suele estar en el adjunto, no en el texto del correo), y admite
varios ficheros a la vez en una misma revisión.

El estado de una carpeta (`ESTADOS` en `app.py`) es un campo más de
`_carpeta.json`, no una tabla nueva — sigue siendo "no base de datos". El
listado de `/carpetas` es el panel de seguimiento: abiertas primero, ordenadas
por antigüedad desde la última actividad; cerradas (Conforme / No aplica) al
final.

## Reglas del dominio

Estas no son preferencias de estilo, son criterio de calidad. Aplican al código
y a cualquier texto que genere la herramienta.

1. **El rol legal se determina por referencia, no por empresa.** La misma
   empresa es importador en unos productos, adquirente intracomunitario en
   otros y envasador propio en otros. Las obligaciones cambian con el rol. Por
   eso el rol es un campo del formulario en cada revisión, no una constante de
   configuración. No refactorizar a constante global.
2. **La unidad de gestión es el componente de envase, no el SKU.** Caja, blíster,
   etiqueta, tapón: cada uno tiene material, proveedor y requisitos propios.
3. **Ninguna afirmación de proveedor cuenta sin documento que la respalde.**
   Ninguna exención se registra sin justificación escrita.
4. **La fecha importa.** Distinguir siempre lo exigible el 12/08/2026 de lo que
   vence en 2030 o 2038. Mezclarlo genera trabajo urgente que no lo es.
5. **Citar artículo concreto.** "Art. 12.1", "Anexo VII". Nunca "el reglamento
   dice". Si el texto cargado no cubre la pregunta, decirlo y señalar qué
   artículo del índice haría falta. No completar con conocimiento general.
6. **Exención conocida:** la etiqueta de clasificación de residuos del art. 12.1
   no aplica a envases de medicamentos, productos sanitarios e IVD destinados
   solo a usuarios finales profesionales. Es real pero estrecha: el resto de
   obligaciones del reglamento siguen aplicando. No extenderla a otros artículos.

## Convenciones

- Código y comentarios en castellano. Es una herramienta de trabajo en castellano.
- Sin dependencias nuevas sin justificarlo: la Pi tiene RAM limitada y todo lo
  que se instale hay que mantenerlo. Ahora mismo: flask, anthropic, pypdf.
- Sin frameworks de frontend. HTML en plantilla dentro de `app.py`.
- Funcional antes que bonito.

## Estado y siguientes pasos

Ya cargado: 71 artículos y 13 anexos reales (no la estimación inicial). Carpetas
con estado/proveedor y panel de seguimiento, triaje rápido sin documento, subida
de varios documentos y de `.eml` con adjuntos, botón de copiar respuesta.

- [ ] Los anexos con tablas densas (Anexo II, cuadros de reciclabilidad) pierden
      formato al convertir. Revisar y decidir si merece un parser específico.
- [ ] Añadir la Guía de la Comisión (2026) como segunda fuente junto al reglamento.
- [ ] Recordatorios de plazos de respuesta más allá del aviso visual a partir de
      3 días sin actividad (constante a revisar si 3 días resulta ruidoso o poco).
- [ ] `pypdf` no hace OCR: una ficha de proveedor escaneada como imagen no da
      texto extraíble. Vigilar si empieza a pasar en la práctica.

## Seguridad

Sin autenticación. Solo red local, nunca expuesto a internet tal cual.
Los documentos de proveedor salen de la red local al llamar a la API de
Anthropic: no subir nada con datos personales o condiciones comerciales
sensibles sin pensarlo antes.
