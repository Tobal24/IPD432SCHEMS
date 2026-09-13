"""
Main Window for the ELO212 & IPD432 Digital Design Suite.
Integrates RTL Schematic Editor and FSM Designer tabs,
file persistence, vector/raster export, and academic rules reference.
"""

import json
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon, QFont
from PySide6.QtWidgets import (
    QMainWindow, QTabWidget, QFileDialog, QMessageBox,
    QDialog, QVBoxLayout, QTextBrowser, QPushButton
)
from app.gui.rtl_view import RTLEditorWidget
from app.gui.fsm_view import FSMDesignerWidget
from app.gui.export_dialog import DiagramExporter


GUIDELINES_ELO212 = """
<h2>Convenciones para Esquemáticos y Diagramas RTL (ELO212 - USM)</h2>
<p>Los diagramas en este curso <b>no son ilustraciones artísticas</b>, sino especificaciones formales y planos de construcción.</p>

<h3>1. Orientación de Entradas y Salidas</h3>
<ul>
  <li><b>Entradas:</b> Siempre se dibujan a la <b>izquierda</b> del bloque.</li>
  <li><b>Salidas:</b> Siempre se dibujan a la <b>derecha</b> del bloque.</li>
  <li><b>Señales de Control:</b> Reloj (<code>clk</code>), reset (<code>rst</code>), habilitación (<code>CE</code>) y selección de MUX suelen ubicarse arriba o abajo.</li>
  <li>Si se invierte esta dirección (ej: lazos de realimentación), <b>es obligatorio usar flechas direccionales</b>.</li>
</ul>

<h3>2. Cables y Trazado de Señales</h3>
<ul>
  <li>Los cables deben ser <b>estrictamente ortogonales</b> (solo tramos horizontales o verticales).</li>
  <li><b>Prohibido:</b> Trazos diagonales o curvas.</li>
  <li><b>Ancho de Bits:</b> Si no se indica ancho, se asume 1 bit. Para buses (> 1 bit), debe marcarse una <b>barra diagonal <code>/N</code></b> con el número de bits o corchetes <code>bus[N:0]</code>.</li>
</ul>

<h3>3. Cruces e Intersecciones</h3>
<ul>
  <li>Dos cables que se cruzan <b>NO están conectados</b> a menos que tengan un <b>punto de conexión (solder dot)</b> explícito.</li>
  <li>No use saltos o puentes curvos; mantenga el trazo recto continuo.</li>
</ul>

<h3>4. Primitivas Obligatorias</h3>
<ul>
  <li><b>Multiplexores:</b> Forma trapezoidal con entradas por el lado ancho y salida por el angosto. Entradas claramente indexadas (0, 1...).</li>
  <li><b>Flip-Flops y Registros:</b> Caja rectangular con entrada D a la izquierda, salida Q a la derecha, pin de reloj con <b>símbolo triangular (^)</b> y pin de reset rotulado.</li>
  <li><b>Desagregador de Bus:</b> Línea perpendicular al bus principal de la cual emergen los subgrupos (ej: <code>[2:0], [3], [15:4]</code>).</li>
  <li><b>Constantes:</b> Valores explícitos como <code>1'b0</code>, <code>4'd1</code>, <code>8'hFF</code> (no dejar entradas flotantes).</li>
</ul>
"""

GUIDELINES_IPD432 = """
<h2>Guía de Diseño de Máquinas de Estados Finitos (IPD432 - USM)</h2>

<h3>1. Principios Fundamentales</h3>
<ul>
  <li><b>Completitud:</b> Todos los estados deben tener transiciones de salida totalmente especificadas.</li>
  <li><b>Mutua Exclusión:</b> Para cualquier combinación de entradas, exactamente un arco de transición debe ser válido (transiciones complementarias).</li>
  <li><b>Estado de Reset:</b> Flecha de reset externa apuntando al estado inicial.</li>
</ul>

<h3>2. Notación Gráfica</h3>
<ul>
  <li><b>Máquinas de Moore:</b> Salidas dentro del círculo del estado (círculo dividido con línea horizontal: arriba Estado, abajo Salidas).</li>
  <li><b>Máquinas de Mealy:</b> Salidas sobre las flechas de transición en formato <code>condición / salidas</code>.</li>
  <li><b>Transiciones Temporizadas:</b> Formato <code>t = T - 1</code> asociado a un contador sincrónico.</li>
</ul>

<h3>3. Buenas Prácticas en SystemVerilog (Anti-Latches)</h3>
<ul>
  <li><b>Estructura canónica de 2 bloques always:</b> Un <code>always_ff</code> para el registro de estado y un <code>always_comb</code> para el estado siguiente y salidas.</li>
  <li><b>Asignación por Defecto al inicio de <code>always_comb</code>:</b><br/>
    <code>NextState = State;</code> y asignación por defecto a todas las salidas. <i>¡La última asignación gana y previene la inferencia accidental de latches!</i></li>
  <li><b>Tipos Enumerados:</b> Usar <code>typedef enum logic [k-1:0] {...} state_t;</code> con nombres simbólicos claros.</li>
</ul>
"""


class HelpRulesDialog(QDialog):
    def __init__(self, title: str, html_content: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(650, 500)
        layout = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setHtml(html_content)
        layout.addWidget(browser)
        btn_close = QPushButton("Entendido")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Suite de Diseño Digital RTL & FSM (ELO212 / IPD432 - USM)")
        self.resize(1280, 850)

        self.tab_widget = QTabWidget()
        self.tab_rtl = RTLEditorWidget()
        self.tab_fsm = FSMDesignerWidget()

        self.tab_widget.addTab(self.tab_rtl, "📐 Editor Esquemático RTL (ELO212)")
        self.tab_widget.addTab(self.tab_fsm, "🔄 Diseñador y Validador FSM (IPD432)")

        self.setCentralWidget(self.tab_widget)
        self._create_menus()

    def _create_menus(self):
        menubar = self.menuBar()

        # Menu Archivo
        menu_file = menubar.addMenu("&Archivo")

        act_save_proj = QAction("Guardar Proyecto Completo (.json)...", self)
        act_save_proj.setShortcut("Ctrl+S")
        act_save_proj.triggered.connect(self.save_project)
        menu_file.addAction(act_save_proj)

        act_load_proj = QAction("Abrir Proyecto (.json)...", self)
        act_load_proj.setShortcut("Ctrl+O")
        act_load_proj.triggered.connect(self.load_project)
        menu_file.addAction(act_load_proj)

        menu_file.addSeparator()

        act_export_svg = QAction("Exportar Diagrama Activo a SVG...", self)
        act_export_svg.triggered.connect(self.export_active_svg)
        menu_file.addAction(act_export_svg)

        act_export_png = QAction("Exportar Diagrama Activo a PNG (Alta Res)...", self)
        act_export_png.triggered.connect(self.export_active_png)
        menu_file.addAction(act_export_png)

        menu_file.addSeparator()
        act_exit = QAction("Salir", self)
        act_exit.triggered.connect(self.close)
        menu_file.addAction(act_exit)

        # Menu Editar
        menu_edit = menubar.addMenu("&Editar")
        act_undo = QAction("Deshacer", self)
        act_undo.setShortcut("Ctrl+Z")
        act_undo.triggered.connect(self.undo_active)
        menu_edit.addAction(act_undo)

        act_redo = QAction("Rehacer", self)
        act_redo.setShortcut("Ctrl+Y")
        act_redo.triggered.connect(self.redo_active)
        menu_edit.addAction(act_redo)

        # Menu Ayuda
        menu_help = menubar.addMenu("A&yuda y Normas")
        act_rules_elo = QAction("Reglas de Esquemáticos ELO212...", self)
        act_rules_elo.triggered.connect(lambda: HelpRulesDialog("Normas ELO212", GUIDELINES_ELO212, self).exec())
        menu_help.addAction(act_rules_elo)

        act_rules_ipd = QAction("Reglas de FSMs IPD432...", self)
        act_rules_ipd.triggered.connect(lambda: HelpRulesDialog("Normas IPD432", GUIDELINES_IPD432, self).exec())
        menu_help.addAction(act_rules_ipd)

        menu_help.addSeparator()
        act_about = QAction("Acerca de", self)
        act_about.triggered.connect(self.show_about)
        menu_help.addAction(act_about)

    def undo_active(self):
        if self.tab_widget.currentIndex() == 0:
            self.tab_rtl.scene.undo()

    def redo_active(self):
        if self.tab_widget.currentIndex() == 0:
            self.tab_rtl.scene.redo()

    def export_active_svg(self):
        curr_idx = self.tab_widget.currentIndex()
        if curr_idx == 0:
            DiagramExporter.export_svg(self.tab_rtl.scene, self, default_name="esquematico_rtl.svg")
        else:
            DiagramExporter.export_svg(self.tab_fsm.fsm_scene, self, default_name="diagrama_fsm.svg")

    def export_active_png(self):
        curr_idx = self.tab_widget.currentIndex()
        if curr_idx == 0:
            DiagramExporter.export_png(self.tab_rtl.scene, self, default_name="esquematico_rtl.png")
        else:
            DiagramExporter.export_png(self.tab_fsm.fsm_scene, self, default_name="diagrama_fsm.png")

    def save_project(self):
        path, _ = QFileDialog.getSaveFileName(self, "Guardar Proyecto", "proyecto_digital.json", "Archivos JSON (*.json)")
        if not path:
            return

        proj_data = {
            "version": "1.0",
            "rtl": self.tab_rtl.scene.schematic.to_dict(),
            "fsm": self.tab_fsm.fsm.to_dict()
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(proj_data, f, indent=2, ensure_ascii=False)
        QMessageBox.information(self, "Guardado", f"Proyecto guardado exitosamente en:\n{path}")

    def load_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Abrir Proyecto", "", "Archivos JSON (*.json)")
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                proj_data = json.load(f)

            if "fsm" in proj_data:
                from app.core.fsm_model import FSM
                self.tab_fsm.fsm = FSM.from_dict(proj_data["fsm"])
                self.tab_fsm.fsm_scene.fsm = self.tab_fsm.fsm
                self.tab_fsm.refresh_all()

            if "rtl" in proj_data:
                from app.core.rtl_model import RTLSchematic
                from app.gui.rtl_items import RTLComponentItem, RTLWireItem, RTLJunctionItem
                sch = RTLSchematic.from_dict(proj_data["rtl"])
                scene = self.tab_rtl.scene
                scene.clear()
                scene.schematic = sch
                scene.comp_items.clear()
                scene.wire_items.clear()
                scene.junction_items.clear()

                for c in sch.components:
                    item = RTLComponentItem(c)
                    scene.addItem(item)
                    scene.comp_items[c.id] = item

                for w in sch.wires:
                    item = RTLWireItem(w)
                    scene.addItem(item)
                    scene.wire_items[w.id] = item

                for j in sch.junctions:
                    item = RTLJunctionItem(j.x, j.y, j.id)
                    scene.addItem(item)
                    scene.junction_items[j.id] = item

            QMessageBox.information(self, "Cargado", "Proyecto cargado exitosamente.")
        except Exception as e:
            QMessageBox.critical(self, "Error al cargar", f"No se pudo cargar el archivo:\n{str(e)}")

    def show_about(self):
        QMessageBox.about(
            self,
            "Acerca de la Suite de Diseño",
            "<h3>Suite de Diseño Digital RTL & FSM</h3>"
            "<p>Diseñada específicamente según los requerimientos de <b>ELO212</b> e <b>IPD432</b> (USM 2026).</p>"
            "<p>Permite generar diagramas formales sin ambigüedades, verificar FSMs para evitar inferencia de latches y exportar código SystemVerilog canónico.</p>"
        )
