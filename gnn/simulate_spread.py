"""
PHASE 6c: Spread simulation -- the GNN's "teacher".

We don't have real labeled spread data (how many people actually shared a
given health claim), so we can't just download a dataset and train on it.

Instead we use a well-established technique: run a simulation grounded in
known dynamics (an SIR-style epidemic spread model over the social graph,
where infection probability scales with how "risky" the claim is), and use
the simulation's output as training labels. The GNN then learns to predict
that outcome directly from graph structure + claim features -- much faster
at inference time than re-running a full simulation on every request.

This is the same pattern used in surrogate modeling / simulation-based
training in network science and epidemiology.
"""

import random
import networkx as nx


def simulate_epidemic_spread(
    G: nx.Graph,
    claim_risk_score: float,
    seed_node: int,
    max_steps: int = 20,
    rng: random.Random | None = None,
) -> tuple[int, int, list[int]]:
    """
    Simulates how a claim spreads through the network starting from seed_node.

    claim_risk_score: 0-1, higher = spreads more aggressively (false/sensational claims)
    Returns: (total_nodes_reached, step_of_peak_growth, step_by_step_infected_counts)
    """
    rng = rng or random.Random()

    # Base infection probability per edge per step, scaled up for risky claims.
    # Even a "safe" true claim has some baseline chance of being shared.
    infection_prob = 0.12 + 0.55 * claim_risk_score

    infected = {seed_node}
    frontier = {seed_node}
    history = []

    for _step in range(max_steps):
        new_frontier = set()
        for node in frontier:
            for neighbor in G.neighbors(node):
                if neighbor not in infected and rng.random() < infection_prob:
                    infected.add(neighbor)
                    new_frontier.add(neighbor)
        history.append(len(infected))
        if not new_frontier:
            break
        frontier = new_frontier

    total_reached = len(infected)
    peak_step = (history.index(max(history)) + 1) if history else 1

    return total_reached, peak_step, history


if __name__ == "__main__":
    # Quick manual test -- run: python gnn/simulate_spread.py
    from graph_utils import generate_social_graph, top_hub_nodes

    G = generate_social_graph(seed=1)
    seed_node = top_hub_nodes(G, k=1)[0]

    for risk_label, risk_score in [("Low-risk (true claim)", 0.05), ("High-risk (false+sensational)", 0.95)]:
        total, peak_step, history = simulate_epidemic_spread(G, risk_score, seed_node, rng=random.Random(7))
        print(f"{risk_label}: reached {total}/{G.number_of_nodes()} nodes, peaked at step {peak_step}")
