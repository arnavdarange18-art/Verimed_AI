"""
PHASE 6a: Synthetic social graph construction.

We don't have access to real social media sharing data (no Twitter/WhatsApp
API access, and that data is not publicly available for a hackathon anyway).
Instead we generate a synthetic network using the Barabasi-Albert model,
which produces the same "hub-and-spoke" structure real social networks have
(a few highly-connected accounts, many loosely-connected ones) -- this is a
standard, well-established technique in network science for studying spread
dynamics without needing real platform data.

This graph structure is what the GNN reasons over.
"""

import networkx as nx
import numpy as np


def generate_social_graph(num_nodes: int = 150, m: int = 3, seed: int | None = None) -> nx.Graph:
    """
    Generates a synthetic social network with realistic hub structure.

    num_nodes: total simulated accounts in the network
    m: number of edges each new node attaches with (controls hub concentration)
    """
    return nx.barabasi_albert_graph(num_nodes, m, seed=seed)


def graph_node_features(G: nx.Graph, seed: int | None = None) -> np.ndarray:
    """
    Builds a [num_nodes, 2] feature matrix:
      feature 0: normalized degree centrality (how "hub-like" this account is)
      feature 1: random engagement/susceptibility score (how likely this
                 account is to reshare content it sees -- stands in for
                 real engagement-rate data we don't have access to)
    """
    rng = np.random.default_rng(seed)
    degrees = dict(G.degree())
    max_deg = max(degrees.values()) or 1

    features = []
    for node in G.nodes():
        deg_norm = degrees[node] / max_deg
        susceptibility = rng.uniform(0.2, 0.9)
        features.append([deg_norm, susceptibility])

    return np.array(features, dtype=np.float32)


def top_hub_nodes(G: nx.Graph, k: int = 3) -> list[int]:
    """Returns the k highest-degree nodes -- the accounts most responsible for spread."""
    degrees = dict(G.degree())
    return sorted(degrees, key=degrees.get, reverse=True)[:k]


if __name__ == "__main__":
    # Quick manual test -- run: python gnn/graph_utils.py
    G = generate_social_graph(seed=42)
    feats = graph_node_features(G, seed=42)
    hubs = top_hub_nodes(G, k=3)

    print(f"Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    print(f"Node feature matrix shape: {feats.shape}")
    print(f"Top 3 hub nodes (by degree): {hubs}")
    print(f"Degree of top hub: {G.degree(hubs[0])}")
