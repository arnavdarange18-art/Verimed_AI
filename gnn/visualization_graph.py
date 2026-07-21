"""
Visualization graph generator.

The 150-node graph used for the GNN's actual inference (in gnn_predict.py)
is too dense to render legibly in a browser widget. This module builds a
SMALLER graph (default 32 nodes) purely for visualization, runs the SAME
epidemic simulation logic used to train the GNN on it, and outputs 2D layout
coordinates -- so the frontend can draw real nodes and edges, colored by
whether the simulated claim "reached" them, with the hub/seed node marked.

This is not a separate model -- it's the same simulate_epidemic_spread()
function used during training (gnn/simulate_spread.py), run live on a
claim's actual risk score, so what judges see on screen is a real,
claim-specific simulation, not a canned animation.
"""

import random
import networkx as nx

try:
    from .graph_utils import generate_social_graph, top_hub_nodes
    from .simulate_spread import simulate_epidemic_spread
    from .claim_features import VERDICT_RISK, sensational_score
except ImportError:  # pragma: no cover - allows running as a plain script
    from graph_utils import generate_social_graph, top_hub_nodes
    from simulate_spread import simulate_epidemic_spread
    from claim_features import VERDICT_RISK, sensational_score

VIZ_NUM_NODES = 32
VIZ_M = 2
VIZ_SEED = 7  # fixed layout so the graph shape looks the same across requests


def _compute_risk_score(claim_text: str, verdict: str, confidence: float, entities: list[dict]) -> float:
    """Same risk-scoring logic used elsewhere -- false/sensational claims spread further."""
    verdict_risk = VERDICT_RISK.get(verdict, 0.3)
    sensational = sensational_score(claim_text)
    entity_density = min(len(entities or []) / 5, 1.0)
    risk_score = 0.55 * verdict_risk + 0.25 * sensational + 0.20 * entity_density
    return min(risk_score, 1.0)


def generate_visualization_graph(claim_text: str, verdict: str, confidence: float, entities: list[dict]) -> dict:
    """
    Returns a JSON-serializable structure:
    {
        "nodes": [{"id": 0, "x": 0.42, "y": 0.71, "infected": true, "is_hub": false, "is_seed": true}, ...],
        "edges": [{"source": 0, "target": 4}, ...],
        "infected_count": 14,
        "total_count": 32,
    }
    x/y are normalized to [0, 1] so the frontend can scale them to any SVG viewBox.
    """
    G = generate_social_graph(num_nodes=VIZ_NUM_NODES, m=VIZ_M, seed=VIZ_SEED)

    seed_node = top_hub_nodes(G, k=1)[0]
    hub_nodes = set(top_hub_nodes(G, k=3))

    risk_score = _compute_risk_score(claim_text, verdict, confidence, entities)
    # Use a seeded RNG so re-running the same claim gives a stable, reproducible
    # visualization instead of a different random result every request.
    rng_seed = abs(hash(claim_text)) % (2**31)
    rng = random.Random(rng_seed)

    _total_reached, _peak_step, _history, infected_set = simulate_epidemic_spread(
        G, risk_score, seed_node, max_steps=15, rng=rng, return_set=True
    )

    # Spring layout gives a natural "social network" look -- connected nodes
    # cluster together, hubs end up visually central.
    positions = nx.spring_layout(G, seed=VIZ_SEED, k=0.6)

    # Normalize all coordinates to [0, 1] for easy frontend scaling
    xs = [p[0] for p in positions.values()]
    ys = [p[1] for p in positions.values()]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    x_range = (x_max - x_min) or 1
    y_range = (y_max - y_min) or 1

    nodes = []
    for node_id in G.nodes():
        x, y = positions[node_id]
        nodes.append({
            "id": int(node_id),
            "x": round(float((x - x_min) / x_range), 4),
            "y": round(float((y - y_min) / y_range), 4),
            "infected": node_id in infected_set,
            "is_hub": node_id in hub_nodes,
            "is_seed": node_id == seed_node,
        })

    edges = [{"source": int(u), "target": int(v)} for u, v in G.edges()]

    return {
        "nodes": nodes,
        "edges": edges,
        "infected_count": len(infected_set),
        "total_count": G.number_of_nodes(),
    }


if __name__ == "__main__":
    # Quick manual test -- run: python gnn/visualization_graph.py
    result = generate_visualization_graph(
        "Garlic cures COVID-19 instantly, doctors hate this secret!",
        "False", 92, [{"text": "garlic"}, {"text": "COVID-19"}],
    )
    print(f"Nodes: {len(result['nodes'])}, Edges: {len(result['edges'])}")
    print(f"Infected: {result['infected_count']}/{result['total_count']}")
    print(f"Sample node: {result['nodes'][0]}")

    result2 = generate_visualization_graph(
        "Regular exercise is good for your heart",
        "True", 88, [{"text": "exercise"}, {"text": "heart"}],
    )
    print(f"\nTrue/neutral claim infected: {result2['infected_count']}/{result2['total_count']}")
