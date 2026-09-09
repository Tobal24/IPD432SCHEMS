"""
Unit tests for FSM Data Model, Validator and SystemVerilog Generator.
Validates against the course examples (Traffic Light Controller & Level-to-Pulse).
"""

import unittest
from app.core.fsm_model import FSM, FSMType, Port, State, Transition, ResetType, FSMEncoding
from app.core.fsm_validator import FSMValidator
from app.core.sv_generator import SystemVerilogGenerator


class TestFSMSuite(unittest.TestCase):
    def test_traffic_light_controller(self):
        fsm = FSM(
            name="traffic_light_controller",
            fsm_type=FSMType.MOORE,
            reset_type=ResetType.SYNC_HIGH,
            encoding=FSMEncoding.SEQUENTIAL,
            inputs=[
                Port(name="TA", width=1, default_val="1'b0"),
                Port(name="TB", width=1, default_val="1'b0")
            ],
            outputs=[
                Port(name="LA", width=2, default_val="2'b10"), # Default red
                Port(name="LB", width=2, default_val="2'b10")
            ],
            states=[
                State(name="S0", is_initial=True, moore_outputs={"LA": "2'b00", "LB": "2'b10"}), # Green, Red
                State(name="S1", moore_outputs={"LA": "2'b01", "LB": "2'b10"}),                 # Yellow, Red
                State(name="S2", moore_outputs={"LA": "2'b10", "LB": "2'b00"}),                 # Red, Green
                State(name="S3", moore_outputs={"LA": "2'b10", "LB": "2'b01"}),                 # Red, Yellow
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

        issues = FSMValidator.validate(fsm)
        errors = [i for i in issues if i.severity == "ERROR"]
        self.assertEqual(len(errors), 0, f"Unexpected validation errors: {errors}")

        sv_code = SystemVerilogGenerator.generate(fsm, style="two_always")
        self.assertIn("module traffic_light_controller", sv_code)
        self.assertIn("typedef enum logic [1:0] {S0, S1, S2, S3} state_t;", sv_code)
        self.assertIn("always_ff @(posedge clk)", sv_code)
        self.assertIn("always_comb begin", sv_code)
        self.assertIn("LA = 2'b00;", sv_code)

    def test_level_to_pulse(self):
        fsm = FSM(
            name="level_to_pulse",
            fsm_type=FSMType.MOORE,
            reset_type=ResetType.SYNC_HIGH,
            inputs=[Port(name="L", width=1, default_val="1'b0")],
            outputs=[Port(name="P", width=1, default_val="1'b0")],
            states=[
                State(name="S0", is_initial=True, moore_outputs={"P": "1'b0"}),
                State(name="S1", moore_outputs={"P": "1'b1"}),
                State(name="S2", moore_outputs={"P": "1'b0"}),
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

        issues = FSMValidator.validate(fsm)
        errors = [i for i in issues if i.severity == "ERROR"]
        self.assertEqual(len(errors), 0)

        sv_code = SystemVerilogGenerator.generate(fsm, style="three_always")
        self.assertIn("module level_to_pulse", sv_code)
        self.assertIn("P = 1'b1;", sv_code)

    def test_validator_catches_unassigned_outputs(self):
        fsm = FSM(
            name="bad_fsm",
            inputs=[Port(name="x")],
            outputs=[Port(name="y", default_val="")], # No default value!
            states=[
                State(name="S0", is_initial=True, moore_outputs={}), # Unassigned y!
            ],
            transitions=[
                Transition(source="S0", target="S0", condition="else")
            ]
        )
        issues = FSMValidator.validate(fsm)
        errors = [i for i in issues if i.severity == "ERROR" and "latch" in i.message.lower()]
        self.assertTrue(len(errors) > 0, "Validator should detect potential latch")


if __name__ == "__main__":
    unittest.main()
