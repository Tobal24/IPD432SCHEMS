"""
RTL Schematic Data Model for ELO212 Digital Systems Lab.
Defines components (MUX, FF/Registers, Gates, Circles, Blocks, Bus Splitters, Constants),
orthogonal wires, bit-width annotations, and solder-dot junctions.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
import json
import uuid
import re


class ComponentType(str, Enum):
    MUX = "MUX"
    REGISTER = "REGISTER"
    GATE_AND = "GATE_AND"
    GATE_OR = "GATE_OR"
    GATE_NOT = "GATE_NOT"
    GATE_XOR = "GATE_XOR"
    OPERATOR_CIRCLE = "OPERATOR_CIRCLE"  # e.g., '+', 'A>B', '*'
    BLOCK = "BLOCK"                      # Generic module box (ALU, Memory, etc.)
    BUS_SPLITTER = "BUS_SPLITTER"        # Perpendicular branch bar (Figure 2)
    CONSTANT = "CONSTANT"                # 1'b0, 4'd0, 8'hFF (Figure 9)
    LABEL = "LABEL"                      # Free text annotation


class PinDirection(str, Enum):
    IN = "IN"
    OUT = "OUT"
    CONTROL = "CONTROL"


class PinSide(str, Enum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    TOP = "TOP"
    BOTTOM = "BOTTOM"


@dataclass
class RTLPin:
    id: str
    name: str
    direction: PinDirection
    side: PinSide
    offset: float = 0.5  # Relative position (0.0 to 1.0) along side
    width: int = 1       # 1 for single-bit, >1 for bus

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "direction": self.direction.value,
            "side": self.side.value,
            "offset": self.offset,
            "width": self.width
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RTLPin":
        return cls(
            id=data["id"],
            name=data["name"],
            direction=PinDirection(data.get("direction", PinDirection.IN.value)),
            side=PinSide(data.get("side", PinSide.LEFT.value)),
            offset=data.get("offset", 0.5),
            width=data.get("width", 1)
        )


@dataclass
class RTLComponent:
    id: str
    type: ComponentType
    label: str
    x: float = 0.0
    y: float = 0.0
    width: float = 80.0
    height: float = 80.0
    pins: List[RTLPin] = field(default_factory=list)
    properties: Dict[str, str] = field(default_factory=dict)

    def get_pin(self, pin_id: str) -> Optional[RTLPin]:
        for p in self.pins:
            if p.id == pin_id:
                return p
        return None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type.value,
            "label": self.label,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "pins": [p.to_dict() for p in self.pins],
            "properties": dict(self.properties)
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RTLComponent":
        return cls(
            id=data["id"],
            type=ComponentType(data["type"]),
            label=data.get("label", ""),
            x=data.get("x", 0.0),
            y=data.get("y", 0.0),
            width=data.get("width", 80.0),
            height=data.get("height", 80.0),
            pins=[RTLPin.from_dict(p) for p in data.get("pins", [])],
            properties=dict(data.get("properties", {}))
        )


@dataclass
class RTLWire:
    id: str
    source_comp_id: Optional[str] = None
    source_pin_id: Optional[str] = None
    target_comp_id: Optional[str] = None
    target_pin_id: Optional[str] = None
    points: List[Tuple[float, float]] = field(default_factory=list)  # (x, y) Manhattan vertices
    width: int = 1                                                   # Bit width (default 1)
    label: str = ""                                                  # Signal name, e.g. "bus_ej[5:0]"
    show_slash: bool = True                                          # Show diagonal slash with bit width
    manual_routing: bool = False                                     # If True, wire was manually routed/adjusted
    label_pos: Optional[Tuple[float, float]] = None                  # Custom position for label (x, y) if dragged
    show_arrow: bool = False                                         # Show arrowhead indicating signal direction at target

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_comp_id": self.source_comp_id,
            "source_pin_id": self.source_pin_id,
            "target_comp_id": self.target_comp_id,
            "target_pin_id": self.target_pin_id,
            "points": self.points,
            "width": self.width,
            "label": self.label,
            "show_slash": self.show_slash,
            "manual_routing": self.manual_routing,
            "label_pos": list(self.label_pos) if self.label_pos else None,
            "show_arrow": self.show_arrow
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RTLWire":
        raw_lpos = data.get("label_pos")
        lpos = (float(raw_lpos[0]), float(raw_lpos[1])) if raw_lpos else None
        return cls(
            id=data["id"],
            source_comp_id=data.get("source_comp_id"),
            source_pin_id=data.get("source_pin_id"),
            target_comp_id=data.get("target_comp_id"),
            target_pin_id=data.get("target_pin_id"),
            points=[(p[0], p[1]) for p in data.get("points", [])],
            width=data.get("width", 1),
            label=data.get("label", ""),
            show_slash=data.get("show_slash", True),
            manual_routing=data.get("manual_routing", False),
            label_pos=lpos,
            show_arrow=data.get("show_arrow", False)
        )


@dataclass
class RTLJunction:
    id: str
    x: float
    y: float
    wire_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "x": self.x,
            "y": self.y,
            "wire_ids": list(self.wire_ids)
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RTLJunction":
        return cls(
            id=data["id"],
            x=data["x"],
            y=data["y"],
            wire_ids=list(data.get("wire_ids", []))
        )


@dataclass
class RTLSchematic:
    name: str = "schematic_top"
    components: List[RTLComponent] = field(default_factory=list)
    wires: List[RTLWire] = field(default_factory=list)
    junctions: List[RTLJunction] = field(default_factory=list)

    def add_component(self, comp: RTLComponent):
        self.components.append(comp)

    def find_component(self, comp_id: str) -> Optional[RTLComponent]:
        for c in self.components:
            if c.id == comp_id:
                return c
        return None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "components": [c.to_dict() for c in self.components],
            "wires": [w.to_dict() for w in self.wires],
            "junctions": [j.to_dict() for j in self.junctions]
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RTLSchematic":
        return cls(
            name=data.get("name", "schematic_top"),
            components=[RTLComponent.from_dict(c) for c in data.get("components", [])],
            wires=[RTLWire.from_dict(w) for w in data.get("wires", [])],
            junctions=[RTLJunction.from_dict(j) for j in data.get("junctions", [])]
        )

    def save_to_file(self, filepath: str):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load_from_file(cls, filepath: str) -> "RTLSchematic":
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


def parse_slice_width(slice_str: str) -> int:
    """
    Parses a bus slice string and returns the bit-width.
    Examples:
      '[2:0]' -> 3
      '[3]' -> 1
      '[15:4]' -> 12
      'bus_ej[2:0]' -> 3
      'data[7:0]' -> 8
      'sig' -> 1
    """
    m_range = re.search(r'\[\s*(\d+)\s*:\s*(\d+)\s*\]', slice_str)
    if m_range:
        h = int(m_range.group(1))
        l = int(m_range.group(2))
        return abs(h - l) + 1
    m_single = re.search(r'\[\s*(\d+)\s*\]', slice_str)
    if m_single:
        return 1
    return 1


# Helper Component Factory to instantiate compliant standard symbols
class ComponentFactory:
    @staticmethod
    def create_mux(x: float = 0, y: float = 0, num_inputs: int = 2, width: int = 1,
                   label: str = "MUX", input_names: Optional[List[str]] = None,
                   sel_side: str = "BOTTOM") -> RTLComponent:
        comp_id = f"mux_{uuid.uuid4().hex[:6]}"
        pins = []
        if input_names:
            num_inputs = len(input_names)
        else:
            input_names = [str(i) for i in range(num_inputs)]

        # Calculate width needed for input labels
        max_label_len = max((len(n) for n in input_names), default=1)
        mux_w = max(70.0, 40.0 + max_label_len * 9.0 + 20.0)

        # Input pins on left (wide side)
        for i, in_name in enumerate(input_names):
            offset = (i + 1) / (num_inputs + 1)
            pins.append(RTLPin(
                id=f"{comp_id}_in_{i}",
                name=in_name,
                direction=PinDirection.IN,
                side=PinSide.LEFT,
                offset=offset,
                width=width
            ))
        # Select pin on top or bottom
        s_side = PinSide.TOP if sel_side.upper() == "TOP" else PinSide.BOTTOM
        pins.append(RTLPin(
            id=f"{comp_id}_sel",
            name="sel",
            direction=PinDirection.CONTROL,
            side=s_side,
            offset=0.5,
            width=max(1, (num_inputs - 1).bit_length())
        ))
        # Output pin on right (narrow side)
        pins.append(RTLPin(
            id=f"{comp_id}_out",
            name="out",
            direction=PinDirection.OUT,
            side=PinSide.RIGHT,
            offset=0.5,
            width=width
        ))
        return RTLComponent(
            id=comp_id,
            type=ComponentType.MUX,
            label=label,
            x=x,
            y=y,
            width=mux_w,
            height=max(80.0, num_inputs * 30.0),
            pins=pins,
            properties={
                "num_inputs": str(num_inputs),
                "bus_width": str(width),
                "input_names": json.dumps(input_names),
                "sel_side": sel_side.upper()
            }
        )

    @staticmethod
    def create_register(x: float = 0, y: float = 0, width: int = 1, label: str = "REG") -> RTLComponent:
        comp_id = f"reg_{uuid.uuid4().hex[:6]}"
        pins = [
            RTLPin(id=f"{comp_id}_D", name="D", direction=PinDirection.IN, side=PinSide.LEFT, offset=0.5, width=width),
            RTLPin(id=f"{comp_id}_Q", name="Q", direction=PinDirection.OUT, side=PinSide.RIGHT, offset=0.5, width=width),
            RTLPin(id=f"{comp_id}_clk", name="clk", direction=PinDirection.CONTROL, side=PinSide.BOTTOM, offset=0.5, width=1),
            RTLPin(id=f"{comp_id}_rst", name="rst", direction=PinDirection.CONTROL, side=PinSide.TOP, offset=0.5, width=1),
            RTLPin(id=f"{comp_id}_ce", name="CE", direction=PinDirection.CONTROL, side=PinSide.LEFT, offset=0.8, width=1)
        ]
        return RTLComponent(
            id=comp_id,
            type=ComponentType.REGISTER,
            label=label,
            x=x,
            y=y,
            width=80.0,
            height=100.0,
            pins=pins,
            properties={"bus_width": str(width)}
        )

    @staticmethod
    def create_operator(x: float = 0, y: float = 0, op: str = "+", width: int = 4) -> RTLComponent:
        comp_id = f"op_{uuid.uuid4().hex[:6]}"
        pins = [
            RTLPin(id=f"{comp_id}_a", name="A", direction=PinDirection.IN, side=PinSide.LEFT, offset=0.3, width=width),
            RTLPin(id=f"{comp_id}_b", name="B", direction=PinDirection.IN, side=PinSide.LEFT, offset=0.7, width=width),
            RTLPin(id=f"{comp_id}_out", name="out", direction=PinDirection.OUT, side=PinSide.RIGHT, offset=0.5, width=width)
        ]
        return RTLComponent(
            id=comp_id,
            type=ComponentType.OPERATOR_CIRCLE,
            label=op,
            x=x,
            y=y,
            width=60.0,
            height=60.0,
            pins=pins,
            properties={"op": op, "bus_width": str(width)}
        )

    @staticmethod
    def create_constant(x: float = 0, y: float = 0, val: str = "1'b0", width: int = 1) -> RTLComponent:
        comp_id = f"const_{uuid.uuid4().hex[:6]}"
        pins = [
            RTLPin(id=f"{comp_id}_out", name="val", direction=PinDirection.OUT, side=PinSide.RIGHT, offset=0.5, width=width)
        ]
        return RTLComponent(
            id=comp_id,
            type=ComponentType.CONSTANT,
            label=val,
            x=x,
            y=y,
            width=70.0,
            height=35.0,
            pins=pins,
            properties={"val": val, "bus_width": str(width)}
        )

    @staticmethod
    def create_bus_splitter(x: float = 0, y: float = 0, in_width: int = 16,
                            slices: str = "[2:0], [3], [15:4]", base_name: str = "") -> RTLComponent:
        comp_id = f"split_{uuid.uuid4().hex[:6]}"
        slice_list = [s.strip() for s in slices.split(",") if s.strip()]
        in_name = f"{base_name}[{in_width-1}:0]" if base_name else f"[{in_width-1}:0]"
        pins = [
            RTLPin(id=f"{comp_id}_in", name=in_name, direction=PinDirection.IN, side=PinSide.LEFT, offset=0.5, width=in_width)
        ]
        for idx, s in enumerate(slice_list):
            offset = (idx + 1) / (len(slice_list) + 1)
            swidth = parse_slice_width(s)
            slice_label = f"{base_name}{s}" if base_name and not s.startswith(base_name) else s
            pins.append(RTLPin(
                id=f"{comp_id}_out_{idx}",
                name=slice_label,
                direction=PinDirection.OUT,
                side=PinSide.RIGHT,
                offset=offset,
                width=swidth
            ))
        max_s_len = max((len(p.name) for p in pins), default=5)
        comp_w = max(110.0, 45.0 + max_s_len * 8.0)
        return RTLComponent(
            id=comp_id,
            type=ComponentType.BUS_SPLITTER,
            label=base_name or "SPLIT",
            x=x,
            y=y,
            width=comp_w,
            height=max(70.0, len(slice_list) * 40.0),
            pins=pins,
            properties={"in_width": str(in_width), "slices": slices, "base_name": base_name}
        )

    @staticmethod
    def create_gate(x: float = 0, y: float = 0, gate_type: str = "AND") -> RTLComponent:
        gtype_map = {
            "AND": ComponentType.GATE_AND,
            "OR": ComponentType.GATE_OR,
            "NOT": ComponentType.GATE_NOT,
            "XOR": ComponentType.GATE_XOR
        }
        ctype = gtype_map.get(gate_type.upper(), ComponentType.GATE_AND)
        comp_id = f"gate_{gate_type.lower()}_{uuid.uuid4().hex[:6]}"
        if ctype == ComponentType.GATE_NOT:
            pins = [
                RTLPin(id=f"{comp_id}_in", name="in", direction=PinDirection.IN, side=PinSide.LEFT, offset=0.5, width=1),
                RTLPin(id=f"{comp_id}_out", name="out", direction=PinDirection.OUT, side=PinSide.RIGHT, offset=0.5, width=1)
            ]
        else:
            pins = [
                RTLPin(id=f"{comp_id}_a", name="A", direction=PinDirection.IN, side=PinSide.LEFT, offset=0.3, width=1),
                RTLPin(id=f"{comp_id}_b", name="B", direction=PinDirection.IN, side=PinSide.LEFT, offset=0.7, width=1),
                RTLPin(id=f"{comp_id}_out", name="out", direction=PinDirection.OUT, side=PinSide.RIGHT, offset=0.5, width=1)
            ]
        return RTLComponent(
            id=comp_id,
            type=ctype,
            label=gate_type.upper(),
            x=x,
            y=y,
            width=65.0,
            height=55.0,
            pins=pins
        )

    @staticmethod
    def create_generic_block(x: float = 0, y: float = 0, name: str = "ALU",
                             inputs: List[str] = None, outputs: List[str] = None) -> RTLComponent:
        comp_id = f"blk_{uuid.uuid4().hex[:6]}"
        inputs = inputs or ["A", "B", "ctrl"]
        outputs = outputs or ["result", "zero"]
        pins = []
        for i, in_name in enumerate(inputs):
            pins.append(RTLPin(
                id=f"{comp_id}_in_{i}",
                name=in_name,
                direction=PinDirection.IN,
                side=PinSide.LEFT,
                offset=(i + 1) / (len(inputs) + 1),
                width=1
            ))
        for i, out_name in enumerate(outputs):
            pins.append(RTLPin(
                id=f"{comp_id}_out_{i}",
                name=out_name,
                direction=PinDirection.OUT,
                side=PinSide.RIGHT,
                offset=(i + 1) / (len(outputs) + 1),
                width=1
            ))
        return RTLComponent(
            id=comp_id,
            type=ComponentType.BLOCK,
            label=name,
            x=x,
            y=y,
            width=100.0,
            height=max(80.0, max(len(inputs), len(outputs)) * 30.0),
            pins=pins
        )
