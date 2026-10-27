"""
FSM Data Model for IPD432 Digital Systems Design.
Defines Moore & Mealy state machines, states, transitions, ports, and encoding.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
import json
import re


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
    start_angle: Optional[float] = None                         # Custom start angle (radians) on source state circle
    end_angle: Optional[float] = None                           # Custom end angle (radians) on target state circle

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "condition": self.condition,
            "timer_cycles": self.timer_cycles,
            "is_timed": self.is_timed,
            "mealy_outputs": dict(self.mealy_outputs),
            "custom_label_pos": list(self.custom_label_pos) if self.custom_label_pos else None,
            "start_angle": self.start_angle,
            "end_angle": self.end_angle
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Transition":
        raw_pos = data.get("custom_label_pos")
        c_pos = (float(raw_pos[0]), float(raw_pos[1])) if raw_pos else None
        raw_sa = data.get("start_angle")
        raw_ea = data.get("end_angle")
        return cls(
            source=data["source"],
            target=data["target"],
            condition=data.get("condition", "else"),
            timer_cycles=data.get("timer_cycles", 0),
            is_timed=data.get("is_timed", False),
            mealy_outputs=dict(data.get("mealy_outputs", {})),
            custom_label_pos=c_pos,
            start_angle=float(raw_sa) if raw_sa is not None else None,
            end_angle=float(raw_ea) if raw_ea is not None else None
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
    legend_pos: Optional[Tuple[float, float]] = None

    @staticmethod
    def infer_literal_width(val_str: str) -> int:
        if not val_str:
            return 1
        s = val_str.strip()
        m_sized = re.match(r"^(\d+)\s*'[bBdDhHoO]", s)
        if m_sized:
            return max(1, int(m_sized.group(1)))
        m_bin = re.match(r"^[01xXzZ]{2,}$", s)
        if m_bin:
            return len(s)
        return 1

    def extract_diagram_io(self) -> Tuple[List[Port], List[Port]]:
        """Extracts input and output ports referenced in transitions and states."""
        state_names = {s.name for s in self.states}
        reserved = {
            "else", "default", "and", "or", "not", "xor", "nand", "nor", "xnor",
            "true", "false", "posedge", "negedge", "clk", "reset", "rst",
            self.clk_name, self.rst_name
        }

        # 1. Outputs from states (Moore) and transitions (Mealy)
        out_widths: Dict[str, int] = {}
        out_defaults: Dict[str, str] = {}
        for s in self.states:
            for k, v in s.moore_outputs.items():
                k_clean = k.strip()
                if not k_clean:
                    continue
                w = self.infer_literal_width(v)
                out_widths[k_clean] = max(out_widths.get(k_clean, 1), w)
                if k_clean not in out_defaults and v.strip():
                    out_defaults[k_clean] = v.strip()

        for t in self.transitions:
            for k, v in t.mealy_outputs.items():
                k_clean = k.strip()
                if not k_clean:
                    continue
                w = self.infer_literal_width(v)
                out_widths[k_clean] = max(out_widths.get(k_clean, 1), w)
                if k_clean not in out_defaults and v.strip():
                    out_defaults[k_clean] = v.strip()

        extracted_outputs = [
            Port(name=k, direction="output", width=w, default_val=out_defaults.get(k, f"{w}'b0" if w > 1 else "1'b0"))
            for k, w in out_widths.items()
        ]
        output_names = set(out_widths.keys()) | {p.name for p in self.outputs}

        # 2. Inputs from transition conditions
        in_widths: Dict[str, int] = {}
        for t in self.transitions:
            cond = t.condition.strip()
            if not cond or cond.lower() in ("else", "default"):
                continue

            # Check comparisons like sig == 2'b10 to infer width
            for m_cmp in re.finditer(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:==|!=|<=|>=|<|>)\s*(\d+\s*'[bBdDhHoO][0-9a-fA-FxXzZ_]+)", cond):
                sig_name = m_cmp.group(1)
                w = self.infer_literal_width(m_cmp.group(2))
                in_widths[sig_name] = max(in_widths.get(sig_name, 1), w)

            # Check bit slice like sig[3:0]
            for m_slice in re.finditer(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*\[\s*(\d+)\s*:\s*(\d+)\s*\]", cond):
                sig_name = m_slice.group(1)
                msb, lsb = int(m_slice.group(2)), int(m_slice.group(3))
                w = abs(msb - lsb) + 1
                in_widths[sig_name] = max(in_widths.get(sig_name, 1), w)

            # Remove Verilog sized literals (e.g. 1'b0, 4'hF) and numbers before scanning identifiers
            cleaned = re.sub(r"\b\d+\s*'[bBdDhHoO][0-9a-fA-FxXzZ_]+\b", " ", cond)
            cleaned = re.sub(r"'[01xXzZ]\b", " ", cleaned)
            cleaned = re.sub(r"\b\d+\b", " ", cleaned)

            for m_id in re.finditer(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b", cleaned):
                ident = m_id.group(1)
                if ident.lower() in reserved or ident in reserved:
                    continue
                if ident in state_names or ident in output_names:
                    continue
                if ident == "t" and (t.is_timed or re.search(r"\bt\s*(?:==|=|>=|<=|>|<)", cond)):
                    continue
                if ident not in in_widths:
                    in_widths[ident] = 1

        extracted_inputs = [
            Port(name=k, direction="input", width=w, default_val=f"{w}'b0" if w > 1 else "1'b0")
            for k, w in in_widths.items()
        ]
        return extracted_inputs, extracted_outputs

    def get_all_declared_io(self) -> Tuple[List[Port], List[Port]]:
        """Returns all declared inputs and outputs, combining explicit ports with diagram signals."""
        ext_in, ext_out = self.extract_diagram_io()

        in_map: Dict[str, Port] = {}
        for p in self.inputs:
            in_map[p.name] = Port(name=p.name, direction="input", width=p.width, default_val=p.default_val)
        for p in ext_in:
            if p.name not in in_map:
                in_map[p.name] = p
            else:
                in_map[p.name].width = max(in_map[p.name].width, p.width)

        out_map: Dict[str, Port] = {}
        for p in self.outputs:
            out_map[p.name] = Port(name=p.name, direction="output", width=p.width, default_val=p.default_val)
        for p in ext_out:
            if p.name not in out_map:
                out_map[p.name] = p
            else:
                out_map[p.name].width = max(out_map[p.name].width, p.width)

        return list(in_map.values()), list(out_map.values())

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
            "transitions": [t.to_dict() for t in self.transitions],
            "legend_pos": list(self.legend_pos) if self.legend_pos else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FSM":
        raw_lpos = data.get("legend_pos")
        l_pos = (float(raw_lpos[0]), float(raw_lpos[1])) if raw_lpos else None
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
            transitions=[Transition.from_dict(t) for t in data.get("transitions", [])],
            legend_pos=l_pos
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
