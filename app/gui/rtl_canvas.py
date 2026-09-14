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


def _clean_path(pts: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    if len(pts) <= 2:
        return pts
    # Deduplicate adjacent identical points
    cleaned = [pts[0]]
    for p in pts[1:]:
        if abs(p[0] - cleaned[-1][0]) > 0.1 or abs(p[1] - cleaned[-1][1]) > 0.1:
            cleaned.append((round(p[0], 2), round(p[1], 2)))
    if len(cleaned) <= 2:
        return cleaned
    # Collapse collinear segments
    res = [cleaned[0]]
    for i in range(1, len(cleaned) - 1):
        prev_p = res[-1]
        curr_p = cleaned[i]
        next_p = cleaned[i + 1]
        is_horiz = abs(prev_p[1] - curr_p[1]) < 0.1 and abs(curr_p[1] - next_p[1]) < 0.1
        is_vert = abs(prev_p[0] - curr_p[0]) < 0.1 and abs(curr_p[0] - next_p[0]) < 0.1
        if not (is_horiz or is_vert):
            res.append(curr_p)
    res.append(cleaned[-1])
    return res


def compute_manhattan_path(
    p1: QPointF, side1: PinSide,
    p2: QPointF, side2: PinSide
) -> List[Tuple[float, float]]:
    """
    Computes an orthogonal (Manhattan) path complying strictly with ELO212.
    Endpoints anchor EXACTLY at pin centers (zero offset gap).
    Respects pin normal directions so wires NEVER route through or behind components.
    All segments are strictly horizontal or vertical.
    """
    x1, y1 = p1.x(), p1.y()
    x2, y2 = p2.x(), p2.y()

    # Direct line if already horizontally or vertically aligned AND matches outward pin normals
    if abs(y1 - y2) < 0.5:
        if x1 < x2 and side1 != PinSide.LEFT and side2 != PinSide.RIGHT:
            return [(x1, y1), (x2, y2)]
        if x1 > x2 and side1 != PinSide.RIGHT and side2 != PinSide.LEFT:
            return [(x1, y1), (x2, y2)]

    if abs(x1 - x2) < 0.5:
        if y1 < y2 and side1 != PinSide.TOP and side2 != PinSide.BOTTOM:
            return [(x1, y1), (x2, y2)]
        if y1 > y2 and side1 != PinSide.BOTTOM and side2 != PinSide.TOP:
            return [(x1, y1), (x2, y2)]

    pts: List[Tuple[float, float]] = [(x1, y1)]

    # --- Group 1: side1 == RIGHT ---
    if side1 == PinSide.RIGHT:
        if side2 == PinSide.LEFT:
            if x1 < x2 - 15:
                mid_x = (x1 + x2) / 2.0
                snapped_mid = snap(mid_x)
                if x1 + 10 < snapped_mid < x2 - 10:
                    mid_x = snapped_mid
                pts.append((mid_x, y1))
                pts.append((mid_x, y2))
            else:
                y_detour = snap(min(y1, y2) - 50.0) if min(y1, y2) > 60 else snap(max(y1, y2) + 60.0)
                x_out = snap(x1 + 25.0)
                x_in = snap(x2 - 25.0)
                pts.extend([(x_out, y1), (x_out, y_detour), (x_in, y_detour), (x_in, y2)])
        elif side2 == PinSide.RIGHT:
            x_turn = snap(max(x1, x2) + 25.0)
            if x1 < x2:
                y_detour = snap(min(y1, y2) - 30.0) if min(y1, y2) > 60 else snap(max(y1, y2) + 30.0)
                mid_x = snap((x1 + x2 - 40.0) / 2.0) if x1 < x2 - 40 else snap(x1 + 20.0)
                pts.extend([(mid_x, y1), (mid_x, y_detour), (x_turn, y_detour), (x_turn, y2)])
            else:
                pts.extend([(x_turn, y1), (x_turn, y2)])
        elif side2 == PinSide.TOP:
            if x1 < x2 and y1 < y2:
                pts.append((x2, y1))
            elif x1 < x2:
                y_above = snap(y2 - 20.0)
                mid_x = snap((x1 + x2) / 2.0)
                if mid_x >= x2 - 10:
                    mid_x = snap(x1 + 20.0)
                pts.extend([(mid_x, y1), (mid_x, y_above), (x2, y_above)])
            else:
                x_out = snap(x1 + 20.0)
                y_above = snap(min(y1, y2) - 30.0)
                pts.extend([(x_out, y1), (x_out, y_above), (x2, y_above)])
        elif side2 == PinSide.BOTTOM:
            if x1 < x2 and y1 > y2:
                pts.append((x2, y1))
            elif x1 < x2:
                y_below = snap(y2 + 20.0)
                mid_x = snap((x1 + x2) / 2.0)
                if mid_x >= x2 - 10:
                    mid_x = snap(x1 + 20.0)
                pts.extend([(mid_x, y1), (mid_x, y_below), (x2, y_below)])
            else:
                x_out = snap(x1 + 20.0)
                y_below = snap(max(y1, y2) + 30.0)
                pts.extend([(x_out, y1), (x_out, y_below), (x2, y_below)])

    # --- Group 2: side1 == LEFT ---
    elif side1 == PinSide.LEFT:
        if side2 == PinSide.RIGHT:
            if x1 > x2 + 15:
                mid_x = (x1 + x2) / 2.0
                snapped_mid = snap(mid_x)
                if x2 + 10 < snapped_mid < x1 - 10:
                    mid_x = snapped_mid
                pts.append((mid_x, y1))
                pts.append((mid_x, y2))
            else:
                y_detour = snap(min(y1, y2) - 50.0) if min(y1, y2) > 60 else snap(max(y1, y2) + 60.0)
                x_out = snap(x1 - 25.0)
                x_in = snap(x2 + 25.0)
                pts.extend([(x_out, y1), (x_out, y_detour), (x_in, y_detour), (x_in, y2)])
        elif side2 == PinSide.LEFT:
            x_turn = snap(min(x1, x2) - 25.0)
            if x1 > x2:
                y_detour = snap(min(y1, y2) - 30.0) if min(y1, y2) > 60 else snap(max(y1, y2) + 30.0)
                mid_x = snap((x1 + x2 + 40.0) / 2.0) if x1 > x2 + 40 else snap(x1 - 20.0)
                pts.extend([(mid_x, y1), (mid_x, y_detour), (x_turn, y_detour), (x_turn, y2)])
            else:
                pts.extend([(x_turn, y1), (x_turn, y2)])
        elif side2 == PinSide.TOP:
            if x1 > x2 and y1 < y2:
                pts.append((x2, y1))
            elif x1 > x2:
                y_above = snap(y2 - 20.0)
                mid_x = snap((x1 + x2) / 2.0)
                if mid_x <= x2 + 10:
                    mid_x = snap(x1 - 20.0)
                pts.extend([(mid_x, y1), (mid_x, y_above), (x2, y_above)])
            else:
                x_out = snap(x1 - 20.0)
                y_above = snap(min(y1, y2) - 30.0)
                pts.extend([(x_out, y1), (x_out, y_above), (x2, y_above)])
        elif side2 == PinSide.BOTTOM:
            if x1 > x2 and y1 > y2:
                pts.append((x2, y1))
            elif x1 > x2:
                y_below = snap(y2 + 20.0)
                mid_x = snap((x1 + x2) / 2.0)
                if mid_x <= x2 + 10:
                    mid_x = snap(x1 - 20.0)
                pts.extend([(mid_x, y1), (mid_x, y_below), (x2, y_below)])
            else:
                x_out = snap(x1 - 20.0)
                y_below = snap(max(y1, y2) + 30.0)
                pts.extend([(x_out, y1), (x_out, y_below), (x2, y_below)])

    # --- Group 3: side1 == TOP ---
    elif side1 == PinSide.TOP:
        if side2 == PinSide.LEFT:
            if y1 > y2 and x1 < x2:
                pts.append((x1, y2))
            elif x1 < x2:
                y_up = snap(y1 - 20.0)
                mid_x = snap((x1 + x2) / 2.0)
                pts.extend([(x1, y_up), (mid_x, y_up), (mid_x, y2)])
            else:
                y_up = snap(min(y1, y2) - 25.0)
                x_in = snap(x2 - 25.0)
                pts.extend([(x1, y_up), (x_in, y_up), (x_in, y2)])
        elif side2 == PinSide.RIGHT:
            if y1 > y2 and x1 > x2:
                pts.append((x1, y2))
            elif x1 > x2:
                y_up = snap(y1 - 20.0)
                mid_x = snap((x1 + x2) / 2.0)
                pts.extend([(x1, y_up), (mid_x, y_up), (mid_x, y2)])
            else:
                y_up = snap(min(y1, y2) - 25.0)
                x_in = snap(x2 + 25.0)
                pts.extend([(x1, y_up), (x_in, y_up), (x_in, y2)])
        elif side2 == PinSide.TOP:
            y_turn = snap(min(y1, y2) - 25.0)
            pts.extend([(x1, y_turn), (x2, y_turn)])
        elif side2 == PinSide.BOTTOM:
            y_up = snap(y1 - 25.0)
            y_down = snap(y2 + 25.0)
            x_mid = snap((x1 + x2) / 2.0)
            pts.extend([(x1, y_up), (x_mid, y_up), (x_mid, y_down), (x2, y_down)])

    # --- Group 4: side1 == BOTTOM ---
    elif side1 == PinSide.BOTTOM:
        if side2 == PinSide.LEFT:
            if y1 < y2 and x1 < x2:
                pts.append((x1, y2))
            elif x1 < x2:
                y_down = snap(y1 + 20.0)
                mid_x = snap((x1 + x2) / 2.0)
                pts.extend([(x1, y_down), (mid_x, y_down), (mid_x, y2)])
            else:
                y_down = snap(max(y1, y2) + 25.0)
                x_in = snap(x2 - 25.0)
                pts.extend([(x1, y_down), (x_in, y_down), (x_in, y2)])
        elif side2 == PinSide.RIGHT:
            if y1 < y2 and x1 > x2:
                pts.append((x1, y2))
            elif x1 > x2:
                y_down = snap(y1 + 20.0)
                mid_x = snap((x1 + x2) / 2.0)
                pts.extend([(x1, y_down), (mid_x, y_down), (mid_x, y2)])
            else:
                y_down = snap(max(y1, y2) + 25.0)
                x_in = snap(x2 + 25.0)
                pts.extend([(x1, y_down), (x_in, y_down), (x_in, y2)])
        elif side2 == PinSide.BOTTOM:
            y_turn = snap(max(y1, y2) + 25.0)
            pts.extend([(x1, y_turn), (x2, y_turn)])
        elif side2 == PinSide.TOP:
            if y1 < y2 - 15:
                mid_y = snap((y1 + y2) / 2.0)
                pts.extend([(x1, mid_y), (x2, mid_y)])
            else:
                y_down = snap(y1 + 25.0)
                y_up = snap(y2 - 25.0)
                x_mid = snap((x1 + x2) / 2.0)
                pts.extend([(x1, y_down), (x_mid, y_down), (x_mid, y_up), (x2, y_up)])

    pts.append((x2, y2))
    return _clean_path(pts)


class RTLGraphicsScene(QGraphicsScene):
    status_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSceneRect(-2000, -2000, 4000, 4000)
        self.setItemIndexMethod(QGraphicsScene.NoIndex)
        self.schematic = RTLSchematic()

        self.comp_items: dict[str, RTLComponentItem] = {}
        self.wire_items: dict[str, RTLWireItem] = {}
        self.junction_items: dict[str, RTLJunctionItem] = {}

        # Undo / Redo history stacks
        self.undo_stack: List[dict] = []
        self.redo_stack: List[dict] = []
        self.max_undo = 50

        # Clipboard for Copy / Paste
        self._clipboard: Optional[dict] = None
        self._paste_count: int = 1

        # Wire drawing mode state
        self.wiring_active = False
        self.wire_start_pin: Optional[RTLPinItem] = None
        self.temp_wire_points: List[Tuple[float, float]] = []
        self.temp_wire_pos: Optional[QPointF] = None

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

    def reflect_selected_components(self):
        selected_comps = [item for item in self.selectedItems() if isinstance(item, RTLComponentItem)]
        if not selected_comps:
            self.status_message.emit("Seleccione uno o más bloques para reflejar (Ctrl+E).")
            return

        self.push_undo_state()
        for comp_item in selected_comps:
            comp = comp_item.model
            comp.mirrored = not getattr(comp, "mirrored", False)
            for pin in comp.pins:
                if pin.side == PinSide.LEFT:
                    pin.side = PinSide.RIGHT
                elif pin.side == PinSide.RIGHT:
                    pin.side = PinSide.LEFT
                elif pin.side in (PinSide.TOP, PinSide.BOTTOM):
                    pin.offset = round(1.0 - pin.offset, 4)
            comp_item.rebuild_pins()
            self.on_component_moved(comp_item)
            comp_item.update()

        self.status_message.emit("Bloque(s) reflejado(s) horizontalmente. (Ctrl+Z para deshacer)")

    @staticmethod
    def apply_operator_rotation(comp: RTLComponent, rot: int):
        rot = rot % 360
        is_unary = comp.properties.get("is_unary") == "True" or comp.properties.get("is_reduction") == "True"
        if rot == 90:
            in_side, out_side = PinSide.TOP, PinSide.BOTTOM
        elif rot == 180:
            in_side, out_side = PinSide.RIGHT, PinSide.LEFT
        elif rot == 270:
            in_side, out_side = PinSide.BOTTOM, PinSide.TOP
        else: # 0
            in_side, out_side = PinSide.LEFT, PinSide.RIGHT

        for pin in comp.pins:
            if pin.direction == PinDirection.OUT:
                pin.side = out_side
                pin.offset = 0.5
            else:
                pin.side = in_side
                if is_unary:
                    pin.offset = 0.5
                else:
                    pin.offset = 0.25 if pin.name == "A" or pin.id.endswith("_a") else 0.75

    def rotate_selected_operators(self):
        selected_ops = [
            item for item in self.selectedItems()
            if isinstance(item, RTLComponentItem) and item.model.type == ComponentType.OPERATOR_CIRCLE
        ]
        if not selected_ops:
            self.status_message.emit("Seleccione al menos un operador circular para rotar (Ctrl+R).")
            return

        self.push_undo_state()
        for op_item in selected_ops:
            comp = op_item.model
            cur_rot = int(comp.properties.get("rotation", "0"))
            new_rot = (cur_rot + 90) % 360
            comp.properties["rotation"] = str(new_rot)
            self.apply_operator_rotation(comp, new_rot)
            op_item.rebuild_pins()
            for w_item in self.wire_items.values():
                w = w_item.model
                if w.source_comp_id == comp.id or w.target_comp_id == comp.id:
                    w.manual_routing = False
            self.on_component_moved(op_item)
            op_item.update()

        self.status_message.emit("Operador(es) rotado(s) 90°. (Ctrl+Z para deshacer)")

    def copy_selected(self):
        sel = self.selectedItems()
        selected_comps = [item.model for item in sel if isinstance(item, RTLComponentItem)]
        selected_comp_ids = {c.id for c in selected_comps}

        # Collect internal wires connecting two selected components or explicitly selected wires
        selected_wires = []
        for w_id, w_item in self.wire_items.items():
            w = w_item.model
            if (w.source_comp_id in selected_comp_ids and w.target_comp_id in selected_comp_ids) or (w_item.isSelected() and w.source_comp_id in selected_comp_ids and w.target_comp_id in selected_comp_ids):
                selected_wires.append(w)

        selected_junctions = [
            next((j for j in self.schematic.junctions if j.id == item.j_id), None)
            for item in sel if isinstance(item, RTLJunctionItem)
        ]
        selected_junctions = [j for j in selected_junctions if j is not None]

        if not selected_comps and not selected_wires and not selected_junctions:
            self.status_message.emit("No hay elementos seleccionados para copiar (Ctrl+C).")
            return

        self._clipboard = {
            "components": [c.to_dict() for c in selected_comps],
            "wires": [w.to_dict() for w in selected_wires],
            "junctions": [j.to_dict() for j in selected_junctions]
        }
        self._paste_count = 1
        total_items = len(selected_comps) + len(selected_wires) + len(selected_junctions)
        self.status_message.emit(f"Copiado(s) {total_items} elemento(s) al portapapeles (Ctrl+C).")

    def paste(self):
        if not self._clipboard or not (
            self._clipboard.get("components") or
            self._clipboard.get("wires") or
            self._clipboard.get("junctions")
        ):
            self.status_message.emit("Portapapeles vacío. Copie elementos primero con Ctrl+C.")
            return

        self.push_undo_state()
        self.clearSelection()

        delta = float(self._paste_count * 20)
        self._paste_count += 1

        comp_id_map = {}
        pin_id_map = {}
        new_items = []

        # 1. Duplicate components
        for c_data in self._clipboard.get("components", []):
            old_id = c_data["id"]
            new_id = f"{c_data.get('type', 'comp').lower()}_{uuid.uuid4().hex[:6]}"
            comp_id_map[old_id] = new_id

            c_copy = RTLComponent.from_dict(c_data)
            c_copy.id = new_id
            c_copy.x = snap(c_copy.x + delta)
            c_copy.y = snap(c_copy.y + delta)

            # Re-generate pin IDs
            for idx, pin in enumerate(c_copy.pins):
                old_pid = pin.id
                new_pid = f"{new_id}_{pin.name}_{idx}"
                pin_id_map[old_pid] = new_pid
                pin.id = new_pid

            self.schematic.add_component(c_copy)
            item = RTLComponentItem(c_copy)
            self.addItem(item)
            self.comp_items[new_id] = item
            item.setSelected(True)
            new_items.append(item)

        # 2. Duplicate wires connecting copied components
        for w_data in self._clipboard.get("wires", []):
            s_cid = w_data.get("source_comp_id")
            t_cid = w_data.get("target_comp_id")
            s_pid = w_data.get("source_pin_id")
            t_pid = w_data.get("target_pin_id")

            if s_cid in comp_id_map and t_cid in comp_id_map:
                w_copy = RTLWire.from_dict(w_data)
                w_copy.id = f"wire_{uuid.uuid4().hex[:6]}"
                w_copy.source_comp_id = comp_id_map[s_cid]
                w_copy.target_comp_id = comp_id_map[t_cid]
                w_copy.source_pin_id = pin_id_map.get(s_pid, s_pid)
                w_copy.target_pin_id = pin_id_map.get(t_pid, t_pid)
                w_copy.points = [(snap(pt[0] + delta), snap(pt[1] + delta)) for pt in w_copy.points]
                if w_copy.label_pos:
                    w_copy.label_pos = (snap(w_copy.label_pos[0] + delta), snap(w_copy.label_pos[1] + delta))

                self.schematic.wires.append(w_copy)
                w_item = RTLWireItem(w_copy)
                self.addItem(w_item)
                self.wire_items[w_copy.id] = w_item
                w_item.setSelected(True)
                new_items.append(w_item)

        # 3. Duplicate junctions
        for j_data in self._clipboard.get("junctions", []):
            j_copy = RTLJunction.from_dict(j_data)
            j_copy.id = f"junc_{uuid.uuid4().hex[:6]}"
            j_copy.x = snap(j_copy.x + delta)
            j_copy.y = snap(j_copy.y + delta)
            self.schematic.junctions.append(j_copy)
            j_item = RTLJunctionItem(j_copy.x, j_copy.y, j_copy.id)
            self.addItem(j_item)
            self.junction_items[j_copy.id] = j_item
            j_item.setSelected(True)
            new_items.append(j_item)

        self.status_message.emit(f"Pegado(s) {len(new_items)} elemento(s) (Ctrl+V). (Ctrl+Z para deshacer)")

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
        self.temp_wire_pos = None
        self.update()
        self.status_message.emit("Listo.")

    def mouseMoveEvent(self, event):
        if self.wiring_active and self.wire_start_pin:
            self.temp_wire_pos = event.scenePos()
            self.update()
        super().mouseMoveEvent(event)

    def drawForeground(self, painter: QPainter, rect: QRectF):
        super().drawForeground(painter, rect)
        if self.wiring_active and self.wire_start_pin and getattr(self, "temp_wire_pos", None):
            p1 = self.wire_start_pin.scenePos()
            p2 = self.temp_wire_pos
            pts = compute_manhattan_path(p1, self.wire_start_pin.pin.side, p2, PinSide.LEFT)
            pen = QPen(QColor(0, 102, 204), 1.8, Qt.DashLine)
            painter.setPen(pen)
            for i in range(len(pts) - 1):
                painter.drawLine(QPointF(pts[i][0], pts[i][1]), QPointF(pts[i+1][0], pts[i+1][1]))

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
                self.cancel_wiring()
                super().mousePressEvent(event)
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
            elif event.key() == Qt.Key_E:
                self.reflect_selected_components()
                event.accept()
                return
            elif event.key() == Qt.Key_C:
                self.copy_selected()
                event.accept()
                return
            elif event.key() == Qt.Key_V:
                self.paste()
                event.accept()
                return
            elif event.key() == Qt.Key_R:
                self.rotate_selected_operators()
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
            act_width = menu.addAction("📏 Definir Ancho de Bus (Bits)...")
            act_reroute = menu.addAction("🔄 Restablecer Ruteo Automático (R)")
            act_relabel = menu.addAction("🏷️ Restablecer Posición de Etiqueta (Shift+R)")
            act_arrow = menu.addAction("➡️ Alternar Flecha de Dirección")
            act_arrow.setCheckable(True)
            act_arrow.setChecked(target_wire.model.show_arrow)
            menu.addSeparator()
            act_del = menu.addAction("🗑️ Eliminar Cable (Supr)")
            action = menu.exec(event.screenPos())
            if action == act_width:
                val, ok = QInputDialog.getInt(
                    None, "Ancho de Bus",
                    "Número de bits (1 = cable simple, >1 = bus con /N):",
                    target_wire.model.width, 1, 512, 1
                )
                if ok:
                    self.push_undo_state()
                    target_wire.model.width = val
                    target_wire._sync_label_item()
                    target_wire.prepareGeometryChange()
                    target_wire.update()
                    self.status_message.emit(f"Ancho del cable actualizado a {val} bit{'s' if val > 1 else ''}.")
            elif action == act_reroute:
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
            act_rotate = None
            act_resize_op = None
            act_resize_mux = None
            if item.model.type == ComponentType.BLOCK:
                act_edit = menu.addAction("⚙️ Configurar Bloque (Puertos y Tamaño)...")
            elif item.model.type == ComponentType.MUX:
                act_edit = menu.addAction("⚙️ Configurar Multiplexor (MUX)...")
                act_resize_mux = menu.addAction("📐 Cambiar Dimensiones del MUX...")
            elif item.model.type == ComponentType.BUS_SPLITTER:
                act_edit = menu.addAction("⚙️ Configurar Desagregador de Bus...")
            elif item.model.type == ComponentType.OPERATOR_CIRCLE:
                act_edit = menu.addAction("⚙️ Configurar Operador...")
                act_rotate = menu.addAction("🔄 Rotar Operador 90° (Ctrl+R)")
                act_resize_op = menu.addAction("📐 Cambiar Diámetro del Operador...")
            elif item.model.type in (ComponentType.INPUT_PORT, ComponentType.OUTPUT_PORT):
                act_edit = menu.addAction("⚙️ Configurar Puerto...")

            act_mirror = menu.addAction("🪞 Reflejar Bloque Horizontalmente (Ctrl+E)")
            act_copy = menu.addAction("📋 Copiar Componente (Ctrl+C)")
            act_paste = menu.addAction("📥 Pegar (Ctrl+V)")
            act_paste.setEnabled(bool(self._clipboard))
            menu.addSeparator()
            act_del = menu.addAction("🗑️ Eliminar Componente (Supr)")
            action = menu.exec(event.screenPos())
            if act_edit and action == act_edit:
                item.mouseDoubleClickEvent(None)
            elif act_rotate and action == act_rotate:
                if not item.isSelected():
                    self.clearSelection()
                    item.setSelected(True)
                self.rotate_selected_operators()
            elif act_resize_op and action == act_resize_op:
                val, ok = QInputDialog.getInt(
                    None, "Diámetro del Operador",
                    "Diámetro en píxeles (40 - 120 px):",
                    int(item.model.width), 40, 120, 10
                )
                if ok:
                    self.push_undo_state()
                    item.prepareGeometryChange()
                    item.model.width = float(val)
                    item.model.height = float(val)
                    item.rebuild_pins()
                    self.on_component_moved(item)
                    item.update()
                    self.status_message.emit(f"Diámetro del operador actualizado a {val} px.")
            elif act_resize_mux and action == act_resize_mux:
                w_val, ok_w = QInputDialog.getInt(
                    None, "Dimensiones del MUX",
                    "Ancho en píxeles (30 - 200 px):",
                    int(item.model.width), 30, 200, 5
                )
                if ok_w:
                    num_in = len([p for p in item.model.pins if p.direction == PinDirection.IN])
                    min_h = max(40, num_in * 15)
                    h_val, ok_h = QInputDialog.getInt(
                        None, "Dimensiones del MUX",
                        f"Largo / Alto en píxeles ({min_h} - 400 px):",
                        int(item.model.height), min_h, 400, 10
                    )
                    if ok_h:
                        self.push_undo_state()
                        item.prepareGeometryChange()
                        item.model.width = float(w_val)
                        item.model.height = float(h_val)
                        item.rebuild_pins()
                        self.on_component_moved(item)
                        item.update()
                        self.status_message.emit(f"Dimensiones del MUX actualizadas a {w_val}x{h_val} px.")
            elif action == act_mirror:
                if not item.isSelected():
                    self.clearSelection()
                    item.setSelected(True)
                self.reflect_selected_components()
            elif action == act_copy:
                if not item.isSelected():
                    self.clearSelection()
                    item.setSelected(True)
                self.copy_selected()
            elif action == act_paste:
                self.paste()
            elif action == act_del:
                self.remove_selected()
            event.accept()
            return

        menu = QMenu()
        act_paste = menu.addAction("📥 Pegar (Ctrl+V)")
        act_paste.setEnabled(bool(self._clipboard))
        action = menu.exec(event.screenPos())
        if action == act_paste:
            self.paste()
        event.accept()


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
            self._is_panning = True
            self._pan_start = event.position().toPoint() if hasattr(event, "position") else event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        if self.dragMode() != QGraphicsView.RubberBandDrag:
            self.setDragMode(QGraphicsView.RubberBandDrag)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if getattr(self, "_is_panning", False):
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            delta = pos - self._pan_start
            self._pan_start = pos
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton and getattr(self, "_is_panning", False):
            self._is_panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)
