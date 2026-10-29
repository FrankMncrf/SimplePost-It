#!/usr/bin/env python3
# SimplePost-It: tus notas FIJADAS de Simplenote como post-its en el escritorio.
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Es una capa sobre Simplenote: necesita la app de escritorio de Simplenote instalada y con
# la sesión iniciada (o, si no se puede leer esa sesión, un inicio de sesión propio en
# Ajustes → Cuenta). Con esa sesión habla con Simperium, el servicio de sincronización de
# Simplenote: lee las notas fijadas y guarda los cambios hechos desde el widget, que luego
# llegan a Simplenote en todos tus dispositivos. Linux (X11), Windows y macOS.
#
# Notas cuadradas del mismo tamaño (rueda del ratón = desplazar el texto), cada una con su
# cinta, inclinación y la esquina inferior izquierda doblada; la primera es amarilla.
# Se arrastran dentro de un tablero (posiciones, inclinación, color y minimizadas en
# layout.json; Ctrl+rueda inclina la nota); un clic la pasa al frente, doble clic en el
# título la abre en Simplenote y en el cuerpo abre el mini editor; el botón + crea una nota
# y la × solo la quita del escritorio (la desfija); a la papelera desde el mini editor o
# el clic derecho. Clic en un "- [ ]" marca la tarea, Ctrl+clic abre el enlace, clic derecho: color,
# minimizar, privada, papelera (etiqueta "privado": texto borroso hasta pasar el ratón). Las notas
# con Markdown activado muestran negritas, cursivas, `código`, bloques ```, subtítulos y
# [enlaces](url) con nombre. El botón ▦ las ordena en cuadrícula.
#   simplepostit              inicia (o, si ya está en marcha, muestra las notas)
#   simplepostit --toggle     ocultar/mostrar las notas (para un atajo de teclado)
#   simplepostit --settings   abrir los ajustes
#   simplepostit --quit       cerrar la instancia en marcha
#   SIMPLEPOSTIT_FILE=<ruta>  demo sin cuenta: notas de un archivo, registros
#                             "id US contenido US etiquetas US md" separados por RS
import json
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
IS_LINUX = not IS_WIN and not IS_MAC
if IS_LINUX and os.environ.get("WAYLAND_DISPLAY") and os.environ.get("DISPLAY"):
    # en Wayland una ventana no puede elegir su posición ni quedarse bajo las demás: XWayland
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

from PyQt6.QtCore import (QPointF, QRectF, Qt, QTimer, QObject, pyqtSignal,  # noqa: E402
                          QAbstractNativeEventFilter, QUrl, QTranslator, QLibraryInfo)
from PyQt6.QtGui import (QColor, QCursor, QDesktopServices, QFont, QFontMetricsF,  # noqa: E402
                         QGuiApplication, QIcon, QImage, QKeySequence, QLinearGradient, QPainter,
                         QPainterPath, QPen, QPixmap, QRegion, QTextCharFormat, QTextLayout,
                         QTextOption, QShortcut)
from PyQt6.QtNetwork import QLocalServer, QLocalSocket  # noqa: E402
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog,  # noqa: E402
                             QDialogButtonBox, QFontComboBox, QFormLayout, QHBoxLayout, QLabel,
                             QLineEdit, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QSlider,
                             QSpinBox, QSystemTrayIcon, QTabWidget, QVBoxLayout, QWidget,
                             QKeySequenceEdit)

APP = "SimplePost-It"
VERSION = "1.1.0"
REPO_URL = "https://github.com/FrankMncrf/SimplePost-It"
# donaciones; un valor vacío oculta esa opción
DONATE = {
    "bmc": "https://buymeacoffee.com/frankmncrf",
    "btc": "bc1qm45kpx35uazdts3q8vc77edqwyajuxe9cexw0er5409dyevl3nysxhln9g",
}
THIRD_PARTY = [
    ("Qt 6", "LGPL-3.0 / GPL", "https://www.qt.io/licensing"),
    ("PyQt6", "GPL-3.0", "https://www.riverbankcomputing.com/software/pyqt/"),
    ("Python", "PSF-2.0", "https://www.python.org/psf/license/"),
]


# ---------------------------------------------------------------------------
# rutas, ajustes e idioma
# ---------------------------------------------------------------------------

def _base_dir():
    """Datos de la app: junto al script, o dentro del ejecutable de PyInstaller."""
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.realpath(__file__)))


def config_dir():
    if IS_WIN:
        return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP)
    if IS_MAC:
        return os.path.expanduser(f"~/Library/Application Support/{APP}")
    return os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "simplepostit")


def state_dir():
    if not IS_LINUX:
        return config_dir()
    return os.path.join(os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "simplepostit")


SETTINGS_FILE = os.path.join(config_dir(), "settings.json")
LAYOUT = os.path.join(state_dir(), "layout.json")
I18N_DIR = os.path.join(_base_dir(), "i18n")
DEMO_FILE = os.environ.get("SIMPLEPOSTIT_FILE")

DEFAULTS = {
    "language": "auto",        # auto | es | en
    "autostart": True,
    "simplenote_background": True,  # Simplenote abierto con la ventana oculta
    "hotkey": "Meta+N" if IS_LINUX else "Ctrl+Alt+N",
    "max_notes": 12,
    "opacity": 95,             # % del papel
    "note_size": 200,
    "tilt": 6,                 # inclinación máxima al azar, en grados
    "font": "",                # vacío: la fuente de la interfaz
    "board_width": 760,
    "board_height": 560,
    "monitor": -1,             # -1 = principal
    "anchor": "top_right",     # esquina del monitor desde la que se mide la posición
    "offset_x": 30,            # distancia al borde izquierdo o derecho (según la esquina)
    "offset_y": 205,           # distancia al borde superior o inferior
    "poll": 10,                # segundos entre lecturas de Simplenote
    "token": "",               # sesión propia (Ajustes → Cuenta) si no se usa la de Simplenote
}


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    if "offset_x" not in data and "right" in data:  # 1.0.x: siempre desde arriba a la derecha
        data["offset_x"], data["offset_y"] = data["right"], data.get("top", DEFAULTS["offset_y"])
    return {k: data.get(k, v) for k, v in DEFAULTS.items()}


def save_settings(settings):
    os.makedirs(config_dir(), exist_ok=True)
    tmp = SETTINGS_FILE + ".tmp"
    # puede contener el token de la sesión propia: solo para el usuario
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=1)
    os.replace(tmp, SETTINGS_FILE)


SETTINGS = load_settings()

ANCHORS = ("top_left", "top_right", "bottom_left", "bottom_right")


def board_origin(screen, size, anchor, ox, oy):
    """Esquina superior izquierda del tablero (x, y) dentro del monitor (x, y, ancho, alto)."""
    sx, sy, sw, sh = screen
    w, h = size
    x = sx + ox if anchor.endswith("left") else sx + sw - ox - w
    y = sy + oy if anchor.startswith("top") else sy + sh - oy - h
    return x, y


def board_offsets(screen, pos, size, anchor):
    """Lo inverso: distancias a los bordes de la esquina elegida (nunca negativas)."""
    sx, sy, sw, sh = screen
    (x, y), (w, h) = pos, size
    ox = x - sx if anchor.endswith("left") else sx + sw - x - w
    oy = y - sy if anchor.startswith("top") else sy + sh - y - h
    return max(0, round(ox)), max(0, round(oy))


def _ui_language():
    lang = SETTINGS.get("language", "auto")
    if lang == "auto":
        lang = "en"
        for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
            val = os.environ.get(var, "").split(":")[0]
            if val:
                lang = "en" if val in ("C", "POSIX") or val.startswith("C.") else val[:2].lower()
                break
        else:
            if IS_WIN or IS_MAC:
                from PyQt6.QtCore import QLocale
                lang = QLocale.system().name()[:2].lower()
    if lang != "es" and not os.path.exists(os.path.join(I18N_DIR, f"{lang}.json")):
        lang = "en"
    return lang


def _load_catalog(lang):
    if lang == "es":
        return {}
    try:
        with open(os.path.join(I18N_DIR, f"{lang}.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


UI_LANG = _ui_language()
_CATALOG = _load_catalog(UI_LANG)


def tr(text):
    return _CATALOG.get(text, text)


# ---------------------------------------------------------------------------
# medidas y colores (las que dependen de los ajustes se recalculan en apply_settings)
# ---------------------------------------------------------------------------

CARD, PAD = 200, 16          # notas cuadradas
TITLE_SIZE, BODY_SIZE, LINE_H = 15, 12, 17
FOLD = 24                    # esquina doblada (abajo a la izquierda)
BOARD_W, BOARD_H = 760, 560  # tablero donde se pueden acomodar las notas
MARGIN = 22                  # espacio para sombra, cinta e inclinación
MAX_NOTES = 12
PLUS_R = 9                   # botones "nueva nota" y "ordenar" (discretos)
DEL_R = 8                    # botón × (quitar del escritorio) de cada nota
ALPHA = 0.95                 # opacidad del papel
TILT = 6.0
FONT = ""

PALETTE = [
    (1.00, 0.89, 0.55),  # amarillo
    (1.00, 0.76, 0.80),  # rosa
    (0.72, 0.92, 0.84),  # menta
    (0.80, 0.75, 0.92),  # lavanda
    (0.67, 0.84, 1.00),  # cielo
    (1.00, 0.80, 0.66),  # durazno
]
COLOR_NAMES = ["Amarillo", "Rosa", "Menta", "Lavanda", "Cielo", "Durazno"]
INK = (0.16, 0.16, 0.20)
PRIVATE_TAGS = {"privado", "privada", "private"}
URL_RE = re.compile(r"https?://[^\s)\]]+")
MD_INLINE = re.compile(r"`([^`]+)`|\*\*(.+?)\*\*|__(.+?)__|~~(.+?)~~|\*([^*\s][^*]*?)\*"
                       r"|(?<!\w)_([^_\s][^_]*?)_(?!\w)|\[([^\]]+)\]\((https?://[^)\s]+)\)"
                       r"|(https?://[^\s)]+)")


def apply_settings():
    global CARD, BOARD_W, BOARD_H, MAX_NOTES, ALPHA, TILT, FONT
    CARD = int(SETTINGS["note_size"])
    BOARD_W = max(CARD, int(SETTINGS["board_width"]))
    BOARD_H = max(CARD, int(SETTINGS["board_height"]))
    MAX_NOTES = int(SETTINGS["max_notes"])
    ALPHA = int(SETTINGS["opacity"]) / 100
    TILT = float(SETTINGS["tilt"])
    FONT = SETTINGS["font"] or ""


apply_settings()


def rgba(c, a=1.0):
    return QColor.fromRgbF(c[0], c[1], c[2], max(0.0, min(1.0, a)))


def font(size, bold=False, mono=False):
    f = QFont()
    if mono:
        f.setFamilies(["monospace", "Consolas", "Menlo", "Courier New"])
        f.setStyleHint(QFont.StyleHint.Monospace)
    elif FONT:
        f.setFamily(FONT)
    f.setPixelSize(int(round(size)))
    f.setBold(bold)
    return f


def fnv(s):
    h = 2166136261
    for b in s.encode():
        h = ((h ^ b) * 16777619) & 0xFFFFFFFF
    return h


def open_url(url):
    QDesktopServices.openUrl(QUrl(url))


def u16(text, i):
    """Índice de Python → índice UTF-16 (el que usa Qt)."""
    return len(text[:i].encode("utf-16-le")) // 2


# ---------------------------------------------------------------------------
# notas: texto, Markdown y dibujo
# ---------------------------------------------------------------------------

def parse(note, md=False):
    """Título + elementos (tipo, texto, nº de línea): text, todo, done, bullet, gap y, con
    Markdown, h (subtítulo) y code (línea de un bloque ```)."""
    lines = note.splitlines()
    title, i = None, 0
    while i < len(lines) and title is None:
        t = re.sub(r"^#+\s*", "", lines[i].strip())
        if t:
            title = t
        i += 1
    items = []
    fence = False
    for n, raw in enumerate(lines[i:], i):
        line = raw.strip()
        if md and line.startswith("```"):
            fence = not fence
            continue
        if fence:
            items.append(("code", raw.rstrip(), n))
            continue
        if md and re.match(r"^#{1,6}\s", line):
            items.append(("h", re.sub(r"^#+\s*", "", line), n))
            continue
        m = re.match(r"^[-*+]\s+\[([ xX])\]\s*(.*)$", line)
        if m:
            items.append(("todo" if m.group(1) == " " else "done", m.group(2), n))
        elif re.match(r"^[-*+]\s+", line):
            items.append(("bullet", re.sub(r"^[-*+]\s+", "", line), n))
        elif line:
            items.append(("text", re.sub(r"^#+\s*", "", line), n))
        elif items and items[-1][0] != "gap":
            items.append(("gap", "", n))
    while items and items[-1][0] == "gap":
        items.pop()
    if md and title:
        title = md_inline(title)[0]
    return title or tr("Sin título"), items


def md_inline(text):
    """Markdown en línea → (texto plano, [(inicio, fin, estilo)], [(inicio, fin, url)]);
    estilos: b, i, s, code, link. Índices de Python sobre el texto plano."""
    plain, spans, links = [], [], []
    size = 0

    def put(p):
        nonlocal size
        plain.append(p)
        size += len(p)

    def nest(inner, style, url=None):
        ip, isp, il = md_inline(inner)
        start = size
        spans.extend((a + start, b + start, s) for a, b, s in isp)
        links.extend((a + start, b + start, u) for a, b, u in il)
        put(ip)
        spans.append((start, size, style))
        if url:
            links.append((start, size, url))

    pos = 0
    for m in MD_INLINE.finditer(text):
        if m.start() > pos:
            put(text[pos:m.start()])
        code, b1, b2, strike, i1, i2, ltext, lurl, bare = m.groups()
        if code:
            start = size
            put(code)
            spans.append((start, size, "code"))
        elif b1 or b2:
            nest(b1 or b2, "b")
        elif strike:
            nest(strike, "s")
        elif i1 or i2:
            nest(i1 or i2, "i")
        elif ltext:
            nest(ltext, "link", lurl)
        else:
            start = size
            put(bare)
            spans.append((start, size, "link"))
            links.append((start, size, bare))
        pos = m.end()
    if pos < len(text):
        put(text[pos:])
    return "".join(plain), spans, links


def plain_links(text):
    """Texto sin Markdown: solo se marcan las URL."""
    found = [(m.start(), m.end(), m.group(0)) for m in URL_RE.finditer(text)]
    return text, [(a, b, "link") for a, b, _u in found], found


def toggle_todo(note, line):
    """Marca o desmarca la tarea "- [ ]" de esa línea (formato de Simplenote)."""
    lines = note.split("\n")
    lines[line] = re.sub(r"^(\s*[-*+]\s+\[)([ xX])\]",
                         lambda m: m.group(1) + (" " if m.group(2) in "xX" else "x") + "]",
                         lines[line], count=1)
    return "\n".join(lines)


def text_layout(text, fnt, width, spans=(), strike=False):
    """QTextLayout con ajuste de línea al ancho; devuelve (layout, líneas)."""
    lay = QTextLayout(text, fnt)
    opt = QTextOption()
    opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    lay.setTextOption(opt)
    ranges = []
    for a, b, style in spans:
        fmt = QTextCharFormat()
        if style == "b":
            fmt.setFontWeight(QFont.Weight.Bold)
        elif style == "i":
            fmt.setFontItalic(True)
        elif style == "s":
            fmt.setFontStrikeOut(True)
        elif style == "code":
            fmt.setFontFamilies(["monospace", "Consolas", "Menlo", "Courier New"])
            fmt.setFontFixedPitch(True)
            fmt.setBackground(QColor(0, 0, 0, 20))
        elif style == "link":  # mismo tono que el texto, más suave y subrayado
            fmt.setFontUnderline(True)
            fmt.setForeground(rgba(INK, 0.68))
        r = QTextLayout.FormatRange()
        r.start, r.length, r.format = u16(text, a), u16(text, b) - u16(text, a), fmt
        ranges.append(r)
    if strike:
        fmt = QTextCharFormat()
        fmt.setFontStrikeOut(True)
        r = QTextLayout.FormatRange()
        r.start, r.length, r.format = 0, u16(text, len(text)), fmt
        ranges.append(r)
    lay.setFormats(ranges)
    lay.beginLayout()
    lines = []
    while True:
        line = lay.createLine()
        if not line.isValid():
            break
        line.setLineWidth(max(10, width))
        line.setPosition(QPointF(0, 0))
        lines.append(line)
    lay.endLayout()
    return lay, lines


class Card:
    def __init__(self, key, note, tags=(), md=False):
        self.key = key
        self.note = note
        self.md = md
        self.title, items = parse(note, md)
        self.items = items
        self.tags = [t for t in tags if t]
        self.private = any(t.lower() in PRIVATE_TAGS for t in self.tags)
        self.done = sum(1 for it in items if it[0] == "done")
        self.total = self.done + sum(1 for it in items if it[0] == "todo")
        self.collapsed = False
        self.fade = 1.0           # aparición de notas nuevas
        self.tx = self.ty = None  # destino de la animación
        self.color = PALETTE[0]
        hs = fnv(key + "#")
        # inclinación por nota: hacia un lado u otro, hasta TILT grados (Ctrl+rueda la ajusta)
        self.tilt = (1 if hs & 1 else -1) * math.radians(TILT * (0.25 + 0.75 * ((hs >> 1) % 46) / 45))
        self.tape_tilt = (((hs >> 8) % 7) - 3) * 0.05
        self.x = self.y = 0.0
        self.scroll = 0.0
        inner = CARD - 2 * PAD
        self.title_layout, lines = text_layout(self.title, font(TITLE_SIZE, True), inner - 14)
        self.title_lines = lines[:2]  # deja sitio a la ×
        # filas: (tipo, sangría, índice del elemento, y en el cuerpo, nº de línea en su layout)
        rows = []
        self.layouts = {}         # índice del elemento -> (layout, líneas, enlaces)
        yy = 4
        for idx, (kind, text, _line) in enumerate(items):
            if kind == "gap":
                rows.append(("gap", 0, idx, yy, 0))
                yy += 7
                continue
            indent = 0 if kind in ("text", "h", "code") else 19
            cont = "cont-done" if kind == "done" else ("code" if kind == "code" else "cont")
            if kind == "h" and rows:
                yy += 4  # aire antes de un subtítulo
            if kind == "code":
                plain, spans, links = text, [], []
                fnt, width = font(BODY_SIZE - 1.5, mono=True), inner - 8
            else:
                plain, spans, links = (md_inline if md else plain_links)(text)
                fnt = font(BODY_SIZE + (1 if kind == "h" else 0), kind == "h")
                width = inner - indent
            lay, lines = text_layout(plain, fnt, width, spans, strike=kind == "done")
            self.layouts[idx] = (lay, lines, [(u16(plain, a), u16(plain, b), u) for a, b, u in links])
            for k in range(len(lines)):
                rows.append((kind if k == 0 else cont, indent, idx, yy, k))
                yy += LINE_H
        self.rows = rows
        self.body_top = PAD + len(self.title_lines) * 19 + 8
        self.body_h = CARD - self.body_top - PAD - (14 if self.tags else 0)
        self.content_h = yy
        self.short_h = PAD + len(self.title_lines) * 19 + 4  # minimizada: solo el título

    @property
    def h(self):
        return self.short_h if self.collapsed else CARD

    def max_scroll(self):
        return max(0, self.content_h - self.body_h)

    def row_at(self, ly):
        """Fila del cuerpo en la coordenada ly de la nota (o None)."""
        if self.collapsed or not self.body_top <= ly <= self.body_top + self.body_h:
            return None
        y = ly - self.body_top + self.scroll
        for row in self.rows:
            if row[0] != "gap" and row[3] <= y < row[3] + LINE_H:
                return row
        return None

    def url_at(self, row, lx):
        """Enlace bajo el puntero en esa fila (o None)."""
        _lay, lines, links = self.layouts[row[2]]
        line = lines[row[4]]
        x = lx - PAD - row[1] - (4 if row[0] == "code" else 0)
        if not 0 <= x <= line.naturalTextWidth() + 2:
            return None
        pos = line.xToCursor(x)
        for a, b, url in links:
            if a <= pos < b or (pos == b and x < line.naturalTextWidth()):
                return url
        return None


def free_spot(placed, hs):
    """Posición (ventana) para una nota nueva que tape lo menos posible a las demás."""
    best = None
    for y in range(0, BOARD_H - CARD + 1, 10):
        for x in range(BOARD_W - CARD, -1, -10):
            over = 0
            for c in placed:
                ox = min(x + CARD, c.x - MARGIN + CARD) - max(x, c.x - MARGIN)
                oy = min(y + CARD, c.y - MARGIN + CARD) - max(y, c.y - MARGIN)
                if ox > -12 and oy > -12:  # deja un pequeño margen entre notas
                    over += (ox + 12) * (oy + 12)
            score = (over, y // 60, BOARD_W - x)
            if best is None or score < best[0]:
                best = (score, x, y)
    _, x, y = best
    return MARGIN + x, MARGIN + y + (hs % 9 if y + 9 <= BOARD_H - CARD else 0)


def card_path(r=9, fold=FOLD, h=None):
    """Papel con la esquina inferior izquierda cortada (ahí va el doblez)."""
    w = CARD
    h = CARD if h is None else h
    path = QPainterPath()
    path.moveTo(r, 0)
    path.lineTo(w - r, 0)
    path.arcTo(w - 2 * r, 0, 2 * r, 2 * r, 90, -90)
    path.lineTo(w, h - r)
    path.arcTo(w - 2 * r, h - 2 * r, 2 * r, 2 * r, 0, -90)
    path.lineTo(fold, h)
    path.cubicTo(fold * 0.55, h - fold * 0.35, fold * 0.35, h - fold * 0.55, 0, h - fold)
    path.lineTo(0, r)
    path.arcTo(0, 0, 2 * r, 2 * r, 180, -90)
    path.closeSubpath()
    return path


def draw_line(p, line, x, base):
    """Una línea de un QTextLayout con su línea base en y = base."""
    line.draw(p, QPointF(x, base - line.ascent()))


def draw_rows(p, card, c):
    """Filas del cuerpo (tareas, viñetas, texto), ya desplazadas por card.scroll."""
    for kind, indent, idx, ry, k in card.rows:
        if kind == "gap":
            continue
        yy = card.body_top + ry - card.scroll
        if yy > card.body_top + card.body_h or yy + LINE_H < card.body_top:
            continue
        base = yy + 12
        done = kind in ("done", "cont-done")
        if kind in ("todo", "done"):
            circle = QRectF(PAD + 0.5, base - 10, 11, 11)
            if done:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(rgba(INK, 0.55))
                p.drawEllipse(circle)
                pen = QPen(rgba(c), 1.5)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPolyline([QPointF(PAD + 3.2, base - 4.5), QPointF(PAD + 5.5, base - 2.2),
                                QPointF(PAD + 9, base - 7.2)])
            else:
                p.setPen(QPen(rgba(INK, 0.6), 1.3))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(circle)
        elif kind == "bullet":
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(rgba(INK, 0.6))
            p.drawEllipse(QPointF(PAD + 6, base - 4.5), 2.2, 2.2)
        if kind == "code":
            p.fillRect(QRectF(PAD - 2, yy, CARD - 2 * PAD + 4, LINE_H), rgba(INK, 0.07))
        p.setPen(rgba(INK, 0.45 if done else 0.9 if kind == "h" else 0.85))
        draw_line(p, card.layouts[idx][1][k], PAD + indent + (4 if kind == "code" else 0), base)


def draw_card(p, card, dragging=False, hover=False, hover_del=False):
    w, h = CARD, card.h
    fold = 12 if card.collapsed else FOLD
    c = card.color
    p.save()
    p.setOpacity(card.fade)
    p.translate(card.x + w / 2, card.y + h / 2)
    p.rotate(math.degrees(card.tilt))
    p.translate(-w / 2, -h / 2)

    lift = 2.2 if dragging else 1.3  # sombra más larga mientras se arrastra
    for i in range(1, 7):
        p.save()
        p.translate(-i * 0.3, i * lift)
        p.fillPath(card_path(9 + i * 0.5, max(4, fold - i), h), QColor(0, 0, 0, 9))
        p.restore()

    g = QLinearGradient(w, 0, w * 0.7, h)
    g.setColorAt(0, rgba(c, ALPHA))
    g.setColorAt(1, rgba([v * 0.92 for v in c], ALPHA))
    p.fillPath(card_path(9, fold, h), g)

    # doblez: la parte de atrás del papel, levantada hacia el frente
    F = fold
    path = QPainterPath()
    path.moveTo(F, h)
    path.cubicTo(F * 0.55, h - F * 0.35, F * 0.35, h - F * 0.55, 0, h - F)
    path.cubicTo(F * 0.4, h - F * 0.95, F * 0.7, h - F * 0.8, F * 1.05, h - F * 1.05)
    path.cubicTo(F * 0.75, h - F * 0.95, F * 0.95, h - F * 0.6, F, h)
    path.closeSubpath()
    fg = QLinearGradient(F, h - F, F * 0.4, h - F * 0.4)
    fg.setColorAt(0, rgba([min(1, v * 1.06) for v in c], ALPHA + 0.08))
    fg.setColorAt(1, rgba([v * 0.78 for v in c], ALPHA + 0.08))
    p.fillPath(path, fg)
    p.strokePath(path, QPen(QColor(0, 0, 0, 31), 0.8))

    # cinta translúcida con los bordes en zigzag, como cortada con el despachador
    p.save()
    p.translate(w / 2, 1)
    p.rotate(math.degrees(card.tape_tilt))
    teeth, hw, hh = 5, 32, 10
    step = 2 * hh / teeth
    hs = fnv(card.key)
    tape = QPainterPath()
    tape.moveTo(-hw, -hh)
    tape.lineTo(hw, -hh)
    for i in range(teeth):
        depth = 3 + ((hs >> i) & 1) * 1.2
        tape.lineTo(hw - depth, -hh + (i + 0.5) * step)
        tape.lineTo(hw, -hh + (i + 1) * step)
    tape.lineTo(-hw, hh)
    for i in range(teeth):
        depth = 3 + ((hs >> (i + 8)) & 1) * 1.2
        tape.lineTo(-hw + depth, hh - (i + 0.5) * step)
        tape.lineTo(-hw, hh - (i + 1) * step)
    tape.closeSubpath()
    p.fillPath(tape, QColor(255, 255, 255, 97))
    p.strokePath(tape, QPen(QColor(255, 255, 255, 64), 0.6))
    if card.total:  # tareas hechas / total, escrito en la cinta
        p.setFont(font(10, True))
        p.setPen(rgba(INK, 0.6))
        p.drawText(QRectF(-hw, -hh, 2 * hw, 2 * hh), Qt.AlignmentFlag.AlignCenter,
                   f"{card.done}/{card.total}")
    p.restore()

    p.setPen(rgba(INK, 0.95))
    for i, line in enumerate(card.title_lines):
        draw_line(p, line, PAD, PAD + 15 + i * 19)
    if card.collapsed:
        draw_delete(p, card, hover, hover_del)
        p.restore()
        return
    if card.rows:
        p.setPen(QPen(rgba(INK, 0.18), 1))
        p.drawLine(QPointF(PAD, card.body_top - 3), QPointF(w - PAD, card.body_top - 3))

    # cuerpo desplazable (borroso en las notas privadas mientras no hay ratón encima)
    body = QRectF(PAD - 2, card.body_top, w - 2 * PAD + 4, card.body_h)
    p.save()
    p.setClipRect(body)
    if card.private and not hover:
        k = 8
        img = QImage(CARD // k + 2, CARD // k + 2, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        ip = QPainter(img)
        ip.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        ip.scale(1 / k, 1 / k)
        draw_rows(ip, card, c)
        ip.end()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.setOpacity(p.opacity() * 0.8)
        p.drawImage(QRectF(0, 0, img.width() * k, img.height() * k), img)
    else:
        draw_rows(p, card, c)
    p.restore()

    if card.tags:  # etiquetas de Simplenote, al pie (a la derecha del doblez)
        f = font(10)
        label = QFontMetricsF(f).elidedText("  ".join("#" + t for t in card.tags),
                                             Qt.TextElideMode.ElideRight, w - FOLD - PAD - 8)
        p.setFont(f)
        p.setPen(rgba(INK, 0.5))
        p.drawText(QRectF(FOLD + 8, h - PAD - 10, w - FOLD - PAD - 8, 13),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label)

    # indicadores de desplazamiento: degradado donde hay más texto y barra fina
    top, bottom = card.body_top, card.body_top + card.body_h
    if card.scroll > 0:
        fade = QLinearGradient(0, top, 0, top + 14)
        fade.setColorAt(0, rgba(c, ALPHA))
        fade.setColorAt(1, rgba(c, 0))
        p.fillRect(QRectF(PAD - 2, top, w - 2 * PAD + 4, 14), fade)
    if card.scroll < card.max_scroll():
        cb = [v * 0.94 for v in c]
        fade = QLinearGradient(0, bottom - 18, 0, bottom)
        fade.setColorAt(0, rgba(cb, 0))
        fade.setColorAt(1, rgba(cb, ALPHA))
        p.fillRect(QRectF(PAD - 2, bottom - 18, w - 2 * PAD + 4, 18), fade)
    if card.max_scroll() > 0:
        track = card.body_h
        bar = max(18, track * card.body_h / card.content_h)
        pos = top + (track - bar) * card.scroll / card.max_scroll()
        pen = QPen(rgba(INK, 0.2 if hover else 0.09), 2)  # discreta; más visible con el ratón
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(w - 6, pos + 2), QPointF(w - 6, pos + bar - 2))

    draw_delete(p, card, hover, hover_del)
    p.restore()


DEL_X, DEL_Y = -16, 16  # centro de la ×: a 16 px del borde derecho y del superior


def draw_delete(p, card, hover, hover_del):
    if hover and card.key != "_info":  # × discreta: quitar del escritorio
        bx, by = CARD + DEL_X, DEL_Y
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(rgba(INK, 0.16 if hover_del else 0.06))
        p.drawEllipse(QPointF(bx, by), DEL_R, DEL_R)
        pen = QPen(rgba(INK, 0.75 if hover_del else 0.4), 1.3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(bx - 2.8, by - 2.8), QPointF(bx + 2.8, by + 2.8))
        p.drawLine(QPointF(bx + 2.8, by - 2.8), QPointF(bx - 2.8, by + 2.8))


def local(card, px, py):
    """Punto de la ventana en coordenadas de la nota inclinada (0..CARD)."""
    dx, dy = px - (card.x + CARD / 2), py - (card.y + card.h / 2)
    ca, sa = math.cos(-card.tilt), math.sin(-card.tilt)
    return dx * ca - dy * sa + CARD / 2, dx * sa + dy * ca + card.h / 2


def contains(card, px, py):
    lx, ly = local(card, px, py)
    return 0 <= lx <= CARD and 0 <= ly <= card.h


def on_delete(card, px, py):
    lx, ly = local(card, px, py)
    return card.key != "_info" and (lx - CARD - DEL_X) ** 2 + (ly - DEL_Y) ** 2 <= DEL_R ** 2


def on_checkbox(card, px, py):
    """Fila de tarea cuyo círculo está bajo el puntero (o None)."""
    lx, ly = local(card, px, py)
    row = card.row_at(ly)
    if row and row[0] in ("todo", "done") and PAD - 3 <= lx <= PAD + 15:
        return row
    return None


def app_icon(size=64):
    """Ícono: post-it amarillo con cinta y la esquina doblada."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size / 64
    p.scale(s, s)
    p.translate(32, 34)
    p.rotate(-6)
    p.translate(-24, -24)
    paper = QPainterPath()
    paper.moveTo(4, 0)
    paper.lineTo(44, 0)
    paper.quadTo(48, 0, 48, 4)
    paper.lineTo(48, 44)
    paper.quadTo(48, 48, 44, 48)
    paper.lineTo(12, 48)
    paper.lineTo(0, 36)
    paper.lineTo(0, 4)
    paper.quadTo(0, 0, 4, 0)
    p.fillPath(paper.translated(1.5, 2.5), QColor(0, 0, 0, 60))
    p.fillPath(paper, rgba(PALETTE[0]))
    flap = QPainterPath()
    flap.moveTo(12, 48)
    flap.lineTo(0, 36)
    flap.lineTo(13, 35)
    flap.closeSubpath()
    p.fillPath(flap, rgba([v * 0.8 for v in PALETTE[0]]))
    p.setPen(QPen(rgba(INK, 0.55), 3, cap=Qt.PenCapStyle.RoundCap))
    for y in (17, 26, 35):
        p.drawLine(QPointF(10, y), QPointF(38 if y != 35 else 30, y))
    p.fillRect(QRectF(14, -6, 20, 10), QColor(255, 255, 255, 150))
    p.end()
    return pm


# ---------------------------------------------------------------------------
# Simplenote: sesión y sincronización (Simperium)
# ---------------------------------------------------------------------------

# app y bucket de Simplenote en Simperium (públicos en el código abierto de Simplenote)
SIMPERIUM_APP = "chalk-bump-f49"
SIMPERIUM_KEY = "a46d4d2a87444c33b8fc77e3662791b4"
API = f"https://api.simperium.com/1/{SIMPERIUM_APP}/note/"
AUTH = f"https://auth.simperium.com/1/{SIMPERIUM_APP}/authorize/"


def simplenote_profiles():
    """Carpetas de datos de la app de escritorio de Simplenote (Electron) en cada sistema."""
    home = os.path.expanduser("~")
    if IS_WIN:
        return [os.path.join(os.environ.get("APPDATA", home), "Simplenote")]
    if IS_MAC:
        return [os.path.join(home, "Library/Application Support/Simplenote")]
    conf = os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
    return [os.path.join(conf, "Simplenote"),
            os.path.join(home, ".var/app/com.simplenote.Simplenote/config/Simplenote"),  # Flatpak
            os.path.join(home, "snap/simplenote/current/.config/Simplenote")]             # Snap


def simplenote_token():
    """Token de la sesión de la app de escritorio de Simplenote: el "stored_user" de su
    localStorage (LevelDB). Solo se lee; si no hay sesión devuelve None."""
    files = []
    for profile in simplenote_profiles():
        storage = os.path.join(profile, "Local Storage", "leveldb")
        try:
            files += [os.path.join(storage, f) for f in os.listdir(storage) if f.endswith((".log", ".ldb"))]
        except OSError:
            pass
    for path in sorted(files, key=os.path.getmtime, reverse=True):  # el más reciente manda
        try:
            with open(path, "rb") as f:
                found = re.findall(rb'"accessToken":"([0-9a-f]{20,})"', f.read())
        except OSError:
            continue
        if found:
            return found[-1].decode()
    return None


def session_token():
    """Sesión propia (Ajustes → Cuenta) o, si no hay, la de la app de Simplenote."""
    return SETTINGS.get("token") or simplenote_token()


def simperium_login(email, password):
    """Inicio de sesión propio, para cuando no se puede leer la sesión de Simplenote."""
    req = urllib.request.Request(AUTH, data=json.dumps({"username": email, "password": password}).encode(),
                                 headers={"X-Simperium-API-Key": SIMPERIUM_KEY,
                                          "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as f:
        return json.load(f)["access_token"]


def parse_records(raw):
    """Formato de SIMPLEPOSTIT_FILE (demo) → [(id, contenido, etiquetas, markdown)]."""
    notes = []
    for rec in raw.split("\x1e") if raw else []:
        parts = rec.split("\x1f") + ["", "", ""]
        notes.append((parts[0], parts[1], [t for t in parts[2].split(",") if t], parts[3] == "md"))
    return notes


class Sync(QObject):
    """Hilo que lee las notas fijadas cada SETTINGS["poll"] segundos y envía los cambios del
    widget (crear, editar, etiquetas, desfijar, papelera); reintenta si no hay red."""
    notes = pyqtSignal(list)
    status = pyqtSignal(str)   # ok | nologin | offline

    def __init__(self):
        super().__init__()
        self.requests = queue.Queue()
        self.pending = []
        self.wake = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self):
        self.thread.start()

    def refresh(self):
        self.wake.set()

    def request(self, op, key=None, **data):
        self.requests.put((op, key, data))
        self.wake.set()

    def call(self, token, path, body=None):
        req = urllib.request.Request(API + path, data=None if body is None else json.dumps(body).encode(),
                                     headers={"X-Simperium-Token": token,
                                              "Content-Type": "application/json"},
                                     method="GET" if body is None else "POST")
        with urllib.request.urlopen(req, timeout=30) as f:
            data = f.read()
        return json.loads(data) if data.strip() else None

    def apply(self, token, op, key, data):
        now = time.time()
        if op == "create":
            note = {"content": data["content"], "tags": [],
                    "systemTags": ["pinned", "markdown"] if data.get("md") else ["pinned"],
                    "deleted": False, "shareURL": "", "publishURL": "",
                    "creationDate": now, "modificationDate": now}
            self.call(token, "i/" + uuid.uuid4().hex, note)
            return
        note = self.call(token, "i/" + key)
        if op == "edit":
            note["content"] = data["content"]
        elif op == "tags":
            note["tags"] = data["tags"]
        elif op == "unpin":
            note["systemTags"] = [t for t in note.get("systemTags", []) if t != "pinned"]
        elif op == "trash":
            note["deleted"] = True
        note["modificationDate"] = now
        self.call(token, "i/" + key, note)

    def flush(self, token):
        while not self.requests.empty():
            self.pending.append(self.requests.get())
        while self.pending:
            try:
                self.apply(token, *self.pending[0])
            except urllib.error.HTTPError as e:
                if e.code not in (400, 404):  # 401 / errores del servidor: reintentar
                    raise
            self.pending.pop(0)

    def fetch(self, token):
        notes, mark = [], None
        while True:
            page = self.call(token, "index?data=1&limit=100" + (f"&mark={mark}" if mark else ""))
            notes += [e for e in page.get("index", [])
                      if "pinned" in e["d"].get("systemTags", []) and not e["d"].get("deleted")]
            mark = page.get("mark")
            if not mark:
                break
        notes.sort(key=lambda e: e["d"].get("modificationDate", 0), reverse=True)
        return [(e["id"], (e["d"].get("content") or "").strip(), e["d"].get("tags", []),
                 "markdown" in e["d"].get("systemTags", [])) for e in notes]

    def run(self):
        while True:
            if DEMO_FILE:
                try:
                    with open(DEMO_FILE, encoding="utf-8") as f:
                        self.notes.emit(parse_records(f.read()))
                except OSError:
                    self.status.emit("offline")
            else:
                token = session_token()
                try:
                    if not token:
                        raise PermissionError
                    self.flush(token)
                    self.notes.emit(self.fetch(token))
                except (PermissionError, urllib.error.HTTPError) as e:
                    nologin = isinstance(e, PermissionError) or e.code == 401
                    self.status.emit("nologin" if nologin else "offline")
                except (OSError, ValueError, KeyError, TypeError):
                    self.status.emit("offline")
            self.wake.wait(max(3, int(SETTINGS["poll"])))
            self.wake.clear()


# ---------------------------------------------------------------------------
# ventanas de otras apps: X11 (Linux), Win32 y AppKit (macOS)
# ---------------------------------------------------------------------------

if IS_LINUX:
    import ctypes
    import ctypes.util

    class _XClientMessage(ctypes.Structure):
        _fields_ = [("type", ctypes.c_int), ("serial", ctypes.c_ulong), ("send_event", ctypes.c_int),
                    ("display", ctypes.c_void_p), ("window", ctypes.c_ulong),
                    ("message_type", ctypes.c_ulong), ("format", ctypes.c_int),
                    ("data", ctypes.c_long * 5)]

    class _XEvent(ctypes.Union):
        _fields_ = [("xclient", _XClientMessage), ("pad", ctypes.c_long * 24)]


class X11:
    """Lo mínimo de Xlib (ctypes) para EWMH: estados de ventana, todos los escritorios y
    ocultar/mostrar la ventana de Simplenote. Solo en el hilo principal."""

    def __init__(self):
        self.dpy = None
        if not IS_LINUX or QGuiApplication.platformName() != "xcb":
            return
        try:
            x = ctypes.cdll.LoadLibrary(ctypes.util.find_library("X11") or "libX11.so.6")
        except OSError:
            return
        x.XOpenDisplay.restype = ctypes.c_void_p
        x.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x.XDefaultRootWindow.restype = ctypes.c_ulong
        x.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        x.XInternAtom.restype = ctypes.c_ulong
        x.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        x.XGetWindowProperty.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_long,
                                         ctypes.c_long, ctypes.c_int, ctypes.c_ulong,
                                         ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_int),
                                         ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
                                         ctypes.POINTER(ctypes.c_void_p)]
        x.XQueryTree.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
                                 ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_void_p),
                                 ctypes.POINTER(ctypes.c_uint)]
        x.XGetGeometry.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong)] + \
            [ctypes.POINTER(ctypes.c_int)] * 2 + [ctypes.POINTER(ctypes.c_uint)] * 4
        x.XSendEvent.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_long,
                                 ctypes.POINTER(_XEvent)]
        x.XWithdrawWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int]
        x.XMapRaised.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        x.XRaiseWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        x.XFlush.argtypes = [ctypes.c_void_p]
        x.XFree.argtypes = [ctypes.c_void_p]
        # una ventana de Simplenote puede cerrarse entre dos consultas: sin esto, el
        # BadWindow de Xlib terminaría el proceso
        handler = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
        self._on_error = handler(lambda dpy, ev: 0)
        x.XSetErrorHandler.argtypes = [handler]
        x.XSetErrorHandler(self._on_error)
        self.x = x
        self.dpy = x.XOpenDisplay(None)
        self.root = x.XDefaultRootWindow(self.dpy) if self.dpy else 0

    def atom(self, name):
        return self.x.XInternAtom(self.dpy, name.encode(), 0)

    def prop(self, win, name, kind=0):
        """Propiedad como bytes (STRING) o lista de enteros (ventanas/cardinales)."""
        t, fmt, n, after, data = (ctypes.c_ulong(), ctypes.c_int(), ctypes.c_ulong(),
                                  ctypes.c_ulong(), ctypes.c_void_p())
        if self.x.XGetWindowProperty(self.dpy, win, self.atom(name), 0, 4096, 0, kind, ctypes.byref(t),
                                     ctypes.byref(fmt), ctypes.byref(n), ctypes.byref(after),
                                     ctypes.byref(data)) != 0 or not data.value:
            return None
        try:
            if fmt.value == 8:
                return ctypes.string_at(data.value, n.value)
            return list((ctypes.c_ulong * n.value).from_address(data.value))
        finally:
            self.x.XFree(data)

    def message(self, win, name, values):
        ev = _XEvent()
        ev.xclient.type = 33  # ClientMessage
        ev.xclient.send_event = 1
        ev.xclient.window = win
        ev.xclient.message_type = self.atom(name)
        ev.xclient.format = 32
        for i, v in enumerate(values[:5]):
            ev.xclient.data[i] = v
        mask = (1 << 19) | (1 << 20)  # SubstructureNotify | SubstructureRedirect
        self.x.XSendEvent(self.dpy, self.root, 0, mask, ctypes.byref(ev))
        self.x.XFlush(self.dpy)

    def desktop_widget(self, win):
        """Debajo de las demás, en todos los escritorios y fuera de la barra de tareas."""
        if not self.dpy:
            return
        self.message(win, "_NET_WM_DESKTOP", [0xFFFFFFFF, 2])
        for a, b in (("_NET_WM_STATE_STICKY", "_NET_WM_STATE_BELOW"),
                     ("_NET_WM_STATE_SKIP_TASKBAR", "_NET_WM_STATE_SKIP_PAGER")):
            self.message(win, "_NET_WM_STATE", [1, self.atom(a), self.atom(b), 2])

    def keep_over_below(self, win):
        """Por encima de las otras ventanas «debajo» (p. ej. conky arrancado después),
        sin salir de esa capa: sigue bajo las ventanas normales."""
        if not self.dpy:
            return
        stack = self.prop(self.root, "_NET_CLIENT_LIST_STACKING") or []
        if win not in stack:
            return
        below = self.atom("_NET_WM_STATE_BELOW")
        if any(below in (self.prop(w, "_NET_WM_STATE") or []) for w in stack[stack.index(win) + 1:]):
            self.x.XRaiseWindow(self.dpy, win)
            self.x.XFlush(self.dpy)

    def children(self, win):
        root, parent, kids, n = ctypes.c_ulong(), ctypes.c_ulong(), ctypes.c_void_p(), ctypes.c_uint()
        if not self.x.XQueryTree(self.dpy, win, ctypes.byref(root), ctypes.byref(parent),
                                 ctypes.byref(kids), ctypes.byref(n)) or not kids.value:
            return []
        try:
            return list((ctypes.c_ulong * n.value).from_address(kids.value))
        finally:
            self.x.XFree(kids)

    def area(self, win):
        r, xy, size = ctypes.c_ulong(), [ctypes.c_int() for _ in range(2)], [ctypes.c_uint() for _ in range(4)]
        if not self.x.XGetGeometry(self.dpy, win, ctypes.byref(r), *[ctypes.byref(v) for v in xy],
                                   *[ctypes.byref(v) for v in size]):
            return 0
        return size[0].value * size[1].value

    def find_class(self, wm_class):
        """La ventana con ese WM_CLASS que maneja el gestor de ventanas (tiene WM_STATE) y,
        entre ellas, la más grande: Electron crea además ventanas internas que nunca muestra."""
        best, best_rank = None, (False, 0)
        for top in self.children(self.root):
            for win in [top] + self.children(top):  # el gestor de ventanas pone marcos
                cls = self.prop(win, "WM_CLASS")
                if cls and wm_class.lower() in cls.decode(errors="replace").lower().split("\0"):
                    rank = (self.prop(win, "WM_STATE") is not None, self.area(win))
                    if rank > best_rank:
                        best, best_rank = win, rank
        return best

    def withdraw(self, win):
        self.x.XWithdrawWindow(self.dpy, win, 0)
        self.x.XFlush(self.dpy)

    def activate(self, win):
        self.x.XMapRaised(self.dpy, win)
        self.x.XFlush(self.dpy)
        self.message(win, "_NET_ACTIVE_WINDOW", [2, 0, 0])

    def visible(self, win):
        state = self.prop(win, "WM_STATE")
        return bool(state) and state[0] == 1  # NormalState


class SimplenoteApp(QObject):
    """La app de escritorio de Simplenote, controlada desde fuera (sin modificarla):
    abrirla, ocultar su ventana (sin ícono en la barra de tareas) y volver a mostrarla."""
    BUNDLE = "com.automattic.simplenote"

    def __init__(self, x11):
        super().__init__()
        self.x11 = x11
        self.win = None          # ventana encontrada (X11) o HWND (Windows)
        self.waiting = None      # temporizador mientras arranca
        self.proc = None

    # --- encontrar, abrir
    def command(self):
        if IS_WIN:
            for base in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("PROGRAMFILES", "")):
                for rel in ("Programs\\simplenote\\Simplenote.exe", "Simplenote\\Simplenote.exe"):
                    path = os.path.join(base, rel)
                    if os.path.exists(path):
                        return [path]
            return None
        if IS_MAC:
            return ["open", "-g", "-b", self.BUNDLE]
        for path in ("/usr/bin/simplenote", "/opt/Simplenote/simplenote", "/snap/bin/simplenote"):
            if os.path.exists(path):
                return [path]
        found = shutil.which("simplenote")
        if found:
            return [found]
        if shutil.which("flatpak"):
            return ["flatpak", "run", "com.simplenote.Simplenote"]
        return None

    def installed(self):
        return self.command() is not None or any(os.path.isdir(p) for p in simplenote_profiles())

    def window(self):
        if IS_LINUX and self.x11.dpy:
            if not self.win or not self.x11.prop(self.win, "WM_CLASS"):
                self.win = self.x11.find_class("simplenote")
            elif self.x11.prop(self.win, "WM_STATE") is None:  # interna, o aún no se mostraba
                self.win = self.x11.find_class("simplenote") or self.win
            return self.win
        if IS_WIN:
            if not self.win or not _user32().IsWindow(self.win):
                self.win = _win_find_simplenote()
            return self.win
        return None

    def running(self):
        if IS_MAC:
            return _mac_app(self.BUNDLE) is not None
        return self.window() is not None

    def launch(self, hidden):
        cmd = self.command()
        if not cmd:
            return False
        self.proc = subprocess.Popen(cmd, cwd=os.path.expanduser("~"), stdin=subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     start_new_session=not IS_WIN)
        threading.Thread(target=self.proc.wait, daemon=True).start()  # sin procesos zombi
        if hidden:
            self.keep_hidden()
        return True

    def keep_hidden(self, seconds=20):
        """Oculta la ventana en cuanto se muestre y sigue vigilando un rato: Electron crea
        la ventana antes de mostrarla (ocultarla entonces no sirve) y a veces la vuelve a
        mostrar al terminar de cargar."""
        if self.waiting:
            self.waiting.stop()
        tries = [0]

        def poll():
            tries[0] += 1
            if self.running() and self.visible():
                self.hide()
            if tries[0] * 0.25 > seconds:
                self.waiting.stop()
        self.waiting = QTimer(self)
        self.waiting.timeout.connect(poll)
        self.waiting.start(250)

    def stop_hiding(self):
        if self.waiting:
            self.waiting.stop()

    # --- mostrar / ocultar
    def visible(self):
        if IS_MAC:
            app = _mac_app(self.BUNDLE)
            return bool(app) and not app.isHidden()
        win = self.window()
        if not win:
            return False
        if IS_WIN:
            return bool(_user32().IsWindowVisible(win))
        return self.x11.visible(win)

    def show(self):
        self.stop_hiding()
        if not self.running():
            return self.launch(hidden=False)
        if IS_MAC:
            app = _mac_app(self.BUNDLE)
            app.unhide()
            app.activateWithOptions_(1 << 1)  # NSApplicationActivateIgnoringOtherApps
        elif IS_WIN:
            u = _user32()
            u.ShowWindow(self.win, 9 if u.IsIconic(self.win) else 5)  # SW_RESTORE / SW_SHOW
            u.SetForegroundWindow(self.win)
        else:
            self.x11.activate(self.window())
        return True

    def hide(self):
        if IS_MAC:
            app = _mac_app(self.BUNDLE)
            if app:
                app.hide()
        elif IS_WIN:
            if self.window():
                _user32().ShowWindow(self.win, 0)  # SW_HIDE: tampoco queda en la barra de tareas
        elif self.window():
            self.x11.withdraw(self.win)

    def toggle(self):
        if self.running() and self.visible():
            self.hide()
        else:
            self.show()


def _user32():
    import ctypes
    return ctypes.windll.user32


def _win_find_simplenote():
    """HWND de la ventana principal de Simplenote.exe (la más grande con título)."""
    import ctypes
    from ctypes import wintypes
    u, k = ctypes.windll.user32, ctypes.windll.kernel32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        pid = wintypes.DWORD()
        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        h = k.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if h:
            buf, size = ctypes.create_unicode_buffer(512), wintypes.DWORD(512)
            if k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)) and \
                    buf.value.lower().endswith("\\simplenote.exe") and u.GetWindowTextLengthW(hwnd) > 0:
                r = wintypes.RECT()
                u.GetWindowRect(hwnd, ctypes.byref(r))
                found.append(((r.right - r.left) * (r.bottom - r.top), hwnd))
            k.CloseHandle(h)
        return True
    u.EnumWindows(each, 0)
    return max(found)[1] if found else None


def _mac_app(bundle):
    try:
        from AppKit import NSRunningApplication
    except ImportError:
        return None
    apps = NSRunningApplication.runningApplicationsWithBundleIdentifier_(bundle)
    return apps[0] if apps else None


class WinHotkey(QAbstractNativeEventFilter):
    """Atajo global en Windows (RegisterHotKey); llama a callback con WM_HOTKEY."""
    ID = 0x5150

    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.active = False

    def register(self, seq):
        import ctypes
        u = ctypes.windll.user32
        if self.active:
            u.UnregisterHotKey(None, self.ID)
            self.active = False
        combo = QKeySequence(seq)
        if combo.isEmpty():
            return True
        key = combo[0]
        mods = key.keyboardModifiers()
        flags = 0x4000  # MOD_NOREPEAT
        flags |= 0x2 if mods & Qt.KeyboardModifier.ControlModifier else 0
        flags |= 0x1 if mods & Qt.KeyboardModifier.AltModifier else 0
        flags |= 0x4 if mods & Qt.KeyboardModifier.ShiftModifier else 0
        flags |= 0x8 if mods & Qt.KeyboardModifier.MetaModifier else 0
        k = key.key()
        if Qt.Key.Key_A.value <= k.value <= Qt.Key.Key_Z.value or Qt.Key.Key_0.value <= k.value <= Qt.Key.Key_9.value:
            vk = k.value
        elif Qt.Key.Key_F1.value <= k.value <= Qt.Key.Key_F24.value:
            vk = 0x70 + k.value - Qt.Key.Key_F1.value
        else:
            return False
        self.active = bool(u.RegisterHotKey(None, self.ID, flags, vk))
        return self.active

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            import ctypes
            from ctypes import wintypes
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam == self.ID:  # WM_HOTKEY
                self.callback()
                return True, 0
        return False, 0


# ---------------------------------------------------------------------------
# inicio con la sesión y atajo global (según el sistema)
# ---------------------------------------------------------------------------

def launch_command():
    """Cómo arrancar esta misma app (ejecutable de PyInstaller, comando instalado o script)."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    installed = shutil.which("simplepostit")
    if installed:
        return [installed]
    return [sys.executable, os.path.realpath(__file__)]


AUTOSTART_LINUX = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
                               "autostart", "simplepostit.desktop")
AUTOSTART_MAC = os.path.expanduser("~/Library/LaunchAgents/com.frankmncrf.simplepostit.plist")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def set_autostart(on):
    cmd = launch_command() + ["--autostart"]
    if IS_WIN:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            if on:
                winreg.SetValueEx(k, APP, 0, winreg.REG_SZ, subprocess.list2cmdline(cmd))
            else:
                try:
                    winreg.DeleteValue(k, APP)
                except FileNotFoundError:
                    pass
    elif IS_MAC:
        if on:
            os.makedirs(os.path.dirname(AUTOSTART_MAC), exist_ok=True)
            args = "".join(f"<string>{a}</string>" for a in cmd)
            with open(AUTOSTART_MAC, "w", encoding="utf-8") as f:
                f.write('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0"><dict>'
                        '<key>Label</key><string>com.frankmncrf.simplepostit</string>'
                        f'<key>ProgramArguments</key><array>{args}</array>'
                        '<key>RunAtLoad</key><true/></dict></plist>\n')
        elif os.path.exists(AUTOSTART_MAC):
            os.remove(AUTOSTART_MAC)
    else:
        if on:
            os.makedirs(os.path.dirname(AUTOSTART_LINUX), exist_ok=True)
            with open(AUTOSTART_LINUX, "w", encoding="utf-8") as f:
                f.write("[Desktop Entry]\nType=Application\nName=SimplePost-It\n"
                        f"Comment={tr('Notas fijadas de Simplenote como post-its en el escritorio')}\n"
                        f"Exec={subprocess.list2cmdline(cmd)}\nIcon=simplepostit\nTerminal=false\n"
                        "StartupNotify=false\nX-GNOME-Autostart-enabled=true\n")
        elif os.path.exists(AUTOSTART_LINUX):
            os.remove(AUTOSTART_LINUX)


def xfce_shortcut(seq, old=""):
    """En XFCE el atajo global es un atajo de teclado del escritorio que ejecuta --toggle."""
    if not shutil.which("xfconf-query"):
        return False

    def key(s):
        combo = QKeySequence(s)
        if combo.isEmpty():
            return None
        k = combo[0]
        mods = k.keyboardModifiers()
        name = QKeySequence(k.key().value).toString().lower()
        return ("/commands/custom/" + ("<Primary>" if mods & Qt.KeyboardModifier.ControlModifier else "")
                + ("<Alt>" if mods & Qt.KeyboardModifier.AltModifier else "")
                + ("<Shift>" if mods & Qt.KeyboardModifier.ShiftModifier else "")
                + ("<Super>" if mods & Qt.KeyboardModifier.MetaModifier else "") + name)

    run = lambda *a: subprocess.run(["xfconf-query", "-c", "xfce4-keyboard-shortcuts", *a],  # noqa: E731
                                    capture_output=True, text=True)
    for prop in {key(old), key(seq)} - {None}:  # quitar el atajo anterior si era nuestro
        if "simplepostit" in run("-p", prop).stdout:
            run("-p", prop, "-r")
    prop = key(seq)
    if not prop:
        return True
    current = run("-p", prop).stdout.strip()
    if current and "simplepostit" not in current:
        return False  # ocupado por otra cosa
    run("-p", prop, "-n", "-t", "string", "-s", subprocess.list2cmdline(launch_command() + ["--toggle"]))
    return True


# ---------------------------------------------------------------------------
# mini editor
# ---------------------------------------------------------------------------

def confirm_trash(title, parent=None):
    """Pregunta antes de mandar la nota completa a la papelera de Simplenote."""
    box = QMessageBox(QMessageBox.Icon.Question, tr("Mover a la papelera"),
                      tr("¿Mover «{0}» a la papelera?").format(title), parent=parent)
    box.setInformativeText(tr("Se puede recuperar desde la papelera de Simplenote."))
    ok = box.addButton(tr("Mover a la papelera"), QMessageBox.ButtonRole.DestructiveRole)
    box.addButton(tr("Cancelar"), QMessageBox.ButtonRole.RejectRole)
    if parent is None:  # desde el tablero: que no quede detrás de las notas
        box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
    box.exec()
    return box.clickedButton() is ok


class NoteEditor(QWidget):
    """Escribir una nota nueva o editar una existente; se guarda en la cuenta de Simplenote."""
    open_editors = []

    def __init__(self, sync, key=None, content="", on_saved=None, on_trashed=None):
        # Tool: sin ícono en la barra de tareas ni en el dock (se quedaba pegado al cerrar)
        flags = Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint
        if not IS_MAC:
            flags |= Qt.WindowType.Tool
        super().__init__(None, flags)
        self.sync, self.key, self.original = sync, key, content
        self.on_saved, self.on_trashed = on_saved, on_trashed
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(tr("Editar nota") if key else tr("Nueva nota"))
        self.setWindowIcon(QIcon(app_icon()))
        self.resize(420, 330)
        lay = QVBoxLayout(self)
        hint = QLabel(tr("<small>La primera línea es el título. Usa <tt>- [ ] tarea</tt> para pendientes. "
                         "Ctrl+Enter guarda.</small>"))
        lay.addWidget(hint)
        self.text = QPlainTextEdit()
        self.text.setPlainText(content)
        lay.addWidget(self.text, 1)
        bar = QHBoxLayout()
        self.markdown = None
        if key:  # borrar solo desde aquí (o desde Simplenote)
            trash = QPushButton(tr("Mover a la papelera"))
            trash.setStyleSheet("QPushButton { color: white; background: #c0392b; border-radius: 4px; "
                                "padding: 5px 12px; } QPushButton:hover { background: #d9463a; }")
            trash.clicked.connect(self.trash)
            bar.addWidget(trash)
        else:  # nota nueva: con o sin Markdown
            self.markdown = QCheckBox("Markdown")
            self.markdown.setToolTip(tr("Activa Markdown en Simplenote: **negrita**, *cursiva*, "
                                        "`código`, ## subtítulos, [enlace](url)"))
            bar.addWidget(self.markdown)
        bar.addStretch(1)
        cancel = QPushButton(tr("Cancelar"))
        cancel.clicked.connect(self.close)
        save = QPushButton(tr("Guardar en Simplenote"))
        save.setDefault(True)
        save.clicked.connect(self.save)
        bar.addWidget(cancel)
        bar.addWidget(save)
        lay.addLayout(bar)
        QShortcut(QKeySequence("Escape"), self, self.close)
        QShortcut(QKeySequence("Ctrl+Return"), self, self.save)
        QShortcut(QKeySequence("Ctrl+Enter"), self, self.save)
        # centrado en el monitor (no encima de las notas), por delante y con el cursor listo
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.center().x() - self.width() // 2, screen.center().y() - self.height() // 2)
        NoteEditor.open_editors.append(self)
        self.show()
        self.raise_()
        self.activateWindow()
        QTimer.singleShot(150, self.grab_focus)
        cursor = self.text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.text.setTextCursor(cursor)

    def grab_focus(self):
        # algunos gestores de ventanas no le dan el foco a una ventana nueva de una app sin foco
        self.raise_()
        self.activateWindow()
        self.text.setFocus()

    def closeEvent(self, ev):
        if self in NoteEditor.open_editors:
            NoteEditor.open_editors.remove(self)
        super().closeEvent(ev)

    def trash(self):
        if confirm_trash(parse(self.original)[0], self):
            self.sync.request("trash", self.key)
            if self.on_trashed:
                self.on_trashed(self.key)
            self.close()

    def save(self):
        content = self.text.toPlainText().strip()
        if content and content != self.original:
            if self.key:
                self.sync.request("edit", self.key, content=content)
                if self.on_saved:
                    self.on_saved(self.key, content)
            else:
                self.sync.request("create", content=content,
                                  md=bool(self.markdown and self.markdown.isChecked()))
        self.close()


# ---------------------------------------------------------------------------
# el tablero de notas
# ---------------------------------------------------------------------------

class Board(QWidget):
    """Ventana transparente sobre el escritorio, bajo las demás ventanas, con las notas."""
    moved = pyqtSignal()   # el tablero se arrastró a otro sitio (con Ajustes abierto)

    def __init__(self, sync, x11, simplenote):
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
                 | Qt.WindowType.WindowStaysOnBottomHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        super().__init__(None, flags)
        self.sync, self.x11, self.simplenote = sync, x11, simplenote
        self.setWindowTitle(APP)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        if IS_MAC:
            self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)
        self.setMouseTracking(True)

        self.raw = None          # última lista recibida de Simplenote (None: aún no hay)
        self.status = "connecting"
        self.overflow = 0
        self.tags = {}           # id -> etiquetas de Simplenote
        self.md = {}             # id -> Markdown activado en Simplenote
        self.notes = []          # (id, contenido) en el orden de Simplenote
        self.cards = []
        self.z = []              # ids de atrás hacia adelante
        self.pos = {}            # id -> [x, y] dentro del tablero
        self.tilts = {}          # id -> inclinación elegida (radianes)
        self.colors = {}         # id -> índice de PALETTE elegido a mano
        self.collapsed = set()   # notas minimizadas (solo el título)
        self.drag = None         # [card, dx, dy, x0, y0, movida]
        self.board_drag = None   # puntero - esquina del tablero, al arrastrar el tablero entero
        self.hover = None        # nota bajo el puntero
        self.hover_del = self.hover_plus = self.hover_grid = False
        self.hidden = set()      # notas desfijadas o en la papelera, aún en la última lista
        self.edited = {}         # id -> contenido editado aún no sincronizado
        self.tag_edits = {}      # id -> etiquetas cambiadas aún no sincronizadas
        self.loaded = False      # la primera carga no anima
        self.outline = False     # contorno del tablero (al arrastrar o en Ajustes)
        self.anim = QTimer(self)
        self.anim.timeout.connect(self.tick)
        if IS_LINUX and x11.dpy:
            self.restack = QTimer(self, interval=2000)
            self.restack.timeout.connect(lambda: self.isVisible() and x11.keep_over_below(int(self.winId())))
            self.restack.start()
        # monitores conectados o quitados (p. ej. el dock), otro principal u otra resolución:
        # volver a colocar el tablero cuando la pantalla se asiente
        self.replace_timer = QTimer(self, singleShot=True, interval=1500)
        self.replace_timer.timeout.connect(self.resize_board)
        qapp = QGuiApplication.instance()
        qapp.primaryScreenChanged.connect(self.screens_changed)
        qapp.screenAdded.connect(self.screens_changed)
        qapp.screenRemoved.connect(self.screens_changed)
        for screen in qapp.screens():
            screen.geometryChanged.connect(self.replace_timer.start)
        self.load_layout()
        sync.notes.connect(self.on_notes)
        sync.status.connect(self.on_status)
        self.resize_board()
        self.rebuild()

    # --- posición en la pantalla ----------------------------------------------------
    def screen_geometry(self):
        screens = QGuiApplication.screens()
        idx = int(SETTINGS["monitor"])
        screen = screens[idx] if 0 <= idx < len(screens) else QGuiApplication.primaryScreen()
        return screen.geometry()

    def resize_board(self):
        w, h = BOARD_W + 2 * MARGIN, BOARD_H + 2 * MARGIN
        self.setFixedSize(w, h)
        g = self.screen_geometry()
        anchor = SETTINGS["anchor"] if SETTINGS["anchor"] in ANCHORS else "top_right"
        self.move(*board_origin((g.x(), g.y(), g.width(), g.height()), (w, h), anchor,
                                int(SETTINGS["offset_x"]), int(SETTINGS["offset_y"])))

    def screens_changed(self, screen=None):
        if screen is not None and screen in QGuiApplication.screens():  # recién conectado
            screen.geometryChanged.connect(self.replace_timer.start)
        self.replace_timer.start()

    def store_position(self):
        """Guarda dónde está ahora el tablero: monitor y distancias a la esquina elegida."""
        screens = QGuiApplication.screens()
        screen = QGuiApplication.screenAt(self.geometry().center()) or self.screen()
        if screen in screens and not (SETTINGS["monitor"] == -1
                                      and screen is QGuiApplication.primaryScreen()):
            SETTINGS["monitor"] = screens.index(screen)
        g = self.screen_geometry()
        anchor = SETTINGS["anchor"] if SETTINGS["anchor"] in ANCHORS else "top_right"
        SETTINGS["offset_x"], SETTINGS["offset_y"] = board_offsets(
            (g.x(), g.y(), g.width(), g.height()), (self.x(), self.y()), (self.width(), self.height()), anchor)
        save_settings(SETTINGS)
        self.moved.emit()

    def showEvent(self, ev):
        super().showEvent(ev)
        QTimer.singleShot(200, self.desktop_level)

    def desktop_level(self):
        """Pegada al escritorio en cada sistema (lo que Qt no hace por sí solo)."""
        if IS_LINUX:
            self.x11.desktop_widget(int(self.winId()))
        elif IS_MAC:
            try:
                import objc
                from AppKit import NSWindowCollectionBehaviorCanJoinAllSpaces, NSWindowCollectionBehaviorStationary
                view = objc.objc_object(c_void_p=int(self.winId()))
                win = view.window()
                win.setLevel_(-2147483623 + 20)  # justo sobre el escritorio (kCGDesktopWindowLevel)
                win.setCollectionBehavior_(NSWindowCollectionBehaviorCanJoinAllSpaces
                                           | NSWindowCollectionBehaviorStationary)
            except Exception:  # sin pyobjc: queda como ventana normal "abajo"
                pass
        self.update_mask()

    # --- datos ----------------------------------------------------------------------
    def load_layout(self):
        try:
            with open(LAYOUT, encoding="utf-8") as f:
                data = json.load(f)
            self.pos = {k: list(v) for k, v in data.get("pos", {}).items()}
            self.z = list(data.get("z", []))
            self.tilts = dict(data.get("tilt", {}))
            self.colors = dict(data.get("color", {}))
            self.collapsed = set(data.get("collapsed", []))
        except (OSError, ValueError):
            pass

    def save_layout(self):
        os.makedirs(state_dir(), exist_ok=True)
        with open(LAYOUT + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"pos": self.pos, "z": self.z, "tilt": self.tilts, "color": self.colors,
                       "collapsed": sorted(self.collapsed)}, f)
        os.replace(LAYOUT + ".tmp", LAYOUT)

    def on_status(self, status):
        if status != self.status:
            self.status = status
            if self.raw is None or status == "nologin":
                self.rebuild()

    def on_notes(self, records):
        was_ok, self.status = self.status == "ok", "ok"
        if records != self.raw or not was_ok:
            first = self.raw is None
            self.raw = records
            self.overflow = max(0, len(records) - MAX_NOTES)  # fijadas que no caben
            records = records[:MAX_NOTES]
            notes = [(k, c) for k, c, _t, _m in records]
            self.tags = {k: t for k, _c, t, _m in records}
            self.md = {k: m for k, _c, _t, m in records}
            self.hidden &= {k for k, _ in notes}
            # un cambio se da por sincronizado cuando Simplenote ya trae ese contenido
            self.edited = {k: v for k, v in self.edited.items() if dict(notes).get(k, v) != v}
            self.tag_edits = {k: v for k, v in self.tag_edits.items() if self.tags.get(k) != v}
            self.notes = notes
            self.loaded = not first
            self.rebuild()
            self.loaded = True

    def rebuild(self):
        scroll = {c.key: c.scroll for c in self.cards}
        if self.status == "nologin":
            cards = [Card("_info", tr("Inicia sesión en Simplenote\nSimplePost-It usa la sesión de la app "
                                      "de escritorio de Simplenote. Ábrela e inicia sesión, o entra en "
                                      "Ajustes → Cuenta."))]
        elif self.raw is None:
            cards = [Card("_info", tr("Conectando con Simplenote…") if self.status == "connecting" else
                          tr("Sin conexión\nSe vuelve a intentar cada pocos segundos."))]
        else:
            cards = [Card(k, self.edited.get(k, n), self.tag_edits.get(k, self.tags.get(k, ())),
                          self.md.get(k, False))
                     for k, n in self.notes if k not in self.hidden]
            if not cards:
                cards = [Card("_info", tr("Sin notas fijadas\nFija una nota en Simplenote (Pin to top) "
                                          "o crea una con +."))]
        others = PALETTE[1:]
        old = {c.key: c for c in self.cards}
        for i, card in enumerate(cards):
            card.color = PALETTE[0] if i == 0 else others[(i - 1) % len(others)]
            if card.key in self.colors:
                card.color = PALETTE[self.colors[card.key] % len(PALETTE)]
            card.collapsed = card.key in self.collapsed
            card.scroll = min(scroll.get(card.key, 0), card.max_scroll())
            card.tilt = self.tilts.get(card.key, card.tilt)
            if card.key in old:  # sigue una animación en curso
                card.tx, card.ty, card.fade = old[card.key].tx, old[card.key].ty, old[card.key].fade
            if card.key in self.pos:
                card.x, card.y = (MARGIN + v for v in self.pos[card.key])
                if card.x > MARGIN + BOARD_W - CARD or card.y > MARGIN + BOARD_H - card.h:
                    # el tablero se achicó: que no quede fuera
                    card.x = min(card.x, MARGIN + BOARD_W - CARD)
                    card.y = min(card.y, MARGIN + BOARD_H - card.h)
        placed = [c for c in cards if c.key in self.pos]
        for card in cards:
            if card.key not in self.pos:
                # nota nueva: al hueco libre (o el menos tapado), lo más arriba a la derecha
                card.x, card.y = free_spot(placed, fnv(card.key))
                placed.append(card)
                if card.key != "_info":
                    self.pos[card.key] = [card.x - MARGIN, card.y - MARGIN]
                    self.save_layout()
                    if self.loaded:  # llega desde arriba, apareciendo
                        card.tx, card.ty, card.fade = card.x, card.y, 0.0
                        card.y = max(MARGIN, card.y - 40)
                        self.animate()
        if cards[0].key == "_info":
            cards[0].color = (0.93, 0.93, 0.95)
        self.cards = cards
        keys = [c.key for c in cards]
        kept = [k for k in self.z if k in keys]
        new = [k for k in reversed(keys) if k not in kept]   # nuevas: encima
        self.z = kept + new
        self.update_mask()
        self.update()

    def by_z(self):
        by_key = {c.key: c for c in self.cards}
        return [by_key[k] for k in self.z if k in by_key]

    # --- geometría --------------------------------------------------------------------
    def plus_center(self):
        return MARGIN + BOARD_W - PLUS_R, MARGIN + PLUS_R

    def grid_center(self):
        return MARGIN + BOARD_W - 3 * PLUS_R - 6, MARGIN + PLUS_R

    def update_mask(self):
        """Solo las notas y los botones reciben clics; el resto deja pasar al escritorio."""
        if self.outline or (self.drag and self.drag[5]):
            self.clearMask()
            return
        region = QRegion()
        for c in self.cards:
            pad = int(abs(math.sin(c.tilt)) * CARD) + 18  # incluye la sombra y la cinta
            region = region.united(QRegion(int(c.x) - pad, int(c.y) - pad, CARD + 2 * pad, int(c.h) + 2 * pad))
        for px, py in (self.plus_center(), self.grid_center()):
            region = region.united(QRegion(px - PLUS_R - 3, py - PLUS_R - 3, 2 * PLUS_R + 6, 2 * PLUS_R + 6))
        if self.overflow:
            region = region.united(QRegion(MARGIN, MARGIN, BOARD_W, 2 * PLUS_R))
        self.setMask(region)

    # --- dibujo -------------------------------------------------------------------------
    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
                         | QPainter.RenderHint.SmoothPixmapTransform)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        dragging = bool(self.drag and self.drag[5])
        if dragging or self.outline:  # zona donde se pueden soltar las notas
            pen = QPen(QColor(255, 255, 255, 90), 1.2)
            pen.setDashPattern([6, 5])
            p.setPen(pen)
            p.setBrush(QColor(255, 255, 255, 13))
            p.drawRect(QRectF(MARGIN - 6, MARGIN - 6, BOARD_W + 12, BOARD_H + 12))
        for card in self.by_z():
            hover = not dragging and card is self.hover
            draw_card(p, card, dragging and card is self.drag[0], hover, hover and self.hover_del)
        if self.overflow:  # aviso junto a los botones
            gx, gy = self.grid_center()
            p.setFont(font(11))
            p.setPen(rgba(PALETTE[0], 0.8))
            text = (tr("+{0} fijadas sin espacio") if self.overflow > 1 else tr("+{0} fijada sin espacio")
                    ).format(self.overflow)
            p.drawText(QRectF(MARGIN, gy - 9, gx - PLUS_R - 8 - MARGIN, 18),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, text)
        # botones + (nueva nota) y ▦ (ordenar)
        for (px, py), on, icon in ((self.plus_center(), self.hover_plus, "plus"),
                                   (self.grid_center(), self.hover_grid, "grid")):
            p.setPen(QPen(rgba(PALETTE[0], 0.85 if on else 0.5), 1))
            p.setBrush(rgba(PALETTE[0], 0.45 if on else 0.2))  # toque amarillo post-it
            p.drawEllipse(QPointF(px, py), PLUS_R, PLUS_R)
            ink = rgba(PALETTE[0], 1 if on else 0.75)
            if icon == "plus":
                pen = QPen(ink, 1.4)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawLine(QPointF(px - 4, py), QPointF(px + 4, py))
                p.drawLine(QPointF(px, py - 4), QPointF(px, py + 4))
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(ink)
                for gx in (-3.6, 0.6):
                    for gy in (-3.6, 0.6):
                        p.drawRect(QRectF(px + gx, py + gy, 3, 3))
        p.end()

    # --- animación ------------------------------------------------------------------------
    def animate(self):
        if not self.anim.isActive():
            self.anim.start(16)

    def tick(self):
        busy = False
        for c in self.cards:
            if c.tx is not None:
                c.x += (c.tx - c.x) * 0.22
                c.y += (c.ty - c.y) * 0.22
                if abs(c.tx - c.x) < 0.5 and abs(c.ty - c.y) < 0.5:
                    c.x, c.y, c.tx, c.ty = c.tx, c.ty, None, None
                else:
                    busy = True
            if c.fade < 1:
                c.fade = min(1.0, c.fade + 0.08)
                busy = True
        self.update()
        if not busy:
            self.anim.stop()
            self.update_mask()

    def arrange(self):
        """Cuadrícula alineada a la derecha, en el orden de Simplenote, con animación."""
        cards = [c for c in self.cards if c.key != "_info"]
        if not cards:
            return
        cols = max(1, min(3 if len(cards) <= 6 else 4, BOARD_W // (CARD // 2)))
        rows = math.ceil(len(cards) / cols)
        sx = min(CARD + 30, (BOARD_W - CARD) / max(1, cols - 1))
        sy = min(CARD + 40, (BOARD_H - CARD) / max(1, rows - 1))
        for i, c in enumerate(cards):
            r, k = divmod(i, cols)
            n = min(cols, len(cards) - r * cols)  # la última fila también pegada a la derecha
            x = BOARD_W - CARD - (n - 1 - k) * sx
            y = r * sy + fnv(c.key) % 9
            self.pos[c.key] = [x, y]
            c.tx, c.ty = MARGIN + x, MARGIN + y
        self.save_layout()
        self.animate()

    # --- ratón ----------------------------------------------------------------------------
    def card_at(self, x, y):
        for card in reversed(self.by_z()):
            if contains(card, x, y):
                return card
        return None

    def on_button(self, x, y, center):
        px, py = center
        return (x - px) ** 2 + (y - py) ** 2 <= (PLUS_R + 1) ** 2

    def mousePressEvent(self, ev):
        x, y = ev.position().x(), ev.position().y()
        if ev.button() == Qt.MouseButton.RightButton:
            card = self.card_at(x, y)
            if card is not None and card.key != "_info":
                self.menu(card)
            return
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        if self.on_button(x, y, self.plus_center()):
            self.new_note()
            return
        if self.on_button(x, y, self.grid_center()):
            self.arrange()
            return
        card = self.card_at(x, y)
        if card is None:
            if self.outline:  # con Ajustes abierto: arrastrar el tablero entero
                self.board_drag = ev.globalPosition().toPoint() - self.geometry().topLeft()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if on_delete(card, x, y):  # × = desfijar, no borra la nota
            self.unpin(card)
            return
        if card.key != "_info":
            row = on_checkbox(card, x, y)
            if row:  # marcar / desmarcar la tarea en Simplenote
                self.save_note(card.key, toggle_todo(card.note, card.items[row[2]][2]))
                return
            row = card.row_at(local(card, x, y)[1])
            if row and ev.modifiers() & Qt.KeyboardModifier.ControlModifier:  # Ctrl+clic: enlace
                url = card.url_at(row, local(card, x, y)[0])
                if url:
                    open_url(url)
                    return
        if self.z and self.z[-1] != card.key:  # al frente
            self.z.remove(card.key)
            self.z.append(card.key)
            self.save_layout()
            self.update()
        self.drag = [card, x - card.x, y - card.y, x, y, False]

    def mouseDoubleClickEvent(self, ev):
        if ev.button() != Qt.MouseButton.LeftButton:
            return
        x, y = ev.position().x(), ev.position().y()
        card = self.card_at(x, y)
        if card is None or card.key == "_info" or on_delete(card, x, y) or on_checkbox(card, x, y):
            if card is not None and card.key == "_info" and self.status == "nologin":
                self.simplenote.show()
            return
        self.drag = None
        if local(card, x, y)[1] < card.body_top or card.collapsed:
            self.simplenote.show()  # doble clic en el título: Simplenote
        else:
            self.edit(card)

    def mouseMoveEvent(self, ev):
        x, y = ev.position().x(), ev.position().y()
        if self.board_drag is not None:
            self.move(ev.globalPosition().toPoint() - self.board_drag)
            return
        if self.drag:
            card, dx, dy, x0, y0, moved = self.drag
            if not moved and abs(x - x0) + abs(y - y0) > 4:
                self.drag[5] = True
                self.update_mask()
            if self.drag[5]:
                card.tx = card.ty = None
                card.x = min(max(x - dx, MARGIN), MARGIN + BOARD_W - CARD)
                card.y = min(max(y - dy, MARGIN), MARGIN + BOARD_H - card.h)
                self.update()
            return
        hover_plus = self.on_button(x, y, self.plus_center())
        hover_grid = self.on_button(x, y, self.grid_center())
        card = self.card_at(x, y)
        hover_del = card is not None and on_delete(card, x, y)
        state = (hover_plus, hover_grid, card, hover_del)
        if state != (self.hover_plus, self.hover_grid, self.hover, self.hover_del):
            self.hover_plus, self.hover_grid, self.hover, self.hover_del = state
            self.update()
        on = hover_plus or hover_grid or card is not None
        self.setCursor(Qt.CursorShape.PointingHandCursor if on else
                       Qt.CursorShape.OpenHandCursor if self.outline else Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, ev):
        if self.board_drag is not None and ev.button() == Qt.MouseButton.LeftButton:
            self.board_drag = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.store_position()
            return
        if self.drag and ev.button() == Qt.MouseButton.LeftButton:
            card, moved = self.drag[0], self.drag[5]
            self.drag = None
            if moved:
                self.pos[card.key] = [card.x - MARGIN, card.y - MARGIN]
                self.save_layout()
            self.update_mask()
            self.update()

    def leaveEvent(self, _ev):
        if self.hover or self.hover_plus or self.hover_grid:
            self.hover, self.hover_plus, self.hover_grid, self.hover_del = None, False, False, False
            self.update()

    def wheelEvent(self, ev):
        x, y = ev.position().x(), ev.position().y()
        card = self.card_at(x, y)
        if card is None:
            return
        steps = ev.angleDelta().y() / 120 if ev.angleDelta().y() else ev.pixelDelta().y() / 40
        if ev.modifiers() & Qt.KeyboardModifier.ControlModifier and card.key != "_info":
            # Ctrl+rueda: inclinar la nota (±15°)
            card.tilt = min(max(card.tilt - math.radians(steps), math.radians(-15)), math.radians(15))
            self.tilts[card.key] = card.tilt
            self.save_layout()
            self.update_mask()
            self.update()
            return
        if card.max_scroll() == 0:
            return
        card.scroll = min(max(card.scroll - steps * 34, 0), card.max_scroll())
        self.update()

    # --- acciones -------------------------------------------------------------------------
    def new_note(self):
        NoteEditor(self.sync)

    def edit(self, card):
        content = dict(self.notes).get(card.key)
        if content is not None:
            NoteEditor(self.sync, card.key, self.edited.get(card.key, content), self.on_edited, self.trashed)

    def on_edited(self, key, content):
        self.edited[key] = content
        self.rebuild()

    def save_note(self, key, content):
        self.sync.request("edit", key, content=content)
        self.on_edited(key, content)

    def trashed(self, key):
        self.hidden.add(key)
        self.hover = None
        self.rebuild()

    def unpin(self, card):
        # se le quita el "pinned" en Simplenote; la nota sigue en la cuenta
        self.sync.request("unpin", card.key)
        self.trashed(card.key)

    def menu(self, card):
        menu = QMenu(self)
        colors = menu.addMenu(tr("Color"))
        auto = colors.addAction(tr("Automático"))
        auto.setCheckable(True)
        auto.setChecked(card.key not in self.colors)
        auto.triggered.connect(lambda: self.set_color(card, None))
        for i, name in enumerate(COLOR_NAMES):
            pm = QPixmap(14, 14)
            pm.fill(rgba(PALETTE[i]))
            act = colors.addAction(QIcon(pm), tr(name))
            act.setCheckable(True)
            act.setChecked(self.colors.get(card.key) == i)
            act.triggered.connect(lambda _c=False, i=i: self.set_color(card, i))
        menu.addAction(tr("Expandir") if card.collapsed else tr("Minimizar"),
                       lambda: self.toggle_collapse(card))
        private = menu.addAction(tr("Privada (texto borroso)"))
        private.setCheckable(True)
        private.setChecked(card.private)
        private.toggled.connect(lambda on: self.set_private(card, on))
        menu.addSeparator()
        menu.addAction(tr("Mover a la papelera"), lambda: self.trash(card))
        menu.exec(QCursor.pos())

    def trash(self, card):
        # la nota entera va a la papelera de Simplenote (la × solo la desfija)
        if confirm_trash(card.title):
            self.sync.request("trash", card.key)
            self.trashed(card.key)

    def set_color(self, card, index):
        if index is None:
            self.colors.pop(card.key, None)
        else:
            self.colors[card.key] = index
        self.save_layout()
        self.rebuild()

    def set_private(self, card, on):
        # etiqueta "privado" en Simplenote, así la marca viaja con la nota
        tags = [t for t in card.tags if t.lower() not in PRIVATE_TAGS] + (["privado"] if on else [])
        self.sync.request("tags", card.key, tags=tags)
        self.tag_edits[card.key] = tags
        self.rebuild()

    def toggle_collapse(self, card):
        self.collapsed ^= {card.key}
        self.save_layout()
        self.rebuild()

    def reset_tilts(self):
        self.tilts = {}
        self.save_layout()
        self.rebuild()

    def toggle_visible(self):
        self.setVisible(not self.isVisible())

    def apply(self):
        """Tras cambiar los Ajustes: medidas nuevas, misma disposición."""
        apply_settings()
        self.resize_board()
        self.rebuild()


# ---------------------------------------------------------------------------
# ajustes, acerca de, donaciones
# ---------------------------------------------------------------------------

def hotkey_note():
    if IS_MAC:
        return tr("En macOS el atajo global no está disponible; usa el ícono de la barra de menús.")
    if IS_LINUX and not shutil.which("xfconf-query"):
        cmd = subprocess.list2cmdline(launch_command() + ["--toggle"])
        return tr("En tu escritorio, crea un atajo de teclado que ejecute: {0}").format(cmd)
    return ""


class LoginDialog(QDialog):
    """Inicio de sesión propio con correo y contraseña de Simplenote (Simperium)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(tr("Iniciar sesión en Simplenote"))
        self.token = None
        lay = QVBoxLayout(self)
        info = QLabel(tr("Solo hace falta si SimplePost-It no puede usar la sesión de la app de "
                         "Simplenote (por ejemplo, con la versión de la Mac App Store). La contraseña "
                         "no se guarda: solo la sesión."))
        info.setWordWrap(True)
        lay.addWidget(info)
        form = QFormLayout()
        self.email = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(tr("Correo"), self.email)
        form.addRow(tr("Contraseña"), self.password)
        lay.addLayout(form)
        self.error = QLabel()
        self.error.setStyleSheet("color: #c0392b")
        lay.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.login)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.setMinimumWidth(420)

    def login(self):
        try:
            self.token = simperium_login(self.email.text().strip(), self.password.text())
        except urllib.error.HTTPError:
            self.error.setText(tr("Correo o contraseña incorrectos."))
            return
        except (OSError, ValueError, KeyError):
            self.error.setText(tr("No se pudo conectar con Simplenote."))
            return
        self.accept()


class SettingsDialog(QDialog):
    """Ajustes con efecto inmediato; mientras está abierta se ve el contorno del tablero."""

    def __init__(self, app):
        super().__init__(None, Qt.WindowType.Window)
        self.app = app
        self.setWindowTitle(tr("Ajustes de SimplePost-It"))
        self.setWindowIcon(QIcon(app_icon()))
        self.old_hotkey = SETTINGS["hotkey"]
        tabs = QTabWidget()
        tabs.addTab(self.general_tab(), tr("General"))
        tabs.addTab(self.notes_tab(), tr("Notas"))
        tabs.addTab(self.board_tab(), tr("Tablero"))
        tabs.addTab(self.account_tab(), tr("Cuenta"))
        tabs.addTab(self.about_tab(), tr("Acerca de"))
        lay = QVBoxLayout(self)
        lay.addWidget(tabs)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.close)
        lay.addWidget(close)
        self.setMinimumWidth(500)

    # --- utilidades
    def changed(self, key, value, relayout=False):
        SETTINGS[key] = value
        save_settings(SETTINGS)
        if relayout:
            self.app.board.apply()

    def spin(self, key, lo, hi, suffix="", relayout=True):
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setValue(int(SETTINGS[key]))
        s.setSuffix(suffix)
        s.valueChanged.connect(lambda v: self.changed(key, v, relayout))
        return s

    # --- pestañas
    def general_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        auto = QCheckBox(tr("Iniciar SimplePost-It al iniciar sesión"))
        auto.setChecked(bool(SETTINGS["autostart"]))
        auto.toggled.connect(self.set_autostart)
        form.addRow(auto)
        bg = QCheckBox(tr("Mantener Simplenote abierto en segundo plano (ventana oculta)"))
        bg.setToolTip(tr("SimplePost-It abre Simplenote al iniciar y oculta su ventana; se muestra con "
                         "doble clic en el título de una nota o desde el ícono de la bandeja."))
        bg.setChecked(bool(SETTINGS["simplenote_background"]))
        bg.toggled.connect(lambda on: self.changed("simplenote_background", on))
        form.addRow(bg)
        lang = QComboBox()
        for code, name in (("auto", tr("Automático")), ("es", "Español"), ("en", "English")):
            lang.addItem(name, code)
        lang.setCurrentIndex(max(0, lang.findData(SETTINGS["language"])))
        lang.currentIndexChanged.connect(lambda _i: self.changed("language", lang.currentData()))
        form.addRow(tr("Idioma"), lang)
        form.addRow("", QLabel(tr("<small>El idioma cambia al reiniciar SimplePost-It.</small>")))
        if not IS_MAC:
            row = QHBoxLayout()
            self.hotkey = QKeySequenceEdit(QKeySequence(SETTINGS["hotkey"]))
            self.hotkey.setMaximumSequenceLength(1)
            self.hotkey.editingFinished.connect(self.set_hotkey)
            clear = QPushButton(tr("Quitar"))
            clear.clicked.connect(lambda: (self.hotkey.clear(), self.set_hotkey()))
            row.addWidget(self.hotkey, 1)
            row.addWidget(clear)
            form.addRow(tr("Mostrar/ocultar notas"), row)
        note = hotkey_note()
        if note:
            label = QLabel(f"<small>{note}</small>")
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow("", label)
        self.hotkey_error = QLabel()
        self.hotkey_error.setStyleSheet("color: #c0392b")
        form.addRow("", self.hotkey_error)
        return w

    def notes_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        form.addRow(tr("Máximo de notas en el escritorio"), self.spin("max_notes", 1, 30))
        row = QHBoxLayout()
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(50, 100)
        slider.setValue(int(SETTINGS["opacity"]))
        value = QLabel(f"{SETTINGS['opacity']} %")
        slider.valueChanged.connect(lambda v: (value.setText(f"{v} %"), self.changed("opacity", v, True)))
        row.addWidget(slider, 1)
        row.addWidget(value)
        form.addRow(tr("Opacidad del papel"), row)
        form.addRow(tr("Tamaño de las notas"), self.spin("note_size", 160, 300, " px"))
        row = QHBoxLayout()
        row.addWidget(self.spin("tilt", 0, 12, "°"), 1)
        reset = QPushButton(tr("Restablecer inclinaciones"))
        reset.setToolTip(tr("Olvida las inclinaciones ajustadas con Ctrl+rueda"))
        reset.clicked.connect(self.app.board.reset_tilts)
        row.addWidget(reset)
        form.addRow(tr("Inclinación máxima"), row)
        row = QHBoxLayout()
        system = QCheckBox(tr("Fuente del sistema"))
        fonts = QFontComboBox()
        system.setChecked(not SETTINGS["font"])
        fonts.setEnabled(bool(SETTINGS["font"]))
        if SETTINGS["font"]:
            fonts.setCurrentFont(QFont(SETTINGS["font"]))
        system.toggled.connect(lambda on: (fonts.setEnabled(not on),
                                           self.changed("font", "" if on else fonts.currentFont().family(), True)))
        fonts.currentFontChanged.connect(lambda f: self.changed("font", f.family(), True))
        row.addWidget(system)
        row.addWidget(fonts, 1)
        form.addRow(tr("Fuente"), row)
        return w

    def board_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        mon = QComboBox()
        mon.addItem(tr("Principal"), -1)
        for i, s in enumerate(QGuiApplication.screens()):
            g = s.geometry()
            mon.addItem(f"{i + 1}: {s.name()} ({g.width()}×{g.height()})", i)
        mon.setCurrentIndex(max(0, mon.findData(int(SETTINGS["monitor"]))))
        mon.currentIndexChanged.connect(lambda _i: self.changed("monitor", mon.currentData(), True))
        form.addRow(tr("Monitor"), mon)
        form.addRow(tr("Ancho del tablero"), self.spin("board_width", 200, 4000, " px"))
        form.addRow(tr("Alto del tablero"), self.spin("board_height", 200, 3000, " px"))
        anchor = QComboBox()
        for key, name in zip(ANCHORS, (tr("Arriba a la izquierda"), tr("Arriba a la derecha"),
                                       tr("Abajo a la izquierda"), tr("Abajo a la derecha"))):
            anchor.addItem(name, key)
        anchor.setCurrentIndex(max(0, anchor.findData(SETTINGS["anchor"])))
        anchor.currentIndexChanged.connect(lambda _i: self.set_anchor(anchor.currentData()))
        form.addRow(tr("Esquina de referencia"), anchor)
        self.offset_x, self.offset_y = self.spin("offset_x", 0, 4000, " px"), self.spin("offset_y", 0, 3000, " px")
        form.addRow(tr("Distancia horizontal al borde"), self.offset_x)
        form.addRow(tr("Distancia vertical al borde"), self.offset_y)
        self.monitor_box = mon
        self.app.board.moved.connect(self.on_board_moved)
        arrange = QPushButton(tr("Ordenar las notas en cuadrícula"))
        arrange.clicked.connect(self.app.board.arrange)
        form.addRow("", arrange)
        hint = QLabel(tr("<small>Mientras esta ventana está abierta se ve el contorno del tablero; "
                         "arrastra un espacio vacío del tablero para moverlo a donde quieras.</small>"))
        hint.setWordWrap(True)
        form.addRow("", hint)
        return w

    def account_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.account = QLabel()
        self.account.setWordWrap(True)
        lay.addWidget(self.account)
        row = QHBoxLayout()
        self.login_btn = QPushButton(tr("Iniciar sesión con correo y contraseña…"))
        self.login_btn.clicked.connect(self.login)
        self.logout_btn = QPushButton(tr("Cerrar la sesión propia"))
        self.logout_btn.clicked.connect(self.logout)
        row.addWidget(self.login_btn)
        row.addWidget(self.logout_btn)
        row.addStretch(1)
        lay.addLayout(row)
        form = QFormLayout()
        form.addRow(tr("Revisar cambios cada"), self.spin("poll", 5, 300, " s", relayout=False))
        lay.addLayout(form)
        privacy = QLabel(tr("<small>SimplePost-It habla directamente con el servicio de sincronización de "
                            "Simplenote (Simperium) con tu sesión. Tus notas no pasan por ningún otro "
                            "servidor; en este equipo solo se guarda la posición y el aspecto de cada "
                            "nota.</small>"))
        privacy.setWordWrap(True)
        lay.addWidget(privacy)
        lay.addStretch(1)
        self.update_account()
        return w

    def update_account(self):
        own = bool(SETTINGS["token"])
        if own:
            text = tr("Sesión propia de SimplePost-It.")
        elif simplenote_token():
            text = tr("Usando la sesión de la app de escritorio de Simplenote.")
        else:
            text = tr("No se encontró la sesión de Simplenote. Abre Simplenote e inicia sesión, o inicia "
                      "sesión aquí con tu correo y contraseña.")
        self.account.setText(f"<b>{text}</b>")
        self.logout_btn.setVisible(own)

    def login(self):
        dlg = LoginDialog(self)
        if dlg.exec() and dlg.token:
            self.changed("token", dlg.token)
            self.app.sync.refresh()
        self.update_account()

    def logout(self):
        self.changed("token", "")
        self.app.sync.refresh()
        self.update_account()

    def about_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        head = QHBoxLayout()
        icon = QLabel()
        icon.setPixmap(app_icon(72))
        head.addWidget(icon)
        title = QLabel(f"<h2>{APP} {VERSION}</h2>"
                       + tr("<p>Tus notas fijadas de Simplenote como post-its en el escritorio.</p>"))
        title.setWordWrap(True)
        head.addWidget(title, 1)
        lay.addLayout(head)
        text = QLabel(f"<p>© 2026 FrankMncrf — <a href='{REPO_URL}'>{REPO_URL.replace('https://', '')}</a></p>"
                      + tr("<p>Software libre bajo la licencia GPL-3.0. Sin ninguna garantía.</p>"
                           "<p>Proyecto independiente: no está afiliado a Simplenote ni a Automattic.</p>"))
        text.setOpenExternalLinks(True)
        text.setWordWrap(True)
        lay.addWidget(text)
        row = QHBoxLayout()
        for label, slot in ((tr("Donar…"), self.app.donate),
                            (tr("Contribuir"), lambda: open_url(REPO_URL)),
                            (tr("Reportar un problema"), lambda: open_url(REPO_URL + "/issues/new")),
                            (tr("Licencias…"), self.app.licenses)):
            b = QPushButton(label)
            b.clicked.connect(slot)
            row.addWidget(b)
        lay.addLayout(row)
        lay.addStretch(1)
        return w

    # --- acciones
    def set_autostart(self, on):
        self.changed("autostart", on)
        try:
            set_autostart(on)
        except OSError:
            pass

    def set_hotkey(self):
        seq = self.hotkey.keySequence().toString()
        ok = self.app.set_hotkey(seq, self.old_hotkey)
        self.hotkey_error.setText("" if ok else tr("Ese atajo ya está en uso; elige otro."))
        if ok:
            self.old_hotkey = seq
            self.changed("hotkey", seq)

    def set_anchor(self, anchor):
        # el tablero no se mueve: solo cambia desde qué esquina se mide
        SETTINGS["anchor"] = anchor
        self.app.board.store_position()

    def on_board_moved(self):
        for box, key in ((self.offset_x, "offset_x"), (self.offset_y, "offset_y")):
            box.blockSignals(True)
            box.setValue(int(SETTINGS[key]))
            box.blockSignals(False)
        self.monitor_box.blockSignals(True)
        self.monitor_box.setCurrentIndex(max(0, self.monitor_box.findData(int(SETTINGS["monitor"]))))
        self.monitor_box.blockSignals(False)

    def showEvent(self, ev):
        super().showEvent(ev)
        self.app.board.outline = True
        self.app.board.update_mask()
        self.app.board.update()

    def closeEvent(self, ev):
        self.app.board.outline = False
        self.app.board.update_mask()
        self.app.board.update()
        super().closeEvent(ev)


# ---------------------------------------------------------------------------
# la aplicación: bandeja, instancia única, arranque
# ---------------------------------------------------------------------------

SERVER = "simplepostit-" + re.sub(r"\W", "", os.environ.get("USER") or os.environ.get("USERNAME") or "user")


class App(QObject):
    def __init__(self, qapp, autostarted):
        super().__init__()
        self.qapp = qapp
        self.x11 = X11()
        self.sync = Sync()
        self.simplenote = SimplenoteApp(self.x11)
        self.board = Board(self.sync, self.x11, self.simplenote)
        self.settings = None
        self.server = QLocalServer(self)
        QLocalServer.removeServer(SERVER)
        self.server.listen(SERVER)
        self.server.newConnection.connect(self.on_message)
        self.win_hotkey = None
        if IS_WIN:
            self.win_hotkey = WinHotkey(self.toggle)
            qapp.installNativeEventFilter(self.win_hotkey)
            self.win_hotkey.register(SETTINGS["hotkey"])
        self.tray = QSystemTrayIcon(QIcon(app_icon()), self)
        self.tray.setToolTip(APP)
        menu = QMenu()
        menu.addAction(tr("Mostrar/ocultar notas"), self.toggle)
        menu.addAction(tr("Nueva nota"), self.board.new_note)
        menu.addAction(tr("Ordenar notas"), self.board.arrange)
        menu.addSeparator()
        self.sn_action = menu.addAction(tr("Mostrar/ocultar Simplenote"), self.simplenote.toggle)
        menu.addSeparator()
        menu.addAction(tr("Ajustes…"), self.open_settings)
        menu.addAction(tr("Acerca de…"), lambda: self.open_settings(about=True))
        menu.addAction(tr("Donar…"), self.donate)
        menu.addSeparator()
        menu.addAction(tr("Salir"), qapp.quit)
        self.tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray)
        self.tray.show()
        self.board.show()
        self.sync.start()
        if SETTINGS["simplenote_background"] and self.simplenote.installed():
            # al iniciar sesión: Simplenote abierto pero con la ventana oculta
            if not self.simplenote.running():
                QTimer.singleShot(1500, lambda: self.simplenote.launch(hidden=True))
            elif autostarted:
                self.simplenote.keep_hidden()

    def on_tray(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger and not IS_MAC:
            self.toggle()

    def toggle(self):
        self.board.toggle_visible()

    def on_message(self):
        conn = self.server.nextPendingConnection()
        if conn.waitForReadyRead(1000):
            cmd = bytes(conn.readAll()).decode(errors="replace").strip()
            if cmd == "toggle":
                self.toggle()
            elif cmd == "settings":
                self.open_settings()
            elif cmd == "quit":
                self.qapp.quit()
            else:
                self.board.show()
        conn.disconnectFromServer()

    def open_settings(self, about=False):
        if self.settings is None:
            self.settings = SettingsDialog(self)
            self.settings.finished.connect(lambda _r: setattr(self, "settings", None))
            self.settings.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        tabs = self.settings.findChild(QTabWidget)
        if about:
            tabs.setCurrentIndex(tabs.count() - 1)
        self.settings.show()
        self.settings.raise_()
        self.settings.activateWindow()

    def set_hotkey(self, seq, old):
        if IS_WIN:
            return self.win_hotkey.register(seq)
        if IS_LINUX:
            return xfce_shortcut(seq, old) or not shutil.which("xfconf-query")
        return True

    def donate(self):
        dlg = QDialog(self.settings)
        dlg.setWindowTitle(tr("Apoyar SimplePost-It"))
        dlg.setWindowIcon(QIcon(app_icon()))
        lay = QVBoxLayout(dlg)
        intro = QLabel(tr("SimplePost-It es gratuito y libre. Si te resulta útil, puedes apoyar su desarrollo:"))
        intro.setWordWrap(True)
        lay.addWidget(intro)
        if DONATE.get("bmc"):
            b = QPushButton("☕  Buy Me a Coffee")
            b.clicked.connect(lambda: open_url(DONATE["bmc"]))
            lay.addWidget(b)
        if DONATE.get("btc"):
            row = QHBoxLayout()
            addr = QLineEdit(DONATE["btc"])
            addr.setReadOnly(True)
            copy = QPushButton(tr("Copiar"))
            copy.clicked.connect(lambda: QApplication.clipboard().setText(DONATE["btc"]))
            wallet = QPushButton(tr("Abrir en mi cartera"))
            wallet.clicked.connect(lambda: open_url(f"bitcoin:{DONATE['btc']}?message=Donaciones%20SimplePost-It"))
            row.addWidget(QLabel("₿ Bitcoin:"))
            row.addWidget(addr, 1)
            row.addWidget(copy)
            row.addWidget(wallet)
            lay.addLayout(row)
        star = QPushButton(tr("★  Dar una estrella en GitHub"))
        star.clicked.connect(lambda: open_url(REPO_URL))
        lay.addWidget(star)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(dlg.reject)
        lay.addWidget(close)
        dlg.setMinimumWidth(480)
        dlg.exec()

    def licenses(self):
        rows = "".join(f"<tr><td><a href='{url}'>{name}</a></td><td>{lic}</td></tr>"
                       for name, lic, url in THIRD_PARTY)
        box = QMessageBox(self.settings)
        box.setWindowTitle(tr("Licencias"))
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(f"<h3>{APP}</h3><p>GPL-3.0-or-later — "
                    f"<a href='https://www.gnu.org/licenses/gpl-3.0.html'>gnu.org/licenses/gpl-3.0</a></p>"
                    f"<h3>{tr('Componentes de terceros')}</h3><table cellpadding=4>{rows}</table>"
                    + tr("<p>Simplenote es una marca de Automattic. SimplePost-It usa su servicio de "
                         "sincronización con tu propia sesión.</p>"))
        box.exec()


def send_to_running(cmd):
    """Si ya hay una instancia, le pasa la orden y devuelve True."""
    sock = QLocalSocket()
    sock.connectToServer(SERVER)
    if not sock.waitForConnected(500):
        return False
    sock.write(cmd.encode())
    sock.flush()
    sock.waitForBytesWritten(500)
    sock.disconnectFromServer()
    return True


def main():
    args = sys.argv[1:]
    if "--version" in args:
        print(f"{APP} {VERSION}")
        return 0
    if "--help" in args or "-h" in args:
        print(tr("Uso: simplepostit [--toggle | --settings]\n\n"
                 "  (sin opciones)   inicia SimplePost-It (o muestra las notas si ya está en marcha)\n"
                 "  --toggle         oculta o muestra las notas\n"
                 "  --settings       abre los ajustes\n"
                 "  --quit           cierra SimplePost-It\n"))
        return 0
    QApplication.setApplicationName(APP)
    QApplication.setDesktopFileName("simplepostit")
    qapp = QApplication(sys.argv[:1])
    qapp.setQuitOnLastWindowClosed(False)
    qt_tr = QTranslator(qapp)  # botones estándar de Qt (Cerrar, Aceptar…) en el idioma elegido
    if qt_tr.load(f"qtbase_{UI_LANG}", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        qapp.installTranslator(qt_tr)
    qapp.setWindowIcon(QIcon(app_icon()))
    cmd = ("toggle" if "--toggle" in args else "settings" if "--settings" in args
           else "quit" if "--quit" in args else "show")
    if send_to_running(cmd) or cmd == "quit":
        return 0
    if "--toggle" in args:
        cmd = "show"  # no estaba en marcha: arranca visible
    first_run = not os.path.exists(SETTINGS_FILE)
    if first_run:
        save_settings(SETTINGS)
        try:
            set_autostart(SETTINGS["autostart"])
        except OSError:
            pass
        if IS_LINUX:
            xfce_shortcut(SETTINGS["hotkey"])
    if IS_MAC:
        try:  # sin ícono en el Dock: vive en la barra de menús
            from AppKit import NSApplication
            NSApplication.sharedApplication().setActivationPolicy_(1)
        except ImportError:
            pass
    app = App(qapp, autostarted="--autostart" in args)
    if "--settings" in args or first_run:
        QTimer.singleShot(400, app.open_settings)
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
