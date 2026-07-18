"""
PHASE 6d: The Spread-Risk GNN.

A Graph Attention Network (GAT) that reads the social graph structure and
the claim's feature vector, and predicts two normalized outputs:
  1. spread_fraction  -- what fraction of the network the claim would reach
  2. time_to_peak_norm -- how quickly it spreads (normalized to [0,1])

Architecture: 2 GAT layers over node features -> global mean pool -> combine
with claim features -> small MLP head -> sigmoid outputs.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import GATConv, global_mean_pool


class SpreadGNN(nn.Module):
    def __init__(self, node_in: int = 2, claim_in: int = 5, hidden: int = 32):
        super().__init__()
        self.gat1 = GATConv(node_in, hidden, heads=2, concat=True)
        self.gat2 = GATConv(hidden * 2, hidden, heads=1, concat=False)

        self.claim_fc = nn.Linear(claim_in, hidden)

        self.head = nn.Sequential(
            nn.Linear(hidden * 2, hidden),
            nn.ReLU(),
            nn.Linear(hidden, 2),  # [spread_fraction, time_to_peak_norm]
        )

    def forward(self, x, edge_index, batch, claim_feat):
        x = F.elu(self.gat1(x, edge_index))
        x = F.elu(self.gat2(x, edge_index))

        graph_embed = global_mean_pool(x, batch)      # [batch_size, hidden]
        claim_embed = F.elu(self.claim_fc(claim_feat))  # [batch_size, hidden]

        combined = torch.cat([graph_embed, claim_embed], dim=1)
        out = torch.sigmoid(self.head(combined))       # both outputs in [0, 1]
        return out


if __name__ == "__main__":
    # Quick manual test -- run: python gnn/model.py
    # Verifies the model runs forward with dummy data before we build the
    # full training pipeline around it.
    import sys
    sys.path.insert(0, ".")
    from torch_geometric.data import Data, Batch

    num_nodes = 150
    dummy_x = torch.rand(num_nodes, 2)
    dummy_edges = torch.randint(0, num_nodes, (2, 400))
    dummy_claim_feat = torch.rand(1, 5)

    data = Data(x=dummy_x, edge_index=dummy_edges)
    batch = Batch.from_data_list([data])

    model = SpreadGNN()
    output = model(batch.x, batch.edge_index, batch.batch, dummy_claim_feat)
    print(f"Model output shape: {output.shape}")  # expect [1, 2]
    print(f"Sample output (spread_fraction, time_to_peak_norm): {output[0].tolist()}")
