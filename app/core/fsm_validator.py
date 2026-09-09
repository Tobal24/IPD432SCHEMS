"""
Formal Validator for Finite State Machines (FSM)
Enforces IPD432 (USM) design rules:
1. Initial state must exist.
2. Truly complimentary / complete transitions (checks for missing 'else' or ambiguous conditions).
3. Anti-latch verification (ensures all outputs are assigned or have defaults).
4. Reachability and deadlock detection.
5. Verilog identifier validity.
"""

import re
from dataclasses import dataclass
from typing import List
from app.core.fsm_model import FSM, FSMType


@dataclass
class ValidationIssue:
    severity: str  # "ERROR", "WARNING", "INFO"
    message: str
    location: str = ""


class FSMValidator:
    @staticmethod
    def is_valid_identifier(name: str) -> bool:
        return bool(re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name))

    @classmethod
    def validate(cls, fsm: FSM) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []

        # 1. Check FSM top module name
        if not cls.is_valid_identifier(fsm.name):
            issues.append(ValidationIssue(
                "ERROR",
                f"El nombre del módulo '{fsm.name}' no es un identificador SystemVerilog válido.",
                "Módulo"
            ))

        # 2. Check ports
        port_names = set()
        for p in fsm.inputs + fsm.outputs:
            if not cls.is_valid_identifier(p.name):
                issues.append(ValidationIssue(
                    "ERROR",
                    f"El nombre del puerto '{p.name}' no es válido.",
                    f"Puerto {p.name}"
                ))
            if p.name in port_names:
                issues.append(ValidationIssue(
                    "ERROR",
                    f"Nombre de puerto duplicado: '{p.name}'.",
                    f"Puerto {p.name}"
                ))
            port_names.add(p.name)
            if p.width < 1:
                issues.append(ValidationIssue(
                    "ERROR",
                    f"El ancho del puerto '{p.name}' debe ser al menos 1.",
                    f"Puerto {p.name}"
                ))

        # 3. Check states existence and uniqueness
        if not fsm.states:
            issues.append(ValidationIssue("ERROR", "La FSM no tiene estados definidos.", "Estados"))
            return issues

        state_names = set()
        initial_states = []
        for s in fsm.states:
            if not cls.is_valid_identifier(s.name):
                issues.append(ValidationIssue(
                    "ERROR",
                    f"El nombre del estado '{s.name}' no es un identificador válido.",
                    f"Estado {s.name}"
                ))
            if s.name in state_names:
                issues.append(ValidationIssue(
                    "ERROR",
                    f"Nombre de estado duplicado: '{s.name}'.",
                    f"Estado {s.name}"
                ))
            state_names.add(s.name)
            if s.is_initial:
                initial_states.append(s.name)

        if len(initial_states) == 0:
            issues.append(ValidationIssue(
                "WARNING",
                f"No se definió un estado de reset explícito. Se asumirá '{fsm.states[0].name}'.",
                "Reset"
            ))
        elif len(initial_states) > 1:
            issues.append(ValidationIssue(
                "ERROR",
                f"Múltiples estados marcados como iniciales: {', '.join(initial_states)}.",
                "Reset"
            ))

        # 4. Anti-Latch Check (IPD432 fundamental principle)
        output_names = {p.name for p in fsm.outputs}
        if fsm.fsm_type == FSMType.MOORE:
            for s in fsm.states:
                unassigned = output_names - set(s.moore_outputs.keys())
                for out_name in unassigned:
                    # Check if port has default value
                    port = next((p for p in fsm.outputs if p.name == out_name), None)
                    if not port or port.default_val is None or port.default_val.strip() == "":
                        issues.append(ValidationIssue(
                            "ERROR",
                            f"En estado '{s.name}', la salida '{out_name}' no está asignada y no tiene valor por defecto (posible inferencia de latch).",
                            f"Estado {s.name}"
                        ))
                    else:
                        issues.append(ValidationIssue(
                            "INFO",
                            f"En estado '{s.name}', la salida '{out_name}' toma el valor por defecto ('{port.default_val}').",
                            f"Estado {s.name}"
                        ))

        # 5. Transitions Validation (Complementary & Deterministic)
        for s in fsm.states:
            out_trans = fsm.get_transitions_from(s.name)
            if not out_trans:
                issues.append(ValidationIssue(
                    "WARNING",
                    f"El estado '{s.name}' no tiene transiciones salientes (estado muerto / deadlock).",
                    f"Estado {s.name}"
                ))
                continue

            conditions = [t.condition.strip() for t in out_trans]
            else_count = sum(1 for c in conditions if c.lower() in ("else", "default", "1", "1'b1", ""))
            
            # Check for ambiguous identical conditions
            seen_conds = set()
            for t in out_trans:
                c = t.condition.strip()
                if c in seen_conds and c.lower() not in ("else", "default", ""):
                    issues.append(ValidationIssue(
                        "ERROR",
                        f"Condición de transición duplicada '{c}' desde el estado '{s.name}'. Diagrama no determinista.",
                        f"Transición desde {s.name}"
                    ))
                seen_conds.add(c)

                # Check target exists
                if t.target not in state_names:
                    issues.append(ValidationIssue(
                        "ERROR",
                        f"Transición desde '{s.name}' apunta a un estado inexistente '{t.target}'.",
                        f"Transición desde {s.name}"
                    ))

                # If Mealy, check output assignments
                if fsm.fsm_type == FSMType.MEALY:
                    unassigned_mealy = output_names - set(t.mealy_outputs.keys())
                    for out_name in unassigned_mealy:
                        port = next((p for p in fsm.outputs if p.name == out_name), None)
                        if not port or not port.default_val:
                            issues.append(ValidationIssue(
                                "WARNING",
                                f"En transición '{s.name}' -> '{t.target}', salida Mealy '{out_name}' no asignada.",
                                f"Transición {s.name}->{t.target}"
                            ))

            # Complementary check: If there are conditional branches, is there an 'else' / default path?
            if len(out_trans) > 1 and else_count == 0:
                issues.append(ValidationIssue(
                    "WARNING",
                    f"Las transiciones del estado '{s.name}' no tienen rama 'else' explícita. Asegúrese de que sean estrictamente complementarias.",
                    f"Estado {s.name}"
                ))
            elif else_count > 1:
                issues.append(ValidationIssue(
                    "ERROR",
                    f"El estado '{s.name}' tiene más de una rama 'else' / por defecto.",
                    f"Estado {s.name}"
                ))

        # 6. Reachability Analysis (Graph Traversal from Initial State)
        init_name = initial_states[0] if initial_states else fsm.states[0].name
        reachable = set()
        queue = [init_name]
        while queue:
            curr = queue.pop(0)
            if curr in reachable:
                continue
            reachable.add(curr)
            for t in fsm.get_transitions_from(curr):
                if t.target in state_names and t.target not in reachable:
                    queue.append(t.target)

        unreachable = state_names - reachable
        for u in unreachable:
            issues.append(ValidationIssue(
                "WARNING",
                f"El estado '{u}' es inalcanzable desde el estado inicial '{init_name}'.",
                f"Estado {u}"
            ))

        return issues
