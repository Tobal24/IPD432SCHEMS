"""
RTL Canvas and Scene for ELO212 Schematic Editor.
Features:
- Snap-to-grid (20px)
- Smart Manhattan (orthogonal) wire routing between pins
- Pin-to-pin wiring interaction
- Solder-dot junctions on wire crossings
- Zoom & pan navigation
"""

import math
import uuid
from typing import Optional, List, Tuple
from PySide6.QtCore import Qt, QRectF, QPointF, QLineF, Signal
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QWheelEvent, QKeyEvent
)
from PySide6.QtWidgets import (
    QGraphicsScene, QGraphicsView, QGraphicsItem, QMenu, QInputDialog, QMessageBox
)
from app.core.rtl_model import (
    RTLSchematic, RTLComponent, RTLPin, RTLWire, RTLJunction,
    ComponentFactory, ComponentType, PinSide, PinDirection
)
from app.gui.rtl_items import (
    RTLComponentItem, RTLWireItem, RTLPinItem, RTLJunctionItem, GRID_SIZE, snap
)


def compute_manhattan_path(
    p1: QPointF, side1: PinSide,
    p2: QPointF, side2: PinSide
) -> List[Tuple[float, float]]:
    """
    Computes an orthogonal (Manhattan) path complying strictly with ELO212.
    Endpoints anchor EXACTLY at pin centers (zero offset gap).
    All segments are strictly horizontal or vertical.
    """
    x1, y1 = p1.x(), p1.y()
    x2, y2 = p2.x(), p2.y()

    # Direct line if already horizontally or vertically aligned
    if abs(x1 - x2) < 0.5 or abs(y1 - y2) < 0.5:
        return [(x1, y1), (x2, y2)]

    pts: List[Tuple[float, float]] = [(x1, y1)]

    # Forward flow (standard left-to-right from output to input)
    if x1 < x2 - 15 and side1 == PinSide.RIGHT and side2 == PinSide.LEFT:
        mid_x = (x1 + x2) / 2.0
        snapped_mid = snap(mid_x)
        if x1 + 10 < snapped_mid < x2 - 10:
            mid_x = snapped_mid
        pts.append((mid_x, y1))
        pts.append((mid_x, y2))
        pts.append((x2, y2))
        return pts

    # Control pins (top/bottom)
    if side1 in (PinSide.TOP, PinSide.BOTTOM) and side2 in (PinSide.LEFT, PinSide.RIGHT):
        pts.append((x1, y2))
        pts.append((x2, y2))
        return pts

    if side2 in (PinSide.TOP, PinSide.BOTTOM) and side1 in (PinSide.LEFT, PinSide.RIGHT):
        pts.append((x2, y1))
        pts.append((x2, y2))
        return pts

    # Feedback loop (x2 <= x1): route around components
    if x2 <= x1:
        y_detour = snap(min(y1, y2) - 50.0) if min(y1, y2) > 60 else snap(max(y1, y2) + 60.0)
        x_out = x1 + 25.0 if side1 == PinSide.RIGHT else x1 - 25.0
        x_in = x2 - 25.0 if side2 == PinSide.LEFT else x2 + 25.0

        pts.append((x_out, y1))
        pts.append((x_out, y_detour))
        pts.append((x_in, y_detour))
        pts.append((x_in, y2))
        pts.append((x2, y2))
        return pts

    # Default 2-bend orthogonal routing
    mid_x = (x1 + x2) / 2.0
    pts.append((mid_x, y1))
    pts.append((mid_x, y2))
    pts.append((x2, y2))
    return pts


class RTLGraphicsScene(QGraphicsScene):
    status_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSceneRect(-2000, -2000, 4000, 4000)
        self.schematic = RTLSchematic()

        self.comp_items: dict[str, RTLComponentItem] = {}
        self.wire_items: dict[str, RTLWireItem] = {}
        self.junction_items: dict[str, RTLJunctionItem] = {}

        # Undo / Redo history stacks
        self.undo_stack: List[dict] = []
        self.redo_stack: List[dict] = []
        self.max_undo = 50

        # Wire drawing mode state
        self.wiring_active = False
        self.wire_start_pin: Optional[RTLPinItem] = None
        self.temp_wire_points: List[Tuple[float, float]] = []

    def push_undo_state(self):
        snapshot = self.schematic.to_dict()
        self.undo_stack.append(snapshot)
        if len(self.undo_stack) > self.max_undo:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self):
        if not self.undo_stack:
            self.status_message.emit("No hay más acciones para deshacer.")
            return
        curr_snapshot = self.schematic.to_dict()
        self.redo_stack.append(curr_snapshot)
        prev_snapshot = self.undo_stack.pop()
        self.restore_snapshot(prev_snapshot)
        self.status_message.emit("Deshecho (Ctrl+Z).")

    def redo(self):
        if not self.redo_stack:
            self.status_message.emit("No hay más acciones para rehacer.")
            return
        curr_snapshot = self.schematic.to_dict()
        self.undo_stack.append(curr_snapshot)
        next_snapshot = self.redo_stack.pop()
        self.restore_snapshot(next_snapshot)
        self.status_message.emit("Rehecho (Ctrl+Y).")

    def restore_snapshot(self, snapshot: dict):
        self.clear()
        self.schematic = RTLSchematic.from_dict(snapshot)
        self.comp_items.clear()
        self.wire_items.clear()
        self.junction_items.clear()

        for c in self.schematic.components:
            item = RTLComponentItem(c)
            self.addItem(item)
            self.comp_items[c.id] = item

        for w in self.schematic.wires:
            item = RTLWireItem(w)
            self.addItem(item)
            self.wire_items[w.id] = item

        for j in self.schematic.junctions:
            item = RTLJunctionItem(j.x, j.y, j.id)
            self.addItem(item)
            self.junction_items[j.id] = item

    def drawBackground(self, painter: QPainter, rect: QRectF):
        super().drawBackground(painter, rect)
        # Clean dotted engineering grid
        painter.setPen(QPen(QColor(220, 225, 230), 1))
        grid = int(GRID_SIZE)

        left = int(math.floor(rect.left() / grid) * grid)
        top = int(math.floor(rect.top() / grid) * grid)
        right = int(math.ceil(rect.right() / grid) * grid)
        bottom = int(math.ceil(rect.bottom() / grid) * grid)

        for x in range(left, right, grid):
            for y in range(top, bottom, grid):
                painter.drawPoint(x, y)

    def add_component(self, comp: RTLComponent) -> RTLComponentItem:
        self.push_undo_state()
        self.schematic.add_component(comp)
        item = RTLComponentItem(comp)
        self.addItem(item)
        self.comp_items[comp.id] = item
        return item

    def remove_selected(self):
        sel = self.selectedItems()
        if not sel:
            return
        self.push_undo_state()
        for item in sel:
            if isinstance(item, RTLComponentItem):
                comp_id = item.model.id
                # Remove connected wires
                to_remove_w = [
                    w_id for w_id, w in self.wire_items.items()
                    if w.model.source_comp_id == comp_id or w.model.target_comp_id == comp_id
                ]
                for w_id in to_remove_w:
                    self.remove_wire(w_id)

                self.removeItem(item)
                del self.comp_items[comp_id]
                self.schematic.components = [c for c in self.schematic.components if c.id != comp_id]

            elif isinstance(item, RTLWireItem):
                self.remove_wire(item.model.id)
            elif isinstance(item, RTLJunctionItem):
                self.removeItem(item)
                if item.j_id in self.junction_items:
                    del self.junction_items[item.j_id]
                self.schematic.junctions = [j for j in self.schematic.junctions if j.id != item.j_id]

    def remove_wire(self, wire_id: str):
        if wire_id in self.wire_items:
            item = self.wire_items[wire_id]
            self.removeItem(item)
            del self.wire_items[wire_id]
            self.schematic.wires = [w for w in self.schematic.wires if w.id != wire_id]

    def on_component_moved(self, comp_item: RTLComponentItem):
        # Update wires connected to this component
        comp_id = comp_item.model.id
        for w_item in self.wire_items.values():
            w = w_item.model
            if w.source_comp_id == comp_id or w.target_comp_id == comp_id:
                self.recompute_wire_path(w_item)
        self.update()

    def recompute_wire_path(self, w_item: RTLWireItem):
        w = w_item.model
        s_comp = self.comp_items.get(w.source_comp_id)
        t_comp = self.comp_items.get(w.target_comp_id)

        if not s_comp or not t_comp:
            return

        s_pin_item = next((pi for pi in s_comp.pin_items if pi.pin.id == w.source_pin_id), None)
        t_pin_item = next((pi for pi in t_comp.pin_items if pi.pin.id == w.target_pin_id), None)

        if not s_pin_item or not t_pin_item:
            return

        p1 = s_pin_item.scenePos()
        p2 = t_pin_item.scenePos()

        if w.manual_routing and len(w.points) >= 4:
            new_pts = [list(pt) for pt in w.points]
            new_pts[0] = [p1.x(), p1.y()]
            new_pts[-1] = [p2.x(), p2.y()]
            # Orthogonalize connection to p1
            if abs(new_pts[1][0] - new_pts[0][0]) < abs(new_pts[1][1] - new_pts[0][1]):
                new_pts[1][0] = p1.x()
            else:
                new_pts[1][1] = p1.y()
            # Orthogonalize connection to p2
            if abs(new_pts[-1][0] - new_pts[-2][0]) < abs(new_pts[-1][1] - new_pts[-2][1]):
                new_pts[-2][0] = p2.x()
            else:
                new_pts[-2][1] = p2.y()
            path_pts = [(p[0], p[1]) for p in new_pts]
        else:
            path_pts = compute_manhattan_path(p1, s_pin_item.pin.side, p2, t_pin_item.pin.side)

        w_item.prepareGeometryChange()
        w.points = path_pts
        w_item.update()
        if w_item.label_item and w.label_pos is None:
            w_item.label_item.update_position()
        if w_item.isSelected():
            w_item.update_handles()

    def reset_selected_wire_routing(self):
        sel = self.selectedItems()
        target_wires = []
        for item in sel:
            if isinstance(item, RTLWireItem):
                target_wires.append(item)
            elif hasattr(item, "wire_item"):
                target_wires.append(item.wire_item)

        if not target_wires:
            self.status_message.emit("Seleccione al menos un cable para re-enrutar automáticamente.")
            return

        self.push_undo_state()
        for w_item in set(target_wires):
            w_item.reset_routing()
        self.status_message.emit("Ruteo automático restablecido (R).")

    def reset_selected_labels(self):
        sel = self.selectedItems()
        target_wires = []
        for item in sel:
            if isinstance(item, RTLWireItem):
                target_wires.append(item)
            elif hasattr(item, "wire_item"):
                target_wires.append(item.wire_item)

        if not target_wires:
            target_wires = list(self.wire_items.values())

        self.push_undo_state()
        for w_item in set(target_wires):
            w_item.reset_label_pos()
        self.status_message.emit("Posición de etiquetas de cable restablecida (Shift+R).")

    def start_wiring(self, pin_item: RTLPinItem):
        self.wiring_active = True
        self.wire_start_pin = pin_item
        start_pt = pin_item.scenePos()
        self.status_message.emit(f"Cableando desde pin '{pin_item.pin.name}'. Haga clic en el pin de destino.")

    def finish_wiring(self, end_pin_item: RTLPinItem):
        if not self.wire_start_pin or self.wire_start_pin == end_pin_item:
            self.cancel_wiring()
            return

        p1_item = self.wire_start_pin
        p2_item = end_pin_item

        # Validate: Don't connect OUT to OUT, or IN to IN
        if p1_item.pin.direction == PinDirection.OUT and p2_item.pin.direction == PinDirection.OUT:
            self.status_message.emit("Aviso: No se recomienda conectar dos salidas entre sí.")
        elif p1_item.pin.direction == PinDirection.IN and p2_item.pin.direction == PinDirection.IN:
            self.status_message.emit("Aviso: Conectando dos entradas sin fuente definida.")

        p1 = p1_item.scenePos()
        p2 = p2_item.scenePos()
        pts = compute_manhattan_path(p1, p1_item.pin.side, p2, p2_item.pin.side)

        # Inherit bus width if either pin has width > 1
        width = max(p1_item.pin.width, p2_item.pin.width)

        self.push_undo_state()
        wire_model = RTLWire(
            id=f"wire_{uuid.uuid4().hex[:6]}",
            source_comp_id=p1_item.parent_comp.model.id,
            source_pin_id=p1_item.pin.id,
            target_comp_id=p2_item.parent_comp.model.id,
            target_pin_id=p2_item.pin.id,
            points=pts,
            width=width
        )

        self.schematic.wires.append(wire_model)
        w_item = RTLWireItem(wire_model)
        self.addItem(w_item)
        self.wire_items[wire_model.id] = w_item

        self.cancel_wiring()
        self.status_message.emit(f"Cable conectado (ancho: {width} bit{'s' if width > 1 else ''}).")

    def cancel_wiring(self):
        self.wiring_active = False
        self.wire_start_pin = None
        self.status_message.emit("Listo.")

    def add_junction_at(self, pos: QPointF):
        self.push_undo_state()
        snapped_pos = QPointF(snap(pos.x()), snap(pos.y()))
        j_id = f"junc_{uuid.uuid4().hex[:6]}"
        junc = RTLJunction(id=j_id, x=snapped_pos.x(), y=snapped_pos.y())
        self.schematic.junctions.append(junc)
        item = RTLJunctionItem(snapped_pos.x(), snapped_pos.y(), j_id)
        self.addItem(item)
        self.junction_items[j_id] = item
        self.status_message.emit(f"Punto de unión (solder dot) colocado en ({int(snapped_pos.x())}, {int(snapped_pos.y())}).")

    def mousePressEvent(self, event):
        item = self.itemAt(event.scenePos(), self.views()[0].transform()) if self.views() else None

        if event.button() == Qt.LeftButton:
            if isinstance(item, RTLPinItem):
                if not self.wiring_active:
                    self.start_wiring(item)
                    return
                else:
                    self.finish_wiring(item)
                    return
            elif self.wiring_active:
                # Cancel if clicked on empty space
                self.cancel_wiring()
                return

        elif event.button() == Qt.RightButton:
            if self.wiring_active:
                self.cancel_wiring()
                return

        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.modifiers() & Qt.ControlModifier:
            if event.key() == Qt.Key_Z:
                if event.modifiers() & Qt.ShiftModifier:
                    self.redo()
                else:
                    self.undo()
                event.accept()
                return
            elif event.key() == Qt.Key_Y:
                self.redo()
                event.accept()
                return

        if event.key() == Qt.Key_R:
            if event.modifiers() & Qt.ShiftModifier:
                self.reset_selected_labels()
            else:
                self.reset_selected_wire_routing()
            event.accept()
            return

        if event.key() == Qt.Key_Delete or event.key() == Qt.Key_Backspace:
            self.remove_selected()
            event.accept()
        elif event.key() == Qt.Key_Escape:
            if self.wiring_active:
                self.cancel_wiring()
            event.accept()
        else:
            super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        item = self.itemAt(event.scenePos(), self.views()[0].transform()) if self.views() else None
        target_wire = None
        if isinstance(item, RTLWireItem):
            target_wire = item
        elif hasattr(item, "wire_item"):
            target_wire = item.wire_item

        if target_wire:
            menu = QMenu()
            act_reroute = menu.addAction("🔄 Restablecer Ruteo Automático (R)")
            act_relabel = menu.addAction("🏷️ Restablecer Posición de Etiqueta (Shift+R)")
            act_arrow = menu.addAction("➡️ Alternar Flecha de Dirección")
            act_arrow.setCheckable(True)
            act_arrow.setChecked(target_wire.model.show_arrow)
            menu.addSeparator()
            act_del = menu.addAction("🗑️ Eliminar Cable (Supr)")
            action = menu.exec(event.screenPos())
            if action == act_reroute:
                self.push_undo_state()
                target_wire.reset_routing()
            elif action == act_relabel:
                self.push_undo_state()
                target_wire.reset_label_pos()
            elif action == act_arrow:
                self.push_undo_state()
                target_wire.model.show_arrow = not target_wire.model.show_arrow
                target_wire.prepareGeometryChange()
                target_wire.update()
                self.status_message.emit("Flecha de dirección actualizada. (Ctrl+Z para deshacer)")
            elif action == act_del:
                self.remove_wire(target_wire.model.id)
            event.accept()
            return

        if isinstance(item, RTLComponentItem):
            menu = QMenu()
            act_edit = None
            if item.model.type == ComponentType.BLOCK:
                act_edit = menu.addAction("⚙️ Configurar Bloque (Puertos y Tamaño)...")
            elif item.model.type == ComponentType.MUX:
                act_edit = menu.addAction("⚙️ Configurar Multiplexor (MUX)...")
            elif item.model.type == ComponentType.BUS_SPLITTER:
                act_edit = menu.addAction("⚙️ Configurar Desagregador de Bus...")

            if act_edit:
                menu.addSeparator()
            act_del = menu.addAction("🗑️ Eliminar Componente (Supr)")
            action = menu.exec(event.screenPos())
            if act_edit and action == act_edit:
                item.mouseDoubleClickEvent(None)
            elif action == act_del:
                self.remove_selected()
            event.accept()
            return

        super().contextMenuEvent(event)


class RTLGraphicsView(QGraphicsView):
    """View with mouse-wheel zoom and smooth panning"""

    def __init__(self, scene: RTLGraphicsScene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self._zoom_factor = 1.15

    def wheelEvent(self, event: QWheelEvent):
        if event.angleDelta().y() > 0:
            self.scale(self._zoom_factor, self._zoom_factor)
        else:
            self.scale(1 / self._zoom_factor, 1 / self._zoom_factor)
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            fake_event = event
            # simulate left click for drag
            super().mousePressEvent(event)
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self.setDragMode(QGraphicsView.RubberBandDrag)
            return
        super().mouseReleaseEvent(event)
