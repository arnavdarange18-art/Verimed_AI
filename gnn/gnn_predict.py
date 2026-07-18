"""
PHASE 6f: GNN inference for real claims.

This is what app.py's /api/predict_spread calls. It replaces the hardcoded
placeholder dict with real predictions from the trained SpreadGNN.

Falls back to a clearly-labeled heuristic if the model file is missing or
inference fails for any reason -- matches the "Fallback Strategy" from the
original spec: never let the GNN layer break the whole request.
"""

import os
import torch
from torch_geometric.data import Data, Batch

from .graph_utils import generate_social_graph, graph_node_features, top_hub_nodes
from .claim_features import build_claim_feature_vector
from .model import SpreadGNN

_MODEL_PATH = os.path.join(os.path.dirname(__file__), "spread_gnn_weights.pt")
_NUM_NODES = 150

# A fixed base network representing a "typical" WhatsApp/social sharing
# cluster -- kept constant across requests so predictions are comparable
# to each other (same "world", different claims).
_GRAPH_SEED = 2026
_SCALE_FACTOR = 90  # scales the small simulated network up to illustrative "real world" numbers

_model = None
_graph = None
_node_feats = None
_hub_labels = ["WhatsApp Forwards Cluster A", "Public Facebook Groups", "X/Twitter Health Community"]


def _load_model():
    global _model
    if _model is not None:
        return _model

    model = SpreadGNN()
    model.load_state_dict(torch.load(_MODEL_PATH, map_location="cpu"))
    model.eval()
    _model = model
    return _model


def _get_graph():
    global _graph, _node_feats
    if _graph is None:
        _graph = generate_social_graph(num_nodes=_NUM_NODES, m=3, seed=_GRAPH_SEED)
        _node_feats = graph_node_features(_graph, seed=_GRAPH_SEED)
    return _graph, _node_feats


def _heuristic_fallback(claim_text: str) -> dict:
    """Same-shape placeholder used if the real model can't run."""
    return {
        "virality_score": 50,
        "risk_level": "Medium Risk",
        "predicted_nodes_reached": 5000,
        "time_to_peak_hours": 24,
        "network_hubs_vulnerable": _hub_labels[:2],
        "is_simulated": True,
    }


def predict_spread(claim_text: str, verdict: str, confidence: float, entities: list[dict]) -> dict:
    """
    Main entry point. Given a claim's verification result, predicts how far
    and how fast it would spread through a simulated social network.

    Returns the same schema the old placeholder endpoint used, so app.py's
    /api/predict_spread and predictor.html/main.js don't need any changes.
    """
    try:
        model = _load_model()
        G, node_feats = _get_graph()

        claim_feat = build_claim_feature_vector(claim_text, verdict, confidence, entities)

        edge_index = torch.tensor(list(G.edges()), dtype=torch.long).t().contiguous()
        edge_index = torch.cat([edge_index, edge_index.flip(0)], dim=1)
        data = Data(x=torch.tensor(node_feats, dtype=torch.float32), edge_index=edge_index)
        batch = Batch.from_data_list([data])

        with torch.no_grad():
            output = model(
                batch.x, batch.edge_index, batch.batch,
                torch.tensor([claim_feat], dtype=torch.float32),
            )

        spread_fraction, time_to_peak_norm = output[0].tolist()

        predicted_nodes_reached = int(spread_fraction * G.number_of_nodes() * _SCALE_FACTOR)
        time_to_peak_hours = round(2 + time_to_peak_norm * 46, 1)  # map to a 2-48hr range

        if spread_fraction >= 0.6:
            risk_level = "High Risk"
        elif spread_fraction >= 0.3:
            risk_level = "Medium Risk"
        else:
            risk_level = "Low Risk"

        hub_indices = top_hub_nodes(G, k=2)
        vulnerable_hubs = [_hub_labels[i % len(_hub_labels)] for i in range(len(hub_indices))]

        return {
            "virality_score": round(spread_fraction * 100),
            "risk_level": risk_level,
            "predicted_nodes_reached": predicted_nodes_reached,
            "time_to_peak_hours": time_to_peak_hours,
            "network_hubs_vulnerable": vulnerable_hubs,
            "is_simulated": False,  # real trained-model prediction, not a placeholder
        }

    except Exception as e:
        print(f"[gnn_predict] Falling back to heuristic -- error: {e}")
        return _heuristic_fallback(claim_text)


if __name__ == "__main__":
    # Quick manual test -- run: python gnn/gnn_predict.py
    test_cases = [
        ("Garlic cures COVID-19 instantly, doctors hate this secret!", "False", 92, [{"text": "garlic"}, {"text": "COVID-19"}]),
        ("Regular exercise is good for your heart", "True", 88, [{"text": "exercise"}, {"text": "heart"}]),
    ]

    for claim, verdict, conf, entities in test_cases:
        result = predict_spread(claim, verdict, conf, entities)
        print(f"\nClaim: '{claim}'  (verdict={verdict})")
        for k, v in result.items():
            print(f"  {k}: {v}")
