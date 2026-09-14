"""
RTL Schematic Editor Widget for ELO212.
Provides component palette, canvas with snap-to-grid, wire property editing,
and quick example loading.
"""

import json
import math
import re
from typing import Optional, List, Tuple
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QGroupBox,
    QPushButton, QLabel, QLineEdit, QSpinBox, QComboBox,
    QFormLayout, QMessageBox, QInputDialog, QDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget, QCheckBox,
    QScrollArea
)
from app.core.rtl_model import (
    RTLSchematic, RTLComponent, RTLWire, RTLPin, ComponentFactory,
    ComponentType, PinSide, PinDirection, parse_slice_width,
    compute_mux_input_offsets
)
from app.gui.rtl_canvas import RTLGraphicsScene, RTLGraphicsView, compute_manhattan_path
from app.gui.rtl_items import RTLComponentItem, RTLWireItem, snap


class BlockPropertiesDialog(QDialog):
    """Configuration dialog for generic functional blocks: name, dimensions, inputs & outputs"""

    def __init__(self, comp: RTLComponent, parent=None):
        super().__init__(parent)
        self.comp = comp
        self.setWindowTitle(f"Configurar Bloque: {comp.label}")
        self.resize(500, 480)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # General Box
        box_gen = QGroupBox("Propiedades Generales")
        form_gen = QFormLayout(box_gen)
        self.edit_name = QLineEdit(self.comp.label)
        self.spin_width = QSpinBox()
        self.spin_width.setRange(60, 800)
        self.spin_width.setSingleStep(20)
        self.spin_width.setValue(int(self.comp.width))

        self.spin_height = QSpinBox()
        self.spin_height.setRange(60, 800)
        self.spin_height.setSingleStep(20)
        self.spin_height.setValue(int(self.comp.height))

        form_gen.addRow("Nombre del Módulo:", self.edit_name)
        form_gen.addRow("Ancho (px):", self.spin_width)
        form_gen.addRow("Alto (px):", self.spin_height)
        layout.addWidget(box_gen)

        # Tabs for Inputs and Outputs
        tabs = QTabWidget()

        # Inputs tab
        w_in = QWidget()
        l_in = QVBoxLayout(w_in)
        self.table_in = QTableWidget(0, 2)
        self.table_in.setHorizontalHeaderLabels(["Nombre Entrada", "Ancho (bits)"])
        self.table_in.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        btn_box_in = QHBoxLayout()
        btn_add_in = QPushButton("➕ Agregar Entrada")
        btn_del_in = QPushButton("➖ Eliminar Entrada")
        btn_add_in.clicked.connect(self._add_input_row)
        btn_del_in.clicked.connect(self._del_input_row)
        btn_box_in.addWidget(btn_add_in)
        btn_box_in.addWidget(btn_del_in)
        l_in.addWidget(self.table_in)
        l_in.addLayout(btn_box_in)
        tabs.addTab(w_in, "Entradas (Inputs)")

        # Outputs tab
        w_out = QWidget()
        l_out = QVBoxLayout(w_out)
        self.table_out = QTableWidget(0, 2)
        self.table_out.setHorizontalHeaderLabels(["Nombre Salida", "Ancho (bits)"])
        self.table_out.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        btn_box_out = QHBoxLayout()
        btn_add_out = QPushButton("➕ Agregar Salida")
        btn_del_out = QPushButton("➖ Eliminar Salida")
        btn_add_out.clicked.connect(self._add_output_row)
        btn_del_out.clicked.connect(self._del_output_row)
        btn_box_out.addWidget(btn_add_out)
        btn_box_out.addWidget(btn_del_out)
        l_out.addWidget(self.table_out)
        l_out.addLayout(btn_box_out)
        tabs.addTab(w_out, "Salidas (Outputs)")

        layout.addWidget(tabs)

        # Populate tables with existing pins
        for p in self.comp.pins:
            if p.side == PinSide.LEFT:
                self._add_input_row(p.name, p.width)
            elif p.side == PinSide.RIGHT:
                self._add_output_row(p.name, p.width)

        # Dialog buttons
        btn_box = QHBoxLayout()
        btn_ok = QPushButton("Aplicar Cambios")
        btn_ok.setStyleSheet("font-weight: bold; background: #0066cc; color: white; padding: 6px;")
        btn_cancel = QPushButton("Cancelar")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_ok)
        layout.addLayout(btn_box)

    def _add_input_row(self, name=None, width=1):
        row = self.table_in.rowCount()
        self.table_in.insertRow(row)
        n = name if isinstance(name, str) else f"in_{row}"
        w = width if isinstance(width, int) else 1
        self.table_in.setItem(row, 0, QTableWidgetItem(n))
        spin = QSpinBox()
        spin.setRange(1, 128)
        spin.setValue(w)
        self.table_in.setCellWidget(row, 1, spin)

    def _del_input_row(self):
        row = self.table_in.currentRow()
        if row >= 0:
            self.table_in.removeRow(row)
        elif self.table_in.rowCount() > 0:
            self.table_in.removeRow(self.table_in.rowCount() - 1)

    def _add_output_row(self, name=None, width=1):
        row = self.table_out.rowCount()
        self.table_out.insertRow(row)
        n = name if isinstance(name, str) else f"out_{row}"
        w = width if isinstance(width, int) else 1
        self.table_out.setItem(row, 0, QTableWidgetItem(n))
        spin = QSpinBox()
        spin.setRange(1, 128)
        spin.setValue(w)
        self.table_out.setCellWidget(row, 1, spin)

    def _del_output_row(self):
        row = self.table_out.currentRow()
        if row >= 0:
            self.table_out.removeRow(row)
        elif self.table_out.rowCount() > 0:
            self.table_out.removeRow(self.table_out.rowCount() - 1)

    def get_configured_pins(self) -> Tuple[List[Tuple[str, int]], List[Tuple[str, int]]]:
        inputs = []
        for r in range(self.table_in.rowCount()):
            item = self.table_in.item(r, 0)
            name = item.text().strip() if item else f"in_{r}"
            spin = self.table_in.cellWidget(r, 1)
            w = spin.value() if isinstance(spin, QSpinBox) else 1
            inputs.append((name, w))

        outputs = []
        for r in range(self.table_out.rowCount()):
            item = self.table_out.item(r, 0)
            name = item.text().strip() if item else f"out_{r}"
            spin = self.table_out.cellWidget(r, 1)
            w = spin.value() if isinstance(spin, QSpinBox) else 1
            outputs.append((name, w))

        return inputs, outputs


class MuxPropertiesDialog(QDialog):
    """Configuration dialog for Multiplexers: input count, abstract labels (numbers or FSM states), sel location, bus width"""

    def __init__(self, comp: RTLComponent, parent=None):
        super().__init__(parent)
        self.comp = comp
        self.setWindowTitle(f"Configurar Multiplexor: {comp.label}")
        self.resize(480, 500)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # General properties
        box_gen = QGroupBox("Propiedades del MUX")
        form_gen = QFormLayout(box_gen)
        self.edit_label = QLineEdit(self.comp.label)

        in_pins = [p for p in self.comp.pins if p.direction == PinDirection.IN and p.side == PinSide.LEFT]
        self.spin_num_inputs = QSpinBox()
        self.spin_num_inputs.setRange(2, 32)
        self.spin_num_inputs.setValue(len(in_pins) if in_pins else 2)
        self.spin_num_inputs.valueChanged.connect(self._on_num_inputs_changed)

        self.combo_sel_side = QComboBox()
        self.combo_sel_side.addItems(["Inferior (Bottom)", "Superior (Top)"])
        cur_sel = self.comp.properties.get("sel_side", "BOTTOM")
        sel_pin = next((p for p in self.comp.pins if p.direction == PinDirection.CONTROL and p.name == "sel"), None)
        if (sel_pin and sel_pin.side == PinSide.TOP) or cur_sel == "TOP":
            self.combo_sel_side.setCurrentIndex(1)
        else:
            self.combo_sel_side.setCurrentIndex(0)

        form_gen.addRow("Etiqueta del MUX:", self.edit_label)
        form_gen.addRow("Número de entradas:", self.spin_num_inputs)
        form_gen.addRow("Ubicación de selector:", self.combo_sel_side)

        self.spin_width = QSpinBox()
        self.spin_width.setRange(30, 200)
        self.spin_width.setValue(int(self.comp.width))

        min_h = max(40, (len(in_pins) if in_pins else 2) * 15)
        self.spin_height = QSpinBox()
        self.spin_height.setRange(min_h, 400)
        self.spin_height.setValue(int(self.comp.height))

        form_gen.addRow("Ancho (px):", self.spin_width)
        form_gen.addRow("Largo / Alto (px):", self.spin_height)
        layout.addWidget(box_gen)

        # Inputs Table
        box_inputs = QGroupBox("Configuración de Entradas (Números o Estados FSM)")
        l_inputs = QVBoxLayout(box_inputs)

        # Presets bar
        btn_box_presets = QHBoxLayout()
        btn_preset_nums = QPushButton("🔢 Preset Números (0, 1, 2...)")
        btn_preset_fsm = QPushButton("🔤 Preset Estados FSM (IDLE, RUN...)")
        btn_preset_nums.clicked.connect(self._apply_preset_nums)
        btn_preset_fsm.clicked.connect(self._apply_preset_fsm)
        btn_box_presets.addWidget(btn_preset_nums)
        btn_box_presets.addWidget(btn_preset_fsm)
        l_inputs.addLayout(btn_box_presets)

        self.table_inputs = QTableWidget(0, 2)
        self.table_inputs.setHorizontalHeaderLabels(["Canal", "Etiqueta / Estado"])
        self.table_inputs.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table_inputs.setColumnWidth(0, 90)
        l_inputs.addWidget(self.table_inputs)
        layout.addWidget(box_inputs)

        # Populate table
        for i in range(self.spin_num_inputs.value()):
            name = in_pins[i].name if i < len(in_pins) else str(i)
            self._add_row(i, name)

        # Dialog buttons
        btn_box = QHBoxLayout()
        btn_ok = QPushButton("Aplicar Cambios")
        btn_ok.setStyleSheet("font-weight: bold; background: #0066cc; color: white; padding: 6px;")
        btn_cancel = QPushButton("Cancelar")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_ok)
        layout.addLayout(btn_box)

    def _add_row(self, idx: int, name: str):
        row = self.table_inputs.rowCount()
        self.table_inputs.insertRow(row)
        item_idx = QTableWidgetItem(f"Entrada {idx}")
        item_idx.setFlags(item_idx.flags() & ~Qt.ItemIsEditable)
        self.table_inputs.setItem(row, 0, item_idx)
        self.table_inputs.setItem(row, 1, QTableWidgetItem(name))

    def _on_num_inputs_changed(self, new_count: int):
        cur_count = self.table_inputs.rowCount()
        if new_count > cur_count:
            for i in range(cur_count, new_count):
                self._add_row(i, str(i))
        elif new_count < cur_count:
            for i in range(cur_count - 1, new_count - 1, -1):
                self.table_inputs.removeRow(i)
        min_h = max(40, new_count * 15)
        self.spin_height.setMinimum(min_h)
        if self.spin_height.value() < min_h:
            self.spin_height.setValue(max(60, new_count * 25))

    def _apply_preset_nums(self):
        for r in range(self.table_inputs.rowCount()):
            self.table_inputs.setItem(r, 1, QTableWidgetItem(str(r)))

    def _apply_preset_fsm(self):
        fsm_names = ["IDLE", "RUN", "WAIT", "DONE", "ERROR", "ACK", "READY", "RESET"]
        for r in range(self.table_inputs.rowCount()):
            val = fsm_names[r] if r < len(fsm_names) else f"S{r}"
            self.table_inputs.setItem(r, 1, QTableWidgetItem(val))

    def get_input_names(self) -> List[str]:
        names = []
        for r in range(self.table_inputs.rowCount()):
            it = self.table_inputs.item(r, 1)
            txt = it.text().strip() if it else ""
            names.append(txt or str(r))
        return names

    def get_sel_side(self) -> str:
        return "TOP" if self.combo_sel_side.currentIndex() == 1 else "BOTTOM"


class SplitterPropertiesDialog(QDialog):
    """Configuration dialog for Bus Splitter: base signal name, total width, slices (ELO212)"""

    def __init__(self, comp: RTLComponent, parent=None):
        super().__init__(parent)
        self.comp = comp
        self.setWindowTitle("Configurar Desagregador de Bus")
        self.resize(480, 380)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        box = QGroupBox("Parámetros del Desagregador (ELO212)")
        form = QFormLayout(box)

        cur_base = self.comp.properties.get("base_name", "")
        cur_in_w = int(self.comp.properties.get("in_width", "16"))
        cur_slices = self.comp.properties.get("slices", "[2:0], [3], [15:4]")

        self.edit_base = QLineEdit(cur_base)
        self.edit_base.setPlaceholderText("ej: bus_ej o data (opcional)")
        self.edit_base.textChanged.connect(self._update_preview)

        self.spin_in_w = QSpinBox()
        self.spin_in_w.setRange(2, 512)
        self.spin_in_w.setValue(cur_in_w)

        self.edit_slices = QLineEdit(cur_slices)
        self.edit_slices.setPlaceholderText("ej: [2:0], [3], [15:4]")
        self.edit_slices.textChanged.connect(self._update_preview)

        form.addRow("Nombre base de señal:", self.edit_base)
        form.addRow("Ancho total de bus entrada:", self.spin_in_w)
        form.addRow("Especificación de rebanadas (slices):", self.edit_slices)
        layout.addWidget(box)

        # Preview box
        layout.addWidget(QLabel("Vista previa de derivaciones calculadas (según ELO212):"))
        self.lbl_preview = QLabel()
        self.lbl_preview.setStyleSheet("background: #f8f9fa; border: 1px solid #dcdfe6; padding: 8px; border-radius: 4px; font-family: Consolas;")
        layout.addWidget(self.lbl_preview)
        self._update_preview()

        # Dialog buttons
        btn_box = QHBoxLayout()
        btn_ok = QPushButton("Aplicar Cambios")
        btn_ok.setStyleSheet("font-weight: bold; background: #0066cc; color: white; padding: 6px;")
        btn_cancel = QPushButton("Cancelar")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_ok)
        layout.addLayout(btn_box)

    def _update_preview(self):
        from app.core.rtl_model import parse_slice_width
        base = self.edit_base.text().strip()
        slices = [s.strip() for s in self.edit_slices.text().split(",") if s.strip()]
        lines = []
        total_w = 0
        for s in slices:
            w = parse_slice_width(s)
            total_w += w
            lbl = f"{base}{s}" if base and not s.startswith(base) else s
            slash_str = f"(/ {w})" if w > 1 else "(1 bit, sin slash)"
            lines.append(f"• Rama '{lbl}': {w} bits {slash_str}")
        if not lines:
            self.lbl_preview.setText("Sin derivaciones especificadas.")
        else:
            in_w = self.spin_in_w.value()
            status = f"✓ Ancho consistente ({total_w} bits)" if total_w == in_w else f"⚠️ Suma de ramas ({total_w} bits) != Entrada ({in_w} bits)"
            txt = "\n".join(lines) + f"\n\nTotal acumulado: {total_w} bits | {status}"
            self.lbl_preview.setText(txt)

class OperatorPropertiesDialog(QDialog):
    """Configuration dialog for Circular Operators: arithmetic, logic, reduction, unary, relational."""

    OPERATIONS = [
        ("Aritméticas (Binarias)", [
            ("Suma (+)", "+", False, False, False),
            ("Resta (-)", "-", False, False, False),
            ("Multiplicación (*)", "*", False, False, False),
            ("División (/)", "/", False, False, False),
            ("Módulo (%)", "%", False, False, False),
        ]),
        ("Lógicas / Bit a bit (Binarias)", [
            ("AND a nivel de bits (&)", "&", False, False, False),
            ("OR a nivel de bits (|)", "|", False, False, False),
            ("XOR a nivel de bits (^)", "^", False, False, False),
            ("XNOR a nivel de bits (~^)", "~^", False, False, False),
            ("Desplazamiento a la izquierda (<<)", "<<", False, False, False),
            ("Desplazamiento a la derecha (>>)", ">>", False, False, False),
        ]),
        ("Reducción (Vector -> 1 bit)", [
            ("Reducción AND (&)", "&", True, False, True),
            ("Reducción OR (|)", "|", True, False, True),
            ("Reducción XOR (^)", "^", True, False, True),
            ("Reducción NAND (~&)", "~&", True, False, True),
            ("Reducción NOR (~|)", "~|", True, False, True),
            ("Reducción XNOR (~^)", "~^", True, False, True),
        ]),
        ("Unarias / Inversión (1 entrada)", [
            ("Inversión bit a bit (~)", "~", False, True, False),
            ("Negación aritmética (-)", "-", False, True, False),
        ]),
        ("Relacionales / Comparación (Salida 1 bit)", [
            ("Igualdad (==)", "==", False, False, True),
            ("Desigualdad (!=)", "!=", False, False, True),
            ("Mayor que (>)", ">", False, False, True),
            ("Mayor o igual que (>=)", ">=", False, False, True),
            ("Menor que (<)", "<", False, False, True),
            ("Menor o igual que (<=)", "<=", False, False, True),
        ]),
    ]

    def __init__(self, comp: RTLComponent, parent=None):
        super().__init__(parent)
        self.comp = comp
        self.setWindowTitle(f"Configurar Operador Circular: {comp.label}")
        self.resize(460, 420)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        box = QGroupBox("Propiedades del Operador")
        form = QFormLayout(box)

        # Category combo
        self.combo_category = QComboBox()
        for cat, _ in self.OPERATIONS:
            self.combo_category.addItem(cat)
        self.combo_category.currentIndexChanged.connect(self._on_category_changed)

        # Operation combo
        self.combo_op = QComboBox()
        self.combo_op.currentIndexChanged.connect(self._on_op_changed)

        # Bus width
        cur_w = int(self.comp.properties.get("bus_width", "4"))
        self.spin_width = QSpinBox()
        self.spin_width.setRange(1, 128)
        self.spin_width.setValue(cur_w)
        self.spin_width.valueChanged.connect(self._update_preview)

        # Custom label
        self.edit_label = QLineEdit(self.comp.label)
        self.edit_label.setPlaceholderText("Dejar en blanco para usar símbolo de operación")
        self.edit_label.textChanged.connect(self._update_preview)

        # Circle Size / Diameter
        self.spin_size = QSpinBox()
        self.spin_size.setRange(40, 120)
        self.spin_size.setSingleStep(10)
        self.spin_size.setValue(int(self.comp.width))
        self.spin_size.valueChanged.connect(self._update_preview)

        # Orientation / Rotation
        self.combo_rotation = QComboBox()
        self.combo_rotation.addItems([
            "0° (Entradas Izquierda → Salida Derecha)",
            "90° (Entradas Arriba → Salida Abajo)",
            "180° (Entradas Derecha → Salida Izquierda)",
            "270° (Entradas Abajo → Salida Arriba)"
        ])
        cur_rot = int(self.comp.properties.get("rotation", "0")) % 360
        self.combo_rotation.setCurrentIndex(cur_rot // 90)
        self.combo_rotation.currentIndexChanged.connect(self._update_preview)

        form.addRow("Categoría:", self.combo_category)
        form.addRow("Operación:", self.combo_op)
        form.addRow("Diámetro del círculo (px):", self.spin_size)
        form.addRow("Orientación:", self.combo_rotation)
        form.addRow("Etiqueta en círculo:", self.edit_label)
        layout.addWidget(box)

        # Info / Preview Box
        layout.addWidget(QLabel("Detalles y puertos del operador:"))
        self.lbl_preview = QLabel()
        self.lbl_preview.setStyleSheet("background: #f8f9fa; border: 1px solid #dcdfe6; padding: 10px; border-radius: 4px; font-family: Consolas;")
        layout.addWidget(self.lbl_preview)

        # Buttons
        btn_box = QHBoxLayout()
        btn_ok = QPushButton("Aplicar Cambios")
        btn_ok.setStyleSheet("font-weight: bold; background: #0066cc; color: white; padding: 6px;")
        btn_cancel = QPushButton("Cancelar")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_ok)
        layout.addLayout(btn_box)

        self._select_current_op()
        self._update_preview()

    def _select_current_op(self):
        cur_op = self.comp.properties.get("op", self.comp.label)
        is_red = self.comp.properties.get("is_reduction", "False") == "True"
        is_unary = self.comp.properties.get("is_unary", "False") == "True"

        matched_cat_idx = 0
        matched_op_idx = 0
        found = False

        for c_idx, (cat, ops) in enumerate(self.OPERATIONS):
            for o_idx, (dname, sym, red, un, out1) in enumerate(ops):
                if sym == cur_op and red == is_red and un == is_unary:
                    matched_cat_idx = c_idx
                    matched_op_idx = o_idx
                    found = True
                    break
                elif not found and sym == cur_op:
                    matched_cat_idx = c_idx
                    matched_op_idx = o_idx
            if found:
                break

        self.combo_category.setCurrentIndex(matched_cat_idx)
        self._populate_ops_for_cat(matched_cat_idx)
        self.combo_op.setCurrentIndex(matched_op_idx)

    def _on_category_changed(self, idx: int):
        self._populate_ops_for_cat(idx)
        self._update_preview()

    def _populate_ops_for_cat(self, cat_idx: int):
        self.combo_op.blockSignals(True)
        self.combo_op.clear()
        if 0 <= cat_idx < len(self.OPERATIONS):
            _, ops = self.OPERATIONS[cat_idx]
            for dname, _, _, _, _ in ops:
                self.combo_op.addItem(dname)
        self.combo_op.blockSignals(False)

    def _on_op_changed(self, idx: int):
        cat_idx = self.combo_category.currentIndex()
        if 0 <= cat_idx < len(self.OPERATIONS):
            _, ops = self.OPERATIONS[cat_idx]
            if 0 <= idx < len(ops):
                _, sym, _, _, _ = ops[idx]
                if not self.edit_label.text() or self.edit_label.text() in [o[1] for c in self.OPERATIONS for o in c[1]]:
                    self.edit_label.setText(sym)
        self._update_preview()

    def get_selected_op_info(self) -> Tuple[str, bool, bool, bool]:
        cat_idx = self.combo_category.currentIndex()
        op_idx = self.combo_op.currentIndex()
        if 0 <= cat_idx < len(self.OPERATIONS):
            _, ops = self.OPERATIONS[cat_idx]
            if 0 <= op_idx < len(ops):
                _, sym, is_red, is_unary, out_1bit = ops[op_idx]
                return sym, is_red, is_unary, out_1bit
        return "+", False, False, False

    def get_size(self) -> float:
        return float(self.spin_size.value())

    def get_rotation(self) -> int:
        return self.combo_rotation.currentIndex() * 90

    def get_label(self) -> str:
        txt = self.edit_label.text().strip()
        if txt:
            return txt
        sym, _, _, _ = self.get_selected_op_info()
        return sym

    def _update_preview(self):
        sym, is_red, is_unary, out_1bit = self.get_selected_op_info()
        lbl = self.get_label()
        sz = self.spin_size.value()
        rot_deg = self.combo_rotation.currentIndex() * 90

        if rot_deg == 90:
            dir_str = "Arriba → Abajo (90°)"
            ports_pos = "Entradas arriba, Salida abajo"
        elif rot_deg == 180:
            dir_str = "Derecha → Izquierda (180°)"
            ports_pos = "Entradas a la derecha, Salida a la izquierda"
        elif rot_deg == 270:
            dir_str = "Abajo → Arriba (270°)"
            ports_pos = "Entradas abajo, Salida arriba"
        else:
            dir_str = "Izquierda → Derecha (0°)"
            ports_pos = "Entradas a la izquierda, Salida a la derecha"

        if is_red:
            mode_str = "Operador de Reducción (Vector a 1 bit)"
            ports_str = f"• Entrada: A\n• Salida:  out (1 bit)"
        elif is_unary:
            mode_str = "Operador Unario / Inversor (1 entrada)"
            ports_str = f"• Entrada: A\n• Salida:  out"
        else:
            out_desc = "1 bit" if out_1bit else "ancho del bus definido en cable"
            mode_str = f"Operador Binario ({'Comparador' if out_1bit else 'Aritmético/Lógico'})"
            ports_str = f"• Entrada: A\n• Entrada: B\n• Salida:  out ({out_desc})"

        self.lbl_preview.setText(
            f"Tipo: {mode_str}\n"
            f"Símbolo Verilog: '{sym}'  |  Texto en círculo: '{lbl}'\n"
            f"Diámetro: {sz} px  |  Orientación: {dir_str}\n\n"
            f"Configuración de Puertos ({ports_pos}):\n{ports_str}"
        )


class ParametersDialog(QDialog):
    """Configuration dialog for Schematic Parameters (Verilog parameters like DATA_WIDTH, ADDR_WIDTH, N)."""

    def __init__(self, schematic: RTLSchematic, parent=None):
        super().__init__(parent)
        self.schematic = schematic
        self.setWindowTitle("Parámetros del Esquemático RTL (Verilog / ELO212)")
        self.resize(520, 440)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        lbl_desc = QLabel(
            "Defina parámetros globales reutilizables para anchos de buses de datos y direcciones (ej. DATA_WIDTH = 8, N = 16).\n"
            "Los cables y bloques que usen estos parámetros se actualizarán automáticamente."
        )
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet("color: #444; font-size: 11px; margin-bottom: 6px;")
        layout.addWidget(lbl_desc)

        # Table of existing parameters
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Nombre del Parámetro", "Valor (bits)"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setColumnWidth(1, 120)
        layout.addWidget(self.table)

        self._populate_table()

        # Add/Edit Box
        box_edit = QGroupBox("Agregar o Modificar Parámetro")
        form_edit = QFormLayout(box_edit)

        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("ej: DATA_WIDTH o N")
        self.spin_val = QSpinBox()
        self.spin_val.setRange(1, 1024)
        self.spin_val.setValue(8)

        form_edit.addRow("Nombre:", self.edit_name)
        form_edit.addRow("Valor en bits:", self.spin_val)

        btn_box_table = QHBoxLayout()
        btn_add = QPushButton("➕ Guardar / Actualizar Parámetro")
        btn_add.setStyleSheet("font-weight: bold; background: #28a745; color: white; padding: 5px;")
        btn_del = QPushButton("➖ Eliminar Seleccionado")
        btn_add.clicked.connect(self._save_param_from_inputs)
        btn_del.clicked.connect(self._del_selected_param)
        btn_box_table.addWidget(btn_add)
        btn_box_table.addWidget(btn_del)
        form_edit.addRow(btn_box_table)

        layout.addWidget(box_edit)

        # Dialog Buttons
        btn_box = QHBoxLayout()
        btn_close = QPushButton("Cerrar")
        btn_close.clicked.connect(self.accept)
        btn_box.addStretch()
        btn_box.addWidget(btn_close)
        layout.addLayout(btn_box)

        self.table.itemSelectionChanged.connect(self._on_row_selected)

    def _populate_table(self):
        self.table.setRowCount(0)
        for name, val in sorted(self.schematic.parameters.items()):
            row = self.table.rowCount()
            self.table.insertRow(row)
            item_name = QTableWidgetItem(name)
            item_name.setFlags(item_name.flags() & ~Qt.ItemIsEditable)
            item_val = QTableWidgetItem(str(val))
            item_val.setFlags(item_val.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 0, item_name)
            self.table.setItem(row, 1, item_val)

    def _save_param_from_inputs(self):
        name = self.edit_name.text().strip().upper()
        if not name:
            QMessageBox.warning(self, "Aviso", "Ingrese un nombre de parámetro válido (ej: DATA_WIDTH).")
            return
        if not re.match(r'^[A-Z_][A-Z0-9_]*$', name):
            QMessageBox.warning(self, "Aviso", "El nombre debe ser un identificador Verilog válido (letras mayúsculas, números, guión bajo).")
            return

        val = self.spin_val.value()
        self.schematic.set_parameter(name, val)
        self._populate_table()
        self.edit_name.clear()
        self.edit_name.setFocus()

    def _del_selected_param(self):
        row = self.table.currentRow()
        if row >= 0:
            name_item = self.table.item(row, 0)
            if name_item:
                name = name_item.text()
                self.schematic.remove_parameter(name)
                self._populate_table()
                self.edit_name.clear()

    def _on_row_selected(self):
        row = self.table.currentRow()
        if row >= 0:
            name_item = self.table.item(row, 0)
            val_item = self.table.item(row, 1)
            if name_item and val_item:
                self.edit_name.setText(name_item.text())
                self.spin_val.setValue(int(val_item.text()))


class RTLPortConfigDialog(QDialog):
    """Configuration dialog for Input / Output Port indicators (Vivado / ELO212 style)"""

    def __init__(self, comp: RTLComponent, schematic_params: dict = None, parent=None):
        super().__init__(parent)
        self.comp = comp
        self.schematic_params = schematic_params or {}
        is_in = (comp.type == ComponentType.INPUT_PORT)
        title_type = "Entrada (Input)" if is_in else "Salida (Output)"
        self.setWindowTitle(f"Configurar Puerto de {title_type}: {comp.label}")
        self.resize(400, 260)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        is_in = (self.comp.type == ComponentType.INPUT_PORT)
        box = QGroupBox(f"Propiedades del Puerto de {'Entrada' if is_in else 'Salida'}")
        form = QFormLayout(box)

        self.edit_name = QLineEdit(self.comp.label)
        self.edit_name.setPlaceholderText("ej: clk_100M, rst, anodes[7:0]")
        self.edit_name.textChanged.connect(self._on_name_changed)

        cur_w = 1
        if self.comp.pins:
            cur_w = self.comp.pins[0].width
        else:
            try:
                cur_w = int(self.comp.properties.get("bus_width", "1"))
            except ValueError:
                cur_w = 1

        self.spin_width = QSpinBox()
        self.spin_width.setRange(1, 128)
        self.spin_width.setValue(cur_w)

        self.combo_param = QComboBox()
        self.combo_param.addItem("(Ninguno - Manual)", None)
        cur_param = self.comp.properties.get("bus_width_param") or (self.comp.pins[0].width_param if self.comp.pins else None)
        sel_idx = 0
        for idx, (p_name, p_val) in enumerate(sorted(self.schematic_params.items()), start=1):
            self.combo_param.addItem(f"{p_name} ({p_val} bits)", p_name)
            if p_name == cur_param:
                sel_idx = idx
        self.combo_param.setCurrentIndex(sel_idx)
        self.combo_param.currentIndexChanged.connect(self._on_param_changed)

        form.addRow("Nombre del Puerto:", self.edit_name)
        form.addRow("Ancho de bits:", self.spin_width)
        form.addRow("Parámetro global:", self.combo_param)

        lbl_hint = QLabel(
            "<i>Consejo: Si escribe corchetes como <code>bus[7:0]</code> en el nombre, "
            "el ancho se calculará automáticamente. Si el ancho es > 1 bit, el indicador "
            "se dibujará con trazo grueso (bus).</i>"
        )
        lbl_hint.setWordWrap(True)
        lbl_hint.setStyleSheet("color: #555; font-size: 11px; padding: 4px;")
        form.addRow(lbl_hint)

        layout.addWidget(box)

        # Buttons
        btn_box = QHBoxLayout()
        btn_ok = QPushButton("Guardar Cambios")
        btn_ok.setStyleSheet("font-weight: bold; background: #0066cc; color: white; padding: 6px;")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancelar")
        btn_cancel.clicked.connect(self.reject)

        btn_box.addStretch()
        btn_box.addWidget(btn_cancel)
        btn_box.addWidget(btn_ok)
        layout.addLayout(btn_box)

    def _on_name_changed(self, text: str):
        parsed = parse_slice_width(text)
        if parsed > 1:
            self.spin_width.setValue(parsed)

    def _on_param_changed(self):
        p_name = self.combo_param.currentData()
        if p_name and p_name in self.schematic_params:
            self.spin_width.setValue(self.schematic_params[p_name])


class RTLEditorWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = RTLGraphicsScene(self)
        self.view = RTLGraphicsView(self.scene)
        self._init_ui()
        self.load_counter_example()

    def _init_ui(self):
        layout = QHBoxLayout(self)

        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter)

        # -------------------------------------------------------------
        # Left Panel: Component Palette & Tools (Scrollable)
        # -------------------------------------------------------------
        palette_panel = QWidget()
        pal_layout = QVBoxLayout(palette_panel)
        pal_layout.setContentsMargins(6, 6, 6, 6)
        pal_layout.setSpacing(8)

        palette_panel.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                margin-top: 6px;
                padding-top: 10px;
                border: 1px solid #dcdfe6;
                border-radius: 5px;
                background: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 5px;
                color: #2c3e50;
            }
            QPushButton {
                min-height: 27px;
                padding: 4px 8px;
                font-size: 11px;
                border-radius: 4px;
                border: 1px solid #d0d7de;
                background-color: #f6f8fa;
                color: #24292f;
            }
            QPushButton:hover {
                background-color: #eef2f6;
                border-color: #0969da;
            }
            QPushButton:pressed {
                background-color: #d8e2ec;
            }
        """)

        # Standards reminder
        box_guide = QGroupBox("Normas ELO212")
        g_layout = QVBoxLayout(box_guide)
        g_layout.setContentsMargins(8, 8, 8, 8)
        lbl_guide = QLabel(
            "• Entradas a la izquierda, salidas a la derecha.\n"
            "• Cables ortogonales (sin diagonales).\n"
            "• Cruces sin punto NO se conectan.\n"
            "• Indique ancho (/N) en buses."
        )
        lbl_guide.setStyleSheet("color: #444; font-size: 11px;")
        g_layout.addWidget(lbl_guide)
        pal_layout.addWidget(box_guide)

        # Component Creation
        box_add = QGroupBox("Agregar Componentes")
        add_layout = QVBoxLayout(box_add)
        add_layout.setContentsMargins(8, 8, 8, 8)
        add_layout.setSpacing(4)

        btn_in_port = QPushButton("➕ Puerto de Entrada (Input)")
        btn_out_port = QPushButton("➕ Puerto de Salida (Output)")
        btn_mux = QPushButton("➕ Multiplexor (MUX)")
        btn_reg = QPushButton("➕ Registro / Flip-Flop")
        btn_op = QPushButton("➕ Operador Circular (+, >)")
        btn_gate = QPushButton("➕ Compuerta Lógica")
        btn_split = QPushButton("➕ Desagregador de Bus")
        btn_const = QPushButton("➕ Constante (1'b0, 4'd1)")
        btn_block = QPushButton("➕ Bloque Genérico")

        btn_in_port.clicked.connect(self.spawn_input_port)
        btn_out_port.clicked.connect(self.spawn_output_port)
        btn_mux.clicked.connect(self.spawn_mux)
        btn_reg.clicked.connect(self.spawn_register)
        btn_op.clicked.connect(self.spawn_operator)
        btn_gate.clicked.connect(self.spawn_gate)
        btn_split.clicked.connect(self.spawn_splitter)
        btn_const.clicked.connect(self.spawn_constant)
        btn_block.clicked.connect(self.spawn_block)

        add_layout.addWidget(btn_in_port)
        add_layout.addWidget(btn_out_port)
        add_layout.addWidget(btn_mux)
        add_layout.addWidget(btn_reg)
        add_layout.addWidget(btn_op)
        add_layout.addWidget(btn_gate)
        add_layout.addWidget(btn_split)
        add_layout.addWidget(btn_const)
        add_layout.addWidget(btn_block)
        pal_layout.addWidget(box_add)

        # Wire / Selection Properties
        box_props = QGroupBox("Propiedades del Cable Seleccionado")
        p_form = QFormLayout(box_props)
        p_form.setContentsMargins(8, 8, 8, 8)
        self.combo_wire_param = QComboBox()
        self.combo_wire_param.currentIndexChanged.connect(self._on_wire_param_changed)
        self.spin_wire_width = QSpinBox()
        self.spin_wire_width.setRange(1, 128)
        self.spin_wire_width.setValue(1)
        self.spin_wire_width.valueChanged.connect(self._on_wire_width_spin_changed)
        self.edit_wire_label = QLineEdit()
        self.edit_wire_label.setPlaceholderText("ej: bus_ej[5:0]")
        self.check_wire_arrow = QCheckBox("Mostrar flecha de dirección (➡️)")

        btn_apply_wire = QPushButton("Aplicar al Cable Seleccionado")
        btn_apply_wire.clicked.connect(self.apply_wire_props)

        p_form.addRow("Ancho de bus (bits):", self.spin_wire_width)
        p_form.addRow("Etiqueta:", self.edit_wire_label)
        p_form.addRow(self.check_wire_arrow)
        p_form.addRow(btn_apply_wire)
        pal_layout.addWidget(box_props)

        # Canvas Actions
        box_actions = QGroupBox("Acciones del Canvas")
        act_layout = QVBoxLayout(box_actions)
        act_layout.setContentsMargins(8, 8, 8, 8)
        act_layout.setSpacing(4)

        btn_reroute = QPushButton("🔄 Re-enrutar Cable (R)")
        btn_relabel = QPushButton("🏷️ Restablecer Etiquetas (Shift+R)")
        btn_rotate_op = QPushButton("🔄 Rotar Operador (Ctrl+R)")
        btn_rotate_op.setToolTip("Rota los operadores circulares seleccionados 90° en sentido horario (Ctrl+R)")
        btn_edit_block = QPushButton("⚙️ Configurar Componente")
        btn_edit_block.setToolTip("Configurar propiedades del bloque funcional, MUX, desagregador, operador o puerto seleccionado")
        btn_mirror = QPushButton("🪞 Reflejar Bloque (Ctrl+E)")
        btn_mirror.setToolTip("Refleja horizontalmente los bloques seleccionados, invirtiendo pines de entrada y salida (Ctrl+E)")
        btn_copy = QPushButton("📋 Copiar (Ctrl+C)")
        btn_copy.setToolTip("Copiar componentes y cables seleccionados (Ctrl+C)")
        btn_paste = QPushButton("📥 Pegar (Ctrl+V)")
        btn_paste.setToolTip("Pegar elementos del portapapeles con desplazamiento (Ctrl+V)")

        btn_solder = QPushButton("⚫ Colocar Solder Dot (Junction)")
        btn_del = QPushButton("🗑️ Eliminar Seleccionado (Supr)")
        btn_example = QPushButton("🔄 Cargar Ejemplo: Contador + Sumador")
        btn_clear = QPushButton("⚠️ Limpiar Todo")

        btn_reroute.clicked.connect(self.scene.reset_selected_wire_routing)
        btn_relabel.clicked.connect(self.scene.reset_selected_labels)
        btn_rotate_op.clicked.connect(self.scene.rotate_selected_operators)
        btn_edit_block.clicked.connect(self.edit_selected_block)
        btn_mirror.clicked.connect(self.scene.reflect_selected_components)
        btn_copy.clicked.connect(self.scene.copy_selected)
        btn_paste.clicked.connect(self.scene.paste)
        btn_solder.clicked.connect(self.add_solder_dot)
        btn_del.clicked.connect(self.scene_delete_selected)
        btn_example.clicked.connect(self.load_counter_example)
        btn_clear.clicked.connect(self.clear_canvas)

        act_layout.addWidget(btn_reroute)
        act_layout.addWidget(btn_relabel)
        act_layout.addWidget(btn_rotate_op)
        act_layout.addWidget(btn_edit_block)
        act_layout.addWidget(btn_mirror)
        act_layout.addWidget(btn_copy)
        act_layout.addWidget(btn_paste)
        act_layout.addWidget(btn_solder)
        act_layout.addWidget(btn_del)
        act_layout.addWidget(btn_example)
        act_layout.addWidget(btn_clear)
        pal_layout.addWidget(box_actions)

        pal_layout.addStretch()

        # Wrap in QScrollArea so that palette options are scrollable and never squished
        palette_scroll = QScrollArea()
        palette_scroll.setWidgetResizable(True)
        palette_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        palette_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        palette_scroll.setWidget(palette_panel)
        palette_scroll.setMinimumWidth(260)
        palette_scroll.setMaximumWidth(320)
        palette_scroll.setStyleSheet("QScrollArea { border: none; background: #fafafa; }")
        splitter.addWidget(palette_scroll)

        # -------------------------------------------------------------
        # Center: Graphics Canvas
        # -------------------------------------------------------------
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)

        center_layout.addWidget(self.view)

        self.lbl_status = QLabel("Listo. Haga clic en los pines de los componentes para trazar cables ortogonales.")
        self.lbl_status.setStyleSheet("background: #f0f2f5; padding: 4px 8px; border-top: 1px solid #dcdfe6;")
        self.scene.status_message.connect(self.lbl_status.setText)
        center_layout.addWidget(self.lbl_status)

        splitter.addWidget(center_widget)
        splitter.setSizes([260, 940])

        self.scene.selectionChanged.connect(self._on_selection_changed)

    def _update_param_combos(self):
        self.combo_wire_param.blockSignals(True)
        cur_data = self.combo_wire_param.currentData()
        self.combo_wire_param.clear()
        self.combo_wire_param.addItem("(Ninguno - Manual)", None)
        for p_name, p_val in sorted(self.scene.schematic.parameters.items()):
            self.combo_wire_param.addItem(f"{p_name} ({p_val} bits)", p_name)

        idx = self.combo_wire_param.findData(cur_data)
        if idx >= 0:
            self.combo_wire_param.setCurrentIndex(idx)
        else:
            self.combo_wire_param.setCurrentIndex(0)
        self.combo_wire_param.blockSignals(False)

    def _on_selection_changed(self):
        self._update_param_combos()
        sel = self.scene.selectedItems()
        for item in sel:
            w_item = item if isinstance(item, RTLWireItem) else getattr(item, "wire_item", None)
            if isinstance(w_item, RTLWireItem):
                self.combo_wire_param.blockSignals(True)
                if w_item.model.width_param:
                    idx = self.combo_wire_param.findData(w_item.model.width_param)
                    if idx >= 0:
                        self.combo_wire_param.setCurrentIndex(idx)
                    else:
                        self.combo_wire_param.setCurrentIndex(0)
                else:
                    self.combo_wire_param.setCurrentIndex(0)
                self.combo_wire_param.blockSignals(False)

                self.spin_wire_width.blockSignals(True)
                self.spin_wire_width.setValue(w_item.model.width)
                self.spin_wire_width.blockSignals(False)
                self.edit_wire_label.setText(w_item.model.label)
                self.check_wire_arrow.setChecked(w_item.model.show_arrow)
                break

    def _on_wire_width_spin_changed(self, val: int):
        sel = self.scene.selectedItems()
        for item in sel:
            w_item = item if isinstance(item, RTLWireItem) else getattr(item, "wire_item", None)
            if isinstance(w_item, RTLWireItem):
                w_item.model.width = val
                w_item.prepareGeometryChange()
                w_item.update()

    def _on_wire_param_changed(self, idx: int):
        p_name = self.combo_wire_param.currentData()
        if p_name:
            val = self.scene.schematic.get_parameter_value(p_name, self.spin_wire_width.value())
            self.spin_wire_width.setValue(val)

    def apply_wire_props(self):
        sel = self.scene.selectedItems()
        applied = False
        param_name = self.combo_wire_param.currentData()
        for item in sel:
            w_item = item if isinstance(item, RTLWireItem) else getattr(item, "wire_item", None)
            if isinstance(w_item, RTLWireItem):
                self.scene.push_undo_state()
                if param_name:
                    w_item.model.width_param = param_name
                    w_item.model.width = self.scene.schematic.get_parameter_value(param_name, self.spin_wire_width.value())
                else:
                    w_item.model.width_param = None
                    w_item.model.width = self.spin_wire_width.value()
                w_item.model.label = self.edit_wire_label.text().strip()
                w_item.model.show_arrow = self.check_wire_arrow.isChecked()
                w_item._sync_label_item()
                w_item.prepareGeometryChange()
                w_item.update()
                applied = True
        if applied:
            self.lbl_status.setText("Propiedades del cable actualizadas.")
        else:
            QMessageBox.information(self, "Aviso", "Seleccione un cable primero en el canvas.")

    def open_parameters_dialog(self):
        dlg = ParametersDialog(self.scene.schematic, self)
        self.scene.push_undo_state()
        if dlg.exec():
            self.scene.schematic.sync_parameter_widths()
            self._update_param_combos()
            for w in self.scene.wire_items.values():
                w.prepareGeometryChange()
                w.update()
            for c in self.scene.comp_items.values():
                c.rebuild_pins()
                c.update()
            self.lbl_status.setText(f"Parámetros del esquemático actualizados ({len(self.scene.schematic.parameters)} definidos).")

    def edit_selected_component(self):
        sel = self.scene.selectedItems()
        for item in sel:
            if isinstance(item, RTLComponentItem):
                if item.model.type == ComponentType.BLOCK:
                    self.open_block_dialog(item)
                    return
                elif item.model.type == ComponentType.MUX:
                    self.open_mux_dialog(item)
                    return
                elif item.model.type == ComponentType.BUS_SPLITTER:
                    self.open_splitter_dialog(item)
                    return
                elif item.model.type == ComponentType.OPERATOR_CIRCLE:
                    self.open_operator_dialog(item)
                    return
                elif item.model.type in (ComponentType.INPUT_PORT, ComponentType.OUTPUT_PORT):
                    self.open_port_dialog(item)
                    return
        QMessageBox.information(self, "Aviso", "Seleccione un bloque, multiplexor, desagregador, operador o puerto para configurar.")

    edit_selected_block = edit_selected_component

    def open_block_dialog(self, comp_item: RTLComponentItem):
        comp = comp_item.model
        dlg = BlockPropertiesDialog(comp, self)
        if dlg.exec():
            self.scene.push_undo_state()
            comp.label = dlg.edit_name.text().strip() or comp.label
            new_w = float(dlg.spin_width.value())
            new_h = float(dlg.spin_height.value())

            inputs, outputs = dlg.get_configured_pins()
            min_h = max(60.0, (max(len(inputs), len(outputs)) + 1) * 25.0)
            new_h = max(new_h, min_h)

            comp.width = new_w
            comp.height = new_h

            old_pins = {p.name: p.id for p in comp.pins}
            new_pins = []

            for i, (in_name, in_w) in enumerate(inputs):
                pid = old_pins.get(in_name, f"{comp.id}_in_{i}")
                offset = (i + 1) / (len(inputs) + 1)
                new_pins.append(RTLPin(
                    id=pid,
                    name=in_name,
                    direction=PinDirection.IN,
                    side=PinSide.LEFT,
                    offset=offset,
                    width=in_w
                ))

            for j, (out_name, out_w) in enumerate(outputs):
                pid = old_pins.get(out_name, f"{comp.id}_out_{j}")
                offset = (j + 1) / (len(outputs) + 1)
                new_pins.append(RTLPin(
                    id=pid,
                    name=out_name,
                    direction=PinDirection.OUT,
                    side=PinSide.RIGHT,
                    offset=offset,
                    width=out_w
                ))

            new_pin_ids = {p.id for p in new_pins}
            wires_to_remove = [
                w.id for w in self.scene.schematic.wires
                if (w.source_comp_id == comp.id and w.source_pin_id not in new_pin_ids) or
                   (w.target_comp_id == comp.id and w.target_pin_id not in new_pin_ids)
            ]
            for w_id in wires_to_remove:
                self.scene.remove_wire(w_id)

            comp.pins = new_pins
            comp_item.rebuild_pins()
            if hasattr(self.scene, "on_component_moved"):
                self.scene.on_component_moved(comp_item)
            self.lbl_status.setText(f"Bloque '{comp.label}' actualizado ({len(inputs)} entradas, {len(outputs)} salidas).")

    def open_mux_dialog(self, comp_item: RTLComponentItem):
        comp = comp_item.model
        dlg = MuxPropertiesDialog(comp, self)
        if dlg.exec():
            self.scene.push_undo_state()
            comp.label = dlg.edit_label.text().strip() or "MUX"
            input_names = dlg.get_input_names()
            num_inputs = len(input_names)
            sel_side_str = dlg.get_sel_side()
            s_side = PinSide.TOP if sel_side_str == "TOP" else PinSide.BOTTOM

            comp.width = float(dlg.spin_width.value())
            comp.height = float(dlg.spin_height.value())
            comp.properties["num_inputs"] = str(num_inputs)
            comp.properties["input_names"] = json.dumps(input_names)
            comp.properties["sel_side"] = sel_side_str

            new_pins = []
            input_offsets = compute_mux_input_offsets(num_inputs, comp.height)
            for i, in_name in enumerate(input_names):
                offset = input_offsets[i] if i < len(input_offsets) else (i + 1) / (num_inputs + 1)
                new_pins.append(RTLPin(
                    id=f"{comp.id}_in_{i}",
                    name=in_name,
                    direction=PinDirection.IN,
                    side=PinSide.LEFT,
                    offset=offset,
                    width=1
                ))
            new_pins.append(RTLPin(
                id=f"{comp.id}_sel",
                name="sel",
                direction=PinDirection.CONTROL,
                side=s_side,
                offset=0.5,
                width=max(1, (num_inputs - 1).bit_length())
            ))
            new_pins.append(RTLPin(
                id=f"{comp.id}_out",
                name="out",
                direction=PinDirection.OUT,
                side=PinSide.RIGHT,
                offset=0.5,
                width=1
            ))

            new_pin_ids = {p.id for p in new_pins}
            wires_to_remove = [
                w.id for w in self.scene.schematic.wires
                if (w.source_comp_id == comp.id and w.source_pin_id not in new_pin_ids) or
                   (w.target_comp_id == comp.id and w.target_pin_id not in new_pin_ids)
            ]
            for w_id in wires_to_remove:
                self.scene.remove_wire(w_id)

            comp.pins = new_pins
            comp_item.rebuild_pins()
            if hasattr(self.scene, "on_component_moved"):
                self.scene.on_component_moved(comp_item)
            self.lbl_status.setText(f"Multiplexor '{comp.label}' actualizado ({num_inputs} entradas).")

    def open_splitter_dialog(self, comp_item: RTLComponentItem):
        comp = comp_item.model
        dlg = SplitterPropertiesDialog(comp, self)
        if dlg.exec():
            self.scene.push_undo_state()
            base_name = dlg.edit_base.text().strip()
            in_w = dlg.spin_in_w.value()
            slices_str = dlg.edit_slices.text().strip() or "[2:0], [3], [15:4]"
            slice_list = [s.strip() for s in slices_str.split(",") if s.strip()]

            from app.core.rtl_model import parse_slice_width
            in_name = f"{base_name}[{in_w-1}:0]" if base_name else f"[{in_w-1}:0]"
            is_mirrored = getattr(comp, "mirrored", False)
            in_side = PinSide.RIGHT if is_mirrored else PinSide.LEFT
            out_side = PinSide.LEFT if is_mirrored else PinSide.RIGHT

            num_slices = len(slice_list)
            if num_slices <= 1:
                comp_h = 80.0
                branch_offsets = [0.5] if num_slices == 1 else []
            else:
                comp_h = max(80.0, float(num_slices * 40))
                branch_offsets = [(20.0 + idx * 40.0) / comp_h for idx in range(num_slices)]

            new_pins = [
                RTLPin(id=f"{comp.id}_in", name=in_name, direction=PinDirection.IN, side=in_side, offset=0.5, width=in_w)
            ]
            for idx, s in enumerate(slice_list):
                offset = branch_offsets[idx]
                swidth = parse_slice_width(s)
                slice_label = f"{base_name}{s}" if base_name and not s.startswith(base_name) else s
                new_pins.append(RTLPin(
                    id=f"{comp.id}_out_{idx}",
                    name=slice_label,
                    direction=PinDirection.OUT,
                    side=out_side,
                    offset=offset,
                    width=swidth
                ))
            comp.label = base_name or "SPLIT"
            max_s_len = max((len(p.name) for p in new_pins), default=5)
            raw_w = max(110.0, 45.0 + max_s_len * 8.0)
            comp.width = math.ceil(raw_w / 20.0) * 20.0
            comp.height = comp_h
            comp.properties["in_width"] = str(in_w)
            comp.properties["slices"] = slices_str
            comp.properties["base_name"] = base_name

            new_pin_ids = {p.id for p in new_pins}
            wires_to_remove = [
                w.id for w in self.scene.schematic.wires
                if (w.source_comp_id == comp.id and w.source_pin_id not in new_pin_ids) or
                   (w.target_comp_id == comp.id and w.target_pin_id not in new_pin_ids)
            ]
            for w_id in wires_to_remove:
                self.scene.remove_wire(w_id)

            comp.pins = new_pins
            comp_item.rebuild_pins()
            if hasattr(self.scene, "on_component_moved"):
                self.scene.on_component_moved(comp_item)
            self.lbl_status.setText(f"Desagregador de bus actualizado ({len(slice_list)} derivaciones).")

    def open_operator_dialog(self, comp_item: RTLComponentItem):
        comp = comp_item.model
        dlg = OperatorPropertiesDialog(comp, self)
        if dlg.exec():
            self.scene.push_undo_state()
            sym, is_red, is_unary, out_1bit = dlg.get_selected_op_info()
            new_size = dlg.get_size()
            new_rot = dlg.get_rotation()
            lbl = dlg.get_label()

            comp.label = lbl
            comp.width = new_size
            comp.height = new_size
            comp.properties["op"] = sym
            comp.properties["rotation"] = str(new_rot)
            if is_red:
                comp.properties["is_reduction"] = "True"
                comp.properties.pop("is_unary", None)
            elif is_unary:
                comp.properties["is_unary"] = "True"
                comp.properties.pop("is_reduction", None)
            else:
                comp.properties.pop("is_reduction", None)
                comp.properties.pop("is_unary", None)

            if new_rot == 90:
                in_side, out_side = PinSide.TOP, PinSide.BOTTOM
            elif new_rot == 180:
                in_side, out_side = PinSide.RIGHT, PinSide.LEFT
            elif new_rot == 270:
                in_side, out_side = PinSide.BOTTOM, PinSide.TOP
            else: # 0
                in_side, out_side = PinSide.LEFT, PinSide.RIGHT

            if getattr(comp, "mirrored", False):
                in_side, out_side = out_side, in_side

            new_pins = []
            if is_red or is_unary:
                new_pins.append(RTLPin(
                    id=f"{comp.id}_a", name="A", direction=PinDirection.IN,
                    side=in_side, offset=0.5, width=1
                ))
                new_pins.append(RTLPin(
                    id=f"{comp.id}_out", name="out", direction=PinDirection.OUT,
                    side=out_side, offset=0.5, width=1
                ))
            else:
                new_pins.append(RTLPin(
                    id=f"{comp.id}_a", name="A", direction=PinDirection.IN,
                    side=in_side, offset=0.25, width=1
                ))
                new_pins.append(RTLPin(
                    id=f"{comp.id}_b", name="B", direction=PinDirection.IN,
                    side=in_side, offset=0.75, width=1
                ))
                new_pins.append(RTLPin(
                    id=f"{comp.id}_out", name="out", direction=PinDirection.OUT,
                    side=out_side, offset=0.5, width=1
                ))

            new_pin_ids = {p.id for p in new_pins}
            wires_to_remove = [
                w.id for w in self.scene.schematic.wires
                if (w.source_comp_id == comp.id and w.source_pin_id not in new_pin_ids) or
                   (w.target_comp_id == comp.id and w.target_pin_id not in new_pin_ids)
            ]
            for w_id in wires_to_remove:
                self.scene.remove_wire(w_id)

            comp.pins = new_pins
            comp_item.prepareGeometryChange()
            comp_item.rebuild_pins()
            for w_item in self.scene.wire_items.values():
                w = w_item.model
                if w.source_comp_id == comp.id or w.target_comp_id == comp.id:
                    w.manual_routing = False
            if hasattr(self.scene, "on_component_moved"):
                self.scene.on_component_moved(comp_item)
            comp_item.update()
            self.lbl_status.setText(f"Operador circular '{comp.label}' actualizado ({int(new_size)}px, {new_rot}°).")

    def open_port_dialog(self, comp_item: RTLComponentItem):
        comp = comp_item.model
        dlg = RTLPortConfigDialog(comp, schematic_params=self.scene.schematic.parameters, parent=self)
        if dlg.exec():
            self.scene.push_undo_state()
            new_name = dlg.edit_name.text().strip()
            if new_name:
                comp.label = new_name
            new_w = dlg.spin_width.value()
            param_name = dlg.combo_param.currentData()

            comp.properties["bus_width"] = str(new_w)
            if param_name:
                comp.properties["bus_width_param"] = param_name
            else:
                comp.properties.pop("bus_width_param", None)

            for pin in comp.pins:
                pin.width = new_w
                pin.width_param = param_name

            # Synchronize bit width of wires connected to this port
            for w in self.scene.schematic.wires:
                if (w.source_comp_id == comp.id) or (w.target_comp_id == comp.id):
                    w.width = new_w
                    w.width_param = param_name

            comp_item.prepareGeometryChange()
            comp_item.update()
            for pi in comp_item.pin_items:
                pi.update_position()
                pi.update()
            for w_item in self.scene.wire_items.values():
                w_item.prepareGeometryChange()
                w_item.update()

            self.lbl_status.setText(f"Puerto '{comp.label}' actualizado ({new_w} bits).")

    def _get_spawn_pos(self, offset_x=0.0, offset_y=0.0) -> Tuple[float, float]:
        center = self.view.mapToScene(self.view.viewport().rect().center())
        base_x = round((center.x() + offset_x) / 20.0) * 20.0
        base_y = round((center.y() + offset_y) / 20.0) * 20.0
        cur_x, cur_y = base_x, base_y
        while any(snap(c.x) == cur_x and snap(c.y) == cur_y for c in self.scene.schematic.components):
            cur_x += 40.0
            cur_y += 40.0
        return cur_x, cur_y

    def spawn_input_port(self):
        name, ok = QInputDialog.getText(
            self, "Agregar Puerto de Entrada",
            "Nombre del puerto (ej: clk_100M, rst, data_in[7:0]):",
            text="clk_100M"
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        width = parse_slice_width(name)
        x, y = self._get_spawn_pos(offset_x=-200.0, offset_y=0.0)
        comp = ComponentFactory.create_input_port(x, y, name=name, width=width)
        item = self.scene.add_component(comp)
        self.lbl_status.setText(f"Puerto de entrada '{name}' ({width} bit{'s' if width > 1 else ''}) agregado.")

    def spawn_output_port(self):
        name, ok = QInputDialog.getText(
            self, "Agregar Puerto de Salida",
            "Nombre del puerto (ej: out, anodes[7:0], segments[7:0]):",
            text="anodes[7:0]"
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        width = parse_slice_width(name)
        x, y = self._get_spawn_pos(offset_x=200.0, offset_y=0.0)
        comp = ComponentFactory.create_output_port(x, y, name=name, width=width)
        item = self.scene.add_component(comp)
        self.lbl_status.setText(f"Puerto de salida '{name}' ({width} bit{'s' if width > 1 else ''}) agregado.")

    def spawn_mux(self):
        x, y = self._get_spawn_pos()
        comp = ComponentFactory.create_mux(x, y, num_inputs=2, width=1, label="MUX")
        item = self.scene.add_component(comp)
        self.open_mux_dialog(item)

    def spawn_register(self):
        name, ok_n = QInputDialog.getText(self, "Configurar Registro", "Nombre o Etiqueta:", text="Reg")
        if not ok_n: return
        x, y = self._get_spawn_pos()
        comp = ComponentFactory.create_register(x, y, width=1, label=name.strip() or "Reg")
        self.scene.add_component(comp)
        self.lbl_status.setText("Registro agregado.")

    def spawn_operator(self):
        x, y = self._get_spawn_pos()
        comp = ComponentFactory.create_operator(x, y, op="+", width=1, size=60.0)
        item = self.scene.add_component(comp)
        self.open_operator_dialog(item)

    def spawn_gate(self):
        gate, ok = QInputDialog.getItem(self, "Compuerta Lógica", "Tipo:", ["AND", "OR", "NOT", "XOR"], 0, False)
        if not ok: return
        x, y = self._get_spawn_pos()
        comp = ComponentFactory.create_gate(x, y, gate_type=gate)
        self.scene.add_component(comp)
        self.lbl_status.setText(f"Compuerta {gate} agregada.")

    def spawn_splitter(self):
        x, y = self._get_spawn_pos()
        comp = ComponentFactory.create_bus_splitter(x, y, in_width=16, slices="[2:0], [3], [15:4]")
        item = self.scene.add_component(comp)
        self.open_splitter_dialog(item)

    def spawn_constant(self):
        val, ok = QInputDialog.getText(self, "Valor Constante", "Constante HDL (ej: 1'b0, 4'd1, 8'hFF):", text="4'd1")
        if not ok: return
        x, y = self._get_spawn_pos()
        comp = ComponentFactory.create_constant(x, y, val=val)
        self.scene.add_component(comp)
        self.lbl_status.setText(f"Constante {val} agregada.")

    def spawn_block(self):
        name, ok = QInputDialog.getText(self, "Bloque Funcional", "Nombre del Módulo:", text="ControlUnit")
        if not ok: return
        x, y = self._get_spawn_pos()
        comp = ComponentFactory.create_generic_block(x, y, name=name)
        self.scene.add_component(comp)
        self.lbl_status.setText("Bloque genérico agregado.")

    def add_solder_dot(self):
        x, y = self._get_spawn_pos()
        self.scene.add_junction_at(QPointF(x, y))
        self.lbl_status.setText(f"Solder dot agregado en ({int(x)}, {int(y)}). Arrástrelo sobre el cruce deseado.")

    def scene_delete_selected(self):
        self.scene.remove_selected()

    def clear_canvas(self):
        ans = QMessageBox.question(self, "Confirmar", "¿Desea limpiar todo el canvas?", QMessageBox.Yes | QMessageBox.No)
        if ans == QMessageBox.Yes:
            self.scene.clear()
            self.scene.schematic = RTLSchematic()
            self.scene.comp_items.clear()
            self.scene.wire_items.clear()
            self.scene.junction_items.clear()

    def load_counter_example(self):
        """Loads canonical 4-bit accumulator/counter from ELO212 slide 5, 7 & 9"""
        self.scene.clear()
        self.scene.schematic = RTLSchematic(name="contador_incremental_4bit")
        self.scene.comp_items.clear()
        self.scene.wire_items.clear()
        self.scene.junction_items.clear()

        # Constant 4'd1 (80x40): out at (120, 180)
        c = ComponentFactory.create_constant(40, 160, val="4'd1", width=4)
        # Adder circle '+' (80x80): B at (180, 180) -> matches Constant out! out at (260, 160)
        adder = ComponentFactory.create_operator(180, 120, op="+", width=4, size=80.0)
        # Register 4-bit (80x80): D at (380, 160) -> matches Adder out!
        reg = ComponentFactory.create_register(380, 120, width=4, label="Count")

        self.scene.add_component(c)
        self.scene.add_component(adder)
        self.scene.add_component(reg)

        # Wire 1: Constant to Adder B (100% straight horizontal line at y=180)
        p_c = self.scene.comp_items[c.id].pin_items[0].scenePos()
        p_b = self.scene.comp_items[adder.id].pin_items[1].scenePos()
        pts1 = compute_manhattan_path(p_c, PinSide.RIGHT, p_b, PinSide.LEFT)
        w1 = RTLWire(
            id="w_const",
            source_comp_id=c.id, source_pin_id=c.pins[0].id,
            target_comp_id=adder.id, target_pin_id=adder.pins[1].id, # pin B
            points=pts1,
            width=4, label="4'd1",
            show_arrow=True
        )
        self.scene.schematic.wires.append(w1)
        item1 = RTLWireItem(w1)
        self.scene.addItem(item1)
        self.scene.wire_items[w1.id] = item1

        # Wire 2: Adder out to Reg D (100% straight horizontal line at y=160)
        p_out = self.scene.comp_items[adder.id].pin_items[2].scenePos()
        p_d = self.scene.comp_items[reg.id].pin_items[0].scenePos()
        pts2 = compute_manhattan_path(p_out, PinSide.RIGHT, p_d, PinSide.LEFT)
        w2 = RTLWire(
            id="w_sum",
            source_comp_id=adder.id, source_pin_id=adder.pins[2].id,
            target_comp_id=reg.id, target_pin_id=reg.pins[0].id, # pin D
            points=pts2,
            width=4, label="next_count[3:0]"
        )
        self.scene.schematic.wires.append(w2)
        item2 = RTLWireItem(w2)
        self.scene.addItem(item2)
        self.scene.wire_items[w2.id] = item2

        # Wire 3: Feedback from Reg Q back to Adder A (ELO212 slide 5 Figure 4)
        p_q = self.scene.comp_items[reg.id].pin_items[1].scenePos()
        p_a = self.scene.comp_items[adder.id].pin_items[0].scenePos()
        pts3 = compute_manhattan_path(p_q, PinSide.RIGHT, p_a, PinSide.LEFT)
        w3 = RTLWire(
            id="w_feedback",
            source_comp_id=reg.id, source_pin_id=reg.pins[1].id, # pin Q
            target_comp_id=adder.id, target_pin_id=adder.pins[0].id, # pin A
            points=pts3,
            width=4, label="Count[3:0]",
            show_arrow=True
        )
        self.scene.schematic.wires.append(w3)
        item3 = RTLWireItem(w3)
        self.scene.addItem(item3)
        self.scene.wire_items[w3.id] = item3

        self.view.centerOn(260, 160)
        self.lbl_status.setText("Ejemplo canónico de ELO212 (Contador con Sumador y Realimentación) cargado.")
