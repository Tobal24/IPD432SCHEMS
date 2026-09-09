"""
RTL Schematic Editor Widget for ELO212.
Provides component palette, canvas with snap-to-grid, wire property editing,
and quick example loading.
"""

import json
from typing import Optional, List, Tuple
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QGroupBox,
    QPushButton, QLabel, QLineEdit, QSpinBox, QComboBox,
    QFormLayout, QMessageBox, QInputDialog, QDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget, QCheckBox
)
from app.core.rtl_model import (
    RTLSchematic, RTLComponent, RTLWire, RTLPin, ComponentFactory,
    ComponentType, PinSide, PinDirection
)
from app.gui.rtl_canvas import RTLGraphicsScene, RTLGraphicsView, compute_manhattan_path
from app.gui.rtl_items import RTLComponentItem, RTLWireItem


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

        cur_width = int(self.comp.properties.get("bus_width", "1"))
        self.spin_width = QSpinBox()
        self.spin_width.setRange(1, 128)
        self.spin_width.setValue(cur_width)

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
        form_gen.addRow("Ancho de bus de datos:", self.spin_width)
        form_gen.addRow("Número de entradas:", self.spin_num_inputs)
        form_gen.addRow("Ubicación de 'sel':", self.combo_sel_side)
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
        # Left Panel: Component Palette & Tools
        # -------------------------------------------------------------
        palette_panel = QWidget()
        pal_layout = QVBoxLayout(palette_panel)

        # Standards reminder
        box_guide = QGroupBox("Normas ELO212")
        g_layout = QVBoxLayout(box_guide)
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

        btn_mux = QPushButton("➕ Multiplexor (MUX)")
        btn_reg = QPushButton("➕ Registro / Flip-Flop")
        btn_op = QPushButton("➕ Operador Circular (+, >)")
        btn_gate = QPushButton("➕ Compuerta Lógica")
        btn_split = QPushButton("➕ Desagregador de Bus")
        btn_const = QPushButton("➕ Constante (1'b0, 4'd1)")
        btn_block = QPushButton("➕ Bloque Genérico")

        btn_mux.clicked.connect(self.spawn_mux)
        btn_reg.clicked.connect(self.spawn_register)
        btn_op.clicked.connect(self.spawn_operator)
        btn_gate.clicked.connect(self.spawn_gate)
        btn_split.clicked.connect(self.spawn_splitter)
        btn_const.clicked.connect(self.spawn_constant)
        btn_block.clicked.connect(self.spawn_block)

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
        self.spin_wire_width = QSpinBox()
        self.spin_wire_width.setRange(1, 128)
        self.spin_wire_width.setValue(1)
        self.edit_wire_label = QLineEdit()
        self.edit_wire_label.setPlaceholderText("ej: bus_ej[5:0]")
        self.check_wire_arrow = QCheckBox("Mostrar flecha de dirección (➡️)")

        btn_apply_wire = QPushButton("Aplicar al Cable Seleccionado")
        btn_apply_wire.clicked.connect(self.apply_wire_props)

        p_form.addRow("Ancho de bits:", self.spin_wire_width)
        p_form.addRow("Etiqueta:", self.edit_wire_label)
        p_form.addRow(self.check_wire_arrow)
        p_form.addRow(btn_apply_wire)
        pal_layout.addWidget(box_props)

        # Canvas Actions
        box_actions = QGroupBox("Acciones del Canvas")
        act_layout = QVBoxLayout(box_actions)

        btn_reroute = QPushButton("🔄 Re-enrutar Cable (R)")
        btn_relabel = QPushButton("🏷️ Restablecer Etiquetas (Shift+R)")
        btn_edit_block = QPushButton("⚙️ Configurar Componente")
        btn_edit_block.setToolTip("Configurar propiedades del bloque funcional, MUX o desagregador seleccionado")
        btn_solder = QPushButton("⚫ Colocar Solder Dot (Junction)")
        btn_del = QPushButton("🗑️ Eliminar Seleccionado (Supr)")
        btn_example = QPushButton("🔄 Cargar Ejemplo: Contador + Sumador")
        btn_clear = QPushButton("⚠️ Limpiar Todo")

        btn_reroute.clicked.connect(self.scene.reset_selected_wire_routing)
        btn_relabel.clicked.connect(self.scene.reset_selected_labels)
        btn_edit_block.clicked.connect(self.edit_selected_block)
        btn_solder.clicked.connect(self.add_solder_dot)
        btn_del.clicked.connect(self.scene_delete_selected)
        btn_example.clicked.connect(self.load_counter_example)
        btn_clear.clicked.connect(self.clear_canvas)

        act_layout.addWidget(btn_reroute)
        act_layout.addWidget(btn_relabel)
        act_layout.addWidget(btn_edit_block)
        act_layout.addWidget(btn_solder)
        act_layout.addWidget(btn_del)
        act_layout.addWidget(btn_example)
        act_layout.addWidget(btn_clear)
        pal_layout.addWidget(box_actions)

        pal_layout.addStretch()
        palette_panel.setMaximumWidth(280)
        splitter.addWidget(palette_panel)

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

    def _on_selection_changed(self):
        sel = self.scene.selectedItems()
        for item in sel:
            w_item = item if isinstance(item, RTLWireItem) else getattr(item, "wire_item", None)
            if isinstance(w_item, RTLWireItem):
                self.spin_wire_width.setValue(w_item.model.width)
                self.edit_wire_label.setText(w_item.model.label)
                self.check_wire_arrow.setChecked(w_item.model.show_arrow)
                break

    def apply_wire_props(self):
        sel = self.scene.selectedItems()
        applied = False
        for item in sel:
            w_item = item if isinstance(item, RTLWireItem) else getattr(item, "wire_item", None)
            if isinstance(w_item, RTLWireItem):
                self.scene.push_undo_state()
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
        QMessageBox.information(self, "Aviso", "Seleccione un bloque, multiplexor o desagregador para configurar.")

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
            bus_w = dlg.spin_width.value()
            sel_side_str = dlg.get_sel_side()
            s_side = PinSide.TOP if sel_side_str == "TOP" else PinSide.BOTTOM

            max_label_len = max((len(n) for n in input_names), default=1)
            comp.width = max(70.0, 40.0 + max_label_len * 9.0 + 20.0)
            comp.height = max(80.0, num_inputs * 30.0)
            comp.properties["num_inputs"] = str(num_inputs)
            comp.properties["bus_width"] = str(bus_w)
            comp.properties["input_names"] = json.dumps(input_names)
            comp.properties["sel_side"] = sel_side_str

            new_pins = []
            for i, in_name in enumerate(input_names):
                offset = (i + 1) / (num_inputs + 1)
                new_pins.append(RTLPin(
                    id=f"{comp.id}_in_{i}",
                    name=in_name,
                    direction=PinDirection.IN,
                    side=PinSide.LEFT,
                    offset=offset,
                    width=bus_w
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
                width=bus_w
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
            new_pins = [
                RTLPin(id=f"{comp.id}_in", name=in_name, direction=PinDirection.IN, side=PinSide.LEFT, offset=0.5, width=in_w)
            ]
            for idx, s in enumerate(slice_list):
                offset = (idx + 1) / (len(slice_list) + 1)
                swidth = parse_slice_width(s)
                slice_label = f"{base_name}{s}" if base_name and not s.startswith(base_name) else s
                new_pins.append(RTLPin(
                    id=f"{comp.id}_out_{idx}",
                    name=slice_label,
                    direction=PinDirection.OUT,
                    side=PinSide.RIGHT,
                    offset=offset,
                    width=swidth
                ))
            comp.label = base_name or "SPLIT"
            max_s_len = max((len(p.name) for p in new_pins), default=5)
            comp.width = max(110.0, 45.0 + max_s_len * 8.0)
            comp.height = max(70.0, len(slice_list) * 40.0)
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

    def spawn_mux(self):
        comp = ComponentFactory.create_mux(0, 0, num_inputs=2, width=1, label="MUX")
        item = self.scene.add_component(comp)
        self.open_mux_dialog(item)

    def spawn_register(self):
        width, ok = QInputDialog.getInt(self, "Configurar Registro / Flip-Flop", "Ancho de bits:", 1, 1, 64, 1)
        if not ok: return
        name, ok_n = QInputDialog.getText(self, "Configurar Registro", "Nombre o Etiqueta:", text="Reg")
        if not ok_n: return
        comp = ComponentFactory.create_register(0, 0, width=width, label=name.strip() or "Reg")
        self.scene.add_component(comp)
        self.lbl_status.setText("Registro agregado.")

    def spawn_operator(self):
        op, ok = QInputDialog.getItem(self, "Operador Aritmético", "Operación:", ["+", "-", "*", "A>B", "A==B", "<<", ">>"], 0, False)
        if not ok: return
        width, ok2 = QInputDialog.getInt(self, "Operador", "Ancho de bits:", 4, 1, 64, 1)
        if not ok2: return
        comp = ComponentFactory.create_operator(0, 0, op=op, width=width)
        self.scene.add_component(comp)
        self.lbl_status.setText("Operador agregado.")

    def spawn_gate(self):
        gate, ok = QInputDialog.getItem(self, "Compuerta Lógica", "Tipo:", ["AND", "OR", "NOT", "XOR"], 0, False)
        if not ok: return
        comp = ComponentFactory.create_gate(0, 0, gate_type=gate)
        self.scene.add_component(comp)
        self.lbl_status.setText(f"Compuerta {gate} agregada.")

    def spawn_splitter(self):
        comp = ComponentFactory.create_bus_splitter(0, 0, in_width=16, slices="[2:0], [3], [15:4]")
        item = self.scene.add_component(comp)
        self.open_splitter_dialog(item)

    def spawn_constant(self):
        val, ok = QInputDialog.getText(self, "Valor Constante", "Constante HDL (ej: 1'b0, 4'd1, 8'hFF):", text="4'd1")
        if not ok: return
        comp = ComponentFactory.create_constant(0, 0, val=val)
        self.scene.add_component(comp)
        self.lbl_status.setText(f"Constante {val} agregada.")

    def spawn_block(self):
        name, ok = QInputDialog.getText(self, "Bloque Funcional", "Nombre del Módulo:", text="ControlUnit")
        if not ok: return
        comp = ComponentFactory.create_generic_block(0, 0, name=name)
        self.scene.add_component(comp)
        self.lbl_status.setText("Bloque genérico agregado.")

    def add_solder_dot(self):
        self.scene.add_junction_at(QPointF(100, 100))
        self.lbl_status.setText("Solder dot agregado en (100, 100). Arrástrelo sobre el cruce deseado.")

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

        # Constant 4'd1
        c = ComponentFactory.create_constant(40, 140, val="4'd1", width=4)
        # Adder circle '+'
        adder = ComponentFactory.create_operator(160, 120, op="+", width=4)
        # Register 4-bit
        reg = ComponentFactory.create_register(360, 100, width=4, label="Count")

        self.scene.add_component(c)
        self.scene.add_component(adder)
        self.scene.add_component(reg)

        # Wire 1: Constant to Adder B
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

        # Wire 2: Adder out to Reg D
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

        self.view.centerOn(240, 140)
        self.lbl_status.setText("Ejemplo canónico de ELO212 (Contador con Sumador y Realimentación) cargado.")
