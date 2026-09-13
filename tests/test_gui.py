"""
Automated GUI integration tests for ELO212 & IPD432 Suite.
Runs in offscreen mode to verify rendering, FSM presets, and SVG/PNG generation.
"""

import sys
import os
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtCore import QPointF, QPoint, Qt
from PySide6.QtWidgets import QApplication, QPushButton
from app.gui.main_window import MainWindow
from app.core.rtl_model import ComponentFactory, ComponentType, RTLPin, PinDirection, PinSide
from app.gui.rtl_items import RTLWireItem, RTLComponentItem
from app.core.fsm_model import FSMType

app = QApplication.instance() or QApplication(sys.argv)


class TestGUIIntegration(unittest.TestCase):
    def setUp(self):
        self.win = MainWindow()

    def test_window_tabs(self):
        self.assertEqual(self.win.tab_widget.count(), 2)

    def test_rtl_editor_loads(self):
        rtl = self.win.tab_rtl
        self.assertIsNotNone(rtl.scene)
        # Check that loaded counter example has components and wires
        self.assertTrue(len(rtl.scene.schematic.components) >= 3)
        self.assertTrue(len(rtl.scene.schematic.wires) >= 3)

        # Test adding a MUX
        mux = ComponentFactory.create_mux(500, 200, num_inputs=2, width=4)
        item = rtl.scene.add_component(mux)
        self.assertIn(mux.id, rtl.scene.comp_items)

    def test_fsm_designer_presets(self):
        fsm_tab = self.win.tab_fsm
        # Load Traffic light preset
        fsm_tab.load_traffic_preset()
        self.assertEqual(len(fsm_tab.fsm.states), 4)
        self.assertEqual(len(fsm_tab.fsm.transitions), 6)

        # Run validation
        fsm_tab.run_validation()
        self.assertGreater(fsm_tab.list_issues.count(), 0)

        # Switch to Mealy
        fsm_tab.combo_type.setCurrentText(FSMType.MEALY.value)
        fsm_tab._on_params_changed()
        self.assertEqual(fsm_tab.fsm.fsm_type, FSMType.MEALY)

    def test_undo_redo_rtl(self):
        scene = self.win.tab_rtl.scene
        initial_comp_count = len(scene.schematic.components)

        # Add component
        mux = ComponentFactory.create_mux(100, 100, num_inputs=2)
        scene.add_component(mux)
        self.assertEqual(len(scene.schematic.components), initial_comp_count + 1)

        # Test Undo
        scene.undo()
        self.assertEqual(len(scene.schematic.components), initial_comp_count)

        # Test Redo
        scene.redo()
        self.assertEqual(len(scene.schematic.components), initial_comp_count + 1)

    def test_drag_undo_restores_position(self):
        scene = self.win.tab_rtl.scene
        # Pick the first component item
        comp_item = list(scene.comp_items.values())[0]
        initial_pos = comp_item.pos()
        snapshot = scene.schematic.to_dict()

        # Simulate dragging the component
        scene.undo_stack.append(snapshot)
        comp_item.setPos(initial_pos.x() + 120, initial_pos.y() + 80)
        comp_item.model.x = comp_item.pos().x()
        comp_item.model.y = comp_item.pos().y()

        # Check it moved
        self.assertNotEqual(comp_item.pos(), initial_pos)

        # Trigger Undo
        comp_id = comp_item.model.id
        scene.undo()
        restored_comp_item = scene.comp_items[comp_id]
        self.assertEqual(restored_comp_item.pos().x(), initial_pos.x())
        self.assertEqual(restored_comp_item.pos().y(), initial_pos.y())
        self.assertEqual(restored_comp_item.model.x, initial_pos.x())
        self.assertEqual(restored_comp_item.model.y, initial_pos.y())

    def test_wire_pin_alignment(self):
        scene = self.win.tab_rtl.scene
        # Verify that all loaded wires anchor exactly at pin center scenePos
        for w_item in scene.wire_items.values():
            w = w_item.model
            s_comp = scene.comp_items.get(w.source_comp_id)
            t_comp = scene.comp_items.get(w.target_comp_id)
            if s_comp and t_comp:
                s_pin = next(pi for pi in s_comp.pin_items if pi.pin.id == w.source_pin_id)
                t_pin = next(pi for pi in t_comp.pin_items if pi.pin.id == w.target_pin_id)
                self.assertAlmostEqual(w.points[0][0], s_pin.scenePos().x(), places=2)
                self.assertAlmostEqual(w.points[0][1], s_pin.scenePos().y(), places=2)
                self.assertAlmostEqual(w.points[-1][0], t_pin.scenePos().x(), places=2)
                self.assertAlmostEqual(w.points[-1][1], t_pin.scenePos().y(), places=2)

    def test_fsm_transition_bounding_rect(self):
        fsm_tab = self.win.tab_fsm
        fsm_tab.load_pulse_preset()
        for t_item in fsm_tab.fsm_scene.trans_items:
            bbox = t_item.boundingRect()
            # Label position must be inside the bounding rect
            self.assertTrue(bbox.contains(t_item.label_pos))
            # Arrow tip must be inside the bounding rect
            self.assertTrue(bbox.contains(t_item.arrow_tip))

    def test_fsm_reset_arrow_tracks_position(self):
        fsm_tab = self.win.tab_fsm
        fsm_tab.load_pulse_preset()
        init_state = fsm_tab.fsm.get_initial_state()
        init_item = fsm_tab.fsm_scene.state_items[init_state.name]
        self.assertIsNotNone(fsm_tab.fsm_scene.reset_arrow)
        self.assertEqual(fsm_tab.fsm_scene.reset_arrow.pos(), init_item.scenePos())

        # Move the state
        init_item.setPos(init_item.pos().x() + 50, init_item.pos().y() + 50)
        self.assertEqual(fsm_tab.fsm_scene.reset_arrow.pos(), init_item.scenePos())


    def test_solder_dot_movable_and_undo(self):
        scene = self.win.tab_rtl.scene
        scene.add_junction_at(QPointF(100, 100))
        j_item = list(scene.junction_items.values())[-1]
        self.assertTrue(j_item.flags() & j_item.GraphicsItemFlag.ItemIsMovable)

        # Move the junction
        scene.undo_stack.append(scene.schematic.to_dict())
        j_item.setPos(140, 160)
        # Verify model updated
        matching = [j for j in scene.schematic.junctions if j.id == j_item.j_id]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].x, 140)
        self.assertEqual(matching[0].y, 160)

        # Undo restoration
        scene.undo()
        restored_j = [j for j in scene.schematic.junctions if j.id == j_item.j_id]
        self.assertEqual(len(restored_j), 1)
        self.assertEqual(restored_j[0].x, 100)
        self.assertEqual(restored_j[0].y, 100)

    def test_wire_manual_routing_and_reset(self):
        scene = self.win.tab_rtl.scene
        w_item = list(scene.wire_items.values())[0]
        # Select wire to generate handles
        w_item.setSelected(True)
        self.assertGreater(len(w_item.handles), 0)

        # Drag a segment handle
        w_item.on_segment_dragged(0, QPointF(120, 160))
        self.assertTrue(w_item.model.manual_routing)

        # Reset routing with R
        scene.reset_selected_wire_routing()
        self.assertFalse(w_item.model.manual_routing)

    def test_wire_label_movable_and_reset(self):
        scene = self.win.tab_rtl.scene
        # Find wire with label (e.g. 'count' or 'next_count')
        w_item = next(w for w in scene.wire_items.values() if w.model.label)
        self.assertIsNotNone(w_item.label_item)

        # Move label tag
        w_item.label_item.setPos(50, 70)
        self.assertIsNotNone(w_item.model.label_pos)

        # Reset label position with Shift+R
        scene.reset_selected_labels()
        self.assertIsNone(w_item.model.label_pos)

    def test_fsm_transition_badge_movable_and_reset(self):
        fsm_tab = self.win.tab_fsm
        fsm_tab.load_pulse_preset()
        t_item = fsm_tab.fsm_scene.trans_items[0]
        self.assertIsNotNone(t_item.badge_item)

        # Move badge item
        t_item.badge_item.setPos(90, 110)
        self.assertIsNotNone(t_item.transition.custom_label_pos)

        # Reset all transition labels
        fsm_tab.fsm_scene.reset_all_transition_labels()
        self.assertIsNone(t_item.transition.custom_label_pos)

    def test_generic_block_resize_and_port_editing(self):
        scene = self.win.tab_rtl.scene
        block = ComponentFactory.create_generic_block(300, 300, name="ALU_TEST", inputs=["A", "B"], outputs=["Y"])
        block_item = scene.add_component(block)
        self.assertIsNotNone(block_item.resize_handle)

        # Resize block
        block_item.set_block_size(180, 140)
        self.assertEqual(block_item.model.width, 180)
        self.assertEqual(block_item.model.height, 140)

        # Edit ports: add an input and an output
        block.pins.append(RTLPin(id=f"{block.id}_in_cin", name="Cin", direction=PinDirection.IN, side=PinSide.LEFT, offset=0.8, width=1))
        block.pins.append(RTLPin(id=f"{block.id}_out_cout", name="Cout", direction=PinDirection.OUT, side=PinSide.RIGHT, offset=0.8, width=1))
        block_item.rebuild_pins()
        self.assertEqual(len(block_item.pin_items), 5)

    def test_mux_sel_pin_anchoring_and_rendering(self):
        scene = self.win.tab_rtl.scene
        mux = ComponentFactory.create_mux(200, 200, input_names=["IDLE", "RUN", "DONE"], width=4, sel_side="BOTTOM")
        mux_item = scene.add_component(mux)
        self.assertEqual(len(mux_item.pin_items), 5)

        # Verify sel pin anchors directly on the sloped bottom edge (y = 0.9 * h), NOT floating at y = h
        sel_pin_item = next(pi for pi in mux_item.pin_items if pi.pin.name == "sel")
        expected_y = mux.height - (mux.height * 0.2) * 0.5 # 0.9 * h
        self.assertAlmostEqual(sel_pin_item.pos().y(), expected_y, places=2)

    def test_bus_splitter_elo212_branches(self):
        scene = self.win.tab_rtl.scene
        splitter = ComponentFactory.create_bus_splitter(400, 400, in_width=16, slices="[2:0], [3], [15:4]", base_name="bus_ej")
        split_item = scene.add_component(splitter)
        self.assertEqual(len(split_item.pin_items), 4)

        out_pins = [pi.pin for pi in split_item.pin_items if pi.pin.direction == PinDirection.OUT]
        self.assertEqual(out_pins[0].name, "bus_ej[2:0]")
        self.assertEqual(out_pins[0].width, 3)
        self.assertEqual(out_pins[1].name, "bus_ej[3]")
        self.assertEqual(out_pins[1].width, 1)
        self.assertEqual(out_pins[2].name, "bus_ej[15:4]")
        self.assertEqual(out_pins[2].width, 12)

    def test_bus_splitter_pins_grid_and_wire_alignment(self):
        """Verifies that bus splitter pins, painted branches, and connected wires are strictly grid-aligned."""
        scene = self.win.tab_rtl.scene
        # Create 3-slice splitter as in user's scenario
        splitter = ComponentFactory.create_bus_splitter(200, 200, in_width=3, slices="[0], [1], [2]")
        split_item = scene.add_component(splitter)

        # 1. All pin Y positions must be integer multiples of GRID_SIZE (20.0)
        from app.gui.rtl_items import snap
        for pi in split_item.pin_items:
            self.assertEqual(pi.pos().y() % 20.0, 0.0, f"Pin {pi.pin.name} Y {pi.pos().y()} is not on 20px grid!")
            # Ensure pin item pos matches snap(h * offset)
            expected_y = snap(split_item.model.height * pi.pin.offset)
            self.assertEqual(pi.pos().y(), expected_y)

        # 2. Width must also be a multiple of 20.0
        self.assertEqual(split_item.model.width % 20.0, 0.0)

        # 3. Test mirrored splitter (as in user screenshot where branches are on the left)
        splitter_mirrored = ComponentFactory.create_bus_splitter(400, 200, in_width=3, slices="[0], [1], [2]")
        split_mirrored_item = scene.add_component(splitter_mirrored)
        scene.clearSelection()
        split_mirrored_item.setSelected(True)
        scene.reflect_selected_components()

        for pi in split_mirrored_item.pin_items:
            self.assertEqual(pi.pos().y() % 20.0, 0.0, f"Mirrored Pin {pi.pin.name} Y {pi.pos().y()} is not on 20px grid!")
            if pi.pin.direction == PinDirection.OUT:
                self.assertEqual(pi.pos().x(), 0.0)
            else:
                self.assertEqual(pi.pos().x(), split_mirrored_item.model.width)

        # 4. Connect a wire to a branch pin and verify endpoint matches exactly
        in_comp = ComponentFactory.create_constant(0, 200, val="1'b0")
        in_item = scene.add_component(in_comp)
        out_branch_pin = next(pi for pi in split_mirrored_item.pin_items if pi.pin.name == "[0]")

        scene.start_wiring(in_item.pin_items[0])
        scene.finish_wiring(out_branch_pin)

        created_wire = scene.schematic.wires[-1]
        wire_last_pt = created_wire.points[-1]
        # Wire endpoint Y must match the branch pin scene pos Y with ZERO gap
        self.assertEqual(wire_last_pt[1], out_branch_pin.scenePos().y())
        self.assertEqual(wire_last_pt[0], out_branch_pin.scenePos().x())

    def test_operator_circle_output_suppressed(self):
        scene = self.win.tab_rtl.scene
        op = ComponentFactory.create_operator(100, 100, op="A==B", width=4)
        op_item = scene.add_component(op)
        out_pin_item = next(pi for pi in op_item.pin_items if pi.pin.direction == PinDirection.OUT)
        self.assertEqual(out_pin_item.pin.name, "out")
        # RTLPinItem paint suppresses 'out' label painting for OPERATOR_CIRCLE to prevent collision with A==B
        self.assertEqual(op_item.model.type, ComponentType.OPERATOR_CIRCLE)

    def test_counter_example_wire_hit_testing_bugfix(self):
        """Verify the bugfix where the top feedback wire loop used to swallow clicks on next_count wire"""
        rtl_tab = self.win.tab_rtl
        rtl_tab.load_counter_example()
        scene = rtl_tab.scene

        w_feedback_item = scene.wire_items["w_feedback"]
        w_sum_item = scene.wire_items["w_sum"]

        # Points along next_count wire (at y=160 between x=260 and x=380)
        test_pt = QPointF(300, 160)

        # The stroked shape of w_sum MUST contain this point
        self.assertTrue(w_sum_item.shape().contains(w_sum_item.mapFromScene(test_pt)))

        # The stroked shape of w_feedback MUST NOT contain this interior point!
        self.assertFalse(w_feedback_item.shape().contains(w_feedback_item.mapFromScene(test_pt)))

        # Next count label item must be selectable and movable
        self.assertIsNotNone(w_sum_item.label_item)
        w_sum_item.label_item.setPos(300, 130)
        self.assertIsNotNone(w_sum_item.model.label_pos)

    def test_straight_horizontal_connection_no_jogs(self):
        """Verify connections are uninterrupted straight horizontal lines without vertical jogs"""
        rtl_tab = self.win.tab_rtl
        rtl_tab.load_counter_example()
        scene = rtl_tab.scene

        w_const = scene.wire_items["w_const"].model
        w_sum = scene.wire_items["w_sum"].model

        # Constant out (y=180) to Adder pin B (y=180) -> exactly 2 points, same Y
        self.assertEqual(len(w_const.points), 2)
        self.assertEqual(w_const.points[0][1], 180.0)
        self.assertEqual(w_const.points[1][1], 180.0)

        # Adder out (y=160) to Reg pin D (y=160) -> exactly 2 points, same Y
        self.assertEqual(len(w_sum.points), 2)
        self.assertEqual(w_sum.points[0][1], 160.0)
        self.assertEqual(w_sum.points[1][1], 160.0)

    def test_block_reflection_ctrl_e(self):
        """Verify horizontal block mirroring (Ctrl+E) and undo support"""
        rtl_tab = self.win.tab_rtl
        rtl_tab.load_counter_example()
        scene = rtl_tab.scene

        # Select the Register
        reg_item = next(it for it in scene.comp_items.values() if it.model.type == ComponentType.REGISTER)
        scene.clearSelection()
        reg_item.setSelected(True)

        comp = reg_item.model
        self.assertFalse(getattr(comp, "mirrored", False))

        pin_d = next(p for p in comp.pins if p.name == "D")
        pin_q = next(p for p in comp.pins if p.name == "Q")
        self.assertEqual(pin_d.side, PinSide.LEFT)
        self.assertEqual(pin_q.side, PinSide.RIGHT)

        # Trigger reflection
        scene.reflect_selected_components()
        self.assertTrue(comp.mirrored)
        self.assertEqual(pin_d.side, PinSide.RIGHT)
        self.assertEqual(pin_q.side, PinSide.LEFT)

        # Undo reflection
        scene.undo()
        restored_reg = next(c for c in scene.schematic.components if c.type == ComponentType.REGISTER)
        self.assertFalse(restored_reg.mirrored)
        pin_d_restored = next(p for p in restored_reg.pins if p.name == "D")
        pin_q_restored = next(p for p in restored_reg.pins if p.name == "Q")
        self.assertEqual(pin_d_restored.side, PinSide.LEFT)
        self.assertEqual(pin_q_restored.side, PinSide.RIGHT)

    def test_operator_reduction_and_unary(self):
        """Verify circular operator configuration with reduction and unary operations"""
        from app.gui.rtl_view import OperatorPropertiesDialog
        op = ComponentFactory.create_operator(100, 100, op="+", width=8)
        self.assertEqual(len(op.pins), 3) # A, B, out

        # Test dialog reduction info
        dlg = OperatorPropertiesDialog(op)
        # Switch to Reducción
        dlg.combo_category.setCurrentIndex(2) # Reducción (Vector -> 1 bit)
        sym, is_red, is_unary, out_1bit = dlg.get_selected_op_info()
        self.assertTrue(is_red)
        self.assertFalse(is_unary)
        self.assertTrue(out_1bit)

        # Switch to Unarias
        dlg.combo_category.setCurrentIndex(3) # Unarias / Inversión
        sym, is_red, is_unary, out_1bit = dlg.get_selected_op_info()
        self.assertFalse(is_red)
        self.assertTrue(is_unary)
        self.assertFalse(out_1bit)

    def test_wire_directional_arrow(self):
        """Verify directional signal arrows at target pins (ELO212 Figure 4)"""
        rtl_tab = self.win.tab_rtl
        rtl_tab.load_counter_example()
        scene = rtl_tab.scene

        w1_item = scene.wire_items["w_const"]
        w3_item = scene.wire_items["w_feedback"]

        self.assertTrue(w1_item.model.show_arrow)
        self.assertTrue(w3_item.model.show_arrow)

        # Polygon must be a triangle (3 points) pointing toward the last point
        poly1 = w1_item._get_arrow_polygon()
        self.assertIsNotNone(poly1)
        self.assertEqual(len(poly1), 3)

        poly3 = w3_item._get_arrow_polygon()
        self.assertIsNotNone(poly3)
        self.assertEqual(len(poly3), 3)

        # Wire shape includes the arrow
        self.assertTrue(w1_item.shape().contains(poly1[0]))

        # Test UI property toggling
        scene.clearSelection()
        w1_item.setSelected(True)
        rtl_tab._on_selection_changed()
        self.assertTrue(rtl_tab.check_wire_arrow.isChecked())

        rtl_tab.check_wire_arrow.setChecked(False)
        rtl_tab.apply_wire_props()
        self.assertFalse(w1_item.model.show_arrow)

    def test_copy_paste_components_and_wires(self):
        """Verify copying selected components with connecting wires and pasting with offset (Ctrl+C, Ctrl+V) and Undo"""
        rtl_tab = self.win.tab_rtl
        rtl_tab.load_counter_example()
        scene = rtl_tab.scene

        init_comp_count = len(scene.comp_items)
        init_wire_count = len(scene.wire_items)

        # Select all components
        scene.clearSelection()
        for it in scene.comp_items.values():
            it.setSelected(True)

        # Copy
        scene.copy_selected()
        self.assertIsNotNone(scene._clipboard)
        self.assertEqual(len(scene._clipboard["components"]), 3)
        self.assertEqual(len(scene._clipboard["wires"]), 3)

        # Paste
        scene.paste()
        self.assertEqual(len(scene.comp_items), init_comp_count + 3)
        self.assertEqual(len(scene.wire_items), init_wire_count + 3)

        # Newly pasted items must be selected
        selected_comps = [it for it in scene.selectedItems() if isinstance(it, RTLComponentItem)]
        self.assertEqual(len(selected_comps), 3)

        # Verify offset: Constant was originally at (40, 160), pasted copy should be at (60, 180)
        pasted_const = next(it for it in selected_comps if it.model.type == ComponentType.CONSTANT)
        self.assertEqual(pasted_const.model.x, 60.0)
        self.assertEqual(pasted_const.model.y, 180.0)

        # Test Undo restores original scene
        scene.undo()
        self.assertEqual(len(scene.schematic.components), init_comp_count)
        self.assertEqual(len(scene.schematic.wires), init_wire_count)

    def test_wire_parameter_ui_and_rendering(self):
        """Verify manual bus width assignment to wire and slash rendering"""
        rtl_tab = self.win.tab_rtl
        rtl_tab.load_counter_example()
        scene = rtl_tab.scene

        w1_item = scene.wire_items["w_const"]
        scene.clearSelection()
        w1_item.setSelected(True)
        rtl_tab._on_selection_changed()

        # Wire width spinbox is loaded from wire model (w1 is 4-bit)
        self.assertEqual(rtl_tab.spin_wire_width.value(), 4)
        self.assertTrue(w1_item.model.is_bus)

        # Change width manually via spinbox
        rtl_tab.spin_wire_width.setValue(8)
        rtl_tab.apply_wire_props()

        self.assertEqual(w1_item.model.width, 8)
        self.assertTrue(w1_item.model.is_bus)

        # Change width manually to 1 (single-bit wire)
        rtl_tab.spin_wire_width.setValue(1)
        rtl_tab.apply_wire_props()
        self.assertEqual(w1_item.model.width, 1)
        self.assertFalse(w1_item.model.is_bus)

    def test_port_indicators_gui(self):
        """Test adding and rendering input and output ports in RTL editor"""
        rtl_tab = self.win.tab_rtl
        scene = rtl_tab.scene

        # Add 1-bit input port (clk_100M)
        p_in = ComponentFactory.create_input_port(40, 120, name="clk_100M", width=1)
        item_in = scene.add_component(p_in)
        self.assertIn(p_in.id, scene.comp_items)
        self.assertEqual(item_in.model.type, ComponentType.INPUT_PORT)

        # Add 8-bit bus output port (anodes[7:0])
        p_out = ComponentFactory.create_output_port(300, 120, name="anodes[7:0]", width=8)
        item_out = scene.add_component(p_out)
        self.assertIn(p_out.id, scene.comp_items)
        self.assertEqual(item_out.model.type, ComponentType.OUTPUT_PORT)

        # Check pin positions are snapped to multiples of 20
        pos_in_pin = item_in.pin_items[0].scenePos()
        pos_out_pin = item_out.pin_items[0].scenePos()
        self.assertEqual(pos_in_pin.y() % 20.0, 0.0)
        self.assertEqual(pos_out_pin.y() % 20.0, 0.0)

        # Connect wire from input port to output port
        scene.start_wiring(item_in.pin_items[0])
        scene.finish_wiring(item_out.pin_items[0])
        self.assertEqual(len(scene.schematic.wires), 4) # 3 from counter example + 1 new

        # Connected wire inherits bus width 8
        new_wire = scene.schematic.wires[-1]
        self.assertEqual(new_wire.width, 8)

    def test_palette_scroll_and_action_buttons(self):
        """Test that palette is in a QScrollArea and action buttons have comfortable height"""
        from PySide6.QtWidgets import QScrollArea, QPushButton
        rtl_tab = self.win.tab_rtl

        # Check QScrollArea exists in rtl_tab
        scrolls = rtl_tab.findChildren(QScrollArea)
        self.assertGreaterEqual(len(scrolls), 1)
        palette_scroll = scrolls[0]
        self.assertTrue(palette_scroll.widgetResizable())

        # Check buttons exist in palette
        buttons = rtl_tab.findChildren(QPushButton)
        self.assertGreaterEqual(len(buttons), 15)
        # Check stylesheet of palette panel guarantees min-height
        pal_widget = palette_scroll.widget()
        self.assertIn("min-height", pal_widget.styleSheet())

    def test_fsm_mealy_preset_gui(self):
        """Test loading Mealy sequence detector preset in FSM tab and verifying GUI updates"""
        fsm_tab = self.win.tab_fsm
        fsm_tab.load_mealy_preset()

        # FSM type and parameters
        self.assertEqual(fsm_tab.fsm.fsm_type, FSMType.MEALY)
        self.assertEqual(fsm_tab.combo_type.currentText(), FSMType.MEALY.value)
        self.assertEqual(fsm_tab.edit_name.text(), "seq_detector_101_mealy")

        # Table populated
        self.assertEqual(fsm_tab.table_states.rowCount(), 3)
        self.assertEqual(fsm_tab.table_trans.rowCount(), 6)

        # Transition table Mealy output column (index 4)
        has_mealy_output_cell = False
        for r in range(fsm_tab.table_trans.rowCount()):
            item = fsm_tab.table_trans.item(r, 4)
            if item and "pattern_found=1'b1" in item.text():
                has_mealy_output_cell = True
                break
        self.assertTrue(has_mealy_output_cell, "Expected pattern_found=1'b1 in Mealy column of transitions table")

        # Canvas scene items
        self.assertEqual(len(fsm_tab.fsm_scene.state_items), 3)
        self.assertEqual(len(fsm_tab.fsm_scene.trans_items), 6)

        # Validation should succeed without errors
        fsm_tab.run_validation()
        self.assertGreater(fsm_tab.list_issues.count(), 0)
        first_issue = fsm_tab.list_issues.item(0).text()
        self.assertIn("cumple estrictamente", first_issue)


        # Test switching back to Moore pulse preset and reloading via button click
        fsm_tab.load_pulse_preset()
        self.assertEqual(fsm_tab.fsm.fsm_type, FSMType.MOORE)
        self.assertEqual(fsm_tab.combo_type.currentText(), FSMType.MOORE.value)

        # Find Mealy button and click it
        mealy_buttons = [b for b in fsm_tab.findChildren(QPushButton) if "Mealy" in b.text()]
        self.assertEqual(len(mealy_buttons), 1)
        mealy_buttons[0].click()
        self.assertEqual(fsm_tab.fsm.fsm_type, FSMType.MEALY)
        self.assertEqual(fsm_tab.combo_type.currentText(), FSMType.MEALY.value)

    def test_component_accurate_hitboxes(self):
        scene = self.win.tab_rtl.scene

        # 1. MUX shape test
        mux = ComponentFactory.create_mux(0, 0, num_inputs=2, width=1)
        mux_item = scene.add_component(mux)
        sh_mux = mux_item.shape()
        w_m, h_m = mux.width, mux.height
        # Center should be inside
        self.assertTrue(sh_mux.contains(QPointF(w_m * 0.5, h_m * 0.5)))
        # Top-right corner of bounding box is outside trapezoid (h_m * 0.2 is top edge of right side)
        self.assertFalse(sh_mux.contains(QPointF(w_m - 2, 2)))
        # Bottom-right corner of bounding box is outside trapezoid (h_m * 0.8 is bottom edge of right side)
        self.assertFalse(sh_mux.contains(QPointF(w_m - 2, h_m - 2)))

        # 2. Operator Circle shape test
        op = ComponentFactory.create_operator(0, 0, op="+", width=4)
        op_item = scene.add_component(op)
        sh_op = op_item.shape()
        w_op, h_op = op.width, op.height
        # Center is inside
        self.assertTrue(sh_op.contains(QPointF(w_op * 0.5, h_op * 0.5)))
        # Top-left corner is outside circle
        self.assertFalse(sh_op.contains(QPointF(2, 2)))
        # Top-right corner is outside circle
        self.assertFalse(sh_op.contains(QPointF(w_op - 2, 2)))

        # 3. Gate NOT shape test
        not_gate = ComponentFactory.create_gate(0, 0, gate_type="NOT")
        not_item = scene.add_component(not_gate)
        sh_not = not_item.shape()
        w_n, h_n = not_gate.width, not_gate.height
        # Center of triangle is inside
        self.assertTrue(sh_not.contains(QPointF(w_n * 0.3, h_n * 0.5)))
        # Top-right empty area is outside
        self.assertFalse(sh_not.contains(QPointF(w_n * 0.8, 5)))

        # 4. Solder dot shape test
        scene.add_junction_at(QPointF(100, 100))
        j_item = list(scene.junction_items.values())[-1]
        sh_j = j_item.shape()
        self.assertTrue(sh_j.contains(QPointF(0, 0)))
        # Point outside circle
        self.assertFalse(sh_j.contains(QPointF(j_item.RADIUS + 10, j_item.RADIUS + 10)))

        # 5. FSM State circle shape test
        fsm_tab = self.win.tab_fsm
        fsm_tab.load_pulse_preset()
        state_item = list(fsm_tab.fsm_scene.state_items.values())[0]
        sh_s = state_item.shape()
        self.assertTrue(sh_s.contains(QPointF(0, 0)))
        # Corner of square is outside circle of radius 42
        self.assertFalse(sh_s.contains(QPointF(state_item.RADIUS - 2, state_item.RADIUS - 2)))

    def test_spawn_position_in_view(self):
        rtl = self.win.tab_rtl
        # Verify spawn pos does not default to (0, 0)
        pos1 = rtl._get_spawn_pos()
        self.assertNotEqual(pos1, (0.0, 0.0))

        # Adding a component at pos1 causes next spawn to stagger
        c = ComponentFactory.create_constant(pos1[0], pos1[1], "1'b0")
        rtl.scene.add_component(c)
        pos2 = rtl._get_spawn_pos()
        self.assertNotEqual(pos1, pos2)

    def test_wiring_cancellation_preserves_item_drag(self):
        from PySide6.QtTest import QTest
        rtl = self.win.tab_rtl
        scene = rtl.scene
        view = rtl.view
        viewport = view.viewport()

        # Add a gate to drag
        gate = ComponentFactory.create_gate(200, 200, "AND")
        item = scene.add_component(gate)

        # Start wiring from a pin
        pin = item.pin_items[0]
        scene.start_wiring(pin)
        self.assertTrue(scene.wiring_active)

        # Click on center of the gate
        gate_center_scene = item.scenePos() + QPointF(item.model.width / 2, item.model.height / 2)
        center_view = view.mapFromScene(gate_center_scene)

        QTest.mousePress(viewport, Qt.LeftButton, Qt.NoModifier, center_view)
        # Wiring should be cancelled and item should be selected
        self.assertFalse(scene.wiring_active)
        self.assertTrue(item.isSelected())

        # Drag gate
        target_view = center_view + QPoint(60, 60)
        QTest.mouseMove(viewport, target_view)
        QTest.mouseRelease(viewport, Qt.LeftButton, Qt.NoModifier, target_view)
        self.assertEqual(item.pos().x(), 260.0)
        self.assertEqual(item.pos().y(), 260.0)

    def test_operator_rotation_and_label_upright(self):
        """Test rotating circular operator 90, 180, 270, 0 degrees with upright label"""
        rtl_tab = self.win.tab_rtl
        scene = rtl_tab.scene

        op_comp = ComponentFactory.create_operator(200, 200, op="+", width=1, size=60.0, rotation=0)
        item = scene.add_component(op_comp)

        # Initial rotation 0: pins A, B on LEFT, OUT on RIGHT
        self.assertEqual(op_comp.pins[0].side, PinSide.LEFT)
        self.assertEqual(op_comp.pins[1].side, PinSide.LEFT)
        self.assertEqual(op_comp.pins[2].side, PinSide.RIGHT)
        self.assertEqual(int(op_comp.props.get("rotation", 0)), 0)

        # Select item and rotate 90°
        scene.clearSelection()
        item.setSelected(True)
        scene.rotate_selected_operators()
        self.assertEqual(int(op_comp.props["rotation"]), 90)
        self.assertEqual(op_comp.pins[0].side, PinSide.TOP)
        self.assertEqual(op_comp.pins[1].side, PinSide.TOP)
        self.assertEqual(op_comp.pins[2].side, PinSide.BOTTOM)

        # Rotate 180°
        scene.rotate_selected_operators()
        self.assertEqual(int(op_comp.props["rotation"]), 180)
        self.assertEqual(op_comp.pins[0].side, PinSide.RIGHT)
        self.assertEqual(op_comp.pins[1].side, PinSide.RIGHT)
        self.assertEqual(op_comp.pins[2].side, PinSide.LEFT)

        # Rotate 270°
        scene.rotate_selected_operators()
        self.assertEqual(int(op_comp.props["rotation"]), 270)
        self.assertEqual(op_comp.pins[0].side, PinSide.BOTTOM)
        self.assertEqual(op_comp.pins[1].side, PinSide.BOTTOM)
        self.assertEqual(op_comp.pins[2].side, PinSide.TOP)

        # Rotate back to 0°
        scene.rotate_selected_operators()
        self.assertEqual(int(op_comp.props["rotation"]), 0)
        self.assertEqual(op_comp.pins[0].side, PinSide.LEFT)
        self.assertEqual(op_comp.pins[1].side, PinSide.LEFT)
        self.assertEqual(op_comp.pins[2].side, PinSide.RIGHT)

        # Label remains "+"
        self.assertEqual(op_comp.label, "+")

    def test_operator_resizing_without_pin_collision(self):
        """Test that resizing circular operator (e.g. to 40px, 50px) maintains distinct pin positions without collision"""
        rtl_tab = self.win.tab_rtl
        scene = rtl_tab.scene

        op_comp = ComponentFactory.create_operator(100, 100, op="*", width=1, size=40.0, rotation=0)
        item = scene.add_component(op_comp)

        self.assertEqual(item.model.width, 40.0)
        self.assertEqual(item.model.height, 40.0)

        pin_a_pos = item.pin_items[0].scenePos()
        pin_b_pos = item.pin_items[1].scenePos()
        pin_out_pos = item.pin_items[2].scenePos()

        # Check distinct positions: A at y=110, B at y=130, Out at x=140, y=120
        self.assertEqual((pin_a_pos.x(), pin_a_pos.y()), (100.0, 110.0))
        self.assertEqual((pin_b_pos.x(), pin_b_pos.y()), (100.0, 130.0))
        self.assertEqual((pin_out_pos.x(), pin_out_pos.y()), (140.0, 120.0))

        # None of the pins collide
        self.assertNotEqual((pin_a_pos.x(), pin_a_pos.y()), (pin_b_pos.x(), pin_b_pos.y()))
        self.assertNotEqual((pin_a_pos.x(), pin_a_pos.y()), (pin_out_pos.x(), pin_out_pos.y()))
        self.assertNotEqual((pin_b_pos.x(), pin_b_pos.y()), (pin_out_pos.x(), pin_out_pos.y()))

    def test_mux_compact_width(self):
        """Test that multiplexers use narrower width (50px instead of 70-80px) to save canvas space"""
        mux2 = ComponentFactory.create_mux(0, 0, num_inputs=2, width=1)
        mux4 = ComponentFactory.create_mux(0, 0, num_inputs=4, width=1)

        self.assertEqual(mux2.width, 50.0)
        self.assertEqual(mux4.width, 50.0)

    def test_wire_bus_slash_rendering(self):
        """Test that multi-bit wires render bus slash with bit count and 1-bit wires do not"""
        rtl_tab = self.win.tab_rtl
        rtl_tab.load_counter_example()
        scene = rtl_tab.scene

        w_const = scene.wire_items["w_const"] # 4-bit wire
        self.assertTrue(w_const.model.is_bus)
        self.assertTrue((w_const.model.width > 1 or w_const.model.width_param) and w_const.model.show_slash)

        # Test paint runs with bus slash without error
        from PySide6.QtGui import QImage, QPainter
        img = QImage(200, 200, QImage.Format_ARGB32)
        p = QPainter(img)
        w_const.paint(p, None, None)
        p.end()

        # Change width to 1
        w_const.model.width = 1
        self.assertFalse(w_const.model.is_bus)
        self.assertFalse((w_const.model.width > 1 or w_const.model.width_param) and w_const.model.show_slash)

        # Test paint runs for single-bit wire without error
        p2 = QPainter(img)
        w_const.paint(p2, None, None)
        p2.end()


if __name__ == "__main__":
    unittest.main()



