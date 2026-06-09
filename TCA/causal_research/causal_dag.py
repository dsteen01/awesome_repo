"""
The causal DAG assumed by demo_dr.py / dr_config_selection.py
=============================================================

This module makes the identifying assumptions of the DR-learner EXPLICIT as a
directed acyclic graph, and checks that the estimand (effect of CONFIG on
implementation shortfall) is identified by adjusting for the pre-trade features.

Why bother: the doubly-robust estimator is only valid under a specific causal
structure -- "no unmeasured confounders" (all common causes of config and cost
are in the feature set) and "propagator features are pre-treatment" (they don't
sit on the config -> cost path). Drawing the DAG forces those claims into the
open and lets us verify them mechanically (backdoor criterion, mediator check).

The DAG below mirrors the generative process actually coded in demo_dr.py:
  * Order/market context is drawn first (root causes).
  * Config is assigned with probabilities depending on size  => CONFOUNDING.
  * Realized IS depends on BOTH context and config.
  * Propagator forecast features are deterministic functions of context only.
"""

from __future__ import annotations
import networkx as nx


# ────────────────────────────────────────────────────────────────────────────
# Node roles
# ────────────────────────────────────────────────────────────────────────────
TREATMENT = "config"
OUTCOME = "implementation_shortfall"

# Pre-trade context (confounders): root causes that drive BOTH config & cost.
CONTEXT = [
    "size_pct_adv",
    "volatility",
    "arrival_spread_bps",
    "momentum",
    "imbalance",
    "time_of_day",
]

# Propagator-derived forecast features. In demo_dr.py these are DETERMINISTIC
# functions of context (size, vol, horizon) computed at arrival -- they carry
# NO information about realized fills, so they are pre-treatment descendants of
# context, NOT mediators on the config -> cost path.
PROPAGATOR_FEATURES = [
    "pred_impact_twap",
    "pred_impact_front",
    "pred_impact_back",
    "pred_impact_pov",
    "pred_impact_dispersion",
]

# The mediator we DELIBERATELY EXCLUDE from the adjustment set (Option 1).
# Config acts on cost THROUGH the realized fill sequence; conditioning on it
# would block the very effect we want. It's drawn to document the real channel,
# but it is NOT observed/used by the Option-1 DR-learner.
MEDIATOR = "realized_fill_sequence"


def build_dag() -> nx.DiGraph:
    """Construct the assumed causal DAG."""
    G = nx.DiGraph()

    # --- node attributes (role tags for later checks / rendering) -----------
    for v in CONTEXT:
        G.add_node(v, role="confounder", observed=True)
    for v in PROPAGATOR_FEATURES:
        G.add_node(v, role="pretrade_feature", observed=True)
    G.add_node(TREATMENT, role="treatment", observed=True)
    G.add_node(OUTCOME, role="outcome", observed=True)
    G.add_node(MEDIATOR, role="mediator", observed=False)  # not used in Option 1

    # --- edges ---------------------------------------------------------------
    # (1) Context -> Config : CONFOUNDING. In the demo, size drives the config
    #     assignment logit; we let all context features point into config to
    #     represent the general "trader/router conditions on order difficulty".
    for v in CONTEXT:
        G.add_edge(v, TREATMENT, kind="confound")

    # (2) Context -> Outcome : difficulty drives cost directly (impact, spread).
    for v in CONTEXT:
        G.add_edge(v, OUTCOME, kind="difficulty")

    # (3) Context -> Propagator features : forecasts are deterministic fns of
    #     size/vol/horizon (computed in build_pretrade_features()).
    for v in ["size_pct_adv", "volatility"]:
        for f in PROPAGATOR_FEATURES:
            G.add_edge(v, f, kind="deterministic")

    # (4) Propagator features -> Outcome : they are PREDICTIVE of cost (they
    #     summarize difficulty), so they have a (statistical) path to outcome.
    #     They are used as covariates to reduce variance / adjust, NOT as the
    #     treatment. Drawn to outcome to reflect their predictive role.
    for f in PROPAGATOR_FEATURES:
        G.add_edge(f, OUTCOME, kind="predictive")

    # (5) Config -> Mediator -> Outcome : the TRUE mechanism. Config shapes the
    #     realized fill sequence, which (through the propagator physics) produces
    #     impact cost. Option 1 does NOT observe/condition on the mediator; it
    #     estimates the TOTAL effect config -> outcome via the direct edge (6).
    G.add_edge(TREATMENT, MEDIATOR, kind="mechanism")
    G.add_edge(MEDIATOR, OUTCOME, kind="mechanism")

    # (6) Config -> Outcome : the total causal effect we want to estimate.
    #     (Represents the net of all config->...->outcome paths; in Option 1 we
    #     treat it as a single direct effect since the mediator is unobserved.)
    G.add_edge(TREATMENT, OUTCOME, kind="causal_effect")

    return G


# ────────────────────────────────────────────────────────────────────────────
# Assumption checks against the DAG
# ────────────────────────────────────────────────────────────────────────────
def adjustment_set() -> list:
    """The set the DR-learner actually conditions on: context + propagator feats.
    (Everything in build_pretrade_features.) The mediator is intentionally absent."""
    return CONTEXT + PROPAGATOR_FEATURES


def check_backdoor(G: nx.DiGraph, Z: list = None) -> dict:
    """
    Verify the adjustment set Z satisfies the backdoor criterion for
    config -> outcome:
      (a) Z contains no descendant of the treatment, AND
      (b) Z blocks every backdoor path (path into treatment) from config to
          outcome.
    Returns a dict of findings.
    """
    if Z is None:
        Z = adjustment_set()
    Z = set(Z)

    # (a) no descendants of treatment in Z
    descendants = nx.descendants(G, TREATMENT)
    bad = Z & descendants

    # (b) enumerate backdoor paths: paths from config to outcome that START with
    # an edge INTO config (i.e. config <- ...). Check each is blocked by Z.
    # Work on the undirected skeleton to enumerate paths, then classify.
    UG = G.to_undirected()
    backdoor_paths = []
    blocked_flags = []
    for path in nx.all_simple_paths(UG, TREATMENT, OUTCOME):
        # backdoor iff the first edge is oriented INTO config: path[1] -> config
        if G.has_edge(path[1], TREATMENT):
            backdoor_paths.append(path)
            blocked_flags.append(_path_blocked_by(G, path, Z))

    return {
        "adjustment_set": sorted(Z),
        "descendants_of_treatment_in_Z": sorted(bad),
        "no_bad_descendants": len(bad) == 0,
        "num_backdoor_paths": len(backdoor_paths),
        "all_backdoor_paths_blocked": all(blocked_flags) if backdoor_paths else True,
        "backdoor_paths": backdoor_paths,
        "identified": len(bad) == 0 and (all(blocked_flags) if backdoor_paths else True),
    }


def _path_blocked_by(G: nx.DiGraph, path: list, Z: set) -> bool:
    """
    d-separation check for a single path given conditioning set Z.
    A path is BLOCKED if any interior node is:
      * a non-collider (chain or fork) that IS in Z, or
      * a collider whose node (and none of its descendants) is in Z.
    """
    for i in range(1, len(path) - 1):
        a, b, c = path[i - 1], path[i], path[i + 1]
        a_to_b = G.has_edge(a, b)   # orientation on skeleton edge (a,b)
        b_to_c = G.has_edge(b, c)
        # collider at b iff a -> b <- c
        is_collider = (a_to_b and not G.has_edge(b, a)) and (b_to_c is False and G.has_edge(c, b))
        # simpler robust collider test using directed edges:
        is_collider = G.has_edge(a, b) and G.has_edge(c, b)
        if is_collider:
            # blocked unless b or any descendant of b is in Z
            desc = nx.descendants(G, b) | {b}
            if not (desc & Z):
                return True   # collider not conditioned -> path blocked here
        else:
            # chain/fork: blocked if b is in Z
            if b in Z:
                return True
    return False


def check_mediator_excluded(G: nx.DiGraph, Z: list = None) -> dict:
    """Confirm the mediator is NOT in the adjustment set (Option 1 total effect)."""
    if Z is None:
        Z = adjustment_set()
    on_path = MEDIATOR in set(Z)
    return {
        "mediator": MEDIATOR,
        "mediator_in_adjustment_set": on_path,
        "correct_for_total_effect": not on_path,
        "note": ("Mediator excluded -> DR-learner estimates the TOTAL effect of "
                 "config on cost (through the fill sequence). Including it would "
                 "block the impact channel (overcontrol bias)."),
    }


# ────────────────────────────────────────────────────────────────────────────
# Rendering
# ────────────────────────────────────────────────────────────────────────────
def to_graphviz_dot(G: nx.DiGraph) -> str:
    """Emit Graphviz DOT for a clean rendered figure."""
    role_style = {
        "confounder": ('box', '#1e2d40', '#c8dff0'),
        "pretrade_feature": ('box', '#0f3a2e', '#7fff6b'),
        "treatment": ('ellipse', '#3a1e0f', '#ff6b35'),
        "outcome": ('ellipse', '#3a0f1e', '#ff4560'),
        "mediator": ('hexagon', '#222222', '#888888'),
    }
    edge_style = {
        "confound": ('#ff6b35', 'solid'),
        "difficulty": ('#5a7a99', 'solid'),
        "deterministic": ('#4a6080', 'dashed'),
        "predictive": ('#5a7a99', 'dotted'),
        "mechanism": ('#888888', 'dashed'),
        "causal_effect": ('#00e396', 'bold'),
    }
    lines = ['digraph causal {', '  rankdir=LR;', '  bgcolor="#0a0e14";',
             '  node [fontname="Helvetica", fontsize=10];',
             '  edge [fontname="Helvetica", fontsize=8];']
    for n, d in G.nodes(data=True):
        shape, fill, font = role_style[d["role"]]
        dashed = ', style="filled,dashed"' if not d.get("observed", True) else ', style=filled'
        lines.append(f'  "{n}" [shape={shape}, fillcolor="{fill}", '
                     f'fontcolor="{font}"{dashed}];')
    for u, v, d in G.edges(data=True):
        color, style = edge_style[d["kind"]]
        pen = 2.0 if d["kind"] == "causal_effect" else 1.0
        lines.append(f'  "{u}" -> "{v}" [color="{color}", style={style}, penwidth={pen}];')
    lines.append('}')
    return "\n".join(lines)


def to_dowhy_graph(G: nx.DiGraph, include_mediator: bool = False) -> str:
    """
    Emit the DAG as a GML string for DoWhy's CausalModel(graph=...).

    include_mediator=False (default): drop the unobserved fill-sequence mediator,
    matching the Option-1 total-effect estimand the DR-learner targets. DoWhy
    then identifies config->outcome via backdoor adjustment on the observed
    context + propagator features -- the same set our hand-rolled check used.
    """
    H = G.copy()
    if not include_mediator:
        H.remove_node(MEDIATOR)
        if not H.has_edge(TREATMENT, OUTCOME):
            H.add_edge(TREATMENT, OUTCOME, kind="causal_effect")

    lines = ["graph [", "  directed 1"]
    node_ids = {n: i for i, n in enumerate(H.nodes())}
    for n, i in node_ids.items():
        lines.append(f'  node [ id {i} label "{n}" ]')
    for u, v in H.edges():
        lines.append(f'  edge [ source {node_ids[u]} target {node_ids[v]} ]')
    lines.append("]")
    return "\n".join(lines)


def print_report():
    G = build_dag()
    print("=" * 72)
    print("ASSUMED CAUSAL DAG  (demo_dr.py / dr_config_selection.py)")
    print("=" * 72)
    print(f"  treatment : {TREATMENT}")
    print(f"  outcome   : {OUTCOME}")
    print(f"  nodes={G.number_of_nodes()}  edges={G.number_of_edges()}  "
          f"is_DAG={nx.is_directed_acyclic_graph(G)}")

    print("\nADJUSTMENT SET (what the DR-learner conditions on):")
    for v in adjustment_set():
        print(f"  - {v}")

    bd = check_backdoor(G)
    print("\nBACKDOOR CRITERION CHECK:")
    print(f"  no treatment-descendants in Z : {bd['no_bad_descendants']}")
    print(f"  backdoor paths found          : {bd['num_backdoor_paths']}")
    print(f"  all backdoor paths blocked    : {bd['all_backdoor_paths_blocked']}")
    print(f"  => EFFECT IDENTIFIED          : {bd['identified']}")

    med = check_mediator_excluded(G)
    print("\nMEDIATOR CHECK:")
    print(f"  mediator in adjustment set    : {med['mediator_in_adjustment_set']}")
    print(f"  correct for TOTAL effect      : {med['correct_for_total_effect']}")

    print("\nKEY ASSUMPTIONS THIS DAG ENCODES (and that must hold in reality):")
    print("  1. No unmeasured confounders: every common cause of config and")
    print("     cost is in CONTEXT. (In live data, trader 'gut feel' not in the")
    print("     features would VIOLATE this -- the load-bearing assumption.)")
    print("  2. Propagator features are PRE-TREATMENT (functions of arrival")
    print("     context only), so they adjust/− reduce variance without blocking")
    print("     the config->cost channel.")
    print("  3. The fill sequence is a MEDIATOR, deliberately excluded, so we")
    print("     estimate the TOTAL effect of config on cost.")
    return G


if __name__ == "__main__":
    G = print_report()
    dot = to_graphviz_dot(G)
    with open("causal_dag.dot", "w") as f:
        f.write(dot)
    print("\nWrote causal_dag.dot (render with: dot -Tpng causal_dag.dot -o dag.png)")
