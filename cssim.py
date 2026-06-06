import json
import copy
import uuid
import numpy as np
import networkx as nx
import sympy as sp
from scipy.integrate import solve_ivp
from collections import defaultdict
import matplotlib.pyplot as plt
import ipywidgets as widgets
from IPython.display import display
from IPython import get_ipython

PID_D_FILTER_N = 100.0
PID_SUPPORTED_MODES = {"P", "PI", "PD", "PID"}

# ==== PARAM STORAGE (formerly TF_PARAM_VALUES) ====
PARAM_VALUES = {}

def set_parameters(params=None, **kwargs):
    """
    Register numeric values for parameters used by any block (input,
    transfer_function, gain, pid). Accepts dict, kwargs or locals().
    Only int/float; reserved names ('s','t') are ignored.
    """
    global PARAM_VALUES
    data = {}
    if params:
        if isinstance(params, dict):
            data.update(params)
    if kwargs:
        data.update(kwargs)
    filtered = {
        k: float(v) for k, v in data.items()
        if k not in ('s', 't') and isinstance(v, (int, float))
    }
    PARAM_VALUES.update(filtered)

def resolve_param(expr, allow_s=False, default=None, param_values=None):
    """
    Convert expr (None | '' | number | string expression) to float using PARAM_VALUES.
    - allow_s=True only for Transfer Function (Laplace).
    - Symbol 't' is not allowed.
    """
    if expr is None or (isinstance(expr, str) and expr.strip() == ""):
        return default
    if isinstance(expr, (int, float)):
        return float(expr)
    if not isinstance(expr, str):
        raise ValueError(f"Invalid parameter type: {type(expr)}")
    txt = expr.strip().replace(',', '.')
    # direct attempt
    try:
        return float(txt)
    except ValueError:
        pass
    # symbolic parser
    import sympy as sp
    resolved_params = param_values or PARAM_VALUES
    syms_map = {k: v for k, v in resolved_params.items()}
    if allow_s:
        syms_map['s'] = sp.Symbol('s')
    if 't' in txt:
        raise ValueError("Symbol 't' is reserved for time and cannot be used in parameters.")
    try:
        sym_expr = sp.sympify(txt, locals=syms_map)
    except Exception as e:
        raise ValueError(f"Invalid expression '{expr}': {e}")
    # If sympify returned a plain Python number, convert and return it
    if isinstance(sym_expr, (int, float)):
        return float(sym_expr)
    # Defensive branch: sympy may return objects without free_symbols
    try:
        free = sym_expr.free_symbols
    except AttributeError:
        return float(sym_expr)
    # Remove symbol s if allowed
    if allow_s and sp.Symbol('s') in free:
        free = [f for f in free if f != sp.Symbol('s')]
    if free:
        raise ValueError(f"Parameter(s) without numeric value: {', '.join(str(f) for f in free)}")
    val = float(sym_expr.evalf())
    return val


def parse_float(value, default=None):
    """Parse a float value accepting commas and blank strings."""
    if value is None or value == "":
        if default is None:
            raise ValueError("Missing required numeric value")
        return float(default)
    try:
        return float(str(value).replace(',', '.'))
    except Exception:
        if default is not None:
            return float(default)
        raise


# Defaults for numeric input block attributes (set in GUI).
INPUT_NUMERIC_DEFAULTS = {
    "data-a": 1.0,
    "data-a0": 0.0,
    "data-t0": 0.0,
    "data-m": 1.0,
    "data-f": 60.0,
    "data-phase": 0.0,
    "data-offset": 0.0,
}


def resolve_input_attributes(attrs, param_values=None):
    """Return numeric-ready attributes for an input block using parameter store."""
    resolved = {}
    for key, default in INPUT_NUMERIC_DEFAULTS.items():
        raw = attrs.get(key)
        try:
            resolved[key] = resolve_param(raw, allow_s=False, default=default, param_values=param_values)
        except Exception:
            resolved[key] = parse_float(raw, default)

    # Copy non numeric fields as-is so downstream consumers still access them.
    for key, value in attrs.items():
        if key not in resolved:
            resolved[key] = value

    return resolved


def resolve_pid_derivative_filter(attrs):
    """Resolve the derivative filter coefficient N for realizable PID blocks."""
    raw_filter = attrs.get("data-filter-n", PID_D_FILTER_N)
    filter_n = resolve_param(raw_filter, default=PID_D_FILTER_N)
    if not np.isfinite(filter_n) or filter_n <= 0:
        raise ValueError(
            "PID derivative filter N must be a finite positive value. "
            "Ideal derivative is not supported; configure a positive filter N."
        )
    return filter_n


def load_json(path):
    """Load and return JSON data from the given file path."""
    with open(path, 'r') as f:
        return json.load(f)


def build_graph(data):
    """
    Build a directed graph from block diagram JSON, collapsing "line-connector" nodes.
    Resulting edges connect blocks directly, preserving connector positions.
    """
    G = nx.DiGraph()
    # Add all blocks as nodes (including connectors temporarily)
    for b in data["blocks"]:
        G.add_node(b["id"], **b)
    # Separate direct block-to-block edges and line-connector preds/succs
    normal_edges = []
    line_preds = defaultdict(list)
    line_succs = defaultdict(list)
    for c in data["connections"]:
        src, dst = c["from"], c["to"]
        # Direct block to block
        if src["type"] == "block-connector" and dst["type"] == "block-connector":
            normal_edges.append((src["blockId"], dst["blockId"], dst.get("position")))
        # Block to line start
        elif src["type"] == "block-connector" and dst["type"] == "line-connector":
            line_preds[dst["id"]].append(src["blockId"])
        # Line end to block
        elif src["type"] == "line-connector" and dst["type"] == "block-connector":
            line_succs[src["id"]].append((dst["blockId"], dst.get("position")))
    # Add direct edges
    for u, v, pos in normal_edges:
        G.add_edge(u, v, position=pos)
    # Collapse line connectors by connecting preds to succs
    for lid in set(line_preds) | set(line_succs):
        for u in line_preds.get(lid, []):
            for v, pos in line_succs.get(lid, []):
                G.add_edge(u, v, position=pos)
    return G


# Draw graph with node IDs
def draw_graph(G):
    pos = nx.spring_layout(G, seed=42)
    labels = {node: str(node) for node in G.nodes}
    plt.figure()
    nx.draw(
        G,
        pos,
        labels=labels,
        with_labels=True,
        node_color='lightblue',
        edge_color='gray',
        node_size=1500,
        font_size=9,
        font_weight='normal',
        arrows=True,
        arrowstyle='-|>',
        arrowsize=20
    )
    plt.title("Graph")
    plt.axis("off")
    plt.show()




def categorize_blocks(data, G, param_values=None):
    """
        Categorize blocks and resolve parameters for:
            - transfer_function: numerator/denominator (strings already handled in tf_to_ss)
            - gain: data-gain
            - pid: data-kp, data-ti, data-td
            - input: numeric attributes (amplitude, delay, etc.)
    """
    input_blocks = []
    tf_blocks = []
    static_blocks = []
    pid_blocks = []
    output_blocks = []
    idx_cursor = 0
    pv = param_values or PARAM_VALUES

    for b in data["blocks"]:
        bid = b["id"]
        typ = b["type"]
        if typ.lower().endswith('connector'):
            continue
        if typ == "input":
            # resolve potential numeric attributes
            attrs = b.get("attributes", {})
            b["resolved_attributes"] = resolve_input_attributes(attrs, param_values=pv)
            input_blocks.append(bid)
        elif typ == "transfer_function":
            num = b["attributes"]["data-numerator"]
            den = b["attributes"]["data-denominator"]
            A, B, C, D = tf_to_ss(num, den, param_values=pv)
            n = A.shape[0]
            preds = list(G.predecessors(bid))
            if not preds:
                raise ValueError(f"Transfer Function {bid} has no input.")
            tf_blocks.append({
                "id": bid, "A": A, "B": B, "C": C, "D": D,
                "in_id": preds[0],
                "state_idx": slice(idx_cursor, idx_cursor + n),
                "order": n
            })
            idx_cursor += n
        elif typ == "pid":
            attrs = b.get("attributes", {})
            preds = list(G.predecessors(bid))
            input_id = preds[0] if preds else None
            mode = (attrs.get("data-mode") or "PID").upper().strip()
            if mode not in PID_SUPPORTED_MODES:
                raise ValueError(
                    f"PID {bid} uses unsupported mode '{mode}'. Supported modes: {', '.join(sorted(PID_SUPPORTED_MODES))}."
                )
            kp = resolve_param(attrs.get("data-kp"), default=1.0, param_values=pv)
            has_integral = 'I' in mode
            has_derivative = 'D' in mode
            ti_val = resolve_param(attrs.get("data-ti"), default=1.0, param_values=pv) if has_integral else None
            if has_integral and (ti_val is None or abs(ti_val) <= 1e-12):
                raise ValueError(f"PID {bid} requires T_i != 0.")
            ki = kp / ti_val if has_integral else 0.0
            td_val = None
            filter_n = None
            if has_derivative:
                td_val = resolve_param(attrs.get("data-td"), default=None, param_values=pv)
                if td_val is None or not np.isfinite(td_val) or td_val <= 0:
                    raise ValueError(f"PID {bid} requires a finite T_d > 0 when derivative action is enabled.")
                filter_n = resolve_pid_derivative_filter(attrs)
            integral_idx = None
            derivative_struct = None
            state_dim = 0
            if has_integral:
                integral_idx = slice(idx_cursor, idx_cursor + 1)
                idx_cursor += 1
                state_dim += 1
            if has_derivative:
                alpha = td_val / filter_n
                if alpha <= 0:
                    alpha = 1e-6
                A_d, B_d, C_d, D_d = tf_to_ss([kp * td_val, 0.0], [alpha, 1.0], param_values=pv)
                order_d = A_d.shape[0]
                derivative_idx = slice(idx_cursor, idx_cursor + order_d)
                idx_cursor += order_d
                state_dim += order_d
                derivative_struct = {
                    "A": A_d,
                    "B": B_d,
                    "C": C_d,
                    "D": D_d,
                    "idx": derivative_idx,
                    "filter_n": filter_n,
                    "alpha": alpha,
                }
            pid_blocks.append({
                "id": bid, "mode": mode, "Kp": kp, "Ki": ki,
                "Ti": ti_val if has_integral else None,
                "Td": td_val if has_derivative else None,
                "filter_n": filter_n,
                "in_id": input_id,
                "integral_idx": integral_idx,
                "derivative": derivative_struct,
                "state_dim": state_dim
            })
        elif typ == "gain":
            attrs = b.get("attributes", {})
            gain_raw = attrs.get("data-gain", "1")
            gain_val = resolve_param(gain_raw, default=1.0)
            static_blocks.append({
                "id": bid,
                "type": typ,
                "gain": gain_val,
                "raw_gain": gain_raw,
                "attrs": attrs,
                "in_ids": list(G.predecessors(bid)),
                "positions": { (u, bid): G.edges[u, bid].get('position') for u in G.predecessors(bid) }
            })
        elif typ == "output":
            output_blocks.append(bid)
        else:
            static_blocks.append({
                "id": bid,
                "type": typ,
                "attrs": b.get("attributes", {}),
                "in_ids": list(G.predecessors(bid)),
                "positions": { (u, bid): G.edges[u, bid].get('position') for u in G.predecessors(bid) }
            })
    return input_blocks, tf_blocks, static_blocks, pid_blocks, output_blocks, idx_cursor


def tf_to_ss(num, den, verbose=False, param_values=None):
    """
    Build the controllable canonical form for a proper transfer function
    G(s) = num(s)/den(s), returning the state-space matrices (A, B, C, D).
    Accepts strings with symbolic parameters. Replaces parameters with numeric values
    provided in param_values or registered globally in PARAM_VALUES.
    Notes:
        - 's' is the Laplace variable.
        - 't' is not allowed in numerator or denominator.
    Example strings:
        "Kp*s + Ki"
        "s**2 + 2*zeta*wn*s + wn**2"
    Parameters must have registered numeric values, otherwise an error is raised.
    """
    s = sp.Symbol('s')
    param_values = (param_values or PARAM_VALUES)

    def to_poly(poly_expr):
        # Already a Poly instance
        if isinstance(poly_expr, sp.Poly):
            return poly_expr
        # Expression
        if isinstance(poly_expr, sp.Expr):
            return sp.Poly(poly_expr, s)
        # String -> symbolic parse
        if isinstance(poly_expr, str):
            txt = poly_expr.strip()
            if txt == "":
                raise ValueError("Empty polynomial.")
            if 't' in txt:
                raise ValueError("Symbol 't' is not allowed in transfer functions.")
            # build local symbol map (parameters -> numbers)
            local_map = {'s': s}
            for k, v in param_values.items():
                local_map[k] = v
            expr = sp.sympify(txt, locals=local_map)
            if not hasattr(expr, "free_symbols"):
                # sympify may return plain Python numbers when locals contain floats
                return sp.Poly(float(expr), s)
            free = expr.free_symbols
            unknown = [sym for sym in free if sym != s]
            if unknown:
                raise ValueError(f"Parameter(s) without value: {', '.join(str(u) for u in unknown)}")
            return sp.Poly(expr, s)
        # List/tuple of coefficients (assume highest-first)
        if isinstance(poly_expr, (list, tuple)):
            return sp.Poly(poly_expr, s)
        # Numeric
        if isinstance(poly_expr, (int, float)):
            return sp.Poly(float(poly_expr), s)
        raise TypeError(f"Unsupported polynomial type: {type(poly_expr)}")

    numerator_poly = to_poly(num)
    denominator_poly = to_poly(den)

    numerator_degree = numerator_poly.degree()
    denominator_degree = denominator_poly.degree()

    # ---- accept only proper (or equal-degree) ----
    if numerator_degree > denominator_degree:
        print("[Warning] Non-proper transfer function detected (deg(num) > deg(den)).")
        print("          This function only handles proper/equal-degree cases. No state-space built.")
        return None

    if denominator_degree < 1:
        raise ValueError("Denominator must be at least first order.")

    # ---- coefficients (highest-first) ----
    denominator_coeffs = [float(c) for c in denominator_poly.all_coeffs()]
    numerator_coeffs = [float(c) for c in numerator_poly.all_coeffs()]

    # ---- normalize to monic denominator ----
    denominator_leading_coeff = denominator_coeffs[0]
    if abs(denominator_leading_coeff) == 0.0:
        raise ValueError("Leading denominator coefficient must be nonzero.")
    denominator_coeffs = [a_i / denominator_leading_coeff for a_i in denominator_coeffs]
    numerator_coeffs = [b_i / denominator_leading_coeff for b_i in numerator_coeffs]

    n = len(denominator_coeffs) - 1  # system order

    # ---- pad numerator to length n+1 ----
    if len(numerator_coeffs) < n + 1:
        numerator_coeffs = [0.0] * (n + 1 - len(numerator_coeffs)) + numerator_coeffs

    # Den (monic): [1, a1, a2, ..., an]
    a1_to_n = denominator_coeffs[1:]              # length n
    # Num (aligned): [b0, b1, ..., bn]
    b0 = numerator_coeffs[0]
    b1_to_n = numerator_coeffs[1:]              # length n

    # ---- build A, B, C, D ----
    A = np.zeros((n, n))
    if n > 1:
        A[:-1, 1:] = np.eye(n - 1)
    A[-1, :] = -np.array(a1_to_n[::-1])  # [-a_n, ..., -a_1]

    B = np.zeros((n, 1))
    B[-1, 0] = 1.0

    C_vec = np.array(b1_to_n[::-1]) - b0 * np.array(a1_to_n[::-1])
    C = C_vec.reshape(1, -1)

    D = float(b0)

    if verbose:
        print("=== Controllable Canonical Form ===")
        print(f"Order n: {n}")
        print(f"Den (monic): [1, a1, ..., an] = {denominator_coeffs}")
        print(f"Num (aligned): [b0, b1, ..., bn] = {numerator_coeffs}")
        print(f"A =\n{A}")
        print(f"B =\n{B}")
        print(f"C =\n{C}")
        print(f"D = {D}")

    return A, B, C, D

def generate_input_signal(data):
    """
    Generate Python functions for Input signals (step, impulse, ramp, sine, square, triangle)
    using attributes already resolved via set_parameters()/resolve_param.
    """
    def get_numeric(attrs, key):
        default = INPUT_NUMERIC_DEFAULTS.get(key, 0.0)
        val = attrs.get(key, default) if attrs else default
        return parse_float(val, default)

    funcs = {}
    for b in data["blocks"]:
        if b["type"] == "input":
            bid = b["id"]
            at = b.get("attributes", {})
            resolved = b.get("resolved_attributes")
            if resolved is None:
                resolved = resolve_input_attributes(at)

            sig = (resolved.get("data-signal") or at.get("data-signal") or "step").lower()
            A = get_numeric(resolved, "data-a")
            A0 = get_numeric(resolved, "data-a0")
            t0 = get_numeric(resolved, "data-t0")
            m_param = get_numeric(resolved, "data-m")
            f = get_numeric(resolved, "data-f")
            phase = get_numeric(resolved, "data-phase")
            off = get_numeric(resolved, "data-offset")
            if sig == "step":
                funcs[bid] = lambda t, A=A, A0=A0, t0=t0: A if t >= t0 else A0
            elif sig == "impulse":
                eps = 1e-3
                funcs[bid] = lambda t, A=A, A0=A0, t0=t0, eps=eps: A / eps if abs(t - t0) < eps else A0
            elif sig == "ramp":
                funcs[bid] = lambda t, A0=A0, m_param=m_param, t0=t0: A0 + m_param * (t - t0) if t >= t0 else A0
            elif sig == "sine":
                funcs[bid] = lambda t, A=A, f=f, phase=phase, off=off, t0=t0, A0=A0: A * np.sin(
                    2 * np.pi * f * (t - t0) + phase) + off if t >= t0 else A0
            elif sig == "square":
                funcs[bid] = lambda t, A=A, f=f, phase=phase, off=off, t0=t0, A0=A0: A * np.sign(
                    np.sin(2 * np.pi * f * (t - t0) + phase)) + off if t >= t0 else A0
            elif sig == "triangle":
                funcs[bid] = lambda t, A=A, f=f, off=off, t0=t0, A0=A0: A * (
                        2 * abs(2 * ((f * (t - t0)) % 1) - 1) - 1) + off if t >= t0 else A0
            else:
                raise ValueError(f"Unsupported signal '{sig}'")
    return funcs


def build_solver(input_blocks, static_blocks, tf_blocks, pid_blocks, total_states):
    """
    Build the algebraic part of the interconnected block diagram.

    This function encodes the algebraic network as:

        M * w = H * x + P * u

    where:
    - w collects internal block outputs that can participate in loops.
    - x is the global state vector.
    - u represents external input signals.
    - M captures how internal signals depend on other internal signals.
    - H captures how internal signals depend on states.
    - P is stored sparsely as `P_u`, because external inputs are easier to evaluate by name than by building a dense matrix.

    The returned inverse M_inv is later used inside compute_rhs() to recover w(t) at each time instant before assembling dx/dt.
    """
    # Only blocks that can appear as algebraic signal sources belong to w.
    # External input blocks are not part of w; they are evaluated separately.
    w_ids = [b["id"] for b in static_blocks] + [b["id"] for b in tf_blocks] + [b["id"] for b in pid_blocks]
    w_index = {bid: i for i, bid in enumerate(w_ids)}
    n_states = total_states

    # Start from w_i on the left-hand side, then move dependencies to M, H and P.
    M = np.eye(len(w_ids))
    H = np.zeros((len(w_ids), n_states))
    P_u = {i: [] for i in range(len(w_ids))}

    for block in static_blocks:
        i = w_index[block["id"]]
        inputs = block["in_ids"]

        if block["type"] == "gain":
            # Prefer resolved value when categorize_blocks already computed it
            if "gain" in block:
                gain = float(block["gain"])
            else:
                # Try resolving symbols/expressions or convert directly
                raw_gain = block.get("attrs", {}).get("data-gain", 1.0)
                try:
                    gain = float(raw_gain)
                except Exception:
                    try:
                        gain = resolve_param(raw_gain, default=1.0)
                    except Exception:
                        gain = 1.0
            src = inputs[0]
            # If the source is another internal algebraic signal, it contributes
            # to M. Otherwise it is an external input term and is stored in P*u.
            if src in w_index:
                M[i, w_index[src]] = -gain
            else:
                P_u[i].append((src, gain))

        elif block["type"] == "operation":
            op1 = block["attrs"].get("data-operator-1", "+").strip()
            op2 = block["attrs"].get("data-operator-2", "+").strip()
            left_input = next(p for p in inputs if block["positions"][(p, block["id"])] == "left")
            vert_input = next(p for p in inputs if block["positions"][(p, block["id"])] != "left")
            coeffs = {
                left_input: 1.0 if op1 == "+" else -1.0,
                vert_input: 1.0 if op2 == "+" else -1.0,
            }
            for src, coeff in coeffs.items():
                # Summing junctions are treated the same way: internal sources
                # modify M, external sources are recorded as P*u contributions.
                if src in w_index:
                    M[i, w_index[src]] = -coeff
                else:
                    P_u[i].append((src, coeff))
        else:
            for src in inputs:
                # Passthrough-like blocks simply copy incoming signals.
                if src in w_index:
                    M[i, w_index[src]] = -1.0
                else:
                    P_u[i].append((src, 1.0))

    for tf in tf_blocks:
        i = w_index[tf["id"]]
        src = tf["in_id"]
        D = float(tf["D"])
        # The direct-feedthrough term D connects the input directly to the
        # algebraic output of the transfer function block.
        if src in w_index:
            M[i, w_index[src]] = -D
        else:
            P_u[i].append((src, D))
        # The state-dependent output term C*x contributes through H.
        H[i, tf["state_idx"]] = tf["C"].flatten()

    for pid in pid_blocks:
        i = w_index[pid["id"]]
        src = pid["in_id"]
        kp = pid["Kp"]

        # The proportional action acts as an instantaneous algebraic path.
        if src in w_index:
            M[i, w_index[src]] = M[i, w_index[src]] - kp
        elif src is not None:
            P_u[i].append((src, kp))

        # The integral state contributes to the PID output through Ki * x_I.
        if pid["integral_idx"] is not None:
            H[i, pid["integral_idx"]] = pid["Ki"]

        derivative = pid["derivative"]
        if derivative is not None:
            # The filtered derivative contributes both through its internal state
            # (C*x_d) and, if D != 0, through direct feedthrough from the input.
            H[i, derivative["idx"]] = derivative["C"].flatten()
            D = derivative["D"]
            if abs(D) > 0:
                if src in w_index:
                    M[i, w_index[src]] = M[i, w_index[src]] - D
                elif src is not None:
                    P_u[i].append((src, D))

    M_inv = np.linalg.inv(M)

    return w_ids, w_index, M_inv, P_u, H




def compute_rhs(u_signals, tf_blocks, pid_blocks, w_ids, w_index, M_inv, P_u, H):
    """
    Build the function dx/dt = f(t, x) used by solve_ivp().

    Arguments:
    - u_signals: dict of input signal functions u_i(t)
    - tf_blocks: list of transfer function blocks
    - w_ids: list of block IDs whose internal algebraic signals compose w(t)
    - w_index: mapping from block ID to row index in M
    - M_inv: inverse of M matrix (algebraic solver)
    - P_u: external input contributions associated with P * u
    - H: matrix multiplying state vector x(t) in the algebraic subsystem

    Returns:
    - Function f(t, x) = dx/dt for numerical integration
    """
    def rhs(t, x):
        # Start from the state-dependent part of the algebraic network.
        Hx_plus_Pu = H.dot(x)

        # Add the external input contributions. P is stored sparsely as named
        # signal references plus coefficients, so we evaluate each u_i(t) here.
        for i, u_terms in P_u.items():
            for u_id, coeff in u_terms:
                func = u_signals.get(u_id)
                Hx_plus_Pu[i] += coeff * func(t) if func else 0.0

        # Recover the internal algebraic signals for the current time/state.
        w = M_inv.dot(Hx_plus_Pu)

        def eval_node(node_id):
            # Internal nodes are read from w; external nodes are evaluated from
            # the user-defined input signal functions.
            if node_id in w_index:
                return w[w_index[node_id]]
            func = u_signals.get(node_id)
            return func(t) if func else 0.0

        # Assemble the global derivative vector by filling each block's state indices.
        dx = np.zeros_like(x)
        for tf in tf_blocks:
            state_idx = tf["state_idx"]
            x_i = x[state_idx]
            input_id = tf["in_id"]
            input_val = eval_node(input_id)
            # Local state equation of the transfer-function realization:
            # x_i_dot = A_i * x_i + B_i * u_i
            dx[state_idx] = tf["A"].dot(x_i) + tf["B"].flatten() * input_val

        for pid in pid_blocks:
            input_id = pid["in_id"]
            input_val = eval_node(input_id) if input_id is not None else 0.0

            if pid["integral_idx"] is not None:
                # Integral action state: d/dt x_I = error input.
                dx[pid["integral_idx"]] = input_val

            derivative = pid["derivative"]
            if derivative is not None:
                derivative_idx = derivative["idx"]
                x_d = x[derivative_idx]
                A_d = derivative["A"]
                B_d = derivative["B"].flatten()
                # Filtered derivative state equation.
                dx[derivative_idx] = A_d.dot(x_d) + B_d * input_val

        return dx

    return rhs


def run_simulation(data, step_size=0.001, simulation_time=10, param_values=None):
    """
    Run the simulation. param_values: optional dict of parameters for transfer functions.
    If None, uses the global PARAM_VALUES registry (set_parameters()).
    """
    param_values = param_values or PARAM_VALUES
    G = build_graph(data)
    input_blocks, tf_blocks, static_blocks, pid_blocks, output_blocks, total_states = categorize_blocks(
        data, G, param_values=param_values
    )
    input_signal_funcs = generate_input_signal(data)
    w_ids, w_index, M_inv, P_u, H = build_solver(
        input_blocks, static_blocks, tf_blocks, pid_blocks, total_states
    )
    rhs = compute_rhs(input_signal_funcs, tf_blocks, pid_blocks, w_ids, w_index, M_inv, P_u, H)
    x0 = np.zeros(H.shape[1])
    t_eval = np.arange(0, simulation_time, step_size)
    sol = solve_ivp(rhs, (0, simulation_time), x0, t_eval=t_eval)
    output_out = {output_id: np.zeros_like(sol.t) for output_id in output_blocks}
    out_sources = {output_id: list(G.predecessors(output_id))[0] for output_id in output_blocks}
    for k, t_k in enumerate(sol.t):
        Hx_plus_Pu = H.dot(sol.y[:, k])
        for i, entries in P_u.items():
            for input_id, coeff in entries:
                func = input_signal_funcs.get(input_id)
                Hx_plus_Pu[i] += coeff * func(t_k) if func else 0.0
        w_k = M_inv.dot(Hx_plus_Pu)
        for output_id, src in out_sources.items():
            if src in w_index:
                output_out[output_id][k] = w_k[w_index[src]]
            else:
                func = input_signal_funcs.get(src)
                output_out[output_id][k] = func(t_k) if func else 0.0
    return sol.t, input_signal_funcs, input_blocks, output_out


def plot_signals(t, input_signals, input_blocks, outputs, data_diagram):
    if t is None or input_signals is None or outputs is None or data_diagram is None:
        from cssim_server import last_sim_t, last_sim_outputs, last_sim_inputs, last_sim_input_blocks, last_data_diagram
        t = last_sim_t
        input_signals = last_sim_inputs
        input_blocks = last_sim_input_blocks
        outputs = last_sim_outputs
        data_diagram = last_data_diagram

    id_to_name = {
        b["id"]: b["attributes"].get("data-name", b["id"])
        for b in data_diagram["blocks"]
        if b["type"] in ("input", "output")
    }

    fig, ax = plt.subplots(figsize=(10, 6))

    for in_id in input_blocks:
        u = [input_signals[in_id](ti) for ti in t]
        label = id_to_name.get(in_id, in_id)
        ax.plot(t, u, '--', label=label)

    for out_id, y in outputs.items():
        label = id_to_name.get(out_id, out_id)
        ax.plot(t, y, label=label)

    ax.set_title("")
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("")
    ax.grid(True)
    ax.legend()
    plt.show()


def interactive_plot(t=None, input_signals=None, input_blocks=None, outputs=None, data_diagram=None):
    if t is None or input_signals is None or outputs is None or data_diagram is None:
        from cssim_server import last_sim_t, last_sim_outputs, last_sim_inputs, last_sim_input_blocks, last_data_diagram
        t = last_sim_t
        input_signals = last_sim_inputs
        input_blocks = last_sim_input_blocks
        outputs = last_sim_outputs
        data_diagram = last_data_diagram

    if (
        t is None
        or input_signals is None
        or input_blocks is None
        or outputs is None
        or data_diagram is None
    ):
        raise ValueError(
            "No simulation results available. Run a simulation through the GUI before calling interactive_plot()."
        )

    id_to_name = {
        b["id"]: b["attributes"].get("data-name", b["id"])
        for b in data_diagram["blocks"]
        if b["type"] in ("input", "output")
    }

    input_checkboxes = {
        in_id: widgets.Checkbox(value=True, description=f"Input: {id_to_name.get(in_id, in_id)}")
        for in_id in input_blocks
    }
    output_checkboxes = {
        out_id: widgets.Checkbox(value=True, description=f"Output: {id_to_name.get(out_id, out_id)}")
        for out_id in outputs
    }

    input_box = widgets.VBox(list(input_checkboxes.values()))
    output_box = widgets.VBox(list(output_checkboxes.values()))
    controls = widgets.HBox([input_box, output_box])
    plot_output = widgets.Output()

    def update_plot(change=None):
        with plot_output:
            plot_output.clear_output(wait=True)
            fig, ax = plt.subplots(figsize=(10, 6))

            for in_id, cb in input_checkboxes.items():
                if cb.value:
                    u = [input_signals[in_id](ti) for ti in t]
                    label = id_to_name.get(in_id, in_id)
                    ax.plot(t, u, '--', label=label)

            for out_id, cb in output_checkboxes.items():
                if cb.value:
                    y = outputs[out_id]
                    label = id_to_name.get(out_id, out_id)
                    ax.plot(t, y, label=label)

            ax.set_xlabel("Time (s)")
            ax.set_ylabel("")
            ax.grid(True)
            ax.legend()
            plt.show()

    for cb in list(input_checkboxes.values()) + list(output_checkboxes.values()):
        cb.observe(update_plot, names="value")

    display(widgets.VBox([controls, plot_output]))
    update_plot()


# Open GUI in Jupyter Notebook

from threading import Thread
from IPython.display import IFrame, display
from cssim_server import run_flask, set_initial_diagram_path

flask_thread = None
flask_port = None


def open_gui(diagram_path=None, port=8000, width="100%", height=700):
    """Open the CSSim GUI, optionally preloading a diagram JSON file."""
    global flask_thread, flask_port

    # Backwards compatibility: allow open_gui(8080) to set port
    if isinstance(diagram_path, (int, float)) and not isinstance(diagram_path, bool):
        port = int(diagram_path)
        diagram_path = None

    set_initial_diagram_path(diagram_path)
    session_id = uuid.uuid4().hex

    if flask_thread is None or not flask_thread.is_alive():
        flask_port = port
        flask_thread = Thread(
            target=lambda: run_flask(port=port, initial_diagram=diagram_path),
            daemon=True
        )
        flask_thread.start()
    else:
        # Reuse existing server port if already running
        if flask_port is not None:
            port = flask_port
        else:
            flask_port = port

    iframe_url = f"http://localhost:{port}/?session={session_id}"
    display(IFrame(iframe_url, width=width, height=height))

    import cssim_server as cssim_srv

    run_button = widgets.Button(
        description=" Run",
        icon="play",
        button_style="success",
        layout=widgets.Layout(width="200px")
    )
    status_label = widgets.HTML(value="")
    output_area = widgets.Output()

    def set_status(message, ok=True):
        color = "#198754" if ok else "#d9534f"
        status_label.value = f"<span style='color:{color};font-weight:500;'>{message}</span>"

    def run_from_diagram(_):
        set_status("Running simulation...", ok=True)
        with output_area:
            output_area.clear_output()
            diagram_data = cssim_srv.session_diagrams.get(session_id)
            if diagram_data is None:
                diagram_data = cssim_srv.last_data_diagram
            if diagram_data is None:
                set_status("No synchronized diagram. Please wait for the GUI to send the data.", ok=False)
                print("No synchronized diagram available.")
                return

            diagram_copy = copy.deepcopy(diagram_data)
            sim_time = parse_float(diagram_copy.get("sim_time"), default=10)
            step_size = parse_float(diagram_copy.get("step_size"), default=0.001)

            try:
                set_parameters(locals())
                ip = get_ipython()
                if ip:
                    user_ns = ip.user_ns
                    numeric_params = {
                        k: float(v) for k, v in user_ns.items()
                        if k not in ("s", "t") and isinstance(v, (int, float))
                    }
                    set_parameters(numeric_params)
            except Exception:
                pass

            try:
                t, input_signals, input_blocks, outputs = run_simulation(
                    diagram_copy,
                    simulation_time=sim_time,
                    step_size=step_size
                )
            except Exception as exc:
                set_status(f"Error during simulation: {exc}", ok=False)
                raise

            cssim_srv.last_sim_t = t
            cssim_srv.last_sim_outputs = outputs
            cssim_srv.last_sim_inputs = input_signals
            cssim_srv.last_sim_input_blocks = input_blocks
            cssim_srv.last_data_diagram = diagram_copy
            cssim_srv.session_diagrams[session_id] = diagram_copy

            interactive_plot(t, input_signals, input_blocks, outputs, diagram_copy)
            set_status("Simulation completed.", ok=True)

    run_button.on_click(run_from_diagram)

    controls = widgets.VBox([
        widgets.HBox([run_button, status_label]),
        output_area
    ])
    display(controls)
