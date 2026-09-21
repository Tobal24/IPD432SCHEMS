"""
FSM Data Model for IPD432 Digital Systems Design.
Defines Moore & Mealy state machines, states, transitions, ports, and encoding.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional
import json


class FSMType(str, Enum):
    MOORE = "Moore"
    MEALY = "Mealy"


class ResetType(str, Enum):
    SYNC_HIGH = "Sincrónico (Activo en Alto)"
    SYNC_LOW = "Sincrónico (Activo en Bajo)"
    ASYNC_HIGH = "Asincrónico (Activo en Alto)"
    ASYNC_LOW = "Asincrónico (Activo en Bajo)"


class FSMEncoding(str, Enum):
    AUTO = "Auto (Vivado decide)"
    SEQUENTIAL = "Sequential (Binario)"
    ONE_HOT = "One-Hot"
    GRAY = "Gray"
    JOHNSON = "Johnson"


@dataclass
class Port:
    name: str
    direction: str = "input"  # "input" or "output"
    width: int = 1
    default_val: str = "0"    # Crucial for preventing latches in combinational logic

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "direction": self.direction,
            "width": self.width,
            "default_val": self.default_val
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Port":
        return cls(
            name=data["name"],
            direction=data.get("direction", "input"),
            width=data.get("width", 1),
            default_val=data.get("default_val", "0")
        )


@dataclass
class State:
    name: str
    is_initial: bool = False
    encoding: str = ""                         # Optional explicit binary/one-hot value (e.g., "2'b00")
    moore_outputs: Dict[str, str] = field(default_factory=dict)  # port_name -> value string
    x: float = 0.0                             # Visual layout coordinates
    y: float = 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "is_initial": self.is_initial,
            "encoding": self.encoding,
            "moore_outputs": dict(self.moore_outputs),
            "x": self.x,
            "y": self.y
        }

    @classmethod
    def from_dict(cls, data: dict) -> "State":
        return cls(
            name=data["name"],
            is_initial=data.get("is_initial", False),
            encoding=data.get("encoding", ""),
            moore_outputs=dict(data.get("moore_outputs", {})),
            x=data.get("x", 0.0),
            y=data.get("y", 0.0)
        )


@dataclass
class Transition:
    source: str
    target: str
    condition: str = "else"                    # e.g., "TA == 1'b0", "en", "else"
    timer_cycles: int = 0                      # >0 indicates timed transition (t == T-1)
    is_timed: bool = False
    mealy_outputs: Dict[str, str] = field(default_factory=dict) # port_name -> value string
    custom_label_pos: Optional[Tuple[float, float]] = None      # Custom position for condition label badge

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "condition": self.condition,
            "timer_cycles": self.timer_cycles,
            "is_timed": self.is_timed,
            "mealy_outputs": dict(self.mealy_outputs),
            "custom_label_pos": list(self.custom_label_pos) if self.custom_label_pos else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Transition":
        raw_pos = data.get("custom_label_pos")
        c_pos = (float(raw_pos[0]), float(raw_pos[1])) if raw_pos else None
        return cls(
            source=data["source"],
            target=data["target"],
            condition=data.get("condition", "else"),
            timer_cycles=data.get("timer_cycles", 0),
            is_timed=data.get("is_timed", False),
            mealy_outputs=dict(data.get("mealy_outputs", {})),
            custom_label_pos=c_pos
        )


@dataclass
class FSM:
    name: str = "fsm_top"
    fsm_type: FSMType = FSMType.MOORE
    reset_type: ResetType = ResetType.SYNC_HIGH
    encoding: FSMEncoding = FSMEncoding.AUTO
    clk_name: str = "clk"
    rst_name: str = "reset"
    inputs: List[Port] = field(default_factory=list)
    outputs: List[Port] = field(default_factory=list)
    states: List[State] = field(default_factory=list)
    transitions: List[Transition] = field(default_factory=list)

    def get_initial_state(self) -> Optional[State]:
        for s in self.states:
            if s.is_initial:
                return s
        return self.states[0] if self.states else None

    def find_state(self, name: str) -> Optional[State]:
        for s in self.states:
            if s.name == name:
                return s
        return None

    def get_transitions_from(self, state_name: str) -> List[Transition]:
        return [t for t in self.transitions if t.source == state_name]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "fsm_type": self.fsm_type.value,
            "reset_type": self.reset_type.value,
            "encoding": self.encoding.value,
            "clk_name": self.clk_name,
            "rst_name": self.rst_name,
            "inputs": [p.to_dict() for p in self.inputs],
            "outputs": [p.to_dict() for p in self.outputs],
            "states": [s.to_dict() for s in self.states],
            "transitions": [t.to_dict() for t in self.transitions]
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FSM":
        fsm = cls(
            name=data.get("name", "fsm_top"),
            fsm_type=FSMType(data.get("fsm_type", FSMType.MOORE.value)),
            reset_type=ResetType(data.get("reset_type", ResetType.SYNC_HIGH.value)),
            encoding=FSMEncoding(data.get("encoding", FSMEncoding.AUTO.value)),
            clk_name=data.get("clk_name", "clk"),
            rst_name=data.get("rst_name", "reset"),
            inputs=[Port.from_dict(p) for p in data.get("inputs", [])],
            outputs=[Port.from_dict(p) for p in data.get("outputs", [])],
            states=[State.from_dict(s) for s in data.get("states", [])],
            transitions=[Transition.from_dict(t) for t in data.get("transitions", [])]
        )
        return fsm

    def save_to_file(self, filepath: str):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load_from_file(cls, filepath: str) -> "FSM":
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def create_sequence_detector_mealy(cls) -> "FSM":
        """
        Canonical Mealy FSM example from digital systems design (IPD432 / ELO212):
        Sequence detector for pattern '101' with overlapping.
        Inputs: din (1-bit)
        Outputs: pattern_found (1-bit, asserted on transition when '101' is detected)
        States: S0 (reset/idle), S1 (matched '1'), S2 (matched '10').
        Requires only 3 states in Mealy compared to 4 states in Moore.
        """
        return cls(
            name="seq_detector_101_mealy",
            fsm_type=FSMType.MEALY,
            reset_type=ResetType.SYNC_HIGH,
            encoding=FSMEncoding.SEQUENTIAL,
            inputs=[
                Port(name="din", width=1, default_val="1'b0")
            ],
            outputs=[
                Port(name="pattern_found", width=1, default_val="1'b0")
            ],
            states=[
                State(name="S0", is_initial=True, x=-220, y=0),
                State(name="S1", x=0, y=0),
                State(name="S2", x=220, y=0),
            ],
            transitions=[
                Transition(source="S0", target="S1", condition="din == 1'b1", mealy_outputs={"pattern_found": "1'b0"}),
                Transition(source="S0", target="S0", condition="else", mealy_outputs={"pattern_found": "1'b0"}),
                Transition(source="S1", target="S2", condition="din == 1'b0", mealy_outputs={"pattern_found": "1'b0"}),
                Transition(source="S1", target="S1", condition="else", mealy_outputs={"pattern_found": "1'b0"}),
                Transition(source="S2", target="S1", condition="din == 1'b1", mealy_outputs={"pattern_found": "1'b1"}),
                Transition(source="S2", target="S0", condition="else", mealy_outputs={"pattern_found": "1'b0"}),
            ]
        )
