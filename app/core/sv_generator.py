"""
SystemVerilog HDL Generator for IPD432.
Strictly follows guidelines:
- Symbolic enum state encoding with optional Vivado synthesis attribute.
- Two-always block (canonical) and Three-always block styles.
- Anti-latch default assignments at the beginning of always_comb.
- Support for synchronous / asynchronous resets (high or low active).
- Timed transitions with automatic timer counter logic.
"""
from __future__ import annotations

import math
from app.core.fsm_model import FSM, FSMType, ResetType, FSMEncoding


class SystemVerilogGenerator:
    @staticmethod
    def generate(fsm: FSM, style: str = "two_always", register_outputs: bool = False) -> str:
        """
        Generate SystemVerilog code.
        style: 'two_always' or 'three_always'
        """
        lines = []
        num_states = len(fsm.states)
        if num_states == 0:
            return "// Error: No states defined in FSM"

        state_bits = max(1, math.ceil(math.log2(num_states)))
        init_state = fsm.get_initial_state()
        init_name = init_state.name if init_state else fsm.states[0].name

        has_timers = any(t.is_timed and t.timer_cycles > 0 for t in fsm.transitions)
        max_timer = max([t.timer_cycles for t in fsm.transitions if t.is_timed], default=0)
        timer_bits = max(1, math.ceil(math.log2(max_timer + 1))) if has_timers else 0

        # Header Comments
        lines.append("// =============================================================================")
        lines.append(f"// Module: {fsm.name}")
        lines.append(f"// Generated for IPD432 / ELO212 - USM")
        lines.append(f"// FSM Type: {fsm.fsm_type.value} | Style: {style} | States: {num_states}")
        lines.append("// Follows strict course conventions: symbolic enum, anti-latch default assignments")
        lines.append("// =============================================================================\n")

        # Module Declaration
        lines.append(f"module {fsm.name} (")
        port_decls = []
        port_decls.append(f"    input  logic {fsm.clk_name}")
        port_decls.append(f"    input  logic {fsm.rst_name}")

        for p in fsm.inputs:
            w_str = f"[{p.width-1}:0] " if p.width > 1 else ""
            port_decls.append(f"    input  logic {w_str}{p.name}")

        for p in fsm.outputs:
            w_str = f"[{p.width-1}:0] " if p.width > 1 else ""
            port_decls.append(f"    output logic {w_str}{p.name}")

        lines.append(",\n".join(port_decls))
        lines.append(");\n")

        # State Enum Definition
        if fsm.encoding == FSMEncoding.ONE_HOT:
            lines.append('    (* fsm_encoding = "one_hot" *)')
        elif fsm.encoding == FSMEncoding.SEQUENTIAL:
            lines.append('    (* fsm_encoding = "sequential" *)')
        elif fsm.encoding == FSMEncoding.GRAY:
            lines.append('    (* fsm_encoding = "gray" *)')
        elif fsm.encoding == FSMEncoding.JOHNSON:
            lines.append('    (* fsm_encoding = "johnson" *)')

        # Check if states have explicit custom encodings
        has_explicit_encoding = any(s.encoding.strip() for s in fsm.states)
        if has_explicit_encoding:
            state_enum_list = [f"{s.name} = {s.encoding.strip()}" if s.encoding.strip() else s.name for s in fsm.states]
        else:
            state_enum_list = [s.name for s in fsm.states]

        enum_str = ", ".join(state_enum_list)
        lines.append(f"    typedef enum logic [{state_bits-1}:0] {{{enum_str}}} state_t;")
        lines.append("    state_t State, NextState;\n")

        # Timer logic if needed
        if has_timers:
            lines.append(f"    // Timer counter for timed transitions (IPD432 slide 58-59)")
            lines.append(f"    logic [{timer_bits-1}:0] timer_cnt;")
            lines.append("    logic timer_rst;\n")

        # -------------------------------------------------------------
        # 1. State Register (always_ff)
        # -------------------------------------------------------------
        is_async = "Asincrónico" in fsm.reset_type.value
        is_low = "Bajo" in fsm.reset_type.value

        if is_async:
            edge = "negedge" if is_low else "posedge"
            sensitivity = f"@(posedge {fsm.clk_name} or {edge} {fsm.rst_name})"
        else:
            sensitivity = f"@(posedge {fsm.clk_name})"

        rst_condition = f"!{fsm.rst_name}" if is_low else f"{fsm.rst_name}"

        lines.append(f"    // 1. State Register (Synchronous Sequential Logic)")
        lines.append(f"    always_ff {sensitivity} begin")
        lines.append(f"        if ({rst_condition}) begin")
        lines.append(f"            State <= {init_name};")
        if has_timers:
            lines.append(f"            timer_cnt <= '0;")
        lines.append(f"        end else begin")
        lines.append(f"            State <= NextState;")
        if has_timers:
            lines.append(f"            if (timer_rst) begin")
            lines.append(f"                timer_cnt <= '0;")
            lines.append(f"            end else begin")
            lines.append(f"                timer_cnt <= timer_cnt + 1'b1;")
            lines.append(f"            end")
        lines.append(f"        end")
        lines.append(f"    end\n")

        if has_timers:
            lines.append(f"    // Timer reset when state changes")
            lines.append(f"    assign timer_rst = (State != NextState);\n")

        # -------------------------------------------------------------
        # 2. Next State Logic & Outputs
        # -------------------------------------------------------------
        if style == "two_always":
            lines.append("    // 2. Next-State & Output Combinational Logic (Anti-Latch default assignments)")
            lines.append("    always_comb begin")
            lines.append("        // Default assignments (prevents latches per IPD432 slide 48 & 51)")
            lines.append("        NextState = State;")
            for p in fsm.outputs:
                def_val = p.default_val if p.default_val else ("'0" if p.width > 1 else "1'b0")
                lines.append(f"        {p.name} = {def_val};")
            lines.append("")

            lines.append("        case (State)")
            for s in fsm.states:
                lines.append(f"            {s.name}: begin")
                # Moore outputs for this state
                if fsm.fsm_type == FSMType.MOORE and s.moore_outputs:
                    for out_name, out_val in s.moore_outputs.items():
                        lines.append(f"                {out_name} = {out_val};")

                # Transitions
                transitions = fsm.get_transitions_from(s.name)
                _emit_transitions(lines, transitions, fsm.fsm_type, has_timers, indent="                ")
                lines.append("            end")

            lines.append("            default: begin")
            lines.append(f"                NextState = {init_name};")
            lines.append("            end")
            lines.append("        endcase")
            lines.append("    end\n")

        else: # three_always
            # Next State Block
            lines.append("    // 2. Next-State Combinational Logic")
            lines.append("    always_comb begin")
            lines.append("        NextState = State;")
            lines.append("        case (State)")
            for s in fsm.states:
                lines.append(f"            {s.name}: begin")
                transitions = fsm.get_transitions_from(s.name)
                _emit_transitions(lines, transitions, FSMType.MOORE, has_timers, indent="                ", ignore_mealy=True)
                lines.append("            end")
            lines.append("            default: begin")
            lines.append(f"                NextState = {init_name};")
            lines.append("            end")
            lines.append("        endcase")
            lines.append("    end\n")

            # Output Logic Block
            if register_outputs:
                lines.append(f"    // 3. Registered Output Logic (Glitch-free, IPD432 slide 52 & 57)")
                lines.append(f"    always_ff {sensitivity} begin")
                lines.append(f"        if ({rst_condition}) begin")
                for p in fsm.outputs:
                    lines.append(f"            {p.name} <= {p.default_val};")
                lines.append("        end else begin")
                lines.append("            case (NextState)")
                for s in fsm.states:
                    lines.append(f"                {s.name}: begin")
                    if s.moore_outputs:
                        for out_name, out_val in s.moore_outputs.items():
                            lines.append(f"                    {out_name} <= {out_val};")
                    lines.append("                end")
                lines.append("                default: begin")
                for p in fsm.outputs:
                    lines.append(f"                    {p.name} <= {p.default_val};")
                lines.append("                end")
                lines.append("            endcase")
                lines.append("        end")
                lines.append("    end\n")
            else:
                lines.append("    // 3. Output Combinational Logic")
                lines.append("    always_comb begin")
                for p in fsm.outputs:
                    lines.append(f"        {p.name} = {p.default_val};")
                lines.append("        case (State)")
                for s in fsm.states:
                    lines.append(f"            {s.name}: begin")
                    if fsm.fsm_type == FSMType.MOORE:
                        if s.moore_outputs:
                            for out_name, out_val in s.moore_outputs.items():
                                lines.append(f"                {out_name} = {out_val};")
                    else:
                        transitions = fsm.get_transitions_from(s.name)
                        _emit_transitions(lines, transitions, FSMType.MEALY, has_timers, indent="                ", ignore_next_state=True)
                    lines.append("            end")
                lines.append("            default: begin")
                for p in fsm.outputs:
                    lines.append(f"                {p.name} = {p.default_val};")
                lines.append("            end")
                lines.append("        endcase")
                lines.append("    end\n")

        lines.append("endmodule\n")
        return "\n".join(lines)


def _emit_transitions(lines, transitions, fsm_type, has_timers, indent="                ", ignore_mealy=False, ignore_next_state=False):
    if not transitions:
        return

    # Sort transitions so 'else' / 'default' comes last
    cond_trans = [t for t in transitions if t.condition.strip().lower() not in ("else", "default", "")]
    else_trans = [t for t in transitions if t.condition.strip().lower() in ("else", "default", "")]

    first = True
    for t in cond_trans:
        cond_expr = t.condition.strip()
        if t.is_timed and t.timer_cycles > 0:
            timer_expr = f"(timer_cnt >= {t.timer_cycles - 1})"
            cond_expr = f"({cond_expr}) && {timer_expr}" if cond_expr and cond_expr != "1" else timer_expr

        keyword = "if" if first else "else if"
        lines.append(f"{indent}{keyword} ({cond_expr}) begin")
        if not ignore_next_state:
            lines.append(f"{indent}    NextState = {t.target};")
        if fsm_type == FSMType.MEALY and not ignore_mealy and t.mealy_outputs:
            for out_name, out_val in t.mealy_outputs.items():
                lines.append(f"{indent}    {out_name} = {out_val};")
        lines.append(f"{indent}end")
        first = False

    if else_trans:
        t = else_trans[0]
        if not first:
            lines.append(f"{indent}else begin")
        else:
            lines.append(f"{indent}begin")
        if not ignore_next_state:
            lines.append(f"{indent}    NextState = {t.target};")
        if fsm_type == FSMType.MEALY and not ignore_mealy and t.mealy_outputs:
            for out_name, out_val in t.mealy_outputs.items():
                lines.append(f"{indent}    {out_name} = {out_val};")
        lines.append(f"{indent}end")
