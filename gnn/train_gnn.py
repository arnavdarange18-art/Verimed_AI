"""
PHASE 6e: Train the Spread-Risk GNN.

Generates synthetic training examples by:
  1. Sampling a random claim feature vector (varying risk levels)
  2. Building a social graph
  3. Running the epidemic simulation to get ground-truth spread outcome
  4. Training the GAT to predict that outcome directly from graph + claim features

Run with: python gnn/train_gnn.py
Takes 1-3 minutes on CPU. Saves weights to gnn/spread_gnn_weights.pt
"""

import random
import numpy as np
import torch
import torch.nn as nn
from torch_geometric.data import Data, Batch

from .graph_utils import generate_social_graph, graph_node_features
from .simulate_spread import simulate_epidemic_spread
from .model import SpreadGNN

NUM_SAMPLES = 400
NUM_NODES = 150
MAX_STEPS = 20
EPOCHS = 60
LR = 0.01

VERDICT_LABELS = ["False", "Misleading", "Unverified", "True"]
VERDICT_RISK = {"False": 1.0, "Misleading": 0.6, "Unverified": 0.3, "True": 0.0}


def random_claim_feature_vector(rng: random.Random) -> tuple[list[float], float]:
    """
    Samples a random claim feature vector AND returns the risk score used to
    drive the simulation label -- these need to be consistent (the model
    learns to map features -> outcome, so the simulation must use a risk
    score derived from those same features, not an independent random one).
    """
    verdict = rng.choice(VERDICT_LABELS)
    verdict_risk = VERDICT_RISK[verdict]
    confidence_norm = rng.uniform(0.5, 1.0)
    entity_density = rng.uniform(0.0, 1.0)
    length_norm = rng.uniform(0.0, 1.0)
    sensational = rng.uniform(0.0, 1.0)

    feature_vector = [verdict_risk, confidence_norm, entity_density, length_norm, sensational]

    # Overall risk score feeding the simulation -- weighted combination,
    # dominated by verdict (false claims spread more) and sensationalism.
    risk_score = 0.55 * verdict_risk + 0.25 * sensational + 0.20 * entity_density
    return feature_vector, min(risk_score, 1.0)


def build_training_set(num_samples: int, rng: random.Random):
    samples = []
    for i in range(num_samples):
        seed = i  # vary the graph slightly per sample for diversity
        G = generate_social_graph(num_nodes=NUM_NODES, m=3, seed=seed % 50)
        node_feats = graph_node_features(G, seed=seed)

        feature_vector, risk_score = random_claim_feature_vector(rng)

        seed_node = max(dict(G.degree()).items(), key=lambda kv: kv[1])[0]
        total_reached, peak_step, _history = simulate_epidemic_spread(
            G, risk_score, seed_node, max_steps=MAX_STEPS, rng=rng
        )

        spread_fraction = total_reached / G.number_of_nodes()
        time_to_peak_norm = peak_step / MAX_STEPS

        edge_index = torch.tensor(list(G.edges()), dtype=torch.long).t().contiguous()
        # Graphs are undirected -- add reverse edges so GATConv sees both directions
        edge_index = torch.cat([edge_index, edge_index.flip(0)], dim=1)

        data = Data(
            x=torch.tensor(node_feats, dtype=torch.float32),
            edge_index=edge_index,
        )
        label = torch.tensor([spread_fraction, time_to_peak_norm], dtype=torch.float32)
        claim_feat = torch.tensor(feature_vector, dtype=torch.float32)

        samples.append((data, claim_feat, label))

    return samples


def train():
    rng = random.Random(42)
    torch.manual_seed(42)

    print(f"Generating {NUM_SAMPLES} synthetic training samples (simulating spread for each)...")
    samples = build_training_set(NUM_SAMPLES, rng)
    print("Done generating training data.\n")

    model = SpreadGNN()
    optimizer = torch.optim.Adam(model.parameters(), lr=LR, weight_decay=1e-4)
    loss_fn = nn.MSELoss()

    print(f"Training for {EPOCHS} epochs...")
    for epoch in range(1, EPOCHS + 1):
        random.shuffle(samples)
        total_loss = 0.0

        for data, claim_feat, label in samples:
            optimizer.zero_grad()
            batch = Batch.from_data_list([data])
            claim_feat_batch = claim_feat.unsqueeze(0)

            pred = model(batch.x, batch.edge_index, batch.batch, claim_feat_batch)
            loss = loss_fn(pred, label.unsqueeze(0))
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        avg_loss = total_loss / len(samples)
        if epoch % 10 == 0 or epoch == 1:
            print(f"  Epoch {epoch:3d}/{EPOCHS}  --  avg MSE loss: {avg_loss:.4f}")

    torch.save(model.state_dict(), "spread_gnn_weights.pt")
    print("\n✅ Training complete. Weights saved to gnn/spread_gnn_weights.pt")

    # Quick sanity check: verify the trained model still shows the expected
    # risk contrast (false/sensational claims should score higher than true ones)
    print("\n--- Sanity check on trained model ---")
    model.eval()
    G = generate_social_graph(num_nodes=NUM_NODES, m=3, seed=99)
    node_feats = graph_node_features(G, seed=99)
    edge_index = torch.tensor(list(G.edges()), dtype=torch.long).t().contiguous()
    edge_index = torch.cat([edge_index, edge_index.flip(0)], dim=1)
    data = Data(x=torch.tensor(node_feats, dtype=torch.float32), edge_index=edge_index)
    batch = Batch.from_data_list([data])

    with torch.no_grad():
        low_risk = model(batch.x, batch.edge_index, batch.batch, torch.tensor([[0.0, 0.9, 0.2, 0.2, 0.0]]))
        high_risk = model(batch.x, batch.edge_index, batch.batch, torch.tensor([[1.0, 0.9, 0.8, 0.8, 1.0]]))

    print(f"True/neutral claim  -> spread_fraction={low_risk[0][0]:.3f}, time_to_peak_norm={low_risk[0][1]:.3f}")
    print(f"False/sensational   -> spread_fraction={high_risk[0][0]:.3f}, time_to_peak_norm={high_risk[0][1]:.3f}")

    if high_risk[0][0] > low_risk[0][0]:
        print("✅ Model correctly learned that risky claims spread further.")
    else:
        print("⚠️  Model did not learn the expected pattern -- consider more epochs/samples.")


if __name__ == "__main__":
    train()
