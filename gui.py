#!/usr/bin/env python3
import os
import sys
import subprocess
import re
from datetime import datetime

# Suppress Qt Wayland text-input warning spam in the terminal
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.wayland.textinput=false")

from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog, QTextEdit, QAbstractItemView, QFrame,
    QSplitter, QMessageBox, QGraphicsDropShadowEffect, QSizePolicy,
    QStatusBar, QDialog, QComboBox, QProgressBar, QScrollArea
)
from PySide6.QtCore import (
    Qt, QSize, Signal, QPointF, QRectF
)
from PySide6.QtGui import (
    QColor, QFont, QIcon, QPainter, QBrush, QPen, QPainterPath,
    QDragEnterEvent, QDropEvent, QDragLeaveEvent, QKeySequence,
    QShortcut, QFontDatabase, QFontMetrics, QPixmap, QPolygonF
)

from core.linker import ModManager
from core.config import auto_find_cyberpunk, MODS_DIR
from core.analyzer import (
    analyse_mod, detect_conflicts, get_mod_conflicts_for,
    verify_symlinks, get_game_version, get_all_frameworks_status,
    get_framework_info, KNOWN_FRAMEWORKS,
)
from core.proton import (
    find_proton_prefix, check_proton_overrides, configure_proton_overrides,
    launch_game_steam, RECOMMENDED_STEAM_OPTIONS,
)

# ─────────────────────────── Color Palette ───────────────────────────
C_BG_VOID      = "#080b11"
C_BG_DEEP      = "#0a0e16"
C_BG_MAIN      = "#0e1420"
C_BG_PANEL     = "#121a27"
C_BG_CARD      = "#1a2534"
C_BG_ELEVATED  = "#243044"
C_BG_HOVER     = "#2a3a4d"

C_CYAN         = "#37dce8"
C_CYAN_DIM     = "#006b73"
C_YELLOW       = "#ffe04b"
C_YELLOW_DIM   = "#7a7300"
C_RED          = "#ff5a76"
C_RED_DIM      = "#590015"
C_GREEN        = "#46e5a2"
C_GREEN_DIM    = "#006636"
C_ORANGE       = "#ffb35e"
C_TEXT         = "#eef3fb"
C_TEXT_MUTED   = "#b0bdd2"
C_TEXT_DIM     = "#7e8ca3"
C_BORDER       = "#273347"
C_BORDER_LIGHT = "#3c4d63"


def compact_mod_identity(name: str) -> tuple[str, str]:
    """Display archive metadata without changing the real storage key."""
    match = re.match(
        r"^(?P<title>.+?)\s+(?P<nexus>\d{2,7})\s+"
        r"(?P<version>\d[\w.\-]*)\s+"
        r"(?P<stamp>\d{4}-\d{2}-\d{2}T\S+)\s+\S+$",
        name,
    )
    if match:
        title = match.group("title")
        version = match.group("version")
        summary = title if version in title else f"{title}  ·  v{version}"
        return summary, f"NEXUS #{match.group('nexus')}  /  BUILD {match.group('stamp')[:10]}"
    return name, "LOCAL PACKAGE"


# ─────────────────────── Custom Vector Icons ─────────────────────────
class VectorIcon:
    """Renders crisp geometric vector icons dynamically without external assets or emojis."""

    @staticmethod
    def create(name: str, color_hex: str, size: int = 16) -> QIcon:
        pix = QPixmap(size * 2, size * 2)
        pix.fill(Qt.transparent)

        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(2.0, 2.0)

        c = QColor(color_hex)
        pen = QPen(c, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        s = float(size)
        m = 2.5

        if name == "play":
            p.setBrush(QBrush(c))
            p.setPen(Qt.NoPen)
            poly = QPolygonF([QPointF(m + 1, m), QPointF(s - m, s / 2.0), QPointF(m + 1, s - m)])
            p.drawPolygon(poly)

        elif name == "plus":
            p.drawLine(QPointF(s / 2, m), QPointF(s / 2, s - m))
            p.drawLine(QPointF(m, s / 2), QPointF(s - m, s / 2))

        elif name == "folder":
            path = QPainterPath()
            path.moveTo(m, m + 2)
            path.lineTo(s * 0.42, m + 2)
            path.lineTo(s * 0.52, m + 4.5)
            path.lineTo(s - m, m + 4.5)
            path.lineTo(s - m, s - m - 1)
            path.lineTo(m, s - m - 1)
            path.closeSubpath()
            p.drawPath(path)

        elif name == "radar":
            r = (s - 2 * m) / 2
            center = QPointF(s / 2, s / 2)
            p.drawEllipse(center, r * 0.75, r * 0.75)
            p.drawLine(QPointF(s / 2, 1.5), QPointF(s / 2, 4.0))
            p.drawLine(QPointF(s / 2, s - 4.0), QPointF(s / 2, s - 1.5))
            p.drawLine(QPointF(1.5, s / 2), QPointF(4.0, s / 2))
            p.drawLine(QPointF(s - 4.0, s / 2), QPointF(s - 1.5, s / 2))
            p.setBrush(QBrush(c))
            p.drawEllipse(center, 1.2, 1.2)

        elif name == "shield":
            path = QPainterPath()
            path.moveTo(s / 2, m)
            path.lineTo(s - m, m + 2.5)
            path.lineTo(s - m, s * 0.55)
            path.quadTo(s - m, s - m + 0.5, s / 2, s - m + 0.5)
            path.quadTo(m, s - m + 0.5, m, s * 0.55)
            path.lineTo(m, m + 2.5)
            path.closeSubpath()
            p.drawPath(path)
            p.drawLine(QPointF(s * 0.36, s * 0.52), QPointF(s * 0.47, s * 0.64))
            p.drawLine(QPointF(s * 0.47, s * 0.64), QPointF(s * 0.66, s * 0.40))

        elif name == "trash":
            p.drawLine(QPointF(m, m + 2), QPointF(s - m, m + 2))
            p.drawLine(QPointF(s * 0.38, m), QPointF(s * 0.62, m))
            p.drawRect(QRectF(m + 1.5, m + 2, s - 2 * (m + 1.5), s - 2 * m - 1.5))
            p.drawLine(QPointF(s * 0.43, m + 5), QPointF(s * 0.43, s - m - 2))
            p.drawLine(QPointF(s * 0.57, m + 5), QPointF(s * 0.57, s - m - 2))

        elif name == "power":
            rect = QRectF(m + 0.5, m + 1.5, s - 2 * m - 1, s - 2 * m - 1)
            p.drawArc(rect, 130 * 16, 280 * 16)
            p.drawLine(QPointF(s / 2, m - 0.5), QPointF(s / 2, s * 0.52))

        elif name == "search":
            r = (s - 2 * m) * 0.36
            c_pt = QPointF(m + r + 0.5, m + r + 0.5)
            p.drawEllipse(c_pt, r, r)
            p.drawLine(QPointF(c_pt.x() + r * 0.72, c_pt.y() + r * 0.72), QPointF(s - m, s - m))

        elif name == "check_all":
            p.drawLine(QPointF(m, s * 0.55), QPointF(s * 0.38, s - m - 1.5))
            p.drawLine(QPointF(s * 0.38, s - m - 1.5), QPointF(s - m, m + 1.5))

        elif name == "close_all":
            p.drawLine(QPointF(m + 1, m + 1), QPointF(s - m - 1, s - m - 1))
            p.drawLine(QPointF(s - m - 1, m + 1), QPointF(m + 1, s - m - 1))

        elif name == "steam":
            r = (s - 2 * m) / 2
            p.drawEllipse(QPointF(s / 2, s / 2), r * 0.85, r * 0.85)
            p.drawEllipse(QPointF(s * 0.38, s * 0.62), r * 0.30, r * 0.30)
            p.drawLine(QPointF(s * 0.40, s * 0.58), QPointF(s * 0.64, s * 0.38))
            p.drawEllipse(QPointF(s * 0.64, s * 0.38), r * 0.22, r * 0.22)

        p.end()
        return QIcon(pix)


# ─────────────────────── Custom Vector Widgets ───────────────────────

class CyberHexLogo(QWidget):
    """Painted vector geometric emblem for the header bar."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 40)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0

        # Outer chamfered octagon
        path = QPainterPath()
        d = 4.0
        c = 8.0
        path.moveTo(d + c, d)
        path.lineTo(w - d - c, d)
        path.lineTo(w - d, d + c)
        path.lineTo(w - d, h - d - c)
        path.lineTo(w - d - c, h - d)
        path.lineTo(d + c, h - d)
        path.lineTo(d, h - d - c)
        path.lineTo(d, d + c)
        path.closeSubpath()

        p.setBrush(QColor(252, 238, 10, 22))
        p.setPen(QPen(QColor(C_YELLOW), 1.8))
        p.drawPath(path)

        # Inner core diamond
        core = QPainterPath()
        r = 6.5
        core.moveTo(cx, cy - r)
        core.lineTo(cx + r, cy)
        core.lineTo(cx, cy + r)
        core.lineTo(cx - r, cy)
        core.closeSubpath()
        p.setBrush(QColor(C_CYAN))
        p.setPen(Qt.NoPen)
        p.drawPath(core)

        # Technical tick lines
        p.setPen(QPen(QColor(C_CYAN), 1.2))
        p.drawLine(QPointF(cx, 1), QPointF(cx, d + 2))
        p.drawLine(QPointF(cx, h - d - 2), QPointF(cx, h - 1))


class ChamferPanel(QFrame):
    """Container widget with angled cyberpunk corners and a top accent line."""
    def __init__(self, accent_color=C_CYAN, bg_color=C_BG_PANEL, cut=10, parent=None):
        super().__init__(parent)
        self._accent = QColor(accent_color)
        self._bg = QColor(bg_color)
        self._border = QColor(C_BORDER)
        self._cut = cut
        self.setAttribute(Qt.WA_StyledBackground, False)

    def set_accent(self, color_hex: str):
        self._accent = QColor(color_hex)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = float(self.width()), float(self.height())
        c = float(self._cut)

        path = QPainterPath()
        path.moveTo(1, 1)
        path.lineTo(w - c - 1, 1)
        path.lineTo(w - 1, c + 1)
        path.lineTo(w - 1, h - 1)
        path.lineTo(c + 1, h - 1)
        path.lineTo(1, h - c - 1)
        path.closeSubpath()

        p.fillPath(path, self._bg)
        p.setPen(QPen(self._border, 1.0))
        p.drawPath(path)

        # Top glowing accent bar
        p.setPen(QPen(self._accent, 2.2))
        p.drawLine(QPointF(2, 1.5), QPointF(min(w * 0.35, 110.0), 1.5))


class MetricCard(ChamferPanel):
    """Top telemetry card displaying live counter and subtitle."""
    def __init__(self, title: str, value: str, subtext: str, accent: str = C_CYAN, parent=None):
        super().__init__(accent_color=accent, bg_color=C_BG_PANEL, cut=9, parent=parent)
        self.setMinimumHeight(88)
        self.setMaximumHeight(100)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 12)
        layout.setSpacing(6)

        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet(
            f"color: {C_TEXT_MUTED}; font-size: 11px; font-weight: 750; letter-spacing: 0.9px;"
        )
        layout.addWidget(self.lbl_title)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.lbl_value = QLabel(value)
        self.lbl_value.setStyleSheet(
            f"color: {C_TEXT}; font-size: 29px; font-weight: 800;"
        )
        row.addWidget(self.lbl_value)

        row.addStretch()

        self.lbl_sub = QLabel(subtext)
        self.lbl_sub.setStyleSheet(
            f"color: {accent}; font-size: 11px; font-weight: 700;"
        )
        row.addWidget(self.lbl_sub, alignment=Qt.AlignBottom)

        layout.addLayout(row)

    def set_metric(self, value: str, subtext: str = None, accent: str = None):
        self.lbl_value.setText(value)
        if subtext is not None:
            self.lbl_sub.setText(subtext)
        if accent is not None:
            self.set_accent(accent)
            self.lbl_sub.setStyleSheet(
                f"color: {accent}; font-size: 11px; font-weight: 700;"
            )


class CyberToggle(QWidget):
    """Interactive vector toggle switch for enabling/disabling mods."""
    toggled = Signal(bool)

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self._checked = checked
        self._hovered = False
        self.setFixedSize(48, 24)
        self.setCursor(Qt.PointingHandCursor)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, val: bool):
        if self._checked != val:
            self._checked = val
            self.update()

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._checked = not self._checked
            self.update()
            self.toggled.emit(self._checked)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = float(self.width()), float(self.height())

        # Angled track
        track = QPainterPath()
        c = 4.0
        track.moveTo(c, 1.5)
        track.lineTo(w - 1.5, 1.5)
        track.lineTo(w - 1.5, h - c)
        track.lineTo(w - c, h - 1.5)
        track.lineTo(1.5, h - 1.5)
        track.lineTo(1.5, c)
        track.closeSubpath()

        if self._checked:
            bg = QColor(0, 255, 136, 45 if not self._hovered else 70)
            border = QColor(C_GREEN)
            knob_color = QColor(C_GREEN)
            kx = w - 18.0
        else:
            bg = QColor(24, 28, 44, 200)
            border = QColor(C_CYAN if self._hovered else C_BORDER_LIGHT)
            knob_color = QColor(C_TEXT_MUTED if not self._hovered else C_TEXT)
            kx = 4.5

        p.fillPath(track, bg)
        p.setPen(QPen(border, 1.3))
        p.drawPath(track)

        # Thumb block
        p.setPen(Qt.NoPen)
        p.setBrush(knob_color)
        p.drawRoundedRect(QRectF(kx, 4.5, 13.5, h - 9.0), 1.5, 1.5)


class StatusPill(QWidget):
    """Draws a crisp rectangular status badge with a vector indicator dot."""
    def __init__(self, text: str, color_hex: str, filled_dot: bool = True, parent=None):
        super().__init__(parent)
        self._text = text
        self._color = QColor(color_hex)
        self._filled = filled_dot
        self.setFixedHeight(26)

        font = QFont("DejaVu Sans Mono", 9)
        font.setBold(True)
        tw = QFontMetrics(font).horizontalAdvance(text)
        self.setFixedWidth(max(tw + 31, 88))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = float(self.width()), float(self.height())

        bg = QColor(self._color)
        bg.setAlpha(28)
        border = QColor(self._color)
        border.setAlpha(130)

        rect = QRectF(1, 1, w - 2, h - 2)
        p.setBrush(bg)
        p.setPen(QPen(border, 1.0))
        p.drawRoundedRect(rect, 3.0, 3.0)

        # Indicator dot
        dot_center = QPointF(10.5, h / 2.0)
        if self._filled:
            p.setBrush(self._color)
            p.setPen(Qt.NoPen)
            p.drawEllipse(dot_center, 3.0, 3.0)
        else:
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(self._color, 1.4))
            p.drawEllipse(dot_center, 2.8, 2.8)

        # Text
        p.setPen(self._color)
        font = QFont("DejaVu Sans Mono", 9)
        font.setBold(True)
        p.setFont(font)
        p.drawText(QRectF(19, 0, w - 22, h), Qt.AlignVCenter | Qt.AlignLeft, self._text)


class DropOverlay(QWidget):
    """Full-window graphical overlay shown when dragging archive files over the app."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.hide()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = float(self.width()), float(self.height())

        p.fillRect(self.rect(), QColor(6, 7, 12, 225))

        m = 28.0
        rect = QRectF(m, m, w - 2 * m, h - 2 * m)
        pen = QPen(QColor(C_CYAN), 2.0, Qt.DashLine)
        p.setPen(pen)
        p.setBrush(QColor(0, 240, 255, 14))
        p.drawRoundedRect(rect, 8.0, 8.0)

        # Center vector arrow
        cx, cy = w / 2.0, h / 2.0 - 20.0
        p.setPen(QPen(QColor(C_YELLOW), 2.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawLine(QPointF(cx, cy - 28), QPointF(cx, cy + 12))
        p.drawLine(QPointF(cx - 14, cy - 2), QPointF(cx, cy + 12))
        p.drawLine(QPointF(cx + 14, cy - 2), QPointF(cx, cy + 12))
        p.drawLine(QPointF(cx - 22, cy + 22), QPointF(cx + 22, cy + 22))

        font = QFont("JetBrains Mono", 15, QFont.Bold)
        p.setFont(font)
        p.setPen(QColor(C_CYAN))
        p.drawText(QRectF(0, cy + 36, w, 30), Qt.AlignCenter, "DROP ARCHIVES TO INSTALL")

        sub_font = QFont("JetBrains Mono", 10)
        p.setFont(sub_font)
        p.setPen(QColor(C_TEXT_MUTED))
        p.drawText(QRectF(0, cy + 64, w, 24), Qt.AlignCenter, "SUPPORTED FORMATS: .ZIP  //  .7Z  //  .RAR  //  .TAR.GZ")


class SteamConfigDialog(QDialog):
    """Cyberpunk modal dialog for configuring Steam launch options and Proton DLL overrides."""
    def __init__(self, game_path: Path, log_fn=None, parent=None):
        super().__init__(parent)
        self.game_path = game_path
        self.log_fn = log_fn
        self.setWindowTitle("STEAM // PROTON CONFIGURATION")
        self.setFixedWidth(560)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {C_BG_MAIN};
                color: {C_TEXT};
            }}
            QLabel {{
                color: {C_TEXT};
            }}
            QLineEdit {{
                background: {C_BG_VOID};
                color: {C_CYAN};
                border: 1px solid {C_BORDER};
                border-radius: 3px;
                padding: 8px 10px;
                font-family: 'JetBrains Mono', 'Fira Code', monospace;
                font-size: 11px;
            }}
            QPushButton {{
                background: {C_BG_PANEL};
                color: {C_TEXT};
                border: 1px solid {C_BORDER};
                border-radius: 3px;
                padding: 8px 16px;
                font-weight: 700;
                font-size: 11px;
            }}
            QPushButton:hover {{
                border-color: {C_CYAN};
                color: {C_CYAN};
            }}
            QPushButton#btnApplyOverrides {{
                background: {C_CYAN};
                color: #050608;
                border: none;
            }}
            QPushButton#btnApplyOverrides:hover {{
                background: #4df3ff;
            }}
            QPushButton#btnCopy {{
                background: {C_YELLOW};
                color: #050608;
                border: none;
            }}
            QPushButton#btnCopy:hover {{
                background: #fdf569;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        # Header
        h_title = QLabel("// STEAM & PROTON MOD SETUP")
        h_title.setFont(QFont("JetBrains Mono", 12, QFont.Bold))
        h_title.setStyleSheet(f"color: {C_YELLOW}; letter-spacing: 0.5px;")
        layout.addWidget(h_title)

        desc = QLabel(
            "For CET, RED4ext and ArchiveXL to work on Linux/Proton, "
            "enable native DLL loading (version.dll, winmm.dll) "
            "and use the recommended launch options."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {C_TEXT_MUTED}; font-size: 11px; line-height: 1.4;")
        layout.addWidget(desc)

        # Status panel
        self.status_panel = ChamferPanel(accent_color=C_CYAN, bg_color=C_BG_PANEL, cut=8)
        sf_layout = QVBoxLayout(self.status_panel)
        sf_layout.setContentsMargins(14, 12, 14, 12)
        sf_layout.setSpacing(8)

        self.lbl_pfx = QLabel()
        self.lbl_pfx.setStyleSheet("font-size: 11px;")
        sf_layout.addWidget(self.lbl_pfx)

        self.lbl_overrides = QLabel()
        self.lbl_overrides.setStyleSheet("font-size: 11px;")
        sf_layout.addWidget(self.lbl_overrides)

        layout.addWidget(self.status_panel)

        # Command line
        cmd_title = QLabel("STEAM LAUNCH OPTIONS")
        cmd_title.setFont(QFont("JetBrains Mono", 9, QFont.Bold))
        cmd_title.setStyleSheet(f"color: {C_CYAN}; letter-spacing: 0.5px;")
        layout.addWidget(cmd_title)

        self.cmd_input = QLineEdit(RECOMMENDED_STEAM_OPTIONS)
        self.cmd_input.setReadOnly(True)
        layout.addWidget(self.cmd_input)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_copy = QPushButton("COPY LAUNCH OPTIONS")
        self.btn_copy.setObjectName("btnCopy")
        self.btn_copy.setCursor(Qt.PointingHandCursor)
        self.btn_copy.setIcon(VectorIcon.create("check_all", "#050608", 14))
        self.btn_copy.clicked.connect(self._copy_command)
        btn_row.addWidget(self.btn_copy)

        self.btn_apply = QPushButton("APPLY TO PROTON PREFIX")
        self.btn_apply.setObjectName("btnApplyOverrides")
        self.btn_apply.setCursor(Qt.PointingHandCursor)
        self.btn_apply.setIcon(VectorIcon.create("power", "#050608", 14))
        self.btn_apply.clicked.connect(self._apply_overrides)
        btn_row.addWidget(self.btn_apply)

        layout.addLayout(btn_row)

        # Instructions
        guide = QLabel(
            "<b>How to configure Steam:</b><br>"
            "1. Open <b>Steam</b> &rarr; right-click <b>Cyberpunk 2077</b> &rarr; <i>Properties</i><br>"
            "2. Under <i>General</i>, find the <b>Launch Options</b> field.<br>"
            "3. Paste the copied command to skip REDlauncher and launch the modded game."
        )
        guide.setTextFormat(Qt.RichText)
        guide.setWordWrap(True)
        guide.setStyleSheet(f"color: {C_TEXT_MUTED}; font-size: 11px; background: {C_BG_DEEP}; padding: 12px; border-radius: 4px; border: 1px solid {C_BORDER};")
        layout.addWidget(guide)

        btn_close = QPushButton("CLOSE")
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

        self._refresh_status()

    def _refresh_status(self):
        pfx = find_proton_prefix(self.game_path)
        if not pfx:
            self.lbl_pfx.setText("<span style='color:#ff003c;'>✖ Proton prefix (compatdata/1091500) not found</span>")
            self.lbl_overrides.setText("Launch the game from Steam once to create its Proton prefix.")
            self.btn_apply.setEnabled(False)
            return

        self.lbl_pfx.setText(f"<span style='color:#00ff88;'>✔ Proton prefix detected:</span> <span style='color:#8c92ac;'>{pfx.name}</span>")
        ok, missing = check_proton_overrides(pfx)
        if ok:
            self.lbl_overrides.setText(
                "<span style='color:#00ff88;'>✔ Wine DLL Overrides (version, winmm) <b>enabled</b> in Proton.</span>"
            )
            self.btn_apply.setText("UPDATE DLL OVERRIDES")
        else:
            self.lbl_overrides.setText(
                f"<span style='color:#ff9500;'>⚠ Missing DLL overrides: <b>{', '.join(missing)}</b></span>"
            )
            self.btn_apply.setText("APPLY DLL OVERRIDES")
            self.btn_apply.setEnabled(True)

    def _copy_command(self):
        QApplication.clipboard().setText(self.cmd_input.text())
        self.btn_copy.setText("COPIED!")
        if self.log_fn:
            self.log_fn("INFO", "Steam launch options copied to clipboard.", C_CYAN)

    def _apply_overrides(self):
        pfx = find_proton_prefix(self.game_path)
        if pfx:
            ok, msg = configure_proton_overrides(pfx)
            if ok:
                if self.log_fn:
                    self.log_fn("OK", f"{msg}", C_GREEN)
            else:
                if self.log_fn:
                    self.log_fn("ERROR", f"{msg}", C_RED)
            self._refresh_status()


# ────────────────────────── Stylesheet ───────────────────────────────

CYBERPUNK_QSS = f"""
QMainWindow, QWidget#central {{
    background-color: {C_BG_VOID};
    color: {C_TEXT};
    font-family: 'Noto Sans', 'DejaVu Sans', sans-serif;
    font-size: 13px;
}}
QToolTip {{
    background-color: {C_BG_ELEVATED};
    color: {C_TEXT};
    border: 1px solid {C_CYAN_DIM};
    padding: 9px 12px;
    font-size: 12px;
}}
QFrame#headerBar {{
    background-color: {C_BG_DEEP};
    border-bottom: 1px solid {C_BORDER_LIGHT};
}}
QLabel#headerTitle {{
    color: {C_TEXT};
    font-family: 'DejaVu Sans Mono', monospace;
    font-size: 19px;
    font-weight: 800;
    letter-spacing: 1.0px;
}}
QLabel#headerSubtitle {{
    color: {C_CYAN};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.8px;
}}
QLabel#sectionTitle {{
    color: {C_TEXT};
    font-size: 15px;
    font-weight: 800;
}}
QLabel#sectionMeta {{
    color: {C_TEXT_DIM};
    font-family: 'DejaVu Sans Mono', monospace;
    font-size: 11px;
}}
QLineEdit {{
    background-color: {C_BG_DEEP};
    border: 1px solid {C_BORDER_LIGHT};
    border-radius: 5px;
    color: {C_TEXT};
    padding: 9px 12px;
    font-size: 13px;
    selection-background-color: {C_CYAN_DIM};
}}
QLineEdit:hover {{ border-color: {C_TEXT_DIM}; }}
QLineEdit:focus {{
    border: 1px solid {C_CYAN};
    background-color: {C_BG_MAIN};
}}
QComboBox {{
    color: {C_TEXT};
    background-color: {C_BG_CARD};
    border: 1px solid {C_BORDER_LIGHT};
    border-radius: 5px;
    padding: 9px 15px;
    min-width: 145px;
    font-size: 12px;
}}
QComboBox:hover {{ border-color: {C_CYAN}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    color: {C_TEXT};
    background-color: {C_BG_PANEL};
    border: 1px solid {C_BORDER_LIGHT};
    selection-background-color: {C_BG_HOVER};
    padding: 4px;
}}
QPushButton {{
    background-color: {C_BG_CARD};
    border: 1px solid {C_BORDER_LIGHT};
    color: {C_TEXT_MUTED};
    padding: 10px 14px;
    font-weight: 700;
    font-size: 12px;
    border-radius: 5px;
}}
QPushButton:hover {{
    background-color: {C_BG_HOVER};
    border-color: {C_CYAN};
    color: {C_TEXT};
}}
QPushButton:pressed {{
    background-color: {C_CYAN_DIM};
    color: #ffffff;
}}
QPushButton:disabled {{
    color: {C_TEXT_DIM};
    border-color: {C_BORDER};
}}
QPushButton#btnPrimary {{
    background-color: {C_YELLOW};
    border: 1px solid {C_YELLOW};
    color: #0b1017;
    font-weight: 800;
}}
QPushButton#btnPrimary:hover {{
    background-color: #ffed88;
    border-color: #ffed88;
}}
QPushButton#btnYellow {{
    background-color: #2d2a17;
    border: 1px solid {C_YELLOW_DIM};
    color: {C_YELLOW};
}}
QPushButton#btnYellow:hover {{
    border-color: {C_YELLOW};
    background-color: #3b3519;
}}
QPushButton#btnDanger {{
    background-color: #281923;
    border: 1px solid {C_RED_DIM};
    color: {C_RED};
}}
QPushButton#btnDanger:hover {{
    border-color: {C_RED};
    background-color: #3b1d2a;
}}
QPushButton#btnSteamCfg {{
    background-color: transparent;
    border: 1px solid {C_BORDER_LIGHT};
    color: {C_TEXT_MUTED};
}}
QPushButton#btnSteamCfg:hover {{
    border-color: {C_CYAN};
    color: {C_CYAN};
}}
QPushButton#btnLaunch {{
    background-color: {C_YELLOW};
    border: 1px solid {C_YELLOW};
    color: #080c13;
    font-size: 13px;
    font-weight: 800;
    padding: 11px 20px;
}}
QPushButton#btnLaunch:hover {{
    background-color: #fff195;
    border-color: #fff195;
}}
QTableWidget {{
    background-color: {C_BG_DEEP};
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    gridline-color: transparent;
    selection-background-color: #163b43;
    selection-color: {C_TEXT};
    outline: none;
    font-size: 13px;
    alternate-background-color: {C_BG_MAIN};
}}
QTableWidget::item {{
    padding: 8px 10px;
    border-bottom: 1px solid #1b2837;
}}
QTableWidget::item:hover {{ background-color: #182a39; }}
QTableWidget::item:selected {{
    background-color: #173c45;
    color: #ffffff;
}}
QHeaderView::section {{
    background-color: {C_BG_PANEL};
    color: {C_TEXT_MUTED};
    font-weight: 800;
    font-size: 11px;
    padding: 12px 10px;
    border: none;
    border-bottom: 1px solid {C_BORDER_LIGHT};
}}
QTableCornerButton::section {{ background-color: {C_BG_PANEL}; }}
QScrollBar:vertical {{
    background: {C_BG_DEEP};
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {C_BORDER_LIGHT};
    min-height: 28px;
    border-radius: 5px;
}}
QScrollBar::handle:vertical:hover {{ background: {C_CYAN_DIM}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    height: 10px;
    background: {C_BG_DEEP};
}}
QScrollBar::handle:horizontal {{
    background: {C_BORDER_LIGHT};
    border-radius: 5px;
}}
QTextEdit#logBox {{
    background-color: {C_BG_DEEP};
    border: 1px solid {C_BORDER};
    border-radius: 6px;
    color: {C_TEXT_MUTED};
    font-family: 'DejaVu Sans Mono', monospace;
    font-size: 12px;
    padding: 9px 11px;
}}
QSplitter::handle {{
    background-color: {C_BG_VOID};
}}
QSplitter::handle:hover {{ background-color: {C_BORDER_LIGHT}; }}
QStatusBar {{
    background-color: {C_BG_DEEP};
    color: {C_TEXT_MUTED};
    border-top: 1px solid {C_BORDER};
    font-size: 11px;
}}
QStatusBar QLabel {{ color: {C_TEXT_MUTED}; font-size: 11px; }}
QMessageBox, QDialog {{
    background-color: {C_BG_PANEL};
    color: {C_TEXT};
}}
QProgressBar {{
    background-color: {C_BG_DEEP};
    border: none;
    border-radius: 3px;
    height: 6px;
}}
QProgressBar::chunk {{
    background-color: {C_GREEN};
    border-radius: 3px;
}}
QScrollArea {{
    background-color: transparent;
    border: none;
}}
"""


# ─────────────────────────── Inspector Panel ─────────────────────────

class ModDetailsPanel(ChamferPanel):
    """Scrollable, health-focused inspector with pinned contextual actions."""

    def __init__(self, parent=None):
        super().__init__(accent_color=C_YELLOW, bg_color=C_BG_PANEL, cut=12, parent=parent)
        self.setMinimumWidth(300)
        self.setMaximumWidth(440)

        shell = QVBoxLayout(self)
        shell.setContentsMargins(1, 8, 1, 1)
        shell.setSpacing(0)

        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QFrame.NoFrame)
        scroller.setStyleSheet(
            f"QScrollArea {{background-color: {C_BG_PANEL}; border: none;}}"
            f"QScrollBar:vertical {{background: {C_BG_DEEP}; width: 9px;}}"
        )
        scroller.viewport().setAutoFillBackground(False)
        scroller.viewport().setStyleSheet(f"background-color: {C_BG_PANEL};")
        scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("inspectorCanvas")
        content.setStyleSheet(
            f"QWidget#inspectorCanvas {{background-color: {C_BG_PANEL}; color: {C_TEXT};}}"
        )
        scroller.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 15, 20, 16)
        layout.setSpacing(11)

        header = QLabel("01   /   MOD INSPECTOR")
        header.setStyleSheet(
            f"color: {C_YELLOW}; font-size: 11px; font-weight: 800; letter-spacing: 0.8px;"
        )
        layout.addWidget(header)

        self.lbl_name = QLabel("NO MOD SELECTED")
        self.lbl_name.setTextFormat(Qt.PlainText)
        self.lbl_name.setWordWrap(True)
        self.lbl_name.setStyleSheet(
            f"color: {C_TEXT}; font-size: 17px; font-weight: 800;"
        )
        layout.addWidget(self.lbl_name)

        self.lbl_mod_meta = QLabel("")
        self.lbl_mod_meta.setWordWrap(True)
        self.lbl_mod_meta.setTextFormat(Qt.PlainText)
        self.lbl_mod_meta.setStyleSheet(
            f"color: {C_TEXT_DIM}; font-family: 'DejaVu Sans Mono'; font-size: 10px;"
        )
        layout.addWidget(self.lbl_mod_meta)

        self.status_pill_holder = QWidget()
        self.status_pill_layout = QHBoxLayout(self.status_pill_holder)
        self.status_pill_layout.setContentsMargins(0, 1, 0, 2)
        self.status_pill_layout.setAlignment(Qt.AlignLeft)
        layout.addWidget(self.status_pill_holder)

        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet(f"color: {C_BORDER_LIGHT};")
        layout.addWidget(divider)

        heading = QLabel("DEPLOYMENT HEALTH")
        heading.setStyleSheet(
            f"color: {C_TEXT_MUTED}; font-size: 11px; font-weight: 800; letter-spacing: 0.7px;"
        )
        layout.addWidget(heading)

        self.lbl_health = QLabel("Select a mod from the library")
        self.lbl_health.setWordWrap(True)
        self.lbl_health.setStyleSheet(
            f"color: {C_TEXT_MUTED}; font-size: 13px; font-weight: 700;"
        )
        layout.addWidget(self.lbl_health)

        self.health_bar = QProgressBar()
        self.health_bar.setRange(0, 100)
        self.health_bar.setTextVisible(False)
        self.health_bar.setFixedHeight(7)
        layout.addWidget(self.health_bar)

        self.lbl_health_detail = QLabel("—")
        self.lbl_health_detail.setWordWrap(True)
        self.lbl_health_detail.setStyleSheet(
            f"color: {C_TEXT_DIM}; font-size: 11px;"
        )
        layout.addWidget(self.lbl_health_detail)

        metric_box = QFrame()
        metric_box.setObjectName("inspectorMetricBox")
        metric_box.setStyleSheet(
            f"QFrame#inspectorMetricBox {{background: {C_BG_DEEP};"
            f" border: 1px solid {C_BORDER}; border-radius: 6px;}}"
            f"QFrame#inspectorMetricBox QLabel {{border: none; background: transparent;}}"
        )
        metric_layout = QHBoxLayout(metric_box)
        metric_layout.setContentsMargins(14, 14, 14, 14)
        metric_layout.setSpacing(14)
        col_a = QVBoxLayout()
        col_a.setSpacing(3)
        label_files = QLabel("LINKS")
        label_files.setStyleSheet(f"color: {C_TEXT_DIM}; font-size: 10px; font-weight: 700;")
        self.lbl_files = QLabel("—")
        self.lbl_files.setStyleSheet(
            f"color: {C_CYAN}; font-size: 24px; font-weight: 800;"
        )
        col_a.addWidget(label_files)
        col_a.addWidget(self.lbl_files)
        metric_layout.addLayout(col_a, 1)
        col_b = QVBoxLayout()
        col_b.setSpacing(3)
        label_size = QLabel("SIZE")
        label_size.setStyleSheet(f"color: {C_TEXT_DIM}; font-size: 10px; font-weight: 700;")
        self.lbl_size = QLabel("—")
        self.lbl_size.setStyleSheet(f"color: {C_TEXT}; font-size: 20px; font-weight: 800;")
        col_b.addWidget(label_size)
        col_b.addWidget(self.lbl_size)
        metric_layout.addLayout(col_b, 1)
        layout.addWidget(metric_box)

        lbl_types_hdr = QLabel("PACKAGE CONTENTS")
        lbl_types_hdr.setStyleSheet(
            f"color: {C_TEXT_MUTED}; font-size: 11px; font-weight: 800; letter-spacing: 0.7px;"
        )
        layout.addWidget(lbl_types_hdr)
        self.lbl_types = QLabel("—")
        self.lbl_types.setWordWrap(True)
        self.lbl_types.setTextFormat(Qt.PlainText)
        self.lbl_types.setStyleSheet(
            f"color: {C_TEXT}; font-family: 'DejaVu Sans Mono'; font-size: 12px;"
        )
        layout.addWidget(self.lbl_types)

        lbl_deps_hdr = QLabel("REQUIRED FRAMEWORKS")
        lbl_deps_hdr.setStyleSheet(
            f"color: {C_TEXT_MUTED}; font-size: 11px; font-weight: 800; letter-spacing: 0.7px;"
        )
        layout.addWidget(lbl_deps_hdr)
        self.lbl_deps = QLabel("—")
        self.lbl_deps.setWordWrap(True)
        self.lbl_deps.setStyleSheet(
            f"color: {C_TEXT_MUTED}; font-size: 12px;"
        )
        layout.addWidget(self.lbl_deps)

        self.lbl_conflicts_hdr = QLabel("POTENTIAL CONFLICTS")
        self.lbl_conflicts_hdr.setStyleSheet(
            f"color: {C_ORANGE}; font-size: 11px; font-weight: 800;"
        )
        self.lbl_conflicts_hdr.hide()
        layout.addWidget(self.lbl_conflicts_hdr)
        self.lbl_conflicts = QLabel("")
        self.lbl_conflicts.setWordWrap(True)
        self.lbl_conflicts.setStyleSheet(
            f"background-color: #33251c; border-left: 3px solid {C_ORANGE};"
            f" color: {C_ORANGE}; font-size: 12px; padding: 9px;"
        )
        self.lbl_conflicts.hide()
        layout.addWidget(self.lbl_conflicts)
        layout.addStretch(1)

        shell.addWidget(scroller, 1)

        footer = QFrame()
        footer.setObjectName("inspectorFooter")
        footer.setStyleSheet(
            f"QFrame#inspectorFooter {{background-color: {C_BG_PANEL};"
            f" border-top: 1px solid {C_BORDER_LIGHT};}}"
        )
        actions = QVBoxLayout(footer)
        actions.setContentsMargins(16, 10, 16, 12)
        actions.setSpacing(7)

        self.btn_repair = QPushButton("REPAIR LINKS")
        self.btn_repair.setObjectName("btnYellow")
        self.btn_repair.setIcon(VectorIcon.create("shield", C_YELLOW, 15))
        self.btn_repair.setCursor(Qt.PointingHandCursor)
        self.btn_repair.setToolTip("Only safely recoverable files can be repaired")
        self.btn_repair.hide()
        actions.addWidget(self.btn_repair)

        footer_buttons = QHBoxLayout()
        footer_buttons.setSpacing(8)
        self.btn_toggle = QPushButton("TOGGLE MOD")
        self.btn_toggle.setObjectName("btnPrimary")
        self.btn_toggle.setIcon(VectorIcon.create("power", "#080c13", 15))
        self.btn_toggle.setCursor(Qt.PointingHandCursor)
        footer_buttons.addWidget(self.btn_toggle, 2)

        self.btn_delete = QPushButton("DELETE")
        self.btn_delete.setObjectName("btnDanger")
        self.btn_delete.setIcon(VectorIcon.create("trash", C_RED, 15))
        self.btn_delete.setToolTip("Permanently delete the selected mod")
        self.btn_delete.setCursor(Qt.PointingHandCursor)
        footer_buttons.addWidget(self.btn_delete, 1)
        actions.addLayout(footer_buttons)
        shell.addWidget(footer)
        self.clear_details()

    def _set_pill(self, text: str, color: str, filled: bool):
        while self.status_pill_layout.count():
            child = self.status_pill_layout.takeAt(0)
            widget = child.widget()
            if widget:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        pill = StatusPill(text, color, filled)
        self.status_pill_layout.addWidget(pill)
        pill.show()

    def update_details(self, mod_name: str, mod_data: dict, game_path=None, mods_state=None, health=None):
        display_name, archive_metadata = compact_mod_identity(mod_name)
        self.lbl_name.setText(display_name)
        self.lbl_name.setToolTip(mod_name)
        self.lbl_mod_meta.setText(archive_metadata)
        self.lbl_mod_meta.setToolTip(mod_name)
        enabled = bool(mod_data.get("enabled", False))
        health = health or {}
        health_level = health.get("level", "disabled" if not enabled else "healthy")
        issues = health.get("issues", [])
        links = mod_data.get("links", [])

        if health_level == "repairable":
            pill_text, color, filled = "REPAIR AVAILABLE", C_YELLOW, True
            health_text = "Some links need repair"
            detail = f"{len(issues)} files can be repaired safely"
        elif health_level in ("blocked", "error"):
            pill_text, color, filled = "MANUAL REVIEW", C_RED, True
            health_text = "File integrity needs attention"
            detail = (health.get("error") or
                      f"{len(issues)} files require manual inspection")
        elif enabled:
            pill_text, color, filled = "DEPLOYMENT HEALTHY", C_GREEN, True
            health_text = "All deployed links are healthy"
            detail = f"Verified {len(links)} active links"
        else:
            pill_text, color, filled = "STANDBY // OFF", C_TEXT_DIM, False
            health_text = "Mod is disabled"
            detail = "Files remain in local mod storage"

        self._set_pill(pill_text, color, filled)
        self.set_accent(color)
        self.lbl_health.setText(health_text)
        self.lbl_health.setStyleSheet(
            f"color: {color}; font-size: 13px; font-weight: 700;"
        )
        self.lbl_health_detail.setText(detail)
        self.health_bar.setValue(100 if enabled and health_level == "healthy" else 0)
        self.health_bar.setStyleSheet(
            f"QProgressBar {{background: {C_BG_DEEP}; border: none; border-radius: 3px;}}"
            f"QProgressBar::chunk {{background: {color}; border-radius: 3px;}}"
        )
        self.btn_repair.setVisible(health_level == "repairable")
        self.btn_toggle.setText("DISABLE MOD" if enabled else "ENABLE MOD")
        self.btn_toggle.setEnabled(True)
        self.btn_delete.setEnabled(True)
        self.lbl_files.setText(str(len(links)))

        mod_path = MODS_DIR / mod_name
        if mod_path.is_dir():
            try:
                total_size = sum(f.stat().st_size for f in mod_path.rglob("*") if f.is_file())
            except OSError:
                self.lbl_size.setText("—")
            else:
                self.lbl_size.setText(self._format_size(total_size))
        else:
            self.lbl_size.setText("—")

        if game_path:
            analysis = analyse_mod(mod_name, game_path)
            if analysis.file_types:
                types = sorted(analysis.file_types.items(), key=lambda item: (-item[1], item[0]))
                self.lbl_types.setText("   ·   ".join(
                    f"{extension} ×{count}" for extension, count in types[:6]
                ))
                self.lbl_types.setToolTip("\n".join(
                    f"{extension}: {count}" for extension, count in types
                ))
            else:
                self.lbl_types.setText("No files found")
                self.lbl_types.setToolTip("")

            if analysis.required_frameworks:
                parts = []
                for fid in analysis.required_frameworks:
                    fw = get_framework_info(fid)
                    name = fw.name if fw else fid
                    if fid in analysis.missing_frameworks:
                        parts.append(f'<div style="color:{C_RED}; font-weight:700;">●  {name}  — missing</div>')
                    else:
                        parts.append(f'<div style="color:{C_GREEN}; font-weight:700;">●  {name}  — ready</div>')
                self.lbl_deps.setText("".join(parts))
            else:
                self.lbl_deps.setText(
                    f'<span style="color:{C_TEXT_DIM};">No additional frameworks required</span>'
                )
        else:
            self.lbl_types.setText("—")
            self.lbl_deps.setText("—")

        conflicts = get_mod_conflicts_for(mod_name, mods_state or {})
        self.lbl_conflicts_hdr.setVisible(bool(conflicts))
        self.lbl_conflicts.setVisible(bool(conflicts))
        if conflicts:
            others = sorted({
                c.mod_b if c.mod_a == mod_name else c.mod_a for c in conflicts
            })
            self.lbl_conflicts.setText("\n".join(others))

    def clear_details(self):
        self.lbl_name.setText("NO MOD SELECTED")
        self.lbl_mod_meta.setText("")
        self._set_pill("AWAITING SELECTION", C_TEXT_DIM, False)
        self.set_accent(C_YELLOW)
        self.lbl_health.setText("Select a mod from the library")
        self.lbl_health.setStyleSheet(f"color: {C_TEXT_MUTED}; font-size: 13px;")
        self.lbl_health_detail.setText("Mod details and deployment health will appear here")
        self.health_bar.setValue(0)
        self.lbl_files.setText("—")
        self.lbl_size.setText("—")
        self.lbl_types.setText("—")
        self.lbl_deps.setText("—")
        self.lbl_conflicts_hdr.hide()
        self.lbl_conflicts.hide()
        self.btn_repair.hide()
        self.btn_toggle.setText("TOGGLE MOD")
        self.btn_toggle.setEnabled(False)
        self.btn_delete.setEnabled(False)

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024**2:
            return f"{size_bytes / 1024:.1f} KB"
        if size_bytes < 1024**3:
            return f"{size_bytes / (1024**2):.1f} MB"
        return f"{size_bytes / (1024**3):.2f} GB"


# ─────────────────────────── Main Window ─────────────────────────────

class CyberpunkModGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.mgr = ModManager()
        self.mod_health = {}
        self.setWindowTitle("CYBERPUNK 2077 // MOD DEPLOYMENT DECK")
        self.resize(1440, 860)
        self.setMinimumSize(1020, 680)
        self.setStyleSheet(CYBERPUNK_QSS)
        self.setAcceptDrops(True)

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ─────────────────── Top Header Bar ───────────────────
        header_bar = QFrame()
        header_bar.setObjectName("headerBar")
        header_layout = QHBoxLayout(header_bar)
        header_layout.setContentsMargins(26, 14, 26, 14)
        header_layout.setSpacing(16)

        header_layout.addWidget(CyberHexLogo())

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("CYBERPUNK 2077  /  MOD MANAGER")
        title.setObjectName("headerTitle")
        title_col.addWidget(title)
        subtitle = QLabel("NIGHT CITY  •  MOD DEPLOYMENT CONTROL  •  LINUX")
        subtitle.setObjectName("headerSubtitle")
        title_col.addWidget(subtitle)
        header_layout.addLayout(title_col)

        header_layout.addStretch()

        self.version_pill_holder = QWidget()
        self.version_pill_layout = QHBoxLayout(self.version_pill_holder)
        self.version_pill_layout.setContentsMargins(0, 0, 8, 0)
        header_layout.addWidget(self.version_pill_holder)

        btn_steam_cfg = QPushButton("STEAM SETTINGS")
        btn_steam_cfg.setObjectName("btnSteamCfg")
        btn_steam_cfg.setIcon(VectorIcon.create("steam", C_CYAN, 14))
        btn_steam_cfg.setCursor(Qt.PointingHandCursor)
        btn_steam_cfg.setToolTip("Steam launch options and Proton DLL overrides")
        btn_steam_cfg.clicked.connect(self.show_steam_config_dialog)
        header_layout.addWidget(btn_steam_cfg)

        btn_launch = QPushButton("LAUNCH GAME")
        btn_launch.setObjectName("btnLaunch")
        btn_launch.setIcon(VectorIcon.create("play", "#050608", 14))
        btn_launch.setCursor(Qt.PointingHandCursor)
        btn_launch.setToolTip("Launch Cyberpunk 2077 through Steam with mods (--launcher-skip -modded)")
        btn_launch.clicked.connect(self.launch_game)
        header_layout.addWidget(btn_launch)

        main_layout.addWidget(header_bar)

        # ─────────────────── Workspace Container ───────────────────
        workspace = QVBoxLayout()
        workspace.setContentsMargins(24, 17, 24, 15)
        workspace.setSpacing(14)

        # ── 1. Telemetry Metric Cards Row ──
        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(14)

        self.card_total = MetricCard("LIBRARY", "0", "MODS", C_CYAN)
        self.card_active = MetricCard("ACTIVE MODS", "0", "0 LINKS", C_GREEN)
        self.card_conflicts = MetricCard("CONFLICTS", "0", "NO ISSUES", C_GREEN)
        self.card_frameworks = MetricCard("FRAMEWORKS", "0/0", "CHECKING", C_YELLOW)

        metrics_row.addWidget(self.card_total, stretch=1)
        metrics_row.addWidget(self.card_active, stretch=1)
        metrics_row.addWidget(self.card_conflicts, stretch=1)
        metrics_row.addWidget(self.card_frameworks, stretch=1)
        workspace.addLayout(metrics_row)

        # ── 2. Target Game Directory Bar ──
        path_panel = ChamferPanel(accent_color=C_CYAN, bg_color=C_BG_PANEL, cut=8)
        path_layout = QHBoxLayout(path_panel)
        path_layout.setContentsMargins(14, 11, 14, 11)
        path_layout.setSpacing(10)

        path_lbl = QLabel("GAME DIRECTORY")
        path_lbl.setStyleSheet(f"color: {C_CYAN}; font-size: 11px; font-weight: 800;")
        path_layout.addWidget(path_lbl)

        self.path_input = QLineEdit(str(self.mgr.state_mgr.game_path))
        self.path_input.setPlaceholderText("Path to your Cyberpunk 2077 installation...")
        self.path_input.editingFinished.connect(self.update_manual_path)
        path_layout.addWidget(self.path_input, stretch=1)

        btn_browse = QPushButton("BROWSE")
        btn_browse.setIcon(VectorIcon.create("folder", C_TEXT, 14))
        btn_browse.setCursor(Qt.PointingHandCursor)
        btn_browse.clicked.connect(self.browse_game_dir)
        path_layout.addWidget(btn_browse)

        btn_auto = QPushButton("AUTO-DETECT")
        btn_auto.setObjectName("btnYellow")
        btn_auto.setIcon(VectorIcon.create("radar", C_YELLOW, 14))
        btn_auto.setCursor(Qt.PointingHandCursor)
        btn_auto.clicked.connect(self.auto_detect_game)
        path_layout.addWidget(btn_auto)

        workspace.addWidget(path_panel)

        # ── 3. Library header and two balanced action rows ──
        library_heading = QHBoxLayout()
        library_heading.setSpacing(10)
        library_title = QLabel("MOD LIBRARY")
        library_title.setObjectName("sectionTitle")
        library_heading.addWidget(library_title)
        library_heading.addStretch(1)
        self.lbl_list_count = QLabel("0 MODS")
        self.lbl_list_count.setObjectName("sectionMeta")
        library_heading.addWidget(self.lbl_list_count)
        workspace.addLayout(library_heading)

        primary_actions = QHBoxLayout()
        primary_actions.setSpacing(10)

        btn_add = QPushButton("INSTALL MOD")
        btn_add.setObjectName("btnPrimary")
        btn_add.setIcon(VectorIcon.create("plus", "#080c13", 16))
        btn_add.setCursor(Qt.PointingHandCursor)
        btn_add.clicked.connect(self.install_archives_dialog)
        primary_actions.addWidget(btn_add)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search mods by name or version...")
        self.search_input.setMinimumWidth(150)
        self.search_input.addAction(
            VectorIcon.create("search", C_TEXT_MUTED, 16), QLineEdit.LeadingPosition
        )
        self.search_input.textChanged.connect(self.filter_table)
        self.search_input.setClearButtonEnabled(True)
        primary_actions.addWidget(self.search_input, stretch=1)

        self.status_filter = QComboBox()
        self.status_filter.addItem("All mods", "all")
        self.status_filter.addItem("Enabled", "active")
        self.status_filter.addItem("Disabled", "disabled")
        self.status_filter.addItem("Needs attention", "issues")
        self.status_filter.setToolTip("Filter mods by deployment state")
        self.status_filter.currentIndexChanged.connect(self.filter_table)
        primary_actions.addWidget(self.status_filter)

        workspace.addLayout(primary_actions)

        secondary_actions = QHBoxLayout()
        secondary_actions.setSpacing(9)
        lbl_actions = QLabel("QUICK ACTIONS")
        lbl_actions.setObjectName("sectionMeta")
        secondary_actions.addWidget(lbl_actions)
        secondary_actions.addStretch(1)

        btn_verify = QPushButton("VERIFY INTEGRITY")
        btn_verify.setIcon(VectorIcon.create("shield", C_CYAN, 15))
        btn_verify.setCursor(Qt.PointingHandCursor)
        btn_verify.setToolTip("Audit deployment links for all enabled mods")
        btn_verify.clicked.connect(self.verify_all_symlinks)
        secondary_actions.addWidget(btn_verify)

        btn_repair = QPushButton("REPAIR MOD")
        btn_repair.setIcon(VectorIcon.create("radar", C_YELLOW, 15))
        btn_repair.setToolTip("Repair recoverable links for the selected mod")
        btn_repair.setCursor(Qt.PointingHandCursor)
        btn_repair.clicked.connect(self.repair_selected_mod)
        secondary_actions.addWidget(btn_repair)

        btn_enable_all = QPushButton("ENABLE ALL")
        btn_enable_all.setIcon(VectorIcon.create("check_all", C_GREEN, 14))
        btn_enable_all.setCursor(Qt.PointingHandCursor)
        btn_enable_all.clicked.connect(self.enable_all_mods)
        secondary_actions.addWidget(btn_enable_all)

        btn_disable_all = QPushButton("DISABLE ALL")
        btn_disable_all.setIcon(VectorIcon.create("close_all", C_RED, 14))
        btn_disable_all.setCursor(Qt.PointingHandCursor)
        btn_disable_all.clicked.connect(self.disable_all_mods)
        secondary_actions.addWidget(btn_disable_all)
        workspace.addLayout(secondary_actions)

        # ── 4. Split workspace: library + contextual inspector above a resizable log ──
        self.vertical_splitter = QSplitter(Qt.Vertical)
        self.vertical_splitter.setHandleWidth(8)
        self.vertical_splitter.setChildrenCollapsible(False)

        self.library_splitter = QSplitter(Qt.Horizontal)
        self.library_splitter.setHandleWidth(8)
        self.library_splitter.setChildrenCollapsible(False)
        self.library_splitter.splitterMoved.connect(self._adapt_columns)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "ENABLED", "HEALTH", "MOD", "DEPENDENCIES", "FILES"
        ])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 76)
        hdr.setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 126)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(3, 260)
        hdr.setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(4, 75)

        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.cellDoubleClicked.connect(lambda r, c: self.toggle_selected_mod())
        self.table.currentCellChanged.connect(self._on_selection_changed)
        self.table.setToolTip("Double-click to enable or disable the selected mod")
        self.library_splitter.addWidget(self.table)

        self.details_panel = ModDetailsPanel()
        self.details_panel.btn_toggle.clicked.connect(self.toggle_selected_mod)
        self.details_panel.btn_delete.clicked.connect(self.delete_selected_mod)
        self.details_panel.btn_repair.clicked.connect(self.repair_selected_mod)
        self.library_splitter.addWidget(self.details_panel)
        self.library_splitter.setSizes([990, 390])
        self.library_splitter.setStretchFactor(0, 1)
        self.library_splitter.setStretchFactor(1, 0)
        self.vertical_splitter.addWidget(self.library_splitter)

        # Resizable log area, instead of a cramped, fixed-height readout.
        log_frame = QFrame()
        log_layout = QVBoxLayout(log_frame)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(8)
        log_hdr_row = QHBoxLayout()
        log_hdr_row.setSpacing(10)

        log_title = QLabel("ACTIVITY LOG")
        log_title.setObjectName("sectionTitle")
        log_hdr_row.addWidget(log_title)

        self.lbl_log_count = QLabel("0 ENTRIES")
        self.lbl_log_count.setObjectName("sectionMeta")
        log_hdr_row.addWidget(self.lbl_log_count)
        log_hdr_row.addStretch(1)

        btn_copy_log = QPushButton("COPY")
        btn_copy_log.setCursor(Qt.PointingHandCursor)
        btn_copy_log.setToolTip("Copy the complete activity log to clipboard")
        btn_copy_log.clicked.connect(self._copy_log)
        log_hdr_row.addWidget(btn_copy_log)

        btn_clear_log = QPushButton("CLEAR")
        btn_clear_log.setCursor(Qt.PointingHandCursor)
        btn_clear_log.clicked.connect(self._clear_log)
        log_hdr_row.addWidget(btn_clear_log)
        log_layout.addLayout(log_hdr_row)

        self.log_box = QTextEdit()
        self.log_box.setObjectName("logBox")
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(70)
        self.log_box.setLineWrapMode(QTextEdit.WidgetWidth)
        self._log_lines = 0
        log_layout.addWidget(self.log_box, 1)

        self.vertical_splitter.addWidget(log_frame)
        self.vertical_splitter.setSizes([580, 125])
        self.vertical_splitter.setStretchFactor(0, 1)
        self.vertical_splitter.setStretchFactor(1, 0)
        workspace.addWidget(self.vertical_splitter, stretch=1)

        main_layout.addLayout(workspace, stretch=1)

        # ─────────────────── Status Bar ───────────────────
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.lbl_status_path = QLabel()
        self.lbl_status_shortcuts = QLabel(
            "SPACE — toggle    DEL — delete    CTRL+O — install    CTRL+K — search"
        )
        self.lbl_status_shortcuts.setStyleSheet(
            f"color: {C_TEXT_MUTED}; font-family: 'DejaVu Sans Mono'; font-size: 10px;"
        )
        self.status_bar.addWidget(self.lbl_status_path)
        self.status_bar.addPermanentWidget(self.lbl_status_shortcuts)

        # ─────────────────── Drop Overlay ───────────────────
        self.drop_overlay = DropOverlay(self)

        # ─────────────────── Shortcuts ───────────────────
        QShortcut(QKeySequence(Qt.Key_Space), self, self.toggle_selected_mod)
        QShortcut(QKeySequence(Qt.Key_Delete), self, self.delete_selected_mod)
        QShortcut(QKeySequence("Ctrl+O"), self, self.install_archives_dialog)
        QShortcut(QKeySequence("Ctrl+F"), self, lambda: self.search_input.setFocus())
        QShortcut(QKeySequence("Ctrl+K"), self, lambda: self.search_input.setFocus())

        # ─────────────────── Initialize ───────────────────
        self.verify_game_path()
        self._update_game_version()
        self._check_frameworks_status()
        self.refresh_table()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "drop_overlay"):
            self.drop_overlay.resize(self.size())
        if hasattr(self, "table"):
            self._adapt_columns()

    def _adapt_columns(self, *_):
        """Keep the name readable when the library pane is narrow."""
        self.table.setColumnHidden(3, self.table.width() < 870)

    def _copy_log(self):
        QApplication.clipboard().setText(self.log_box.toPlainText())
        self.status_bar.showMessage("Log copied to clipboard", 2500)

    def _clear_log(self):
        self.log_box.clear()
        self._log_lines = 0
        self.lbl_log_count.setText("0 ENTRIES")

    # ────────────────────── Logging ──────────────────────

    def log(self, tag: str, message: str, color: str = C_CYAN):
        ts = datetime.now().strftime("%H:%M:%S")
        html = (
            f'<span style="color:{C_TEXT_DIM};">{ts}</span> '
            f'<span style="color:{color}; font-weight:700;">[{tag}]</span> '
            f'<span style="color:{C_TEXT};">{message}</span>'
        )
        self.log_box.append(html)
        self._log_lines += 1
        self.lbl_log_count.setText(f"{self._log_lines} ENTRIES")
        sb = self.log_box.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ────────────────────── Telemetry & Checks ──────────────────────

    def _update_game_version(self):
        while self.version_pill_layout.count():
            child = self.version_pill_layout.takeAt(0)
            widget = child.widget()
            if widget:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

        gp = self.mgr.state_mgr.game_path
        gv = get_game_version(gp)
        if gv:
            self.version_pill_layout.addWidget(StatusPill(f"PATCH {gv}", C_CYAN, True))
            self.log("INFO", f"Detected Cyberpunk 2077 version: <b>{gv}</b>", C_CYAN)
        else:
            self.version_pill_layout.addWidget(StatusPill("EXE NOT FOUND", C_RED, False))

        pfx = find_proton_prefix(gp)
        if pfx:
            ok, _ = check_proton_overrides(pfx)
            if ok:
                self.version_pill_layout.addWidget(StatusPill("PROTON HOOKS: OK", C_GREEN, True))
            else:
                self.version_pill_layout.addWidget(StatusPill("PROTON HOOKS: MISSING", C_ORANGE, True))

    def _check_frameworks_status(self):
        gp = self.mgr.state_mgr.game_path
        statuses = get_all_frameworks_status(gp)
        installed = [fid for fid, ok in statuses.items() if ok]
        total_fw = len(statuses)

        if installed:
            names = [get_framework_info(fid).name for fid in installed]
            self.log("CORE", f"Enabled базові фреймворки: <b>{', '.join(names)}</b>", C_GREEN)
        else:
            self.log("WARN", "No core frameworks (CET / RED4ext / Redscript) detected.", C_ORANGE)

        accent = C_GREEN if len(installed) > 0 else C_ORANGE
        self.card_frameworks.set_metric(
            f"{len(installed)}/{total_fw}",
            "INSTALLED",
            accent
        )

    def _update_dashboard(self):
        mods = self.mgr.state_mgr.state.get("mods", {})
        total = len(mods)
        active = sum(1 for m in mods.values() if m.get("enabled"))
        total_links = sum(len(m.get("links", [])) for m in mods.values() if m.get("enabled"))

        conflicts = detect_conflicts(mods)
        conflict_files = len(set(c.file_path for c in conflicts))

        self.card_total.set_metric(str(total), "IN STORAGE", C_CYAN)
        self.card_active.set_metric(
            str(active),
            f"{total_links} LINKS",
            C_GREEN if active > 0 else C_TEXT_MUTED
        )

        if conflict_files > 0:
            self.card_conflicts.set_metric(str(conflict_files), "OVERLAPS", C_ORANGE)
        else:
            self.card_conflicts.set_metric("0", "CLEAN", C_GREEN)

        gp = self.mgr.state_mgr.game_path
        statuses = get_all_frameworks_status(gp)
        inst_count = sum(1 for ok in statuses.values() if ok)
        self.card_frameworks.set_metric(
            f"{inst_count}/{len(statuses)}",
            "READY" if inst_count else "MISSING",
            C_GREEN if inst_count else C_YELLOW
        )

    # ────────────────────── Game Path ──────────────────────

    def verify_game_path(self):
        gp = self.mgr.state_mgr.game_path
        exe = gp / "bin/x64/Cyberpunk2077.exe"
        if exe.exists():
            self.log("READY", f"Game directory connected: <b>{gp}</b>", C_GREEN)
            self.lbl_status_path.setText("●  GAME CONNECTED")
            self.lbl_status_path.setToolTip(str(gp))
            self.lbl_status_path.setStyleSheet(f"color: {C_GREEN}; font-weight: 800;")
        else:
            self.log("ERR", f"Cyberpunk2077.exe not found in: {gp}", C_RED)
            self.lbl_status_path.setText("●  GAME NOT FOUND")
            self.lbl_status_path.setToolTip(str(gp))
            self.lbl_status_path.setStyleSheet(f"color: {C_RED}; font-weight: 800;")

    def update_manual_path(self):
        new_path = self.path_input.text().strip()
        if new_path:
            self.mgr.state_mgr.game_path = new_path
            self.verify_game_path()
            self._update_game_version()
            self._check_frameworks_status()
            self.refresh_table()

    def browse_game_dir(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select the Cyberpunk 2077 installation directory",
            str(self.mgr.state_mgr.game_path)
        )
        if folder:
            self.path_input.setText(folder)
            self.update_manual_path()

    def auto_detect_game(self):
        self.log("SCAN", "Scanning Steam libraries and mount points...", C_CYAN)
        QApplication.processEvents()
        found = auto_find_cyberpunk()
        self.path_input.setText(str(found))
        self.update_manual_path()

    # ────────────────────── Mod Table ──────────────────────

    def refresh_table(self, recheck=True):
        selected_mod = self.get_selected_mod_name()
        if recheck or not self.mod_health:
            self.mod_health = self.mgr.health_snapshot()
        self.table.setRowCount(0)

        mods = self.mgr.state_mgr.state.get("mods", {})
        search_text = self.search_input.text().strip().lower()
        selected_filter = self.status_filter.currentData()
        game_path = self.mgr.state_mgr.game_path

        row_to_select = -1

        for name, data in sorted(mods.items(), key=lambda item: item[0].casefold()):
            if search_text and search_text not in name.lower():
                continue
            level = self.mod_health.get(name, {}).get("level", "disabled")
            enabled = bool(data.get("enabled", False))
            if selected_filter == "active" and not enabled:
                continue
            if selected_filter == "disabled" and enabled:
                continue
            if selected_filter == "issues" and level not in ("repairable", "blocked", "error"):
                continue

            row = self.table.rowCount()
            self.table.insertRow(row)
            enabled = data.get("enabled", False)

            if name == selected_mod:
                row_to_select = row

            # Col 0: Interactive Toggle Switch
            toggle_holder = QWidget()
            th_layout = QHBoxLayout(toggle_holder)
            th_layout.setContentsMargins(0, 0, 0, 0)
            th_layout.setAlignment(Qt.AlignCenter)
            sw = CyberToggle(checked=enabled)
            sw.toggled.connect(lambda state, m=name: self._on_switch_toggled(m, state))
            th_layout.addWidget(sw)
            self.table.setCellWidget(row, 0, toggle_holder)

            # Col 1: Health-aware status, audited without modifying game files.
            health = self.mod_health.get(name, {"level": "disabled", "issues": []})
            level = health["level"]
            health_styles = {
                "healthy": ("ACTIVE", C_GREEN, True),
                "disabled": ("STANDBY", C_TEXT_DIM, False),
                "repairable": ("REPAIR", C_YELLOW, True),
                "blocked": ("ISSUE", C_RED, True),
                "error": ("ERROR", C_RED, True),
            }
            label, color, filled = health_styles.get(level, ("UNKNOWN", C_ORANGE, False))
            tooltip_lines = [f"Mod status: {level}"]
            if health.get("error"):
                tooltip_lines.append(health["error"])
            tooltip_lines.extend(
                f"{path}: {issue}" for path, issue in health.get("issues", [])[:12]
            )
            if len(health.get("issues", [])) > 12:
                tooltip_lines.append("…")
            health_tooltip = "\n".join(tooltip_lines)
            pill_holder = QWidget()
            pill_holder.setToolTip(health_tooltip)
            ph_layout = QHBoxLayout(pill_holder)
            ph_layout.setContentsMargins(6, 0, 6, 0)
            ph_layout.setAlignment(Qt.AlignCenter)
            pill = StatusPill(label, color, filled)
            pill.setToolTip(health_tooltip)
            ph_layout.addWidget(pill)
            self.table.setCellWidget(row, 1, pill_holder)

            # Col 2: human-readable title; exact original name stays in UserRole.
            display_name, archive_metadata = self._display_mod_name(name)
            name_item = QTableWidgetItem(display_name)
            name_item.setToolTip(
                f"{name}\n{archive_metadata}\n\n{health_tooltip}"
            )
            name_item.setData(Qt.UserRole, name)
            name_font = QFont("Noto Sans", 10)
            name_font.setBold(enabled)
            name_item.setFont(name_font)
            name_item.setForeground(QColor(C_TEXT if enabled else C_TEXT_MUTED))
            self.table.setItem(row, 2, name_item)

            # Col 3: Dependencies status
            analysis = analyse_mod(name, game_path)
            if analysis.missing_frameworks:
                missing_names = [
                    get_framework_info(f).name for f in analysis.missing_frameworks if get_framework_info(f)
                ]
                deps_text = "MISSING: " + ", ".join(missing_names)
                deps_color = C_RED
            elif analysis.required_frameworks:
                ok_names = [
                    get_framework_info(f).name for f in analysis.required_frameworks if get_framework_info(f)
                ]
                deps_text = "OK: " + ", ".join(ok_names)
                deps_color = C_GREEN
            else:
                deps_text = "STANDALONE"
                deps_color = C_TEXT_DIM

            deps_item = QTableWidgetItem(deps_text)
            deps_item.setForeground(QColor(deps_color))
            deps_font = QFont("JetBrains Mono", 9)
            deps_font.setBold(True)
            deps_item.setFont(deps_font)
            self.table.setItem(row, 3, deps_item)

            # Col 4: Symlink count
            link_count = len(data.get("links", []))
            links_item = QTableWidgetItem(str(link_count))
            links_item.setTextAlignment(Qt.AlignCenter)
            links_item.setForeground(QColor(C_CYAN if link_count > 0 else C_TEXT_DIM))
            links_font = QFont("JetBrains Mono", 10)
            links_font.setBold(True)
            links_item.setFont(links_font)
            self.table.setItem(row, 4, links_item)

        self._update_dashboard()
        visible = self.table.rowCount()
        self.lbl_list_count.setText(
            f"{visible} OF {len(mods)} MODS" if visible != len(mods)
            else f"{visible} MODS IN LIBRARY"
        )
        self._adapt_columns()

        if row_to_select >= 0:
            self.table.selectRow(row_to_select)
        elif self.table.rowCount() > 0:
            self.table.selectRow(0)
        else:
            self.details_panel.clear_details()

    @staticmethod
    def _display_mod_name(name: str) -> tuple[str, str]:
        return compact_mod_identity(name)

    def filter_table(self, _value=None):
        self.refresh_table(recheck=False)

    def _on_selection_changed(self, row: int, col: int, prev_row: int, prev_col: int):
        if row < 0:
            self.details_panel.clear_details()
            return
        name_item = self.table.item(row, 2)
        if not name_item:
            return
        mod_name = name_item.data(Qt.UserRole)
        if mod_name:
            mod_data = self.mgr.state_mgr.state.get("mods", {}).get(mod_name, {})
            self.details_panel.update_details(
                mod_name, mod_data,
                game_path=self.mgr.state_mgr.game_path,
                mods_state=self.mgr.state_mgr.state.get("mods", {}),
                health=self.mod_health.get(mod_name),
            )

    def _on_switch_toggled(self, mod_name: str, target_state: bool):
        try:
            if target_state:
                self.mgr.enable_mod(mod_name)
                self.log("LINK", f"Mod <b>{mod_name}</b> has been deployed.", C_GREEN)
            else:
                self.mgr.disable_mod(mod_name)
                self.log("UNLINK", f"Mod <b>{mod_name}</b> has been disabled and unlinked.", C_YELLOW)
            self.refresh_table()
        except Exception as e:
            self.log("ERR", f"{mod_name}: {e}", C_RED)
            self.refresh_table()

    # ────────────────────── Mod Operations ──────────────────────

    def get_selected_mod_name(self) -> str | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 2)
        return item.data(Qt.UserRole) if item else None

    def install_archives_dialog(self):
        downloads_dir = str(Path.home() / "Downloads")
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select mod archives",
            downloads_dir,
            "Archives (*.zip *.7z *.rar *.tar.gz);;All files (*)"
        )
        if files:
            self._install_archives(files)

    def _install_archives(self, file_paths: list[str]):
        for fpath in file_paths:
            try:
                fname = Path(fpath).name
                self.log("DEPLOY", f"Extracting and preparing <b>{fname}</b>...", C_CYAN)
                QApplication.processEvents()
                self.mgr.install_from_archive(fpath)
                self.log("OK", f"Mod <b>{Path(fpath).stem}</b> installed and enabled.", C_GREEN)
            except Exception as e:
                self.log("FAIL", f"{Path(fpath).name}: {e}", C_RED)
        self._check_frameworks_status()
        self.refresh_table()

    def toggle_selected_mod(self):
        mod_name = self.get_selected_mod_name()
        if not mod_name:
            self.log("WARN", "Select a mod from the list first.", C_YELLOW)
            return
        is_enabled = self.mgr.state_mgr.state["mods"][mod_name]["enabled"]
        self._on_switch_toggled(mod_name, not is_enabled)

    def delete_selected_mod(self):
        mod_name = self.get_selected_mod_name()
        if not mod_name:
            return

        reply = QMessageBox.warning(
            self,
            "Confirm deletion",
            f"Permanently delete mod '{mod_name}'?\n\n"
            f"All managed links will be removed, and the mod files will be deleted from local storage.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        try:
            self.mgr.remove_mod(mod_name)
            self.log("PURGE", f"Mod <b>{mod_name}</b> removed from local storage.", C_RED)
            self.details_panel.clear_details()
            self.refresh_table()
        except Exception as e:
            self.log("ERR", str(e), C_RED)

    def enable_all_mods(self):
        mods = self.mgr.state_mgr.state.get("mods", {})
        count = 0
        for name, data in mods.items():
            if not data.get("enabled"):
                try:
                    self.mgr.enable_mod(name)
                    count += 1
                except Exception as e:
                    self.log("ERR", f"{name}: {e}", C_RED)
        if count:
            self.log("BATCH", f"Mods enabled: <b>{count}</b>", C_GREEN)
        self.refresh_table()

    def disable_all_mods(self):
        mods = self.mgr.state_mgr.state.get("mods", {})
        count = 0
        for name, data in mods.items():
            if data.get("enabled"):
                try:
                    self.mgr.disable_mod(name)
                    count += 1
                except Exception as e:
                    self.log("ERR", f"{name}: {e}", C_RED)
        if count:
            self.log("BATCH", f"Mods disabled: <b>{count}</b>", C_YELLOW)
        self.refresh_table()


    def repair_selected_mod(self):
        mod_name = self.get_selected_mod_name()
        if not mod_name:
            self.log("WARN", "Select a mod first.", C_YELLOW)
            return
        try:
            report = self.mgr.inspect_reconcile(mod_name)
            if not report:
                self.log("REPAIR", f"{mod_name}: all deployed links are healthy.", C_GREEN)
                return
            copies = [rel for rel, status in report if status == "identical_copy"]
            missing = [rel for rel, status in report if status == "missing"]
            other = [(rel, status) for rel, status in report if status not in ("identical_copy", "missing")]
            if other:
                self.log("WARN", f"{mod_name}: repair blocked: {other}", C_ORANGE)
                return
            reply = QMessageBox.question(
                self,
                "Safe link repair",
                f"Mod: {mod_name}\n\n"
                f"Identical copies: {len(copies)}. Missing links: {len(missing)}.\n"
                "Restore symbolic links for these files?\n"
                "Modified or foreign files will never be overwritten.",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
            fixed = self.mgr.repair_identical_copies(mod_name)
            self.log("REPAIR", f"{mod_name}: links repaired: {len(fixed)}.", C_GREEN)
            self.refresh_table()
        except Exception as e:
            self.log("ERR", f"{mod_name}: {e}", C_RED)

    def verify_all_symlinks(self):
        self.log("VERIFY", "Checking all enabled mods for deployment issues...", C_CYAN)
        QApplication.processEvents()
        self.mod_health = self.mgr.health_snapshot()
        problems = 0
        for mod_name, health in self.mod_health.items():
            level = health["level"]
            if level in ("disabled", "healthy"):
                continue
            problems += 1
            if level == "error":
                self.log("ERR", f"{mod_name}: audit failed: {health.get('error', 'unknown')}", C_RED)
                continue
            counts = {}
            for _, status in health["issues"]:
                counts[status] = counts.get(status, 0) + 1
            descriptions = {
                "identical_copy": "identical copies",
                "missing": "missing links",
                "missing_source": "missing source files",
                "modified_file": "modified files",
                "foreign_link": "foreign links",
                "unexpected_target": "unexpected files or directories",
                "backup_conflict": "backup conflicts",
            }
            parts = [f"{count} {descriptions.get(status, status)}"
                     for status, count in counts.items()]
            hint = "safe repair available" if level == "repairable" else "manual review required"
            self.log("ISSUE", f"{mod_name}: {', '.join(parts)} — {hint}",
                     C_YELLOW if level == "repairable" else C_RED)
        if problems == 0:
            self.log("OK", "Integrity verified: all enabled mods have healthy deployment links.", C_GREEN)
        else:
            self.log("VERIFY", f"Mods with issues: {problems}. See the HEALTH column for details.", C_ORANGE)
        self.refresh_table(recheck=False)

    def launch_game(self):
        self.log("EXEC", "Preparing Steam launch (AppID 1091500)...", C_YELLOW)
        pfx = find_proton_prefix(self.mgr.state_mgr.game_path)
        if pfx:
            ok, missing = check_proton_overrides(pfx)
            if not ok:
                success, msg = configure_proton_overrides(pfx, missing)
                if success:
                    self.log("CORE", f"Automatically configured Proton DLL overrides ({', '.join(missing)})", C_GREEN)
            else:
                self.log("CORE", "Proton DLL overrides (version.dll, winmm.dll) are active", C_GREEN)

        self.log("INFO", "Launch arguments: <b>--launcher-skip -modded</b>", C_CYAN)
        success, msg = launch_game_steam(self.mgr.state_mgr.game_path)
        if success:
            self.log("OK", f"{msg}", C_GREEN)
        else:
            self.log("ERROR", f"{msg}", C_RED)
            QMessageBox.warning(self, "Launch failed", f"Failed to launch the game:\n{msg}")

    def show_steam_config_dialog(self):
        dialog = SteamConfigDialog(self.mgr.state_mgr.game_path, log_fn=self.log, parent=self)
        dialog.exec()
        self._update_game_version()

    # ────────────────────── Drag & Drop ──────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            valid_exts = (".zip", ".7z", ".rar", ".tar.gz")
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith(valid_exts):
                    event.acceptProposedAction()
                    self.drop_overlay.resize(self.size())
                    self.drop_overlay.raise_()
                    self.drop_overlay.show()
                    return
        event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent):
        self.drop_overlay.hide()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):
        self.drop_overlay.hide()
        if event.mimeData().hasUrls():
            valid_exts = (".zip", ".7z", ".rar", ".tar.gz")
            archive_paths = [
                url.toLocalFile()
                for url in event.mimeData().urls()
                if url.toLocalFile().lower().endswith(valid_exts)
            ]
            if archive_paths:
                event.acceptProposedAction()
                self._install_archives(archive_paths)
                return
        event.ignore()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    for font_name in ["JetBrains Mono", "Fira Code", "Noto Sans Mono"]:
        if QFontDatabase.hasFamily(font_name):
            app.setFont(QFont(font_name, 10))
            break
    window = CyberpunkModGUI()
    window.show()
    sys.exit(app.exec())