"""Graph code tests on a tiny hand-built graph, plus checks of the real Elliptic data against its published counts."""
import numpy as np
import pytest
import scipy.sparse as sp
from safepay_graph.data import PROCESSED, Graph, load_graph
from safepay_graph.experiment import cases, neighbour_score_features
from safepay_graph.features import graph_features, row_normalise

# 0 - 1 - 2   and   3 - 4   and  5 alone
EDGES = [(0, 1), (1, 2), (3, 4)]


def tiny(y=None, time=None) -> Graph:
    n = 6
    d = sp.csr_matrix((np.ones(len(EDGES), dtype=np.float32), ([a for a, _ in EDGES], [b for _, b in EDGES])), shape=(n, n))
    A = ((d + d.T) > 0).astype(np.float32).tocsr()
    X = np.arange(n * 2, dtype=np.float32).reshape(n, 2)
    return Graph(X, np.array(time if time is not None else [1] * n), np.array(y if y is not None else [1, 0, 0, 1, 1, 0], dtype=np.float32), A,
                 np.asarray(d.sum(axis=1)).ravel(), np.asarray(d.sum(axis=0)).ravel(), np.arange(n))


def test_row_normalise_averages_neighbours_and_leaves_isolated_nodes_at_zero():
    g = tiny()
    h = row_normalise(g.A) @ g.X
    assert h[1].tolist() == [(g.X[0][0] + g.X[2][0]) / 2, (g.X[0][1] + g.X[2][1]) / 2] and h[5].tolist() == [0.0, 0.0]


def test_graph_features_have_the_expected_shape_and_start_with_the_own_features():
    g = tiny()
    f = graph_features(g)
    assert f.shape == (6, 2 + 2 + 2 + 4) and np.array_equal(f[:, :2], g.X)


def test_features_never_depend_on_labels():
    a, b = tiny(y=[1, 0, 0, 1, 1, 0]), tiny(y=[0, 1, 1, 0, 0, 1])
    assert np.array_equal(graph_features(a), graph_features(b))


def test_alerts_that_touch_become_one_case_and_isolated_alerts_stay_separate():
    g = tiny(y=[1, 1, 0, 1, 1, 1])
    score = np.array([0.9, 0.9, 0.1, 0.9, 0.9, 0.9])
    c = cases(g, score, 0.5, np.arange(6))
    assert c["alerts"] == 5 and c["cases"] == 3 and c["cases_with_2_or_more_alerts"] == 2 and c["largest_case"] == 2
    assert c["pure_illicit_cases_share_of_labelled_cases"] == 1.0


def test_a_case_that_mixes_licit_and_illicit_is_reported_as_mixed():
    g = tiny(y=[1, 0, 0, 1, 1, 0])
    c = cases(g, np.array([0.9, 0.9, 0.1, 0.1, 0.1, 0.1]), 0.5, np.arange(6))
    assert c["mixed_cases"] == 1


def test_split_uses_time_and_only_labelled_nodes():
    g = tiny(y=[1, 0, np.nan, 1, 0, 0], time=[3, 30, 30, 40, 49, 10])
    s = g.split()
    assert s["train"].tolist() == [0, 5] and s["val"].tolist() == [1] and s["test"].tolist() == [3, 4]


real = pytest.mark.skipif(not (PROCESSED / "elliptic_classes.parquet").exists(), reason="Elliptic data not downloaded")


@real
@pytest.mark.integration
def test_real_graph_matches_the_published_counts():
    g = load_graph()
    assert g.n == 203_769 and g.A.nnz // 2 == 234_355 and g.X.shape[1] == 165
    assert int(np.nansum(g.y)) == 4_545 and int((g.y == 0).sum()) == 42_019 and int(np.isnan(g.y).sum()) == 157_205
    assert (g.A != g.A.T).nnz == 0                                              # symmetric


@real
@pytest.mark.integration
def test_every_real_edge_stays_inside_one_time_step():
    g = load_graph()
    r, c = g.A.nonzero()
    assert (g.time[r] == g.time[c]).all()
