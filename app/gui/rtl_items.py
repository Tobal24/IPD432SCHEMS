"""
Graphical Items for RTL Schematics in ELO212.
Implements:
- MUX (trapezoid with select at top/bottom, index numbers, wide input, narrow output)
- Register / Flip-Flop (box with D, Q, clock triangle, rst, optional CE and bus slash)
- Operators (circular primitives like +, A>B)
- Standard Logic Gates (AND, OR, NOT, XOR)
- Constant sources (1'b0, 4'd0, 8'hFF)
- Bus splitters (perpendicular branch bar with slices)
- Generic functional blocks
- Manhattan orthogonal wires with bus slash /N and solder-dot junctions
"""
from __future__ import annotations

import math
from typing import List, Optional, Tuple
from PySide6.QtCore import Qt, QRectF, QPointF, QLineF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QPainterPath, QPolygonF, QFontMetrics,
    QPainterPathStroker, QTransform
)
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsPathItem, QGraphicsEllipseItem,
    QGraphicsTextItem, QGraphicsSceneMouseEvent, QMenu, QInputDialog
)
from app.core.rtl_model import (
    RTLComponent, RTLPin, ComponentType, PinDirection, PinSide, RTLWire
)


GRID_SIZE = 20.0

def snap(val: float) -> float:
    return round(val / GRID_SIZE) * GRID_SIZE


class RTLPinItem(QGraphicsItem):
    """Visual anchor for component pins"""
    RADIUS = 4.0

    def __init__(self, pin: RTLPin, parent: "RTLComponentItem"):
        super().__init__(parent)
        self.pin = pin
        self.parent_comp = parent
        self.setAcceptHoverEvents(True)
        self.is_hovered = False
        self.update_position()

    def update_position(self):
        self.prepareGeometryChange()
        w = self.parent_comp.model.width
        h = self.parent_comp.model.height
        side = self.pin.side
        off = self.pin.offset
        ctype = self.parent_comp.model.type

        is_mirrored = getattr(self.parent_comp.model, "mirrored", False)
        if ctype == ComponentType.MUX:
            if not is_mirrored:
                if side == PinSide.LEFT:
                    pos = QPointF(0, snap(h * off))
                elif side == PinSide.RIGHT:
                    pos = QPointF(w, snap(h * 0.2 + (h * 0.6) * off))
                elif side == PinSide.TOP:
                    y_edge = (h * 0.2) * off
                    pos = QPointF(w * off, y_edge)
                else: # BOTTOM
                    y_edge = h - (h * 0.2) * off
                    pos = QPointF(w * off, y_edge)
            else:
                if side == PinSide.LEFT:
                    pos = QPointF(0, snap(h * 0.2 + (h * 0.6) * off))
                elif side == PinSide.RIGHT:
                    pos = QPointF(w, snap(h * off))
                elif side == PinSide.TOP:
                    y_edge = (h * 0.2) * (1.0 - off)
                    pos = QPointF(w * off, y_edge)
                else: # BOTTOM
                    y_edge = h - (h * 0.2) * (1.0 - off)
                    pos = QPointF(w * off, y_edge)
        elif ctype == ComponentType.OPERATOR_CIRCLE:
            if side == PinSide.LEFT:
                pos = QPointF(0, h * off)
            elif side == PinSide.RIGHT:
                pos = QPointF(w, h * off)
            elif side == PinSide.TOP:
                pos = QPointF(w * off, 0)
            else: # BOTTOM
                pos = QPointF(w * off, h)
        else:
            if side == PinSide.LEFT:
                pos = QPointF(0, snap(h * off))
            elif side == PinSide.RIGHT:
                pos = QPointF(w, snap(h * off))
            elif side == PinSide.TOP:
                pos = QPointF(snap(w * off), 0)
            else: # BOTTOM
                pos = QPointF(snap(w * off), h)

        self.setPos(pos)

    def boundingRect(self) -> QRectF:
        return QRectF(-120, -25, 240, 50)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(QPointF(0, 0), self.RADIUS + 3, self.RADIUS + 3)
        return path

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        ctype = self.parent_comp.model.type
        if ctype in (ComponentType.INPUT_PORT, ComponentType.OUTPUT_PORT):
            # Suppress default pin circle and redundant pin text; only show hover anchor
            if self.is_hovered:
                painter.setBrush(QBrush(QColor(255, 120, 0)))
                painter.setPen(QPen(QColor(200, 50, 0), 1.5))
                painter.drawEllipse(QPointF(0, 0), self.RADIUS, self.RADIUS)
            return

        if self.is_hovered:
            painter.setBrush(QBrush(QColor(255, 120, 0)))
            painter.setPen(QPen(QColor(200, 50, 0), 1.5))
        else:
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            painter.setPen(QPen(QColor(40, 40, 40), 1.5))
        painter.drawEllipse(QPointF(0, 0), self.RADIUS, self.RADIUS)

        # Suppress redundant output labels that cause visual clutter / collision
        if ctype == ComponentType.OPERATOR_CIRCLE and self.pin.direction == PinDirection.OUT:
            return
        if ctype == ComponentType.BUS_SPLITTER and self.pin.direction == PinDirection.OUT:
            return
        if ctype == ComponentType.MUX and self.pin.direction == PinDirection.OUT and self.pin.name == "out":
            return
        if ctype == ComponentType.MUX and (self.pin.name.lower() == "sel" or self.pin.direction == PinDirection.CONTROL):
            return

        # Draw pin label
        painter.setFont(QFont("Segoe UI", 8, QFont.Normal))
        painter.setPen(QPen(QColor(40, 40, 40)))

        name = self.pin.name
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(name)

        if self.pin.side == PinSide.LEFT:
            if ctype == ComponentType.BUS_SPLITTER:
                painter.drawText(QRectF(-tw - 8, -16, tw + 4, 14), Qt.AlignRight | Qt.AlignVCenter, name)
            else:
                painter.drawText(QRectF(6, -8, tw + 4, 16), Qt.AlignLeft | Qt.AlignVCenter, name)
        elif self.pin.side == PinSide.RIGHT:
            if ctype == ComponentType.BUS_SPLITTER and self.pin.direction == PinDirection.IN:
                painter.drawText(QRectF(8, -16, tw + 4, 14), Qt.AlignLeft | Qt.AlignVCenter, name)
            else:
                painter.drawText(QRectF(-tw - 6, -8, tw + 4, 16), Qt.AlignRight | Qt.AlignVCenter, name)
        elif self.pin.side == PinSide.TOP:
            y_off = 6 if ctype in (ComponentType.MUX, ComponentType.OPERATOR_CIRCLE) else -18
            painter.drawText(QRectF(-25, y_off, 50, 14), Qt.AlignCenter, name)
        elif self.pin.side == PinSide.BOTTOM:
            y_off = -18 if ctype in (ComponentType.MUX, ComponentType.OPERATOR_CIRCLE) else 4
            painter.drawText(QRectF(-25, y_off, 50, 14), Qt.AlignCenter, name)

    def hoverEnterEvent(self, event):
        self.is_hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.is_hovered = False
        self.update()
        super().hoverLeaveEvent(event)


class RTLResizeHandleItem(QGraphicsItem):
    """Bottom-right corner handle to resize generic blocks interactively"""
    SIZE = 10.0

    def __init__(self, comp_item: "RTLComponentItem"):
        super().__init__(comp_item)
        self.comp_item = comp_item
        self._is_updating = False
        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setZValue(5)
        self.setCursor(Qt.SizeFDiagCursor)
        self.update_position()

    def update_position(self):
        self._is_updating = True
        try:
            self.prepareGeometryChange()
            self.setPos(self.comp_item.model.width - self.SIZE / 2, self.comp_item.model.height - self.SIZE / 2)
        finally:
            self._is_updating = False

    def boundingRect(self) -> QRectF:
        s = self.SIZE
        return QRectF(-s / 2 - 2, -s / 2 - 2, s + 4, s + 4)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        s = self.SIZE
        rect = QRectF(-s / 2, -s / 2, s, s)
        painter.setBrush(QBrush(QColor(0, 102, 204)))
        painter.setPen(QPen(QColor(255, 255, 255), 1.2))
        painter.drawRoundedRect(rect, 2, 2)

    def mousePressEvent(self, event):
        self._press_pos = self.pos()
        if self.scene() and hasattr(self.scene(), "schematic"):
            self._press_snapshot = self.scene().schematic.to_dict()
        super().mousePressEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene() and not getattr(self, "_is_updating", False):
            val = value
            target_w = max(60.0, snap(val.x() + self.SIZE / 2))
            in_pins = len([p for p in self.comp_item.model.pins if p.side == PinSide.LEFT])
            out_pins = len([p for p in self.comp_item.model.pins if p.side == PinSide.RIGHT])
            min_h = max(60.0, (max(in_pins, out_pins) + 1) * 25.0)
            target_h = max(min_h, snap(val.y() + self.SIZE / 2))

            self._is_updating = True
            try:
                self.comp_item.set_block_size(target_w, target_h)
            finally:
                self._is_updating = False
            return QPointF(target_w - self.SIZE / 2, target_h - self.SIZE / 2)
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if hasattr(self, "_press_pos") and self.pos() != self._press_pos:
            if self.scene() and hasattr(self.scene(), "undo_stack") and hasattr(self, "_press_snapshot"):
                self.scene().undo_stack.append(self._press_snapshot)
                if len(self.scene().undo_stack) > self.scene().max_undo:
                    self.scene().undo_stack.pop(0)
                self.scene().redo_stack.clear()
                self.scene().status_message.emit(
                    f"Bloque redimensionado a {int(self.comp_item.model.width)}x{int(self.comp_item.model.height)}. (Ctrl+Z para deshacer)"
                )


class RTLComponentItem(QGraphicsItem):
    """Visual QGraphicsItem representing an ELO212 component"""

    def __init__(self, model: RTLComponent):
        super().__init__()
        self.model = model
        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemIsSelectable |
            QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setPos(snap(model.x), snap(model.y))
        self.pin_items: List[RTLPinItem] = []
        self._init_pins()
        self.resize_handle: Optional[RTLResizeHandleItem] = None
        if self.model.type == ComponentType.BLOCK:
            self.resize_handle = RTLResizeHandleItem(self)
            self.resize_handle.setVisible(False)

    def _init_pins(self):
        for p in self.model.pins:
            pin_item = RTLPinItem(p, self)
            self.pin_items.append(pin_item)

    def set_block_size(self, w: float, h: float):
        self.prepareGeometryChange()
        self.model.width = w
        self.model.height = h
        for pi in self.pin_items:
            pi.update_position()
        if self.resize_handle:
            self.resize_handle.update_position()
        self.update()
        if self.scene() and hasattr(self.scene(), "on_component_moved"):
            self.scene().on_component_moved(self)

    def rebuild_pins(self):
        for pi in self.pin_items:
            pi.setParentItem(None)
            if pi.scene():
                pi.scene().removeItem(pi)
        self.pin_items.clear()
        self._init_pins()
        if self.resize_handle:
            self.resize_handle.update_position()
        self.prepareGeometryChange()
        self.update()
        if self.scene() and hasattr(self.scene(), "on_component_moved"):
            self.scene().on_component_moved(self)

    def mouseDoubleClickEvent(self, event):
        if self.scene():
            for v in self.scene().views():
                p = v.parent()
                while p:
                    if self.model.type == ComponentType.BLOCK and hasattr(p, "open_block_dialog"):
                        p.open_block_dialog(self)
                        return
                    elif self.model.type == ComponentType.MUX and hasattr(p, "open_mux_dialog"):
                        p.open_mux_dialog(self)
                        return
                    elif self.model.type == ComponentType.BUS_SPLITTER and hasattr(p, "open_splitter_dialog"):
                        p.open_splitter_dialog(self)
                        return
                    elif self.model.type == ComponentType.OPERATOR_CIRCLE and hasattr(p, "open_operator_dialog"):
                        p.open_operator_dialog(self)
                        return
                    elif self.model.type in (ComponentType.INPUT_PORT, ComponentType.OUTPUT_PORT) and hasattr(p, "open_port_dialog"):
                        p.open_port_dialog(self)
                        return
                    p = p.parent()
        super().mouseDoubleClickEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            new_pos = value
            snapped_x = snap(new_pos.x())
            snapped_y = snap(new_pos.y())
            self.model.x = snapped_x
            self.model.y = snapped_y
            return QPointF(snapped_x, snapped_y)
        elif change == QGraphicsItem.ItemPositionHasChanged and self.scene():
            if hasattr(self.scene(), "on_component_moved"):
                self.scene().on_component_moved(self)
        elif change == QGraphicsItem.ItemSelectedHasChanged:
            if self.resize_handle:
                self.resize_handle.setVisible(self.isSelected())
                if self.isSelected():
                    self.resize_handle.update_position()
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        self._press_pos = self.pos()
        if self.scene() and hasattr(self.scene(), "schematic"):
            self._press_snapshot = self.scene().schematic.to_dict()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if hasattr(self, "_press_pos") and self.pos() != self._press_pos:
            if self.scene() and hasattr(self.scene(), "undo_stack") and hasattr(self, "_press_snapshot"):
                self.scene().undo_stack.append(self._press_snapshot)
                if len(self.scene().undo_stack) > self.scene().max_undo:
                    self.scene().undo_stack.pop(0)
                self.scene().redo_stack.clear()
                self.scene().status_message.emit("Componente movido. (Ctrl+Z para deshacer)")

    def shape(self) -> QPainterPath:
        ctype = self.model.type
        w = self.model.width
        h = self.model.height
        is_mirrored = getattr(self.model, "mirrored", False)
        path = QPainterPath()

        if ctype == ComponentType.MUX:
            if is_mirrored:
                poly = QPolygonF([
                    QPointF(0, h * 0.2),
                    QPointF(w, 0),
                    QPointF(w, h),
                    QPointF(0, h * 0.8)
                ])
            else:
                poly = QPolygonF([
                    QPointF(0, 0),
                    QPointF(w, h * 0.2),
                    QPointF(w, h * 0.8),
                    QPointF(0, h)
                ])
            path.addPolygon(poly)

        elif ctype == ComponentType.OPERATOR_CIRCLE:
            path.addEllipse(QRectF(0, 0, w, h))

        elif ctype == ComponentType.GATE_AND:
            g_path = QPainterPath()
            g_path.moveTo(0, 0)
            g_path.lineTo(w * 0.5, 0)
            g_path.arcTo(QRectF(0, 0, w, h), 90, -180)
            g_path.lineTo(0, h)
            g_path.closeSubpath()
            if is_mirrored:
                t = QTransform().translate(w, 0).scale(-1, 1)
                g_path = t.map(g_path)
            path.addPath(g_path)

        elif ctype == ComponentType.GATE_OR:
            g_path = QPainterPath()
            g_path.moveTo(0, 0)
            g_path.quadTo(w * 0.25, h * 0.5, 0, h)
            g_path.quadTo(w * 0.6, h * 0.95, w, h * 0.5)
            g_path.quadTo(w * 0.6, h * 0.05, 0, 0)
            g_path.closeSubpath()
            if is_mirrored:
                t = QTransform().translate(w, 0).scale(-1, 1)
                g_path = t.map(g_path)
            path.addPath(g_path)

        elif ctype == ComponentType.GATE_NOT:
            poly = QPolygonF([
                QPointF(0, 0),
                QPointF(w - 10, h * 0.5),
                QPointF(0, h)
            ])
            g_path = QPainterPath()
            g_path.addPolygon(poly)
            g_path.addEllipse(QRectF(w - 10, h * 0.5 - 4, 8, 8))
            if is_mirrored:
                t = QTransform().translate(w, 0).scale(-1, 1)
                g_path = t.map(g_path)
            path.addPath(g_path)

        elif ctype == ComponentType.GATE_XOR:
            p_back = QPainterPath()
            p_back.moveTo(-6, 0)
            p_back.quadTo(w * 0.25 - 6, h * 0.5, -6, h)
            stroker = QPainterPathStroker()
            stroker.setWidth(8.0)
            stroke_back = stroker.createStroke(p_back)

            g_path = QPainterPath()
            g_path.moveTo(0, 0)
            g_path.quadTo(w * 0.25, h * 0.5, 0, h)
            g_path.quadTo(w * 0.6, h * 0.95, w, h * 0.5)
            g_path.quadTo(w * 0.6, h * 0.05, 0, 0)
            g_path.closeSubpath()
            g_path.addPath(stroke_back)
            if is_mirrored:
                t = QTransform().translate(w, 0).scale(-1, 1)
                g_path = t.map(g_path)
            path.addPath(g_path)

        elif ctype in (ComponentType.INPUT_PORT, ComponentType.OUTPUT_PORT):
            y_top = 11.0
            y_bot = 29.0
            y_mid = 20.0
            x_left = 0.0
            x_body = 16.0
            x_tip = 24.0
            pointing_right = (not is_mirrored)
            if pointing_right:
                poly = QPolygonF([
                    QPointF(x_left, y_top),
                    QPointF(x_body, y_top),
                    QPointF(x_tip, y_mid),
                    QPointF(x_body, y_bot),
                    QPointF(x_left, y_bot),
                ])
            else:
                poly = QPolygonF([
                    QPointF(x_tip, y_top),
                    QPointF(x_tip - x_body, y_top),
                    QPointF(x_left, y_mid),
                    QPointF(x_tip - x_body, y_bot),
                    QPointF(x_tip, y_bot),
                ])
            path.addPolygon(poly)
            label = self.model.label or ""
            if label:
                fm = QFontMetrics(QFont("Segoe UI", 9, QFont.Normal))
                tw = fm.horizontalAdvance(label)
                th = fm.height()
                is_input = (ctype == ComponentType.INPUT_PORT)
                text_on_left = (is_input and not is_mirrored) or (not is_input and is_mirrored)
                if text_on_left:
                    text_rect = QRectF(-tw - 8, y_mid - th / 2, tw + 4, th)
                else:
                    text_rect = QRectF(x_tip + 8, y_mid - th / 2, tw + 4, th)
                path.addRect(text_rect)

        elif ctype == ComponentType.BUS_SPLITTER:
            spine_x = (w - 24.0) if is_mirrored else 24.0
            out_pins = [p for p in self.model.pins if p.direction == PinDirection.OUT]
            in_pin = next((p for p in self.model.pins if p.direction == PinDirection.IN), None)
            if out_pins:
                min_y = min(snap(h * p.offset) for p in out_pins)
                max_y = max(snap(h * p.offset) for p in out_pins)
            else:
                min_y, max_y = 10.0, h - 10.0
            in_y = snap(h * in_pin.offset) if in_pin else snap(h * 0.5)
            min_y = min(min_y, in_y)
            max_y = max(max_y, in_y)

            spine_w = 8.0
            path.addRect(QRectF(spine_x - spine_w / 2, min_y - 3, spine_w, (max_y - min_y) + 6))

            stroker = QPainterPathStroker()
            stroker.setWidth(8.0)
            wire_path = QPainterPath()
            if is_mirrored:
                wire_path.moveTo(w, in_y)
                wire_path.lineTo(spine_x, in_y)
                for pin in out_pins:
                    py = snap(h * pin.offset)
                    wire_path.moveTo(spine_x, py)
                    wire_path.lineTo(0, py)
            else:
                wire_path.moveTo(0, in_y)
                wire_path.lineTo(spine_x, in_y)
                for pin in out_pins:
                    py = snap(h * pin.offset)
                    wire_path.moveTo(spine_x, py)
                    wire_path.lineTo(w, py)
            path.addPath(stroker.createStroke(wire_path))

            fm = QFontMetrics(QFont("Consolas", 8, QFont.Bold))
            for pin in out_pins:
                py = snap(h * pin.offset)
                tw = fm.horizontalAdvance(pin.name)
                if is_mirrored:
                    path.addRect(QRectF(8, py - 16, tw + 4, 14))
                else:
                    path.addRect(QRectF(spine_x + 8, py - 16, tw + 4, 14))

        else: # REGISTER, CONSTANT, BLOCK
            path.addRect(QRectF(0, 0, w, h))

        return path

    def boundingRect(self) -> QRectF:
        sh_rect = self.shape().boundingRect()
        return sh_rect.adjusted(-2.0, -2.0, 2.0, 2.0)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        pen_color = QColor(0, 102, 204) if self.isSelected() else QColor(30, 30, 30)
        pen_width = 2.0 if self.isSelected() else 1.8
        pen = QPen(pen_color, pen_width)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(255, 255, 255)))

        w = self.model.width
        h = self.model.height
        ctype = self.model.type

        if ctype == ComponentType.MUX:
            self._paint_mux(painter, w, h)
        elif ctype == ComponentType.REGISTER:
            self._paint_register(painter, w, h)
        elif ctype == ComponentType.OPERATOR_CIRCLE:
            self._paint_circle_op(painter, w, h)
        elif ctype in (ComponentType.GATE_AND, ComponentType.GATE_OR, ComponentType.GATE_NOT, ComponentType.GATE_XOR):
            self._paint_gate(painter, w, h, ctype)
        elif ctype == ComponentType.BUS_SPLITTER:
            self._paint_bus_splitter(painter, w, h)
        elif ctype == ComponentType.CONSTANT:
            self._paint_constant(painter, w, h)
        elif ctype in (ComponentType.INPUT_PORT, ComponentType.OUTPUT_PORT):
            self._paint_port(painter, w, h, is_input=(ctype == ComponentType.INPUT_PORT))
        else: # BLOCK
            self._paint_generic_block(painter, w, h)

    def _paint_port(self, painter: QPainter, w: float, h: float, is_input: bool):
        is_mirrored = getattr(self.model, "mirrored", False)
        # Check if bus: pin width > 1 or bus_width property > 1 or width_param
        is_bus = False
        if self.model.pins:
            p = self.model.pins[0]
            if p.width > 1 or bool(p.width_param):
                is_bus = True
        if not is_bus:
            bw_prop = self.model.properties.get("bus_width", "1")
            try:
                if int(bw_prop) > 1:
                    is_bus = True
            except ValueError:
                pass
            if self.model.properties.get("bus_width_param"):
                is_bus = True

        pen_color = QColor(0, 102, 204) if self.isSelected() else QColor(20, 20, 20)
        # Image 1 (single-bit) is thin 1.6px; Image 2 (bus) is thick 3.2px!
        pen_w = 3.2 if is_bus else 1.6
        pen = QPen(pen_color, pen_w, Qt.SolidLine, Qt.SquareCap, Qt.MiterJoin)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(255, 255, 255)))

        # Symbol dimensions: height = 18px (from y=11 to y=29, center=20), width=24px (body=16px, tip=8px)
        y_top = 11.0
        y_bot = 29.0
        y_mid = 20.0
        x_left = 0.0
        x_body = 16.0
        x_tip = 24.0

        pointing_right = (not is_mirrored)
        if pointing_right:
            poly = QPolygonF([
                QPointF(x_left, y_top),
                QPointF(x_body, y_top),
                QPointF(x_tip, y_mid),
                QPointF(x_body, y_bot),
                QPointF(x_left, y_bot),
            ])
        else:
            poly = QPolygonF([
                QPointF(x_tip, y_top),
                QPointF(x_tip - x_body, y_top),
                QPointF(x_left, y_mid),
                QPointF(x_tip - x_body, y_bot),
                QPointF(x_tip, y_bot),
            ])

        painter.drawPolygon(poly)

        # Draw Port Label Text
        label = self.model.label or ""
        if label:
            font = QFont("Segoe UI", 9, QFont.Normal)
            painter.setFont(font)
            fm = painter.fontMetrics()
            tw = fm.horizontalAdvance(label)
            th = fm.height()

            painter.setPen(QPen(QColor(20, 20, 20)))

            # Input (pointing right): text on left (Image 1)
            # Output (pointing right): text on right (Image 2)
            # If mirrored: inverted
            text_on_left = (is_input and not is_mirrored) or (not is_input and is_mirrored)
            if text_on_left:
                text_rect = QRectF(-tw - 8, y_mid - th / 2, tw + 4, th)
                painter.drawText(text_rect, Qt.AlignRight | Qt.AlignVCenter, label)
            else:
                text_rect = QRectF(x_tip + 8, y_mid - th / 2, tw + 4, th)
                painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, label)

    def _paint_mux(self, painter: QPainter, w: float, h: float):
        if getattr(self.model, "mirrored", False):
            # Mirrored: narrow on left, wide on right
            poly = QPolygonF([
                QPointF(0, h * 0.2),
                QPointF(w, 0),
                QPointF(w, h),
                QPointF(0, h * 0.8)
            ])
        else:
            # Trapezoid: wide edge on left (0 to h), narrow edge on right (h*0.2 to h*0.8)
            poly = QPolygonF([
                QPointF(0, 0),
                QPointF(w, h * 0.2),
                QPointF(w, h * 0.8),
                QPointF(0, h)
            ])
        painter.drawPolygon(poly)

    def _paint_register(self, painter: QPainter, w: float, h: float):
        painter.drawRect(QRectF(0, 0, w, h))

        # Clock triangle at bottom or left
        # Per ELO212 slide 5: triangle indicates clk
        tri_size = 10.0
        # Check clk pin position
        clk_pin = next((p for p in self.model.pins if p.name.lower() == "clk"), None)
        if clk_pin and clk_pin.side == PinSide.BOTTOM:
            cx = w * clk_pin.offset
            clk_tri = QPolygonF([
                QPointF(cx - tri_size / 2, h),
                QPointF(cx, h - tri_size),
                QPointF(cx + tri_size / 2, h)
            ])
            painter.drawPolyline(clk_tri)
        elif clk_pin and clk_pin.side == PinSide.LEFT:
            cy = h * clk_pin.offset
            clk_tri = QPolygonF([
                QPointF(0, cy - tri_size / 2),
                QPointF(tri_size, cy),
                QPointF(0, cy + tri_size / 2)
            ])
            painter.drawPolyline(clk_tri)

    def _paint_circle_op(self, painter: QPainter, w: float, h: float):
        painter.drawEllipse(QRectF(0, 0, w, h))
        lbl = self.model.label
        base_size = 9 if w <= 45 else (10 if w <= 60 else 12)
        fsize = base_size - 3 if len(lbl) > 5 else (base_size - 2 if len(lbl) > 3 else (base_size - 1 if len(lbl) > 1 else base_size))
        fsize = max(7, fsize)
        painter.setFont(QFont("Segoe UI", fsize, QFont.Bold))
        painter.setPen(QPen(QColor(30, 30, 30)))
        painter.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, lbl)

    def _paint_gate(self, painter: QPainter, w: float, h: float, ctype: ComponentType):
        is_mirrored = getattr(self.model, "mirrored", False)
        if is_mirrored:
            painter.save()
            t = QTransform().translate(w, 0).scale(-1, 1)
            painter.setTransform(t * painter.transform())

        path = QPainterPath()
        if ctype == ComponentType.GATE_AND:
            path.moveTo(0, 0)
            path.lineTo(w * 0.5, 0)
            path.arcTo(QRectF(0, 0, w, h), 90, -180)
            path.lineTo(0, h)
            path.closeSubpath()
            painter.drawPath(path)
        elif ctype == ComponentType.GATE_OR:
            path.moveTo(0, 0)
            path.quadTo(w * 0.25, h * 0.5, 0, h)
            path.quadTo(w * 0.6, h * 0.95, w, h * 0.5)
            path.quadTo(w * 0.6, h * 0.05, 0, 0)
            painter.drawPath(path)
        elif ctype == ComponentType.GATE_NOT:
            poly = QPolygonF([
                QPointF(0, 0),
                QPointF(w - 10, h * 0.5),
                QPointF(0, h)
            ])
            painter.drawPolygon(poly)
            # Inversion bubble
            painter.drawEllipse(QRectF(w - 10, h * 0.5 - 4, 8, 8))
        elif ctype == ComponentType.GATE_XOR:
            # Back arc
            p_back = QPainterPath()
            p_back.moveTo(-6, 0)
            p_back.quadTo(w * 0.25 - 6, h * 0.5, -6, h)
            painter.drawPath(p_back)
            # Body
            path.moveTo(0, 0)
            path.quadTo(w * 0.25, h * 0.5, 0, h)
            path.quadTo(w * 0.6, h * 0.95, w, h * 0.5)
            path.quadTo(w * 0.6, h * 0.05, 0, 0)
            painter.drawPath(path)

        if is_mirrored:
            painter.restore()

    def _paint_bus_splitter(self, painter: QPainter, w: float, h: float):
        is_mirrored = getattr(self.model, "mirrored", False)
        spine_x = (w - 24.0) if is_mirrored else 24.0
        out_pins = [p for p in self.model.pins if p.direction == PinDirection.OUT]
        in_pin = next((p for p in self.model.pins if p.direction == PinDirection.IN), None)

        if out_pins:
            min_y = min(snap(h * p.offset) for p in out_pins)
            max_y = max(snap(h * p.offset) for p in out_pins)
        else:
            min_y, max_y = 10.0, h - 10.0

        in_y = snap(h * in_pin.offset) if in_pin else snap(h * 0.5)
        min_y = min(min_y, in_y)
        max_y = max(max_y, in_y)

        # Draw input wire
        painter.setPen(QPen(QColor(30, 30, 30), 1.8))
        if is_mirrored:
            painter.drawLine(QLineF(w, in_y, spine_x, in_y))
            if in_pin and in_pin.width > 1:
                ix = w - (w - spine_x) * 0.45
                painter.drawLine(QLineF(ix - 4, in_y + 6, ix + 4, in_y - 6))
                painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
                painter.drawText(QRectF(ix - 2, in_y + 1, 24, 12), Qt.AlignLeft, str(in_pin.width))
        else:
            painter.drawLine(QLineF(0, in_y, spine_x, in_y))
            if in_pin and in_pin.width > 1:
                ix = spine_x * 0.45
                painter.drawLine(QLineF(ix - 4, in_y + 6, ix + 4, in_y - 6))
                painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
                painter.drawText(QRectF(ix - 2, in_y + 1, 24, 12), Qt.AlignLeft, str(in_pin.width))

        # Draw thick vertical spine bar
        spine_w = 5.0
        painter.setBrush(QBrush(QColor(30, 30, 30)))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(spine_x - spine_w / 2, min_y - 2, spine_w, (max_y - min_y) + 4), 1.5, 1.5)

        # Draw output branches
        for pin in out_pins:
            py = snap(h * pin.offset)
            painter.setPen(QPen(QColor(30, 30, 30), 1.8))
            if is_mirrored:
                painter.drawLine(QLineF(spine_x, py, 0, py))
                painter.setFont(QFont("Consolas", 8, QFont.Bold))
                painter.setPen(QPen(QColor(20, 20, 20)))
                painter.drawText(QRectF(8, py - 16, spine_x - 12, 14), Qt.AlignLeft | Qt.AlignVCenter, pin.name)
                if pin.width > 1:
                    sx = spine_x - 18.0
                    painter.setPen(QPen(QColor(30, 30, 30), 1.5))
                    painter.drawLine(QLineF(sx - 4, py + 6, sx + 4, py - 6))
                    painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
                    painter.drawText(QRectF(sx - 12, py + 1, 22, 12), Qt.AlignLeft, str(pin.width))
            else:
                painter.drawLine(QLineF(spine_x, py, w, py))
                painter.setFont(QFont("Consolas", 8, QFont.Bold))
                painter.setPen(QPen(QColor(20, 20, 20)))
                painter.drawText(QRectF(spine_x + 8, py - 16, w - spine_x - 10, 14), Qt.AlignLeft | Qt.AlignVCenter, pin.name)
                if pin.width > 1:
                    sx = spine_x + 18.0
                    painter.setPen(QPen(QColor(30, 30, 30), 1.5))
                    painter.drawLine(QLineF(sx - 4, py + 6, sx + 4, py - 6))
                    painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
                    painter.drawText(QRectF(sx - 1, py + 1, 22, 12), Qt.AlignLeft, str(pin.width))

    def _paint_constant(self, painter: QPainter, w: float, h: float):
        painter.setBrush(QBrush(QColor(245, 245, 245)))
        painter.drawRoundedRect(QRectF(0, 0, w, h), 4, 4)
        painter.setFont(QFont("Consolas", 10, QFont.Bold))
        painter.drawText(QRectF(0, 0, w, h), Qt.AlignCenter, self.model.label)

    def _paint_generic_block(self, painter: QPainter, w: float, h: float):
        painter.drawRect(QRectF(0, 0, w, h))
        # Header separator
        painter.drawLine(0, 26, w, 26)
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.drawText(QRectF(0, 2, w, 24), Qt.AlignCenter, self.model.label)


class RTLWireLabelItem(QGraphicsItem):
    """Draggable signal name / bus label tag on a wire (e.g. 'count', 'next_count')"""

    def __init__(self, wire_item: "RTLWireItem"):
        super().__init__(wire_item)
        self.wire_item = wire_item
        self._is_updating = False
        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemIsSelectable |
            QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setZValue(3)
        self.update_position()

    def update_position(self):
        self._is_updating = True
        try:
            self.prepareGeometryChange()
            w = self.wire_item.model
            if w.label_pos is not None:
                scene_pt = QPointF(w.label_pos[0], w.label_pos[1])
                self.setPos(self.wire_item.mapFromScene(scene_pt))
            else:
                auto_pt = self.wire_item.get_auto_label_pos()
                self.setPos(auto_pt)
        finally:
            self._is_updating = False

    def boundingRect(self) -> QRectF:
        text = self.wire_item.model.label
        if not text:
            return QRectF()
        fm = QFontMetrics(QFont("Consolas", 8, QFont.Bold))
        tw = fm.horizontalAdvance(text) + 12
        th = fm.height() + 6
        return QRectF(-tw / 2 - 2, -th / 2 - 2, tw + 4, th + 4)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged and not getattr(self, "_is_updating", False):
            scene_pos = self.mapToScene(QPointF(0, 0))
            self.wire_item.model.label_pos = (scene_pos.x(), scene_pos.y())
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        self._press_pos = self.pos()
        if self.scene() and hasattr(self.scene(), "schematic"):
            self._press_snapshot = self.scene().schematic.to_dict()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if hasattr(self, "_press_pos") and self.pos() != self._press_pos:
            if self.scene() and hasattr(self.scene(), "undo_stack") and hasattr(self, "_press_snapshot"):
                self.scene().undo_stack.append(self._press_snapshot)
                if len(self.scene().undo_stack) > self.scene().max_undo:
                    self.scene().undo_stack.pop(0)
                self.scene().redo_stack.clear()
                self.scene().status_message.emit("Etiqueta desplazada. (Shift+R para restablecer posición)")

    def paint(self, painter: QPainter, option, widget=None):
        text = self.wire_item.model.label
        if not text:
            return
        painter.setRenderHint(QPainter.Antialiasing)
        fm = QFontMetrics(QFont("Consolas", 8, QFont.Bold))
        tw = fm.horizontalAdvance(text) + 10
        th = fm.height() + 4
        badge_rect = QRectF(-tw / 2, -th / 2, tw, th)

        bg_color = QColor(230, 243, 255) if self.isSelected() else QColor(255, 255, 255, 245)
        border_color = QColor(0, 102, 204) if self.isSelected() else QColor(180, 180, 180)
        painter.setBrush(QBrush(bg_color))
        painter.setPen(QPen(border_color, 1.2 if self.isSelected() else 0.8))
        painter.drawRoundedRect(badge_rect, 3, 3)

        painter.setFont(QFont("Consolas", 8, QFont.Bold))
        painter.setPen(QPen(QColor(20, 20, 20)))
        painter.drawText(badge_rect, Qt.AlignCenter, text)


class RTLWireHandleItem(QGraphicsItem):
    """Draggable handle on wire vertices or segment midpoints to adjust routing freely"""
    SIZE = 7.0

    def __init__(self, wire_item: "RTLWireItem", handle_type: str, index: int, pos: QPointF):
        super().__init__(wire_item)
        self.wire_item = wire_item
        self.handle_type = handle_type  # "segment" or "vertex"
        self.index = index
        self.setPos(pos)
        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setZValue(10)
        is_horiz = self._is_horiz_segment()
        if handle_type == "segment":
            self.setCursor(Qt.SizeVerCursor if is_horiz else Qt.SizeHorCursor)
        else:
            self.setCursor(Qt.SizeAllCursor)

    def _is_horiz_segment(self) -> bool:
        pts = self.wire_item.model.points
        if self.handle_type == "segment" and self.index < len(pts) - 1:
            p1 = pts[self.index]
            p2 = pts[self.index + 1]
            return abs(p2[0] - p1[0]) >= abs(p2[1] - p1[1])
        return False

    def boundingRect(self) -> QRectF:
        s = self.SIZE
        return QRectF(-s / 2 - 2, -s / 2 - 2, s + 4, s + 4)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        s = self.SIZE
        rect = QRectF(-s / 2, -s / 2, s, s)
        if self.handle_type == "segment":
            painter.setBrush(QBrush(QColor(0, 102, 204)))
            painter.setPen(QPen(QColor(255, 255, 255), 1.0))
            painter.drawRoundedRect(rect, 2, 2)
        else:
            painter.setBrush(QBrush(QColor(255, 120, 0)))
            painter.setPen(QPen(QColor(255, 255, 255), 1.0))
            painter.drawEllipse(rect)

    def mousePressEvent(self, event):
        self._press_pos = self.pos()
        if self.scene() and hasattr(self.scene(), "schematic"):
            self._press_snapshot = self.scene().schematic.to_dict()
        super().mousePressEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            val = value
            if self.handle_type == "segment":
                return self.wire_item.on_segment_dragged(self.index, val)
            elif self.handle_type == "vertex":
                return self.wire_item.on_vertex_dragged(self.index, val)
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if hasattr(self, "_press_pos") and self.pos() != self._press_pos:
            if self.scene() and hasattr(self.scene(), "undo_stack") and hasattr(self, "_press_snapshot"):
                self.scene().undo_stack.append(self._press_snapshot)
                if len(self.scene().undo_stack) > self.scene().max_undo:
                    self.scene().undo_stack.pop(0)
                self.scene().redo_stack.clear()
                self.scene().status_message.emit("Cable ruteado manualmente. (Presione 'R' para re-enrutar automáticamente)")
            self.wire_item.update_handles()


class RTLWireItem(QGraphicsItem):
    """
    Orthogonal (Manhattan) Wire Item conforming strictly to ELO212 rules:
    - Only horizontal and vertical segments.
    - Bit width diagonal slash '/N' if width > 1.
    - Interactive draggable handles on vertices and segments.
    - Independent draggable label tag.
    """

    def __init__(self, model: RTLWire):
        super().__init__()
        self.model = model
        self.setFlags(
            QGraphicsItem.ItemIsSelectable |
            QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setZValue(-1)
        self.handles: List[RTLWireHandleItem] = []
        self.label_item: Optional[RTLWireLabelItem] = None
        self._sync_label_item()

    def _sync_label_item(self):
        if self.model.label.strip():
            if not self.label_item:
                self.label_item = RTLWireLabelItem(self)
            else:
                self.label_item.update_position()
        else:
            if self.label_item:
                if self.label_item.scene():
                    self.label_item.scene().removeItem(self.label_item)
                self.label_item = None

    def get_auto_label_pos(self) -> QPointF:
        if len(self.model.points) < 2:
            return QPointF(0, 0)
        pts = [QPointF(p[0], p[1]) for p in self.model.points]
        p1, p2 = self._get_longest_segment(pts)
        has_slash = ((self.model.width > 1 or self.model.width_param) and self.model.show_slash)
        t_label = 0.72 if has_slash else 0.50
        mid = p1 + (p2 - p1) * t_label
        return mid

    def reset_label_pos(self):
        self.model.label_pos = None
        if self.label_item:
            self.label_item.update_position()

    def reset_routing(self):
        self.model.manual_routing = False
        if self.scene() and hasattr(self.scene(), "recompute_wire_path"):
            self.scene().recompute_wire_path(self)
        self.update_handles()

    def create_handles(self):
        self.clear_handles()
        pts = [QPointF(p[0], p[1]) for p in self.model.points]
        if len(pts) < 2:
            return
        # Segment handles at midpoints
        for i in range(len(pts) - 1):
            mid = (pts[i] + pts[i + 1]) / 2.0
            h = RTLWireHandleItem(self, "segment", i, mid)
            self.handles.append(h)
        # Intermediate vertex handles
        for i in range(1, len(pts) - 1):
            h = RTLWireHandleItem(self, "vertex", i, pts[i])
            self.handles.append(h)

    def clear_handles(self):
        for h in self.handles:
            h.setParentItem(None)
            if h.scene():
                h.scene().removeItem(h)
        self.handles.clear()

    def update_handles(self):
        if self.isSelected():
            self.create_handles()
        else:
            self.clear_handles()

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemSelectedHasChanged:
            self.setZValue(2 if self.isSelected() else -1)
            self.update_handles()
        return super().itemChange(change, value)

    def on_segment_dragged(self, index: int, val: QPointF) -> QPointF:
        pts = [list(p) for p in self.model.points]
        if index >= len(pts) - 1:
            return val
        p1 = pts[index]
        p2 = pts[index + 1]
        is_horiz = abs(p2[0] - p1[0]) >= abs(p2[1] - p1[1])

        if is_horiz:
            target_y = snap(val.y())
            if index == 0 and len(pts) == 2:
                mid_x = snap((pts[0][0] + pts[1][0]) / 2.0)
                pts = [pts[0], [mid_x, pts[0][1]], [mid_x, target_y], [pts[1][0], target_y], pts[1]]
            elif index == 0:
                pts[1][1] = target_y
            elif index + 1 == len(pts) - 1:
                pts[index][1] = target_y
            else:
                pts[index][1] = target_y
                pts[index + 1][1] = target_y
            ret_pos = QPointF(val.x(), target_y)
        else:
            target_x = snap(val.x())
            if index == 0 and len(pts) == 2:
                mid_y = snap((pts[0][1] + pts[1][1]) / 2.0)
                pts = [pts[0], [pts[0][0], mid_y], [target_x, mid_y], [target_x, pts[1][1]], pts[1]]
            elif index == 0:
                pts[1][0] = target_x
            elif index + 1 == len(pts) - 1:
                pts[index][0] = target_x
            else:
                pts[index][0] = target_x
                pts[index + 1][0] = target_x
            ret_pos = QPointF(target_x, val.y())

        self.model.points = [(p[0], p[1]) for p in pts]
        self.model.manual_routing = True
        self.prepareGeometryChange()
        self.update()
        if self.label_item and self.model.label_pos is None:
            self.label_item.update_position()
        return ret_pos

    def on_vertex_dragged(self, index: int, val: QPointF) -> QPointF:
        pts = [list(p) for p in self.model.points]
        if not (0 < index < len(pts) - 1):
            return val
        target_x = snap(val.x())
        target_y = snap(val.y())

        prev_horiz = abs(pts[index][0] - pts[index - 1][0]) >= abs(pts[index][1] - pts[index - 1][1])
        if prev_horiz:
            pts[index - 1][1] = target_y
            pts[index] = [target_x, target_y]
            if index + 1 < len(pts):
                pts[index + 1][0] = target_x
        else:
            pts[index - 1][0] = target_x
            pts[index] = [target_x, target_y]
            if index + 1 < len(pts):
                pts[index + 1][1] = target_y

        self.model.points = [(p[0], p[1]) for p in pts]
        self.model.manual_routing = True
        self.prepareGeometryChange()
        self.update()
        if self.label_item and self.model.label_pos is None:
            self.label_item.update_position()
        return QPointF(target_x, target_y)

    def _get_arrow_polygon(self) -> Optional[QPolygonF]:
        if len(self.model.points) < 2:
            return None
        pts = [QPointF(p[0], p[1]) for p in self.model.points]
        p_prev = pts[-2]
        p_last = pts[-1]
        d = p_last - p_prev
        length = math.hypot(d.x(), d.y())
        if length < 0.001:
            return None
        ux = d.x() / length
        uy = d.y() / length
        vx, vy = -uy, ux
        arrow_len = 8.0
        arrow_w = 4.5
        offset = 4.0 if self.model.target_pin_id else 0.0
        tip = QPointF(p_last.x() - offset * ux, p_last.y() - offset * uy)
        left = QPointF(tip.x() - arrow_len * ux + arrow_w * vx, tip.y() - arrow_len * uy + arrow_w * vy)
        right = QPointF(tip.x() - arrow_len * ux - arrow_w * vx, tip.y() - arrow_len * uy - arrow_w * vy)
        return QPolygonF([tip, left, right])

    def shape(self) -> QPainterPath:
        if len(self.model.points) < 2:
            return super().shape()
        path = QPainterPath()
        path.moveTo(self.model.points[0][0], self.model.points[0][1])
        for p in self.model.points[1:]:
            path.lineTo(p[0], p[1])
        stroker = QPainterPathStroker()
        stroker.setWidth(12.0)
        stroker.setCapStyle(Qt.RoundCap)
        stroker.setJoinStyle(Qt.RoundJoin)
        stroke_path = stroker.createStroke(path)
        if self.model.show_arrow:
            poly = self._get_arrow_polygon()
            if poly:
                stroke_path.addPolygon(poly)
        return stroke_path

    def boundingRect(self) -> QRectF:
        if not self.model.points:
            return QRectF()
        xs = [p[0] for p in self.model.points]
        ys = [p[1] for p in self.model.points]
        pad = 65.0
        return QRectF(min(xs) - pad, min(ys) - pad, max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad)

    def paint(self, painter: QPainter, option, widget=None):
        if len(self.model.points) < 2:
            return

        painter.setRenderHint(QPainter.Antialiasing)
        color = QColor(0, 102, 204) if self.isSelected() else QColor(30, 30, 30)
        pen_w = 2.2 if self.model.width > 1 else 1.5
        painter.setPen(QPen(color, pen_w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))

        pts = [QPointF(p[0], p[1]) for p in self.model.points]
        for i in range(len(pts) - 1):
            painter.drawLine(pts[i], pts[i + 1])

        # Draw diagonal slash '/N' or '/PARAM' for buses (ELO212 Figure 1b)
        if (self.model.width > 1 or self.model.width_param) and self.model.show_slash:
            self._paint_bus_slash(painter, pts)

        # Draw directional arrow at target (ELO212 Figure 4)
        if self.model.show_arrow:
            poly = self._get_arrow_polygon()
            if poly:
                painter.setBrush(QBrush(color))
                painter.setPen(Qt.NoPen)
                painter.drawPolygon(poly)


    def _get_longest_segment(self, pts: List[QPointF]) -> Tuple[QPointF, QPointF]:
        longest_seg = (pts[0], pts[1])
        max_len = 0
        for i in range(len(pts) - 1):
            d = (pts[i+1] - pts[i]).manhattanLength()
            if d > max_len:
                max_len = d
                longest_seg = (pts[i], pts[i+1])
        return longest_seg

    def _paint_bus_slash(self, painter: QPainter, pts: List[QPointF]):
        p1, p2 = self._get_longest_segment(pts)
        t_slash = 0.16 if self.model.label.strip() else 0.50
        mid = p1 + (p2 - p1) * t_slash
        is_horiz = abs(p2.x() - p1.x()) >= abs(p2.y() - p1.y())

        slash_len = 7.0
        slash_pen = QPen(QColor(30, 30, 30), 1.6)
        painter.setPen(slash_pen)

        slash_text = self.model.width_param if self.model.width_param else str(self.model.width)
        font = QFont("Segoe UI", 9, QFont.Bold)
        painter.setFont(font)
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(slash_text)
        box_w = max(28.0, float(tw + 6))

        if is_horiz:
            painter.drawLine(
                QPointF(mid.x() - slash_len, mid.y() + slash_len),
                QPointF(mid.x() + slash_len, mid.y() - slash_len)
            )
            painter.drawText(
                QRectF(mid.x() - box_w / 2, mid.y() - slash_len - 14, box_w, 14),
                Qt.AlignCenter,
                slash_text
            )
        else:
            painter.drawLine(
                QPointF(mid.x() - slash_len, mid.y() - slash_len),
                QPointF(mid.x() + slash_len, mid.y() + slash_len)
            )
            painter.drawText(
                QRectF(mid.x() + slash_len + 3, mid.y() - 8, box_w, 16),
                Qt.AlignLeft | Qt.AlignVCenter,
                slash_text
            )


class RTLJunctionItem(QGraphicsItem):
    """Solder dot marking explicit connection at crossed wires (ELO212 Figure 3b)"""
    RADIUS = 4.5

    def __init__(self, x: float, y: float, j_id: str = ""):
        super().__init__()
        self.j_id = j_id
        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemIsSelectable |
            QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setPos(snap(x), snap(y))
        self.setZValue(1)
    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(QPointF(0, 0), self.RADIUS + 2.0, self.RADIUS + 2.0)
        return path

    def boundingRect(self) -> QRectF:
        r = self.RADIUS + 3.0
        return QRectF(-r, -r, 2 * r, 2 * r)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.scene():
            new_pos = value
            snapped_x = snap(new_pos.x())
            snapped_y = snap(new_pos.y())
            return QPointF(snapped_x, snapped_y)
        elif change == QGraphicsItem.ItemPositionHasChanged and self.scene():
            if hasattr(self.scene(), "schematic"):
                for j in self.scene().schematic.junctions:
                    if j.id == self.j_id:
                        j.x = self.pos().x()
                        j.y = self.pos().y()
                        break
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        self._press_pos = self.pos()
        if self.scene() and hasattr(self.scene(), "schematic"):
            self._press_snapshot = self.scene().schematic.to_dict()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if hasattr(self, "_press_pos") and self.pos() != self._press_pos:
            if self.scene() and hasattr(self.scene(), "undo_stack") and hasattr(self, "_press_snapshot"):
                self.scene().undo_stack.append(self._press_snapshot)
                if len(self.scene().undo_stack) > self.scene().max_undo:
                    self.scene().undo_stack.pop(0)
                self.scene().redo_stack.clear()
                self.scene().status_message.emit(
                    f"Punto de unión movido a ({int(self.pos().x())}, {int(self.pos().y())}). (Ctrl+Z para deshacer)"
                )

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        if self.isSelected():
            painter.setPen(QPen(QColor(0, 102, 204), 2.0))
            painter.setBrush(QBrush(QColor(0, 102, 204)))
            painter.drawEllipse(QPointF(0, 0), self.RADIUS + 2.0, self.RADIUS + 2.0)
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            painter.drawEllipse(QPointF(0, 0), self.RADIUS * 0.5, self.RADIUS * 0.5)
        else:
            painter.setPen(QPen(QColor(20, 20, 20), 1.0))
            painter.setBrush(QBrush(QColor(20, 20, 20)))
            painter.drawEllipse(QPointF(0, 0), self.RADIUS, self.RADIUS)

