"""
Unit tests for RTL Schematic Data Model and Factory.
"""

import unittest
import os
import tempfile
from app.core.rtl_model import (
    RTLSchematic, ComponentFactory, ComponentType, RTLWire, RTLJunction
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


if __name__ == "__main__":
    unittest.main()
