"""
FSM Designer & Visualizer for IPD432.
Features:
- Tabular / Option-based description of States, I/O ports, and Transitions
- Formal Rule Validator (Latches, Unreachable, Non-complimentary checks)
- Auto-rendered State Diagram (Moore split circles, Mealy arrow labels, Reset arrow, I/O Legend)
- Real-time SystemVerilog Code Generator (2-always / 3-always block formats)
"""
from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Tuple
from PySide6.QtCore import Qt, QRectF, QPointF, QLineF, Signal
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QFontMetrics, QPainterPath, QPolygonF,
    QPainterPathStroker
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QGroupBox,
    QFormLayout, QLineEdit, QComboBox, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QLabel, QTextEdit, QListWidget,
    QListWidgetItem, QGraphicsView, QGraphicsScene, QGraphicsItem,
    QGraphicsPathItem, QGraphicsTextItem, QMessageBox, QFileDialog,
    QCheckBox, QTabWidget, QDialog, QMenu
)

from app.core.fsm_model import (
    FSM, FSMType, ResetType, FSMEncoding, Port, State, Transition
)
from app.core.fsm_validator import FSMValidator, ValidationIssue
from app.core.sv_generator import SystemVerilogGenerator


class StateOutputsDialog(QDialog):
    """Configuration dialog for Moore outputs of an FSM state"""

    def __init__(self, state: State, parent=None):
        super().__init__(parent)
        self.state = state
        self.setWindowTitle(f"Configurar Salidas Moore: Estado {state.name}")
        self.resize(420, 340)
        layout = QVBoxLayout(self)

        lbl_info = QLabel(f"Defina las señales de salida y sus valores para el estado <b>{state.name}</b>:")
        layout.addWidget(lbl_info)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Señal de Salida", "Valor Asignado (ej: 1'b1, 2'b00)"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 160)
        layout.addWidget(self.table)

        # Populate
        for k, v in sorted(state.moore_outputs.items()):
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(k))
            self.table.setItem(r, 1, QTableWidgetItem(v))

        btn_row = QHBoxLayout()
        btn_add = QPushButton("➕ Agregar Salida")
        btn_del = QPushButton("➖ Eliminar Salida")
        btn_add.clicked.connect(self._add_row)
        btn_del.clicked.connect(self._del_row)
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_del)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        dlg_btns = QHBoxLayout()
        btn_ok = QPushButton("Aplicar Cambios")
        btn_ok.setStyleSheet("font-weight: bold; background: #0066cc; color: white; padding: 6px;")
        btn_cancel = QPushButton("Cancelar")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        dlg_btns.addStretch()
        dlg_btns.addWidget(btn_cancel)
        dlg_btns.addWidget(btn_ok)
        layout.addLayout(dlg_btns)

    def _add_row(self):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(f"out_{r}"))
        self.table.setItem(r, 1, QTableWidgetItem("1'b1"))

    def _del_row(self):
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)

    def get_outputs(self) -> Dict[str, str]:
        res = {}
        for r in range(self.table.rowCount()):
            k_item = self.table.item(r, 0)
            v_item = self.table.item(r, 1)
            k = k_item.text().strip() if k_item else ""
            v = v_item.text().strip() if v_item else ""
            if k:
                res[k] = v or "1'b0"
        return res


class FSMStateCircleItem(QGraphicsItem):
    """
    State circle complying strictly with IPD432 conventions:
    - Moore: circle divided by horizontal line (Top: State Name, Bottom: Output values)
    - Mealy: circle with State Name (outputs on transitions)
    - Long state names are automatically split into two balanced lines so circles stay compact
    - Draggable for clean report layouts
    - Dynamic radius: auto-scales when a Moore state has > 2 outputs so they never run out of space
    """
    BASE_RADIUS = 42.0
    RADIUS = 42.0  # Backwards compatibility

    def __init__(self, state: State, fsm: FSM, parent_scene=None):
        super().__init__()
        self.state = state
        self.fsm = fsm
        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemIsSelectable |
            QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setPos(state.x, state.y)
        self.setZValue(2)

    @staticmethod
    def wrap_state_name(name: str, max_chars: int = 8) -> List[str]:
        """Splits long state names into up to two balanced lines to fit cleanly inside state circles."""
        name = name.strip()
        if not name:
            return [""]
        if len(name) <= max_chars:
            return [name]

        # 1. Try splitting at '_', '-', or whitespace closest to the midpoint
        best_split: Optional[Tuple[str, str]] = None
        best_diff = float("inf")
        for m in re.finditer(r"[_\-\s]+", name):
            sep = m.group(0)
            split_idx = m.end() if ("_" in sep or "-" in sep) else m.start()
            left = name[:split_idx].strip()
            right = name[m.end():].strip()
            if left and right:
                diff = abs(len(left) - len(right))
                if diff < best_diff:
                    best_diff = diff
                    best_split = (left, right)

        if best_split:
            left, right = best_split
            if max(len(left), len(right)) <= max(max_chars + 3, int(len(name) * 0.72)):
                return [left, right]

        # 2. Try CamelCase boundary (e.g. EstadoInicial -> Estado / Inicial)
        for m in re.finditer(r"(?<=[a-z0-9])(?=[A-Z])", name):
            idx = m.start()
            left, right = name[:idx], name[idx:]
            if left and right:
                diff = abs(len(left) - len(right))
                if diff < best_diff:
                    best_diff = diff
                    best_split = (left, right)

        if best_split:
            left, right = best_split
            if max(len(left), len(right)) <= max(max_chars + 3, int(len(name) * 0.72)):
                return [left, right]

        # 3. Fallback: split evenly into two lines at midpoint
        half = (len(name) + 1) // 2
        return [name[:half], name[half:]]

    @property
    def radius(self) -> float:
        name_lines = self.wrap_state_name(self.state.name)
        max_name_len = max((len(line) for line in name_lines), default=0)
        r_name = self.BASE_RADIUS if max_name_len <= 9 else min(54.0, self.BASE_RADIUS + (max_name_len - 9) * 2.5)

        if self.fsm.fsm_type == FSMType.MOORE and self.state.moore_outputs:
            num_outs = len(self.state.moore_outputs)
            max_len = max((len(f"{k} = {v}") for k, v in self.state.moore_outputs.items()), default=0)
            if num_outs <= 2 and max_len <= 12:
                return max(self.BASE_RADIUS, r_name)
            # Vertical space in lower hemisphere (Consolas font ~13-14px per line)
            r_h = 16.0 + num_outs * 13.0
            # Horizontal space (chord width near bottom line)
            r_w = (max_len * 6.0 + 10.0) / 1.4
            return max(self.BASE_RADIUS, r_name, r_h, r_w)
        return max(self.BASE_RADIUS, r_name)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        r = self.radius
        path.addEllipse(QPointF(0, 0), r, r)
        return path

    def boundingRect(self) -> QRectF:
        r = self.radius + 3
        return QRectF(-r, -r, 2 * r, 2 * r)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            pos = self.pos()
            self.state.x = pos.x()
            self.state.y = pos.y()
            if self.scene() and hasattr(self.scene(), "update_transitions"):
                self.scene().update_transitions()
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event):
        if self.fsm.fsm_type == FSMType.MOORE:
            parent_view = self.scene().views()[0] if self.scene() and self.scene().views() else None
            w = parent_view
            while w and not isinstance(w, FSMDesignerWidget):
                w = w.parentWidget()
            if w:
                w.open_state_outputs_dialog(self.state)
            else:
                dlg = StateOutputsDialog(self.state, parent_view)
                if dlg.exec():
                    self.state.moore_outputs = dlg.get_outputs()
                    if self.scene():
                        self.scene().rebuild_scene()
            if event:
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    @staticmethod
    def _fit_font_size(lines: List[str], max_width: float, start_size: int, min_size: int = 7) -> int:
        fsize = start_size
        while fsize > min_size:
            fm = QFontMetrics(QFont("Segoe UI", fsize, QFont.Bold))
            w = max((fm.horizontalAdvance(line) for line in lines), default=0)
            if w <= max_width:
                break
            fsize -= 1
        return fsize

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        r = self.radius
        rect = QRectF(-r, -r, 2 * r, 2 * r)

        # Background and outline
        pen_color = QColor(0, 102, 204) if self.isSelected() else QColor(30, 30, 30)
        painter.setPen(QPen(pen_color, 2.0))
        painter.setBrush(QBrush(QColor(250, 250, 252)))
        painter.drawEllipse(rect)

        name_lines = self.wrap_state_name(self.state.name)
        wrapped_name = "\n".join(name_lines)

        if self.fsm.fsm_type == FSMType.MOORE:
            # Divided circle (IPD432 slide 11 & 24)
            painter.drawLine(QLineF(-r, 0, r, 0))

            # Top: State ID (1 or 2 lines inside upper hemisphere)
            base_top_fsize = (10 if r <= 50 else 11) if len(name_lines) == 1 else (9 if r <= 50 else 10)
            avail_top_w = 2 * r * (0.76 if len(name_lines) == 1 else 0.70)
            top_fsize = self._fit_font_size(name_lines, avail_top_w, base_top_fsize, min_size=7)
            painter.setFont(QFont("Segoe UI", top_fsize, QFont.Bold))
            top_rect = QRectF(-r + 4, -r + 3, 2 * r - 8, r - 4)
            painter.drawText(top_rect, Qt.AlignCenter, wrapped_name)

            # Bottom: Outputs
            out_lines = []
            for k, v in self.state.moore_outputs.items():
                out_lines.append(f"{k} = {v}")
            out_text = "\n".join(out_lines) if out_lines else "(none)"

            f_size = 8 if len(out_lines) <= 2 else (8 if len(out_lines) <= 4 else 7)
            painter.setFont(QFont("Consolas", f_size, QFont.Normal))
            out_rect = QRectF(-r + 4, 4, 2 * r - 8, r - 8)
            painter.drawText(out_rect, Qt.AlignCenter, out_text)

        else:  # MEALY
            base_fsize = 11 if len(name_lines) == 1 else 10
            avail_w = 2 * r - 12.0
            top_fsize = self._fit_font_size(name_lines, avail_w, base_fsize, min_size=8)
            painter.setFont(QFont("Segoe UI", top_fsize, QFont.Bold))
            text_rect = QRectF(-r + 5, -r + 5, 2 * r - 10, 2 * r - 10)
            painter.drawText(text_rect, Qt.AlignCenter, wrapped_name)


class FSMTransitionBadgeItem(QGraphicsItem):
    """Draggable condition & Mealy output badge tag on an FSM transition arrow"""
    FONT_FAMILY = "Segoe UI"
    FONT_SIZE = 11

    def __init__(self, trans_item: "FSMTransitionItem"):
        super().__init__(trans_item)
        self.trans_item = trans_item
        self._is_updating = False
        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemIsSelectable |
            QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setZValue(3)
        self.update_position()

    @classmethod
    def measure_text(cls, text: str) -> Tuple[float, float]:
        if not text:
            return 0.0, 0.0
        font = QFont(cls.FONT_FAMILY, cls.FONT_SIZE, QFont.Bold)
        fm = QFontMetrics(font)
        lines = text.splitlines() or [text]
        tw = max((fm.horizontalAdvance(line) for line in lines), default=0) + 16
        th = len(lines) * fm.lineSpacing() + 6
        return float(tw), float(th)

    def update_position(self):
        self._is_updating = True
        try:
            self.prepareGeometryChange()
            t = self.trans_item.transition
            if t.custom_label_pos is not None:
                scene_pt = QPointF(t.custom_label_pos[0], t.custom_label_pos[1])
                self.setPos(self.trans_item.mapFromScene(scene_pt))
            else:
                if hasattr(self.trans_item, "label_pos"):
                    self.setPos(self.trans_item.label_pos)
        finally:
            self._is_updating = False

    def boundingRect(self) -> QRectF:
        text = self.trans_item.display_text
        if not text:
            return QRectF()
        tw, th = self.measure_text(text)
        return QRectF(-tw / 2 - 2, -th / 2 - 2, tw + 4, th + 4)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged and not getattr(self, "_is_updating", False):
            scene_pos = self.mapToScene(QPointF(0, 0))
            self.trans_item.transition.custom_label_pos = (scene_pos.x(), scene_pos.y())
        return super().itemChange(change, value)

    def reset_position(self):
        self.trans_item.transition.custom_label_pos = None
        self.update_position()

    def paint(self, painter: QPainter, option, widget=None):
        text = self.trans_item.display_text
        if not text:
            return
        painter.setRenderHint(QPainter.Antialiasing)
        tw, th = self.measure_text(text)
        badge_rect = QRectF(-tw / 2, -th / 2, tw, th)

        bg_color = QColor(230, 243, 255) if self.isSelected() else QColor(255, 255, 255, 245)
        border_color = QColor(0, 102, 204) if self.isSelected() else QColor(180, 180, 180)
        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1.2 if self.isSelected() else 0.8))
        painter.drawRoundedRect(badge_rect, 4, 4)

        painter.setFont(QFont(self.FONT_FAMILY, self.FONT_SIZE, QFont.Bold))
        painter.setPen(QPen(QColor(20, 20, 20)))
        painter.drawText(badge_rect, Qt.AlignCenter, text)


class FSMTransitionEndpointHandle(QGraphicsItem):
    """
    Draggable handle on the circumference of a state circle to adjust
    the start point or end point of a transition arrow.
    """
    RADIUS = 4.5

    def __init__(self, trans_item: "FSMTransitionItem", is_start: bool):
        super().__init__(trans_item)
        self.trans_item = trans_item
        self.is_start = is_start
        self._is_updating = False
        self.is_hovered = False
        self.setAcceptHoverEvents(True)
        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setZValue(5)
        self.setCursor(Qt.CrossCursor)
        role_str = "inicio" if is_start else "final"
        self.setToolTip(
            f"Arrastre sobre el borde del estado para ajustar el {role_str} de la flecha.\n"
            f"(Doble clic para restablecer posición automática)"
        )
        self.update_position()

    def update_position(self):
        self._is_updating = True
        try:
            self.prepareGeometryChange()
            pt = getattr(self.trans_item, "start_pt" if self.is_start else "end_pt", None)
            if pt is not None:
                self.setPos(self.trans_item.mapFromScene(pt))
        finally:
            self._is_updating = False

    def boundingRect(self) -> QRectF:
        r = self.RADIUS + 5.0
        return QRectF(-r, -r, 2 * r, 2 * r)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(QPointF(0, 0), self.RADIUS + 4.0, self.RADIUS + 4.0)
        return path

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and not getattr(self, "_is_updating", False):
            state_item = self.trans_item.src_item if self.is_start else self.trans_item.dst_item
            if state_item:
                center = state_item.scenePos()
                r = getattr(state_item, "radius", FSMStateCircleItem.BASE_RADIUS)
                scene_target = self.trans_item.mapToScene(value)
                dx = scene_target.x() - center.x()
                dy = scene_target.y() - center.y()
                if abs(dx) > 1e-4 or abs(dy) > 1e-4:
                    angle = math.atan2(dy, dx)
                    if self.is_start:
                        self.trans_item.transition.start_angle = angle
                    else:
                        self.trans_item.transition.end_angle = angle
                    snapped_scene = QPointF(center.x() + r * math.cos(angle), center.y() + r * math.sin(angle))
                    self.trans_item.update_path()
                    return self.trans_item.mapFromScene(snapped_scene)
        return super().itemChange(change, value)

    def reset_angle(self):
        if self.is_start:
            self.trans_item.transition.start_angle = None
        else:
            self.trans_item.transition.end_angle = None
        self.trans_item.update_path()

    def mouseDoubleClickEvent(self, event):
        self.reset_angle()
        if event:
            event.accept()

    def hoverEnterEvent(self, event):
        self.is_hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.is_hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def paint(self, painter: QPainter, option, widget=None):
        scene = self.scene()
        is_exporting = bool(getattr(scene, "is_exporting", False)) if scene else (widget is None)
        if is_exporting:
            return

        painter.setRenderHint(QPainter.Antialiasing)
        if self.is_hovered:
            painter.setBrush(QBrush(QColor(255, 120, 0)))
            painter.setPen(QPen(QColor(255, 255, 255), 1.5))
            painter.drawEllipse(QPointF(0, 0), self.RADIUS + 1.0, self.RADIUS + 1.0)
        else:
            is_custom = (
                self.trans_item.transition.start_angle is not None
                if self.is_start
                else self.trans_item.transition.end_angle is not None
            )
            fill = QColor(0, 102, 204, 210) if is_custom else QColor(230, 243, 255, 210)
            border = QColor(0, 80, 170)
            painter.setBrush(QBrush(fill))
            painter.setPen(QPen(border, 1.2))
            painter.drawEllipse(QPointF(0, 0), 3.4, 3.4)


class FSMTransitionItem(QGraphicsPathItem):
    """
    Transition arrow with smart obstacle avoidance, adaptive curvature,
    draggable circumference start/end handles, and crisp condition badges.
    Strictly prevents overlapping lines and intersections with intermediate states.
    """

    def __init__(self, transition: Transition, fsm: FSM, src_item: FSMStateCircleItem, dst_item: FSMStateCircleItem):
        super().__init__()
        self.transition = transition
        self.fsm = fsm
        self.src_item = src_item
        self.dst_item = dst_item
        self.display_text = ""
        self.start_pt: QPointF = QPointF()
        self.end_pt: QPointF = QPointF()
        self.setZValue(3)
        self.badge_item: Optional[FSMTransitionBadgeItem] = None
        self.start_handle: Optional[FSMTransitionEndpointHandle] = None
        self.end_handle: Optional[FSMTransitionEndpointHandle] = None
        self.update_path()
        self.badge_item = FSMTransitionBadgeItem(self)
        self.start_handle = FSMTransitionEndpointHandle(self, is_start=True)
        self.end_handle = FSMTransitionEndpointHandle(self, is_start=False)

    def _sync_auxiliary_items(self):
        if hasattr(self, "badge_item") and self.badge_item:
            self.badge_item.update_position()
        if hasattr(self, "start_handle") and self.start_handle:
            self.start_handle.update_position()
        if hasattr(self, "end_handle") and self.end_handle:
            self.end_handle.update_position()

    def reset_endpoints(self):
        self.transition.start_angle = None
        self.transition.end_angle = None
        self.update_path()

    def _prepare_label_text(self):
        cond = self.transition.condition
        if self.transition.is_timed and self.transition.timer_cycles > 0:
            timer_str = f"t={self.transition.timer_cycles-1}"
            cond = f"{cond} & {timer_str}" if cond and cond != "else" else timer_str

        if self.fsm.fsm_type == FSMType.MEALY and self.transition.mealy_outputs:
            out_strs = [f"{k}={v}" for k, v in self.transition.mealy_outputs.items()]
            outs_joined = ", ".join(out_strs)
            if len(cond) + len(outs_joined) > 18:
                cond = f"{cond} /\n{outs_joined}"
            else:
                cond = f"{cond} / {outs_joined}"

        self.display_text = cond

    def update_path(self):
        self.prepareGeometryChange()
        p1 = self.src_item.scenePos()
        p2 = self.dst_item.scenePos()
        r1 = getattr(self.src_item, "radius", FSMStateCircleItem.BASE_RADIUS)
        r2 = getattr(self.dst_item, "radius", FSMStateCircleItem.BASE_RADIUS)
        self._prepare_label_text()
        num_lines = len(self.display_text.splitlines()) if self.display_text else 1

        path = QPainterPath()

        # -------------------------------------------------------------
        # 1. Self-Loop Handling (IPD432 slide 11, 25, 36)
        # -------------------------------------------------------------
        if self.src_item == self.dst_item:
            # Default: arch cleanly above the state circle without touching labels or perimeter
            default_a1 = -math.radians(130)
            default_a2 = -math.radians(50)
            a1 = self.transition.start_angle if self.transition.start_angle is not None else default_a1
            a2 = self.transition.end_angle if self.transition.end_angle is not None else default_a2

            start_pt = QPointF(p1.x() + r1 * math.cos(a1), p1.y() + r1 * math.sin(a1))
            end_pt = QPointF(p1.x() + r1 * math.cos(a2), p1.y() + r1 * math.sin(a2))

            loop_h = max(50.0, r1 * 0.9)
            extra_h = (num_lines - 1) * 9.0
            if self.transition.start_angle is None and self.transition.end_angle is None:
                c1 = QPointF(start_pt.x() - 15, start_pt.y() - loop_h)
                c2 = QPointF(end_pt.x() + 15, end_pt.y() - loop_h)
                self.arrow_angle = 120.0
                self.label_pos = QPointF(p1.x(), p1.y() - r1 - loop_h - 12 - extra_h)
            else:
                ctrl_dist = loop_h * 1.15
                c1 = QPointF(start_pt.x() + ctrl_dist * math.cos(a1), start_pt.y() + ctrl_dist * math.sin(a1))
                c2 = QPointF(end_pt.x() + ctrl_dist * math.cos(a2), end_pt.y() + ctrl_dist * math.sin(a2))
                self.arrow_angle = math.degrees(math.atan2(end_pt.y() - c2.y(), end_pt.x() - c2.x()))
                apex = 0.125 * start_pt + 0.375 * c1 + 0.375 * c2 + 0.125 * end_pt
                mid_dx = apex.x() - p1.x()
                mid_dy = apex.y() - p1.y()
                mid_len = math.hypot(mid_dx, mid_dy) or 1.0
                offset_dist = 20.0 + extra_h
                self.label_pos = QPointF(
                    apex.x() + (mid_dx / mid_len) * offset_dist,
                    apex.y() + (mid_dy / mid_len) * offset_dist
                )

            path.moveTo(start_pt)
            path.cubicTo(c1, c2, end_pt)
            self.setPath(path)

            self.start_pt = start_pt
            self.end_pt = end_pt
            self.arrow_tip = end_pt
            self._sync_auxiliary_items()
            return

        # -------------------------------------------------------------
        # 2. Inter-State Arc with Smart Obstacle Avoidance
        # -------------------------------------------------------------
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        dist = math.hypot(dx, dy)
        if dist < 1:
            return

        # Multi-transition index between this exact pair
        same_dir = [
            t for t in self.fsm.transitions
            if t.source == self.transition.source and t.target == self.transition.target
        ]
        pair_idx = same_dir.index(self.transition) if self.transition in same_dir else 0

        # Check for intervening states along the chord
        has_obstacle = False
        max_req_clearance = 0.0

        for other in self.fsm.states:
            if other.name in (self.src_item.state.name, self.dst_item.state.name):
                continue
            ox, oy = other.x, other.y
            t = ((ox - p1.x()) * dx + (oy - p1.y()) * dy) / (dist * dist)
            if 0.08 < t < 0.92:
                perp = abs(dx * (p1.y() - oy) - dy * (p1.x() - ox)) / dist
                other_r = FSMStateCircleItem.BASE_RADIUS
                if self.scene() and hasattr(self.scene(), "state_items") and other.name in self.scene().state_items:
                    other_r = getattr(self.scene().state_items[other.name], "radius", FSMStateCircleItem.BASE_RADIUS)
                if perp < (other_r + 45.0):
                    has_obstacle = True
                    req = (other_r + 65.0) - perp
                    if req > max_req_clearance:
                        max_req_clearance = req

        # Normal vector to chord
        norm_x = -dy / dist
        norm_y = dx / dist

        is_mostly_horiz = abs(dx) >= abs(dy) * 0.7

        if is_mostly_horiz:
            if dx > 0:
                # Forward transition (moving right): Curve ABOVE (negative y)
                curve_dir = -1.0 if norm_y > 0 else 1.0
                base_curve = 34.0
            else:
                # Backward transition (moving left): Curve BELOW (positive y)
                curve_dir = 1.0 if norm_y > 0 else -1.0
                if has_obstacle or dist > 280:
                    base_curve = max(80.0 + (dist - 200) * 0.18, max_req_clearance + 40.0)
                else:
                    base_curve = 34.0
        else:
            # Vertical or general layout: curve away from center of mass
            cx = sum(s.x for s in self.fsm.states) / len(self.fsm.states)
            cy = sum(s.y for s in self.fsm.states) / len(self.fsm.states)
            mid_pt = (p1 + p2) * 0.5
            to_out_x = mid_pt.x() - cx
            to_out_y = mid_pt.y() - cy
            dot = norm_x * to_out_x + norm_y * to_out_y
            curve_dir = 1.0 if dot >= 0 else -1.0
            base_curve = max(34.0, max_req_clearance + 40.0 if has_obstacle else 34.0)

        total_curvature = base_curve + pair_idx * 24.0

        mid_x = (p1.x() + p2.x()) * 0.5
        mid_y = (p1.y() + p2.y()) * 0.5

        ctrl_x = mid_x + norm_x * (total_curvature * curve_dir)
        ctrl_y = mid_y + norm_y * (total_curvature * curve_dir)
        ctrl_pt = QPointF(ctrl_x, ctrl_y)

        # Default angular circle attachment points
        angle_to_ctrl_1 = math.atan2(ctrl_y - p1.y(), ctrl_x - p1.x())
        angle_to_ctrl_2 = math.atan2(ctrl_y - p2.y(), ctrl_x - p2.x())

        a1 = self.transition.start_angle if self.transition.start_angle is not None else angle_to_ctrl_1
        a2 = self.transition.end_angle if self.transition.end_angle is not None else angle_to_ctrl_2

        start_pt = QPointF(p1.x() + r1 * math.cos(a1), p1.y() + r1 * math.sin(a1))
        end_pt = QPointF(p2.x() + r2 * math.cos(a2), p2.y() + r2 * math.sin(a2))

        label_out_dist = 16.0 + (num_lines - 1) * 8.0
        if self.transition.start_angle is None and self.transition.end_angle is None:
            path.moveTo(start_pt)
            path.quadTo(ctrl_pt, end_pt)
            self.arrow_angle = math.degrees(math.atan2(end_pt.y() - ctrl_pt.y(), end_pt.x() - ctrl_pt.x()))
            self.label_pos = QPointF(
                ctrl_x + norm_x * (label_out_dist * curve_dir),
                ctrl_y + norm_y * (label_out_dist * curve_dir)
            )
        else:
            dist_c1 = max(40.0, (2.0 / 3.0) * (math.hypot(ctrl_x - p1.x(), ctrl_y - p1.y()) - r1))
            dist_c2 = max(40.0, (2.0 / 3.0) * (math.hypot(ctrl_x - p2.x(), ctrl_y - p2.y()) - r2))
            c1 = QPointF(start_pt.x() + dist_c1 * math.cos(a1), start_pt.y() + dist_c1 * math.sin(a1))
            c2 = QPointF(end_pt.x() + dist_c2 * math.cos(a2), end_pt.y() + dist_c2 * math.sin(a2))

            path.moveTo(start_pt)
            path.cubicTo(c1, c2, end_pt)
            self.arrow_angle = math.degrees(math.atan2(end_pt.y() - c2.y(), end_pt.x() - c2.x()))

            apex = 0.125 * start_pt + 0.375 * c1 + 0.375 * c2 + 0.125 * end_pt
            chord_mid = 0.5 * (start_pt + end_pt)
            defl = apex - chord_mid
            defl_len = math.hypot(defl.x(), defl.y())
            if defl_len > 2.0:
                ux, uy = defl.x() / defl_len, defl.y() / defl_len
            else:
                ux, uy = norm_x * curve_dir, norm_y * curve_dir
            self.label_pos = QPointF(apex.x() + ux * label_out_dist, apex.y() + uy * label_out_dist)

        self.setPath(path)
        self.start_pt = start_pt
        self.end_pt = end_pt
        self.arrow_tip = end_pt
        self._sync_auxiliary_items()

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(10.0)
        return stroker.createStroke(self.path())

    def boundingRect(self) -> QRectF:
        rect = self.path().boundingRect()
        if hasattr(self, "badge_item") and self.badge_item:
            rect = rect.united(self.badge_item.mapToParent(self.badge_item.boundingRect()).boundingRect())
        elif hasattr(self, "label_pos") and hasattr(self, "display_text") and self.display_text:
            tw, th = FSMTransitionBadgeItem.measure_text(self.display_text)
            badge_rect = QRectF(self.label_pos.x() - tw / 2 - 4, self.label_pos.y() - th / 2 - 4, tw + 8, th + 8)
            rect = rect.united(badge_rect)
        if hasattr(self, "arrow_tip"):
            tip_rect = QRectF(self.arrow_tip.x() - 15, self.arrow_tip.y() - 15, 30, 30)
            rect = rect.united(tip_rect)
        return rect.adjusted(-12, -12, 12, 12)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(40, 40, 40), 1.6)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(self.path())

        # Draw Arrowhead
        if hasattr(self, "arrow_tip"):
            painter.setBrush(QBrush(QColor(40, 40, 40)))
            rad = math.radians(self.arrow_angle)
            tip = self.arrow_tip
            arrow_len = 9.0
            arrow_w = 4.5

            p_back = QPointF(tip.x() - arrow_len * math.cos(rad), tip.y() - arrow_len * math.sin(rad))
            p_left = QPointF(p_back.x() + arrow_w * math.sin(rad), p_back.y() - arrow_w * math.cos(rad))
            p_right = QPointF(p_back.x() - arrow_w * math.sin(rad), p_back.y() + arrow_w * math.cos(rad))

            poly = QPolygonF([tip, p_left, p_right])
            painter.drawPolygon(poly)


class FSMResetArrowItem(QGraphicsItem):
    """Incoming arrow pointing to initial state with 'Reset' text (IPD432 slide 11 & 24)"""
    def __init__(self, init_item: FSMStateCircleItem):
        super().__init__()
        self.init_item = init_item
        self.setZValue(1)
        self.update_position()

    def update_position(self):
        self.prepareGeometryChange()
        self.setPos(self.init_item.scenePos())

    def boundingRect(self) -> QRectF:
        r = getattr(self.init_item, "radius", FSMStateCircleItem.BASE_RADIUS)
        # Local bounding box relative to state center
        return QRectF(-r - 95, -r - 50, 110, 70)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        r = getattr(self.init_item, "radius", FSMStateCircleItem.BASE_RADIUS)

        # Arrow from upper left into circle in local coordinates
        start_pt = QPointF(-r - 45, -r - 25)
        tip_pt = QPointF(-r * 0.7, -r * 0.7)

        painter.setPen(QPen(QColor(30, 30, 30), 2.0))
        painter.drawLine(start_pt, tip_pt)

        # Arrow tip
        angle = math.atan2(tip_pt.y() - start_pt.y(), tip_pt.x() - start_pt.x())
        a_len = 10.0
        a_w = 5.0
        p_back = QPointF(tip_pt.x() - a_len * math.cos(angle), tip_pt.y() - a_len * math.sin(angle))
        p1 = QPointF(p_back.x() + a_w * math.sin(angle), p_back.y() - a_w * math.cos(angle))
        p2 = QPointF(p_back.x() - a_w * math.sin(angle), p_back.y() + a_w * math.cos(angle))
        painter.setBrush(QBrush(QColor(30, 30, 30)))
        painter.drawPolygon(QPolygonF([tip_pt, p1, p2]))

        painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
        painter.drawText(QRectF(start_pt.x() - 28, start_pt.y() - 20, 66, 22), Qt.AlignCenter, "Reset")


class FSMLegendItem(QGraphicsItem):
    """
    Formal I/O Legend box for FSM Diagrams (IPD432 / ELO212).
    Lists all declared Inputs (Entradas) and Outputs (Salidas) with their bit widths.
    """

    def __init__(self, fsm: FSM):
        super().__init__()
        self.fsm = fsm
        self._is_updating = False
        self._width = 180.0
        self._height = 100.0
        self._in_lines: List[str] = []
        self._out_lines: List[str] = []
        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemIsSelectable |
            QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setZValue(4)
        self.setToolTip("Leyenda de Entradas y Salidas (Arrastre para mover, Shift+R para restablecer posición)")
        self.update_content()

    @staticmethod
    def _format_port(p: Port) -> str:
        if p.width > 1:
            return f"• {p.name}[{p.width - 1}:0] ({p.width} bits)"
        return f"• {p.name} (1 bit)"

    def update_content(self):
        self.prepareGeometryChange()
        inputs, outputs = self.fsm.get_all_declared_io()
        self._in_lines = [self._format_port(p) for p in inputs] if inputs else ["• (ninguna)"]
        self._out_lines = [self._format_port(p) for p in outputs] if outputs else ["• (ninguna)"]

        title_font = QFont("Segoe UI", 10, QFont.Bold)
        sec_font = QFont("Segoe UI", 9, QFont.Bold)
        item_font = QFont("Consolas", 9, QFont.Normal)

        fm_title = QFontMetrics(title_font)
        fm_sec = QFontMetrics(sec_font)
        fm_item = QFontMetrics(item_font)

        max_w = fm_title.horizontalAdvance("Leyenda (Entradas / Salidas)")
        max_w = max(max_w, fm_sec.horizontalAdvance("Entradas:"), fm_sec.horizontalAdvance("Salidas:"))
        for line in self._in_lines + self._out_lines:
            max_w = max(max_w, fm_item.horizontalAdvance(line) + 10)

        self._width = float(max(165, max_w + 26))
        header_h = 26.0
        sec_h = float(fm_sec.lineSpacing() + 2)
        item_h = float(fm_item.lineSpacing() + 1)
        total_items = len(self._in_lines) + len(self._out_lines)
        self._height = header_h + 2 * sec_h + total_items * item_h + 20.0

    def boundingRect(self) -> QRectF:
        return QRectF(-2, -2, self._width + 4, self._height + 4)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged and not getattr(self, "_is_updating", False):
            pos = self.pos()
            self.fsm.legend_pos = (pos.x(), pos.y())
        return super().itemChange(change, value)

    def reset_position(self):
        self.fsm.legend_pos = None
        if self.scene() and hasattr(self.scene(), "update_legend_position"):
            self.scene().update_legend_position()

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        box_rect = QRectF(0, 0, self._width, self._height)

        border_col = QColor(0, 102, 204) if self.isSelected() else QColor(60, 60, 65)
        painter.setPen(QPen(border_col, 1.5))
        painter.setBrush(QBrush(QColor(252, 252, 254, 248)))
        painter.drawRoundedRect(box_rect, 5, 5)

        # Header banner
        header_h = 26.0
        header_rect = QRectF(0, 0, self._width, header_h)
        painter.save()
        clip_path = QPainterPath()
        clip_path.addRoundedRect(box_rect, 5, 5)
        painter.setClipPath(clip_path)
        painter.fillRect(header_rect, QColor(235, 241, 248))
        painter.restore()
        painter.setPen(QPen(border_col, 1.2))
        painter.drawLine(QLineF(0, header_h, self._width, header_h))

        # Title
        painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
        painter.setPen(QPen(QColor(20, 25, 35)))
        painter.drawText(header_rect, Qt.AlignCenter, "Leyenda (Entradas / Salidas)")

        sec_font = QFont("Segoe UI", 9, QFont.Bold)
        item_font = QFont("Consolas", 9, QFont.Normal)
        fm_sec = QFontMetrics(sec_font)
        fm_item = QFontMetrics(item_font)

        y = header_h + 6.0
        # Inputs section
        painter.setFont(sec_font)
        painter.setPen(QPen(QColor(0, 80, 160)))
        painter.drawText(QRectF(10, y, self._width - 20, fm_sec.lineSpacing()), Qt.AlignLeft | Qt.AlignVCenter, "Entradas:")
        y += fm_sec.lineSpacing() + 2

        painter.setFont(item_font)
        painter.setPen(QPen(QColor(30, 30, 30)))
        for line in self._in_lines:
            painter.drawText(QRectF(16, y, self._width - 24, fm_item.lineSpacing()), Qt.AlignLeft | Qt.AlignVCenter, line)
            y += fm_item.lineSpacing() + 1

        y += 4.0
        # Outputs section
        painter.setFont(sec_font)
        painter.setPen(QPen(QColor(150, 50, 0)))
        painter.drawText(QRectF(10, y, self._width - 20, fm_sec.lineSpacing()), Qt.AlignLeft | Qt.AlignVCenter, "Salidas:")
        y += fm_sec.lineSpacing() + 2

        painter.setFont(item_font)
        painter.setPen(QPen(QColor(30, 30, 30)))
        for line in self._out_lines:
            painter.drawText(QRectF(16, y, self._width - 24, fm_item.lineSpacing()), Qt.AlignLeft | Qt.AlignVCenter, line)
            y += fm_item.lineSpacing() + 1


class FSMGraphicsScene(QGraphicsScene):
    def __init__(self, fsm: FSM, parent=None):
        super().__init__(parent)
        self.setItemIndexMethod(QGraphicsScene.NoIndex)
        self.fsm = fsm
        self.state_items: Dict[str, FSMStateCircleItem] = {}
        self.trans_items: List[FSMTransitionItem] = []
        self.reset_arrow: Optional[FSMResetArrowItem] = None
        self.legend_item: Optional[FSMLegendItem] = None
        self.rebuild_scene()

    def rebuild_scene(self):
        self.clear()
        self.state_items.clear()
        self.trans_items.clear()
        self.reset_arrow = None
        self.legend_item = None

        if not self.fsm.states:
            return

        # Add states
        for s in self.fsm.states:
            item = FSMStateCircleItem(s, self.fsm, self)
            self.addItem(item)
            self.state_items[s.name] = item

        # Add transitions
        for t in self.fsm.transitions:
            src = self.state_items.get(t.source)
            dst = self.state_items.get(t.target)
            if src and dst:
                item = FSMTransitionItem(t, self.fsm, src, dst)
                self.addItem(item)
                self.trans_items.append(item)

        # Add Reset arrow to initial state
        init_state = self.fsm.get_initial_state()
        if init_state and init_state.name in self.state_items:
            self.reset_arrow = FSMResetArrowItem(self.state_items[init_state.name])
            self.addItem(self.reset_arrow)

        # Add I/O Legend item
        self.legend_item = FSMLegendItem(self.fsm)
        self.addItem(self.legend_item)
        self.update_legend_position()

        self.update()
        for v in self.views():
            v.viewport().update()

    def _compute_diagram_bounds_without_legend(self) -> QRectF:
        rect = QRectF()
        for s_item in self.state_items.values():
            rect = rect.united(s_item.sceneBoundingRect())
        for t_item in self.trans_items:
            rect = rect.united(t_item.sceneBoundingRect())
        if self.reset_arrow:
            rect = rect.united(self.reset_arrow.sceneBoundingRect())
        return rect

    def update_legend_position(self):
        if not self.legend_item:
            return
        self.legend_item.update_content()
        self.legend_item._is_updating = True
        try:
            if self.fsm.legend_pos is not None:
                self.legend_item.setPos(self.fsm.legend_pos[0], self.fsm.legend_pos[1])
            else:
                diag_rect = self._compute_diagram_bounds_without_legend()
                if diag_rect.isEmpty():
                    self.legend_item.setPos(0, 0)
                else:
                    self.legend_item.setPos(diag_rect.right() + 30.0, diag_rect.top())
        finally:
            self.legend_item._is_updating = False

    def prepare_for_export(self):
        if self.fsm.states and not self.legend_item:
            self.legend_item = FSMLegendItem(self.fsm)
            self.addItem(self.legend_item)
        self.update_legend_position()

    def update_transitions(self):
        for t_item in self.trans_items:
            t_item.update_path()
        if self.reset_arrow:
            self.reset_arrow.update_position()
            self.reset_arrow.update()
        self.update_legend_position()
        self.update()
        for v in self.views():
            v.viewport().update()

    def auto_layout_circular(self):
        n = len(self.fsm.states)
        if n == 0:
            return
        radius = max(160.0, n * 50.0)
        for i, s in enumerate(self.fsm.states):
            theta = 2 * math.pi * i / n - math.pi / 2
            x = radius * math.cos(theta)
            y = radius * math.sin(theta)
            s.x = x
            s.y = y
            if s.name in self.state_items:
                self.state_items[s.name].setPos(x, y)
        self.fsm.legend_pos = None
        self.update_transitions()

    def auto_layout_horizontal(self):
        n = len(self.fsm.states)
        if n == 0:
            return
        step = 230.0
        start_x = - ((n - 1) * step) / 2.0
        for i, s in enumerate(self.fsm.states):
            s.x = start_x + i * step
            s.y = 0.0
            if s.name in self.state_items:
                self.state_items[s.name].setPos(s.x, s.y)
        self.fsm.legend_pos = None
        self.update_transitions()

    def reset_all_transition_labels(self):
        for t_item in self.trans_items:
            t_item.transition.custom_label_pos = None
            if hasattr(t_item, "badge_item") and t_item.badge_item:
                t_item.badge_item.update_position()
        self.fsm.legend_pos = None
        self.update_legend_position()
        self.update()
        for v in self.views():
            v.viewport().update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_R and (event.modifiers() & Qt.ShiftModifier):
            self.reset_all_transition_labels()
            event.accept()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        item = self.itemAt(event.scenePos(), self.views()[0].transform()) if self.views() else None
        target_trans = None
        if isinstance(item, FSMTransitionItem):
            target_trans = item
        elif isinstance(item, (FSMTransitionBadgeItem, FSMTransitionEndpointHandle)):
            target_trans = item.trans_item

        if target_trans:
            menu = QMenu()
            act_reset_pts = menu.addAction("🔄 Restablecer Puntos de Inicio y Fin de Flecha")
            act_reset_lbl = menu.addAction("🏷️ Restablecer Posición de Etiqueta (Shift+R)")
            action = menu.exec(event.screenPos())
            if action == act_reset_pts:
                target_trans.reset_endpoints()
            elif action == act_reset_lbl and target_trans.badge_item:
                target_trans.badge_item.reset_position()
            event.accept()
            return

        if isinstance(item, FSMLegendItem):
            menu = QMenu()
            act_reset_leg = menu.addAction("🏷️ Restablecer Posición de la Leyenda")
            action = menu.exec(event.screenPos())
            if action == act_reset_leg:
                item.reset_position()
            event.accept()
            return

        super().contextMenuEvent(event)


class FSMDesignerWidget(QWidget):
    """Complete FSM Designer Tab with options table, validator, visualizer & I/O management"""

    def __init__(self, fsm: Optional[FSM] = None, parent=None):
        super().__init__(parent)
        self.fsm = fsm or self._create_default_fsm()
        self._init_ui()
        self.refresh_all()

    def _create_default_fsm(self) -> FSM:
        """Default: Level-to-Pulse converter from course (slide 35-54)"""
        return FSM(
            name="level_to_pulse",
            fsm_type=FSMType.MOORE,
            reset_type=ResetType.SYNC_HIGH,
            encoding=FSMEncoding.AUTO,
            inputs=[Port(name="L", width=1, default_val="1'b0")],
            outputs=[Port(name="P", width=1, default_val="1'b0")],
            states=[
                State(name="S0", is_initial=True, moore_outputs={"P": "1'b0"}, x=-230, y=0),
                State(name="S1", moore_outputs={"P": "1'b1"}, x=0, y=0),
                State(name="S2", moore_outputs={"P": "1'b0"}, x=230, y=0),
            ],
            transitions=[
                Transition(source="S0", target="S1", condition="L"),
                Transition(source="S0", target="S0", condition="else"),
                Transition(source="S1", target="S2", condition="L"),
                Transition(source="S1", target="S0", condition="else"),
                Transition(source="S2", target="S2", condition="L"),
                Transition(source="S2", target="S0", condition="else"),
            ]
        )

    def _init_ui(self):
        main_layout = QHBoxLayout(self)

        # Splitter: Left (Options & Tables), Right (Diagram)
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # -------------------------------------------------------------
        # Left Panel: Description and Configuration Tables
        # -------------------------------------------------------------
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        # Top Bar: Presets
        preset_box = QGroupBox("Cargar Plantillas del Curso")
        preset_layout = QHBoxLayout(preset_box)
        btn_tmpl_traffic = QPushButton("Semáforo (4 Estados)")
        btn_tmpl_pulse = QPushButton("Conversor Nivel a Pulso")
        btn_tmpl_mealy = QPushButton("Detector Secuencia '101' (Mealy)")
        btn_tmpl_traffic.setToolTip("Cargar plantilla de Semáforo de 4 estados (Moore)")
        btn_tmpl_pulse.setToolTip("Cargar plantilla de Conversor Nivel a Pulso de 3 estados (Moore)")
        btn_tmpl_mealy.setToolTip("Cargar plantilla de Detector de Secuencia '101' de 3 estados (Mealy)")
        btn_tmpl_traffic.clicked.connect(self.load_traffic_preset)
        btn_tmpl_pulse.clicked.connect(self.load_pulse_preset)
        btn_tmpl_mealy.clicked.connect(self.load_mealy_preset)
        preset_layout.addWidget(btn_tmpl_traffic)
        preset_layout.addWidget(btn_tmpl_pulse)
        preset_layout.addWidget(btn_tmpl_mealy)
        left_layout.addWidget(preset_box)

        # FSM Parameters
        param_box = QGroupBox("Parámetros Generales de la FSM")
        form = QFormLayout(param_box)
        self.edit_name = QLineEdit(self.fsm.name)
        self.combo_type = QComboBox()
        self.combo_type.addItems([FSMType.MOORE.value, FSMType.MEALY.value])
        self.combo_reset = QComboBox()
        self.combo_reset.addItems([r.value for r in ResetType])
        self.combo_encoding = QComboBox()
        self.combo_encoding.addItems([e.value for e in FSMEncoding])

        self.edit_name.textChanged.connect(self._on_params_changed)
        self.combo_type.currentTextChanged.connect(self._on_params_changed)
        self.combo_reset.currentTextChanged.connect(self._on_params_changed)
        self.combo_encoding.currentTextChanged.connect(self._on_params_changed)

        form.addRow("Nombre del Módulo:", self.edit_name)
        form.addRow("Modelo FSM:", self.combo_type)
        form.addRow("Tipo de Reset:", self.combo_reset)
        form.addRow("Codificación (Vivado):", self.combo_encoding)
        left_layout.addWidget(param_box)

        # Tabs for Tables (States, Transitions, Ports)
        table_tabs = QTabWidget()

        # States Tab
        states_w = QWidget()
        s_layout = QVBoxLayout(states_w)
        self.table_states = QTableWidget(0, 3)
        self.table_states.setHorizontalHeaderLabels(["Nombre Estado", "Es Reset?", "Salidas Moore (ej: P=1'b1)"])
        self.table_states.setColumnWidth(0, 110)
        self.table_states.setColumnWidth(1, 75)
        self.table_states.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.table_states.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.table_states.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table_states.cellDoubleClicked.connect(self._on_state_cell_double_clicked)

        s_btn_layout = QHBoxLayout()
        btn_add_state = QPushButton("+ Agregar Estado")
        btn_del_state = QPushButton("- Eliminar Estado")
        btn_edit_outs = QPushButton("✏️ Configurar Salidas...")
        btn_edit_outs.setToolTip("Abre una ventana para gestionar cómodamente las salidas Moore del estado seleccionado")
        btn_add_state.clicked.connect(self.add_state)
        btn_del_state.clicked.connect(self.del_state)
        btn_edit_outs.clicked.connect(self.edit_selected_state_outputs)
        s_btn_layout.addWidget(btn_add_state)
        s_btn_layout.addWidget(btn_del_state)
        s_btn_layout.addWidget(btn_edit_outs)
        s_layout.addWidget(self.table_states)
        s_layout.addLayout(s_btn_layout)
        table_tabs.addTab(states_w, "Estados")

        # Transitions Tab
        trans_w = QWidget()
        t_layout = QVBoxLayout(trans_w)
        self.table_trans = QTableWidget(0, 5)
        self.table_trans.setHorizontalHeaderLabels(["Origen", "Condición (o 'else')", "Destino", "Temporizador (ciclos)", "Salidas Mealy"])
        self.table_trans.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t_btn_layout = QHBoxLayout()
        btn_add_trans = QPushButton("+ Agregar Transición")
        btn_del_trans = QPushButton("- Eliminar Transición")
        btn_add_trans.clicked.connect(self.add_transition)
        btn_del_trans.clicked.connect(self.del_transition)
        t_btn_layout.addWidget(btn_add_trans)
        t_btn_layout.addWidget(btn_del_trans)
        t_layout.addWidget(self.table_trans)
        t_layout.addLayout(t_btn_layout)
        table_tabs.addTab(trans_w, "Transiciones")

        # Ports (Entradas / Salidas) Tab
        ports_w = QWidget()
        p_layout = QVBoxLayout(ports_w)
        self.table_ports = QTableWidget(0, 4)
        self.table_ports.setHorizontalHeaderLabels(["Nombre", "Dirección (input/output)", "Ancho (bits)", "Valor Defecto"])
        self.table_ports.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        p_btn_layout = QHBoxLayout()
        btn_add_in = QPushButton("+ Agregar Entrada")
        btn_add_out = QPushButton("+ Agregar Salida")
        btn_del_port = QPushButton("- Eliminar Puerto")
        btn_add_in.clicked.connect(lambda: self.add_port("input"))
        btn_add_out.clicked.connect(lambda: self.add_port("output"))
        btn_del_port.clicked.connect(self.del_port)
        p_btn_layout.addWidget(btn_add_in)
        p_btn_layout.addWidget(btn_add_out)
        p_btn_layout.addWidget(btn_del_port)
        p_layout.addWidget(self.table_ports)
        p_layout.addLayout(p_btn_layout)
        table_tabs.addTab(ports_w, "Entradas / Salidas (I/O)")

        left_layout.addWidget(table_tabs)

        # Validation Box
        val_box = QGroupBox("Validación Formal (Reglas IPD432)")
        val_layout = QVBoxLayout(val_box)
        btn_validate = QPushButton("🔍 Comprobar Reglas del Curso (Latches, Completitud, Deadlocks)")
        btn_validate.setStyleSheet("font-weight: bold; padding: 6px;")
        btn_validate.clicked.connect(self.run_validation)
        self.list_issues = QListWidget()
        self.list_issues.setMaximumHeight(100)
        val_layout.addWidget(btn_validate)
        val_layout.addWidget(self.list_issues)
        left_layout.addWidget(val_box)

        # Connect cell changed signals
        self.table_states.cellChanged.connect(self._sync_states_from_table)
        self.table_trans.cellChanged.connect(self._sync_trans_from_table)
        self.table_ports.cellChanged.connect(self._sync_ports_from_table)

        splitter.addWidget(left_widget)

        # -------------------------------------------------------------
        # Right Panel: State Diagram
        # -------------------------------------------------------------
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # Diagram Scene & View
        self.fsm_scene = FSMGraphicsScene(self.fsm)
        self.fsm_view = QGraphicsView(self.fsm_scene)
        self.fsm_view.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
        self.fsm_view.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)

        # Diagram View Toolbar
        diag_tools = QHBoxLayout()
        btn_layout_horiz = QPushButton("➡️ Auto-Alinear Horizontal (Flujo L->R)")
        btn_layout_horiz.clicked.connect(self.auto_layout_horizontal)
        btn_layout_circle = QPushButton("⭕ Auto-Alinear en Círculo")
        btn_layout_circle.clicked.connect(self.auto_layout)
        diag_tools.addWidget(QLabel("<b>Diagrama de Estados</b> (Los estados se pueden arrastrar con el mouse)"))
        btn_relabel_fsm = QPushButton("🏷️ Restablecer Etiquetas (Shift+R)")
        btn_relabel_fsm.clicked.connect(self.fsm_scene.reset_all_transition_labels)
        diag_tools.addWidget(btn_layout_horiz)
        diag_tools.addWidget(btn_layout_circle)
        diag_tools.addWidget(btn_relabel_fsm)
        right_layout.addLayout(diag_tools)
        right_layout.addWidget(self.fsm_view, 1)

        splitter.addWidget(right_widget)
        splitter.setSizes([520, 680])

    def refresh_all(self):
        # Block signals while programmatically updating controls
        self.edit_name.blockSignals(True)
        self.combo_type.blockSignals(True)
        self.combo_reset.blockSignals(True)
        self.combo_encoding.blockSignals(True)

        # Update inputs
        self.edit_name.setText(self.fsm.name)
        self.combo_type.setCurrentText(self.fsm.fsm_type.value)
        self.combo_reset.setCurrentText(self.reset_type_to_str(self.fsm.reset_type))
        self.combo_encoding.setCurrentText(self.fsm.encoding.value)

        self.edit_name.blockSignals(False)
        self.combo_type.blockSignals(False)
        self.combo_reset.blockSignals(False)
        self.combo_encoding.blockSignals(False)

        self._populate_states_table()
        self._populate_trans_table()
        self._populate_ports_table()
        self.fsm_scene.rebuild_scene()
        self.run_validation()

    def reset_type_to_str(self, r: ResetType) -> str:
        return r.value

    def _on_params_changed(self):
        self.fsm.name = self.edit_name.text().strip() or "fsm_top"
        self.fsm.fsm_type = FSMType(self.combo_type.currentText())
        self.fsm.reset_type = ResetType(self.combo_reset.currentText())
        self.fsm.encoding = FSMEncoding(self.combo_encoding.currentText())
        self.fsm_scene.rebuild_scene()

    def _populate_ports_table(self):
        self.table_ports.blockSignals(True)
        all_in, all_out = self.fsm.get_all_declared_io()
        all_ports = all_in + all_out
        self.table_ports.setRowCount(len(all_ports))
        for row, p in enumerate(all_ports):
            self.table_ports.setItem(row, 0, QTableWidgetItem(p.name))
            self.table_ports.setItem(row, 1, QTableWidgetItem(p.direction))
            self.table_ports.setItem(row, 2, QTableWidgetItem(str(p.width)))
            self.table_ports.setItem(row, 3, QTableWidgetItem(p.default_val))
        self.table_ports.blockSignals(False)

    def _sync_ports_from_table(self):
        inputs = []
        outputs = []
        for r in range(self.table_ports.rowCount()):
            name_item = self.table_ports.item(r, 0)
            dir_item = self.table_ports.item(r, 1)
            w_item = self.table_ports.item(r, 2)
            def_item = self.table_ports.item(r, 3)

            name = name_item.text().strip() if name_item else f"sig_{r}"
            if not name:
                continue
            raw_dir = dir_item.text().strip().lower() if dir_item else "input"
            direction = "output" if raw_dir in ("output", "salida", "out", "o") else "input"
            try:
                width = max(1, int(w_item.text())) if w_item else 1
            except ValueError:
                width = 1
            default_val = def_item.text().strip() if def_item else ("1'b0" if width == 1 else f"{width}'b0")

            p = Port(name=name, direction=direction, width=width, default_val=default_val)
            if direction == "output":
                outputs.append(p)
            else:
                inputs.append(p)

        self.fsm.inputs = inputs
        self.fsm.outputs = outputs
        self.fsm_scene.rebuild_scene()

    def _auto_sync_ports_from_diagram(self, prev_ext_in: set[str], prev_ext_out: set[str]):
        """Synchronizes FSM inputs/outputs when signals in states/transitions are edited."""
        ext_in_ports, ext_out_ports = self.fsm.extract_diagram_io()
        curr_in_names = {p.name for p in ext_in_ports}
        curr_out_names = {p.name for p in ext_out_ports}

        # Keep manually declared ports + currently active diagram signals, removing stale auto-signals
        removed_in = prev_ext_in - curr_in_names
        removed_out = prev_ext_out - curr_out_names

        in_map = {p.name: p for p in self.fsm.inputs if p.name not in removed_in}
        for p in ext_in_ports:
            if p.name not in in_map:
                in_map[p.name] = p
            else:
                in_map[p.name].width = max(in_map[p.name].width, p.width)

        out_map = {p.name: p for p in self.fsm.outputs if p.name not in removed_out}
        for p in ext_out_ports:
            if p.name not in out_map:
                out_map[p.name] = p
            else:
                out_map[p.name].width = max(out_map[p.name].width, p.width)

        self.fsm.inputs = list(in_map.values())
        self.fsm.outputs = list(out_map.values())
        self._populate_ports_table()

    def add_port(self, direction: str = "input"):
        self.table_ports.blockSignals(True)
        r = self.table_ports.rowCount()
        self.table_ports.insertRow(r)
        prefix = "out" if direction == "output" else "in"
        self.table_ports.setItem(r, 0, QTableWidgetItem(f"{prefix}_{r}"))
        self.table_ports.setItem(r, 1, QTableWidgetItem(direction))
        self.table_ports.setItem(r, 2, QTableWidgetItem("1"))
        self.table_ports.setItem(r, 3, QTableWidgetItem("1'b0"))
        self.table_ports.blockSignals(False)
        self._sync_ports_from_table()

    def del_port(self):
        r = self.table_ports.currentRow()
        if r >= 0:
            self.table_ports.removeRow(r)
            self._sync_ports_from_table()

    def _populate_states_table(self):
        self.table_states.blockSignals(True)
        self.table_states.setRowCount(len(self.fsm.states))
        for row, s in enumerate(self.fsm.states):
            self.table_states.setItem(row, 0, QTableWidgetItem(s.name))
            init_item = QTableWidgetItem("Sí" if s.is_initial else "No")
            self.table_states.setItem(row, 1, init_item)
            out_str = ", ".join([f"{k}={v}" for k, v in sorted(s.moore_outputs.items())])
            out_item = QTableWidgetItem(out_str)
            if s.moore_outputs:
                out_item.setToolTip(f"Salidas de {s.name} (Doble clic para editar):\n" + "\n".join([f"  • {k} = {v}" for k, v in sorted(s.moore_outputs.items())]))
            self.table_states.setItem(row, 2, out_item)
        self.table_states.blockSignals(False)

    def _sync_states_from_table(self):
        prev_in, prev_out = self.fsm.extract_diagram_io()
        prev_in_set = {p.name for p in prev_in}
        prev_out_set = {p.name for p in prev_out}

        for r in range(self.table_states.rowCount()):
            if r >= len(self.fsm.states):
                break
            s = self.fsm.states[r]
            name_item = self.table_states.item(r, 0)
            init_item = self.table_states.item(r, 1)
            outs_item = self.table_states.item(r, 2)

            if name_item:
                s.name = name_item.text().strip()
            if init_item:
                s.is_initial = (init_item.text().strip().lower() in ("sí", "si", "yes", "true", "1"))
            if outs_item:
                outs_dict = {}
                pairs = [p.strip() for p in re.split(r'[,;\n]+', outs_item.text()) if p.strip()]
                for p in pairs:
                    if "=" in p:
                        k, v = p.split("=", 1)
                        outs_dict[k.strip()] = v.strip()
                s.moore_outputs = outs_dict

        self._auto_sync_ports_from_diagram(prev_in_set, prev_out_set)
        self.fsm_scene.rebuild_scene()

    def _on_state_cell_double_clicked(self, row: int, col: int):
        if col == 2 and 0 <= row < len(self.fsm.states):
            self.open_state_outputs_dialog(self.fsm.states[row])

    def open_state_outputs_dialog(self, state: State):
        prev_in, prev_out = self.fsm.extract_diagram_io()
        prev_in_set = {p.name for p in prev_in}
        prev_out_set = {p.name for p in prev_out}

        dlg = StateOutputsDialog(state, self)
        if dlg.exec():
            state.moore_outputs = dlg.get_outputs()
            self._populate_states_table()
            self._auto_sync_ports_from_diagram(prev_in_set, prev_out_set)
            self.fsm_scene.rebuild_scene()

    def edit_selected_state_outputs(self):
        r = self.table_states.currentRow()
        if 0 <= r < len(self.fsm.states):
            self.open_state_outputs_dialog(self.fsm.states[r])
        else:
            QMessageBox.information(self, "Aviso", "Seleccione un estado en la tabla para configurar sus salidas.")

    def _populate_trans_table(self):
        self.table_trans.blockSignals(True)
        self.table_trans.setRowCount(len(self.fsm.transitions))
        for row, t in enumerate(self.fsm.transitions):
            self.table_trans.setItem(row, 0, QTableWidgetItem(t.source))
            self.table_trans.setItem(row, 1, QTableWidgetItem(t.condition))
            self.table_trans.setItem(row, 2, QTableWidgetItem(t.target))
            self.table_trans.setItem(row, 3, QTableWidgetItem(str(t.timer_cycles)))
            mealy_str = ", ".join([f"{k}={v}" for k, v in t.mealy_outputs.items()])
            self.table_trans.setItem(row, 4, QTableWidgetItem(mealy_str))
        self.table_trans.blockSignals(False)

    def _sync_trans_from_table(self):
        prev_in, prev_out = self.fsm.extract_diagram_io()
        prev_in_set = {p.name for p in prev_in}
        prev_out_set = {p.name for p in prev_out}

        for r in range(self.table_trans.rowCount()):
            if r >= len(self.fsm.transitions):
                break
            t = self.fsm.transitions[r]
            src = self.table_trans.item(r, 0)
            cond = self.table_trans.item(r, 1)
            dst = self.table_trans.item(r, 2)
            timer = self.table_trans.item(r, 3)
            mealy = self.table_trans.item(r, 4)

            if src: t.source = src.text().strip()
            if cond: t.condition = cond.text().strip()
            if dst: t.target = dst.text().strip()
            if timer:
                try:
                    c = int(timer.text())
                    t.timer_cycles = c
                    t.is_timed = (c > 0)
                except ValueError:
                    t.timer_cycles = 0
                    t.is_timed = False
            if mealy:
                m_dict = {}
                for p in mealy.text().split(","):
                    if "=" in p:
                        k, v = p.split("=", 1)
                        m_dict[k.strip()] = v.strip()
                t.mealy_outputs = m_dict

        self._auto_sync_ports_from_diagram(prev_in_set, prev_out_set)
        self.fsm_scene.rebuild_scene()

    def add_state(self):
        idx = len(self.fsm.states)
        s_name = f"S{idx}"
        new_state = State(name=s_name, is_initial=(idx == 0))
        self.fsm.states.append(new_state)
        self._populate_states_table()
        self.fsm_scene.rebuild_scene()
        self.auto_layout()

    def del_state(self):
        r = self.table_states.currentRow()
        if 0 <= r < len(self.fsm.states):
            s_name = self.fsm.states[r].name
            del self.fsm.states[r]
            # remove transitions to or from this state
            self.fsm.transitions = [t for t in self.fsm.transitions if t.source != s_name and t.target != s_name]
            self._populate_states_table()
            self._populate_trans_table()
            self._populate_ports_table()
            self.fsm_scene.rebuild_scene()

    def add_transition(self):
        if not self.fsm.states:
            QMessageBox.warning(self, "Aviso", "Primero agregue estados a la FSM.")
            return
        src = self.fsm.states[0].name
        dst = self.fsm.states[1].name if len(self.fsm.states) > 1 else src
        self.fsm.transitions.append(Transition(source=src, target=dst, condition="else"))
        self._populate_trans_table()
        self.fsm_scene.rebuild_scene()

    def del_transition(self):
        r = self.table_trans.currentRow()
        if 0 <= r < len(self.fsm.transitions):
            del self.fsm.transitions[r]
            self._populate_trans_table()
            self._populate_ports_table()
            self.fsm_scene.rebuild_scene()

    def auto_layout(self):
        self.fsm_scene.auto_layout_circular()

    def auto_layout_horizontal(self):
        self.fsm_scene.auto_layout_horizontal()

    def run_validation(self):
        self.list_issues.clear()
        issues = FSMValidator.validate(self.fsm)
        if not issues:
            item = QListWidgetItem("✅ ¡La FSM cumple estrictamente con todas las convenciones de IPD432!")
            item.setForeground(QColor(0, 150, 0))
            self.list_issues.addItem(item)
            return

        for iss in issues:
            prefix = "❌ ERROR: " if iss.severity == "ERROR" else ("⚠️ ADVERTENCIA: " if iss.severity == "WARNING" else "ℹ️ INFO: ")
            text = f"{prefix}[{iss.location}] {iss.message}"
            item = QListWidgetItem(text)
            if iss.severity == "ERROR":
                item.setForeground(QColor(200, 0, 0))
            elif iss.severity == "WARNING":
                item.setForeground(QColor(180, 100, 0))
            else:
                item.setForeground(QColor(50, 100, 180))
            self.list_issues.addItem(item)

    def load_traffic_preset(self):
        self.fsm = FSM(
            name="traffic_light_controller",
            fsm_type=FSMType.MOORE,
            reset_type=ResetType.SYNC_HIGH,
            encoding=FSMEncoding.SEQUENTIAL,
            inputs=[
                Port(name="TA", width=1, default_val="1'b0"),
                Port(name="TB", width=1, default_val="1'b0")
            ],
            outputs=[
                Port(name="LA", width=2, default_val="2'b10"),
                Port(name="LB", width=2, default_val="2'b10")
            ],
            states=[
                State(name="S0", is_initial=True, moore_outputs={"LA": "2'b00", "LB": "2'b10"}, x=-150, y=-150),
                State(name="S1", moore_outputs={"LA": "2'b01", "LB": "2'b10"}, x=150, y=-150),
                State(name="S2", moore_outputs={"LA": "2'b10", "LB": "2'b00"}, x=150, y=150),
                State(name="S3", moore_outputs={"LA": "2'b10", "LB": "2'b01"}, x=-150, y=150),
            ],
            transitions=[
                Transition(source="S0", target="S1", condition="TA == 1'b0"),
                Transition(source="S0", target="S0", condition="else"),
                Transition(source="S1", target="S2", condition="else"),
                Transition(source="S2", target="S3", condition="TB == 1'b0"),
                Transition(source="S2", target="S2", condition="else"),
                Transition(source="S3", target="S0", condition="else"),
            ]
        )
        self.fsm_scene.fsm = self.fsm
        self.refresh_all()

    def load_pulse_preset(self):
        self.fsm = self._create_default_fsm()
        self.fsm_scene.fsm = self.fsm
        self.refresh_all()

    def load_mealy_preset(self):
        self.fsm = FSM.create_sequence_detector_mealy()
        self.fsm_scene.fsm = self.fsm
        self.refresh_all()
