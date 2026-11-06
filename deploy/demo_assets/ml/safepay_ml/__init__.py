"""Models and evaluation for SafePay Command. Pure functions for metrics; training scripts write reports generated from real data."""
# RULE: never load LightGBM and PyTorch in the same process on macOS. Each ships its own OpenMP runtime; having both loaded makes
# PyTorch training segfault (exit 139 / -11) or deadlock, even if LightGBM is only imported and never used. So:
#   - train_risk.py (LightGBM, scikit-learn) never imports torch;  - train_mlp.py (PyTorch) never imports lightgbm and runs as its own process;
#   - scorers import their library lazily, and a serving process loads only the library of the model it serves.
__version__ = "0.3.0"
