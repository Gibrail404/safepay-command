"""Settings shared by the orchestrator and the MLP trainer. No heavy imports here on purpose."""
FRACTIONS = (0.6, 0.2, 0.2)
SEEDS = [0, 1, 2, 3, 4]
MLP_PARAMS = dict(epochs=40, patience=5, batch_size=1024, lr=1e-3, weight_decay=1e-4, pos_weight="sqrt(neg/pos)")
