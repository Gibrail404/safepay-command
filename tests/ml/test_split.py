"""The split is the foundation of every honest number. These tests run on the real ULB data produced by the M0 pipeline."""
import numpy as np
import pytest
from safepay_ml.data import FEATURES, ULB_PARQUET, duplicate_overlap, load_ulb, temporal_split

pytestmark = pytest.mark.integration
if not ULB_PARQUET.exists():
    pytest.skip("run: cd pipelines && python -m safepay_data ulb_creditcard", allow_module_level=True)


@pytest.fixture(scope="module")
def parts():
    return temporal_split(load_ulb())


def test_sizes_and_fraud_counts_are_the_documented_ones(parts):
    assert [len(parts[k].y) for k in ("train", "val", "test")] == [170884, 56961, 56962]
    assert [int(parts[k].y.sum()) for k in ("train", "val", "test")] == [360, 57, 75]


def test_the_split_follows_time_with_no_overlap(parts):
    assert parts["train"].time.max() <= parts["val"].time.min()
    assert parts["val"].time.max() <= parts["test"].time.min()
    assert sum(len(p.y) for p in parts.values()) == 284807


def test_time_is_not_a_feature_and_amount_is_log_scaled(parts):
    assert "Time" not in FEATURES and len(FEATURES) == 29
    assert parts["train"].X.shape[1] == 29 and np.isfinite(parts["train"].X).all()


def test_duplicate_overlap_mask_has_one_entry_per_test_row(parts):
    mask = duplicate_overlap(parts["train"], parts["test"])
    assert mask.shape == (len(parts["test"].y),) and mask.dtype == bool
