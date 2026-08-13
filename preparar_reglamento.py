#!/usr/bin/env python3
"""
preparar_reglamento.py — descarga el Reglamento (UE) 2025/40 de EUR-Lex y lo
convierte en markdown troceado por artículo y anexo.

Se ejecuta UNA vez (y cada vez que salga una versión consolidada nueva).

    python preparar_reglamento.py

Resultado en ./reglamento/:
    00-INDICE.md          índice tema -> artículo (esto va siempre en contexto)
    articulos/art-001.md  ... un fichero por artículo
    anexos/anexo-I.md     ... un fichero por anexo
    considerandos.md      preámbulo completo, aparte
"""
import re
import sys
import json
import html
import unicodedata
from pathlib import Path
from urllib.request import Request, urlopen

URL = ("https://eur-lex.europa.eu/legal-content/ES/TXT/HTML/"
       "?uri=CELEX:32025R0040&from=ES")

BASE = Path(__file__).parent / "reglamento"
ROMANOS = "I II III IV V VI VII VIII IX X XI XII XIII XIV XV XVI".split()


# --------------------------------------------------------------------------
# 1. Descarga
# --------------------------------------------------------------------------
def descargar() -> str:
    print("Descargando de EUR-Lex...", flush=True)
    req = Request(URL, headers={"User-Agent": "Mozilla/5.0 (compatible; ppwr-local)"})
    with urlopen(req, timeout=180) as r:
        crudo = r.read()
    print(f"  {len(crudo)/1024:.0f} KB recibidos")
    for enc in ("utf-8", "iso-8859-1", "cp1252"):
        try:
            return crudo.decode(enc)
        except UnicodeDecodeError:
            continue
    return crudo.decode("utf-8", errors="replace")


# --------------------------------------------------------------------------
# 2. HTML -> texto plano, conservando tablas como markdown
# --------------------------------------------------------------------------
def html_a_texto(doc: str) -> str:
    # fuera todo lo que no es contenido
    doc = re.sub(r"(?is)<(script|style|head|nav|footer)\b.*?</\1>", " ", doc)

    # tablas -> filas separadas por | (los anexos del PPWR son casi todo tablas)
    def celda(m):
        return " | " + m.group(1)
    doc = re.sub(r"(?is)<t[dh][^>]*>(.*?)</t[dh]>", celda, doc)
    doc = re.sub(r"(?is)</tr\s*>", "\n", doc)
    doc = re.sub(r"(?is)</table\s*>", "\n\n", doc)

    # saltos de bloque
    doc = re.sub(r"(?i)<br\s*/?>", "\n", doc)
    doc = re.sub(r"(?i)</(p|div|li|h[1-6])\s*>", "\n", doc)

    doc = re.sub(r"(?s)<[^>]+>", " ", doc)          # resto de etiquetas
    doc = html.unescape(doc)
    doc = doc.replace("\xa0", " ").replace("\u2011", "-")
    doc = unicodedata.normalize("NFC", doc)

    doc = re.sub(r"[ \t]+", " ", doc)
    doc = re.sub(r" *\n *", "\n", doc)
    doc = re.sub(r"\n{3,}", "\n\n", doc)
    return doc.strip()


# --------------------------------------------------------------------------
# 3. Troceado por estructura
# --------------------------------------------------------------------------
RE_ART = re.compile(r"^\s*Art[ií]culo\s+(\d{1,3})\s*$", re.M | re.I)
RE_ANEXO = re.compile(r"^\s*ANEXO\s+([IVX]{1,6})\s*$", re.M)


def cortar(texto, regex):
    """Devuelve [(clave, cuerpo)] cortando el texto en cada coincidencia."""
    marcas = list(regex.finditer(texto))
    trozos = []
    for i, m in enumerate(marcas):
        fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        trozos.append((m.group(1), texto[m.end():fin].strip()))
    return trozos


def primer_renglon(cuerpo: str) -> str:
    """El título del artículo es la primera línea corta tras el encabezado."""
    for linea in cuerpo.split("\n"):
        linea = linea.strip()
        if linea and len(linea) < 160 and not re.match(r"^\d+[\.\)]", linea):
            return linea
    return ""


def slug(s, n=60):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    return re.sub(r"[\s_-]+", "-", s)[:n]


# --------------------------------------------------------------------------
# 4. Escritura
# --------------------------------------------------------------------------
def main():
    BASE.mkdir(exist_ok=True)
    (BASE / "articulos").mkdir(exist_ok=True)
    (BASE / "anexos").mkdir(exist_ok=True)

    crudo = descargar()
    texto = html_a_texto(crudo)
    (BASE / "_texto-plano.txt").write_text(texto, encoding="utf-8")
    print(f"Texto plano: {len(texto):,} caracteres (~{len(texto)//6:,} palabras)")

    # separar preámbulo / articulado / anexos
    corte_anexos = RE_ANEXO.search(texto)
    cuerpo = texto[: corte_anexos.start()] if corte_anexos else texto
    cola = texto[corte_anexos.start():] if corte_anexos else ""

    primer_art = RE_ART.search(cuerpo)
    considerandos = cuerpo[: primer_art.start()] if primer_art else ""
    articulado = cuerpo[primer_art.start():] if primer_art else cuerpo

    (BASE / "considerandos.md").write_text(
        "# Considerandos — Reglamento (UE) 2025/40\n\n"
        "> No vinculantes. Sirven para interpretar el articulado.\n\n" + considerandos,
        encoding="utf-8")

    # artículos
    indice_art = []
    for num, cuerpo_art in cortar(articulado, RE_ART):
        titulo = primer_renglon(cuerpo_art)
        n = int(num)
        nombre = f"art-{n:03d}.md"
        (BASE / "articulos" / nombre).write_text(
            f"# Artículo {n}. {titulo}\n\n"
            f"*Reglamento (UE) 2025/40 — aplicable desde 12/08/2026*\n\n"
            f"{cuerpo_art}\n", encoding="utf-8")
        indice_art.append((n, titulo, nombre, len(cuerpo_art)))

    # anexos
    indice_anx = []
    for rom, cuerpo_anx in cortar(cola, RE_ANEXO):
        titulo = primer_renglon(cuerpo_anx)
        nombre = f"anexo-{rom}.md"
        (BASE / "anexos" / nombre).write_text(
            f"# Anexo {rom}. {titulo}\n\n{cuerpo_anx}\n", encoding="utf-8")
        indice_anx.append((rom, titulo, nombre, len(cuerpo_anx)))

    escribir_indice(indice_art, indice_anx)

    print(f"\n{len(indice_art)} artículos y {len(indice_anx)} anexos escritos en {BASE}")
    if len(indice_art) < 60:
        print("AVISO: se esperaban ~79 artículos. Revisa reglamento/_texto-plano.txt "
              "por si EUR-Lex cambió el formato.", file=sys.stderr)


TEMAS = {
    "Ámbito, definiciones y roles": (1, 3),
    "Sostenibilidad del envase (sustancias, reciclabilidad, contenido reciclado, minimización)": (5, 11),
    "Etiquetado, marcado y soporte de datos": (12, 14),
    "Obligaciones de fabricantes, importadores y distribuidores": (15, 22),
    "Conformidad: procedimiento, declaración UE y marcado": (36, 40),
    "Vigilancia del mercado y salvaguardias": (41, 43),
    "Registro del productor y responsabilidad ampliada": (44, 48),
    "Gestión de residuos y recogida separada": (49, 58),
    "Reutilización, recarga y sistemas de depósito": (27, 35),
    "Información, informes y actos delegados": (59, 70),
    "Disposiciones finales y fechas de aplicación": (71, 79),
}


def escribir_indice(arts, anexos):
    por_num = {n: (t, f) for n, t, f, _ in arts}
    L = ["# Índice — Reglamento (UE) 2025/40 (PPWR)",
         "",
         "Envases y residuos de envases. Aplicable desde el **12 de agosto de 2026**.",
         "Deroga la Directiva 94/62/CE. Aplicación directa, sin transposición.",
         "",
         "Este índice es el mapa de navegación: localiza el tema, abre el fichero del artículo.",
         "",
         "## Por tema", ""]
    for tema, (a, b) in TEMAS.items():
        L.append(f"### {tema}")
        for n in range(a, b + 1):
            if n in por_num:
                t, f = por_num[n]
                L.append(f"- **Art. {n}** — {t} · `articulos/{f}`")
        L.append("")

    L += ["## Todos los artículos", ""]
    for n, t, f, tam in arts:
        L.append(f"- Art. {n} — {t} · `articulos/{f}` ({tam:,} car.)")

    L += ["", "## Anexos", ""]
    for r, t, f, tam in anexos:
        L.append(f"- Anexo {r} — {t} · `anexos/{f}` ({tam:,} car.)")

    L += ["", "## Notas de aplicación para uso propio", "",
          "- La etiqueta de clasificación de residuos del art. 12.1 **no aplica** a envases de "
          "medicamentos, productos sanitarios e IVD destinados solo a usuarios finales "
          "profesionales. El resto de obligaciones sí aplica.",
          "- El rol legal (envasador, importador, adquirente intracomunitario, distribuidor) "
          "se determina **por referencia**, no por empresa. Condiciona qué artículos obligan.",
          "- Ninguna exención se da por buena sin justificación escrita del proveedor.",
          ""]
    (BASE / "00-INDICE.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
