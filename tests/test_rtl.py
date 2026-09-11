"""
Unit tests for RTL Schematic Data Model and Factory.
"""

import unittest
import os
import tempfile
from app.core.rtl_model import (
    RTLSchematic, RTLComponent, ComponentFactory, ComponentType, RTLWire, RTLJunction,
    PinDirection, PinSide
)


class TestRTLSuite(unittest.TestCase):
    def test_component_factory(self):
        mux = ComponentFactory.create_mux(100, 100, num_inputs=4, width=3, label="MUX4")
        self.assertEqual(mux.type, ComponentType.MUX)
        self.assertEqual(len(mux.pins), 6) # 4 inputs + 1 sel + 1 out

        reg = ComponentFactory.create_register(200, 100, width=8, label="REG_COUNT")
        self.assertEqual(reg.type, ComponentType.REGISTER)
        pin_names = [p.name for p in reg.pins]
        self.assertIn("clk", pin_names)
        self.assertIn("rst", pin_names)
        self.assertIn("D", pin_names)
        self.assertIn("Q", pin_names)

        splitter = ComponentFactory.create_bus_splitter(300, 100, in_width=16, slices="[2:0], [3], [15:4]")
        self.assertEqual(len(splitter.pins), 4) # 1 in + 3 outputs
        # Verify correct ELO212 bit widths calculated for slices:
        # [2:0] -> 3 bits, [3] -> 1 bit, [15:4] -> 12 bits
        self.assertEqual(splitter.pins[1].width, 3)
        self.assertEqual(splitter.pins[2].width, 1)
        self.assertEqual(splitter.pins[3].width, 12)

    def test_mux_abstract_inputs(self):
        fsm_states = ["IDLE", "RUN_PHASE_A", "DONE"]
        mux = ComponentFactory.create_mux(100, 100, input_names=fsm_states, width=8, label="STATE_MUX", sel_side="TOP")
        self.assertEqual(len(mux.pins), 5) # 3 inputs + 1 sel + 1 out
        self.assertEqual(mux.pins[0].name, "IDLE")
        self.assertEqual(mux.pins[1].name, "RUN_PHASE_A")
        self.assertEqual(mux.pins[2].name, "DONE")
        self.assertEqual(mux.pins[3].name, "sel")
        self.assertEqual(mux.pins[3].side.value, "TOP")
        self.assertEqual(mux.pins[4].name, "out")
        # Width should expand to fit long labels comfortably
        self.assertGreaterEqual(mux.width, 140.0)

    def test_schematic_serialization(self):
        schematic = RTLSchematic(name="counter_4bit")
        reg = ComponentFactory.create_register(150, 100, width=4, label="Count")
        op = ComponentFactory.create_operator(50, 100, op="+", width=4)
        c = ComponentFactory.create_constant(10, 150, val="4'd1", width=4)
        schematic.add_component(reg)
        schematic.add_component(op)
        schematic.add_component(c)

        # Connect wire
        wire = RTLWire(
            id="w1",
            source_comp_id=op.id,
            source_pin_id=op.pins[2].id, # out
            target_comp_id=reg.id,
            target_pin_id=reg.pins[0].id, # D
            points=[(110, 130), (150, 130)],
            width=4,
            label="next_count[3:0]"
        )
        schematic.wires.append(wire)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            temp_path = tf.name

        try:
            schematic.save_to_file(temp_path)
            loaded = RTLSchematic.load_from_file(temp_path)
            self.assertEqual(len(loaded.components), 3)
            self.assertEqual(len(loaded.wires), 1)
            self.assertEqual(loaded.wires[0].width, 4)
            self.assertEqual(loaded.wires[0].label, "next_count[3:0]")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_operator_reduction_and_unary_factory(self):
        # Reduction operator
        op_red = ComponentFactory.create_operator(100, 100, op="&", width=8, is_reduction=True)
        self.assertEqual(len(op_red.pins), 2)
        pin_a = next(p for p in op_red.pins if p.name == "A")
        pin_out = next(p for p in op_red.pins if p.name == "out")
        self.assertEqual(pin_a.width, 8)
        self.assertEqual(pin_out.width, 1) # Reduction produces 1-bit result
        self.assertEqual(pin_a.offset, 0.5) # Centered
        self.assertEqual(pin_out.offset, 0.5)

        # Unary operator
        op_un = ComponentFactory.create_operator(100, 100, op="~", width=16)
        self.assertEqual(len(op_un.pins), 2)
        pin_a = next(p for p in op_un.pins if p.name == "A")
        pin_out = next(p for p in op_un.pins if p.name == "out")
        self.assertEqual(pin_a.width, 16)
        self.assertEqual(pin_out.width, 16)

        # Relational operator
        op_rel = ComponentFactory.create_operator(100, 100, op="A>B", width=8)
        self.assertEqual(len(op_rel.pins), 3) # A, B, out
        pin_out = next(p for p in op_rel.pins if p.name == "out")
        self.assertEqual(pin_out.width, 1) # Boolean output

    def test_mirrored_serialization(self):
        reg = ComponentFactory.create_register(150, 100, width=4, label="MirroredReg")
        reg.mirrored = True
        d = reg.to_dict()
        self.assertTrue(d.get("mirrored", False))

        restored = RTLComponent.from_dict(d)
        self.assertTrue(restored.mirrored)

    def test_schematic_parameters(self):
        schematic = RTLSchematic(name="param_test")
        schematic.set_parameter("DATA_WIDTH", 8)
        schematic.set_parameter("ADDR_WIDTH", 4)
        self.assertEqual(schematic.get_parameter_value("DATA_WIDTH"), 8)
        self.assertEqual(schematic.get_parameter_value("ADDR_WIDTH"), 4)

        wire = RTLWire(id="w1", width=8, width_param="DATA_WIDTH")
        schematic.wires.append(wire)

        # Update parameter value
        schematic.set_parameter("DATA_WIDTH", 16)
        self.assertEqual(wire.width, 16)

        # Serialization round-trip
        data = schematic.to_dict()
        self.assertIn("DATA_WIDTH", data["parameters"])
        self.assertEqual(data["parameters"]["DATA_WIDTH"], 16)
        self.assertEqual(data["wires"][0]["width_param"], "DATA_WIDTH")

        loaded = RTLSchematic.from_dict(data)
        self.assertEqual(loaded.get_parameter_value("DATA_WIDTH"), 16)
        self.assertEqual(loaded.wires[0].width_param, "DATA_WIDTH")
        self.assertEqual(loaded.wires[0].width, 16)

        # Remove parameter
        loaded.remove_parameter("DATA_WIDTH")
        self.assertNotIn("DATA_WIDTH", loaded.parameters)
        self.assertIsNone(loaded.wires[0].width_param)

    def test_port_indicators(self):
        # 1-bit Input Port (clk_100M)
        in_clk = ComponentFactory.create_input_port(40, 100, name="clk_100M", width=1)
        self.assertEqual(in_clk.type, ComponentType.INPUT_PORT)
        self.assertEqual(in_clk.label, "clk_100M")
        self.assertEqual(len(in_clk.pins), 1)
        self.assertEqual(in_clk.pins[0].direction, PinDirection.OUT)
        self.assertEqual(in_clk.pins[0].side, PinSide.RIGHT)
        self.assertEqual(in_clk.pins[0].width, 1)

        # Bus Output Port (anodes[7:0])
        out_anodes = ComponentFactory.create_output_port(400, 100, name="anodes[7:0]", width=8)
        self.assertEqual(out_anodes.type, ComponentType.OUTPUT_PORT)
        self.assertEqual(out_anodes.label, "anodes[7:0]")
        self.assertEqual(len(out_anodes.pins), 1)
        self.assertEqual(out_anodes.pins[0].direction, PinDirection.IN)
        self.assertEqual(out_anodes.pins[0].side, PinSide.LEFT)
        self.assertEqual(out_anodes.pins[0].width, 8)

        # Serialization round-trip
        d_in = in_clk.to_dict()
        restored_in = RTLComponent.from_dict(d_in)
        self.assertEqual(restored_in.type, ComponentType.INPUT_PORT)
        self.assertEqual(restored_in.label, "clk_100M")
        self.assertEqual(restored_in.pins[0].width, 1)

        d_out = out_anodes.to_dict()
        restored_out = RTLComponent.from_dict(d_out)
        self.assertEqual(restored_out.type, ComponentType.OUTPUT_PORT)
        self.assertEqual(restored_out.label, "anodes[7:0]")
        self.assertEqual(restored_out.pins[0].width, 8)


if __name__ == "__main__":
    unittest.main()
