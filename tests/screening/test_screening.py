"""Unit tests for name normalisation and matching on a tiny list, plus integration tests on the real OFAC data (skipped when it is not downloaded)."""
import random
import pytest
from safepay_screening.data import PROCESSED
from safepay_screening.evaluate import perturb, wilson
from safepay_screening.matcher import NameIndex
from safepay_screening.normalise import clean, fold

LIST = [("1", "GADDAFI, Muammar", False), ("1", "Kadhafi, Moammar", True), ("2", "PUTIN, Vladimir Vladimirovich", False), ("3", "AL-ZOMOR, Abboud Abdul Latif Hassan", False),
        ("4", "ACME TRADING COMPANY LIMITED", False), ("5", "SMITH, Jonathan", False)]


def test_clean_removes_accents_case_punctuation_and_titles():
    assert clean("Dr. JOSÉ  Núñez-Pérez") == "jose nunez perez"


@pytest.mark.parametrize("a,b", [("Mohammed Alzomor", "Muhammad AL-ZOMOR"), ("Muammar Qaddafi", "Moammar Gaddafi"), ("Vladimir Putin", "Wladimir Putin")])
def test_known_spelling_variants_fold_to_the_same_key(a, b):
    assert fold(a) == fold(b)


def test_different_names_do_not_fold_together():
    assert fold("John Smith") != fold("Maria Garcia")


def test_fold_is_idempotent_on_its_own_output_shape():
    assert fold(fold("Muhammad Ali")) == fold("Muhammad Ali")


def test_exact_variants_and_typos_find_the_right_entry():
    idx = NameIndex(LIST)
    assert idx.search("Moammar Gadhafi")[0].ent_num == "1"
    assert idx.search("Vladimir Putin")[0].ent_num == "2"
    assert idx.search("Putn Vladimir")[0].ent_num == "2"


def test_word_order_does_not_matter():
    assert NameIndex(LIST).search("Vladimir PUTIN")[0].score == NameIndex(LIST).search("PUTIN Vladimir")[0].score


def test_a_shared_first_name_alone_is_not_a_strong_match():
    top = NameIndex(LIST).search("Jonathan Fernandez")[0]
    assert top.score < 80


def test_a_different_person_with_the_same_common_given_name_scores_low():
    assert NameIndex(LIST).search("Muammar Johnson")[0].score < 85


def test_alias_hit_is_reported_with_the_alias_and_the_list_entry():
    h = NameIndex(LIST).search("Kadhafi Moammar")[0]
    assert h.ent_num == "1" and h.is_alias and h.matched_name == "Kadhafi, Moammar"


def test_empty_and_punctuation_only_queries_return_nothing():
    idx = NameIndex(LIST)
    assert idx.search("") == [] and idx.search("  ,.- ") == []


def test_a_name_with_spaces_moved_still_matches():
    assert NameIndex(LIST).search("ALZOMOR Abboud Abdul Latif Hassan")[0].ent_num == "3"


def test_one_entry_appears_once_even_when_primary_and_alias_both_match():
    hits = NameIndex(LIST).search("Gaddafi Muammar", top=5)
    assert [h.ent_num for h in hits].count("1") == 1


def test_perturb_is_deterministic_for_a_seed_and_changes_the_name():
    a = [perturb("ABDUL RAHMAN HASSAN", "typo", random.Random(1)) for _ in range(3)]
    b = [perturb("ABDUL RAHMAN HASSAN", "typo", random.Random(1)) for _ in range(3)]
    assert a == b and all(x != "ABDUL RAHMAN HASSAN" for x in a)


def test_wilson_interval_contains_the_estimate_and_stays_in_bounds():
    lo, hi = wilson(5, 100)
    assert 0 <= lo < 0.05 < hi <= 1 and wilson(0, 0) == (0.0, 0.0) and wilson(100, 100)[1] == pytest.approx(1.0)


real = pytest.mark.skipif(not (PROCESSED / "ofac_alt.parquet").exists(), reason="real data not downloaded")


@real
@pytest.mark.integration
def test_real_list_finds_a_well_known_entry_and_a_common_name_does_not_alert_strongly():
    from safepay_screening.data import alias_rows, load_aliases, load_sdn, primary_rows
    idx = NameIndex(primary_rows(load_sdn()) + alias_rows(load_aliases()))
    assert idx.search("Ayman Zawahiri")[0].score >= 95
    assert idx.search("Sarah Johnson")[0].score < 90


@real
@pytest.mark.integration
def test_screen_name_tool_returns_band_and_hits_from_the_real_list():
    from pydantic import TypeAdapter
    from safepay import screening_tool as st
    if not st.BANDS_PATH.exists():
        pytest.skip("bands not generated")
    out = st.screen_name(st.ScreenInput(name="Ayman Zawahiri"))
    assert out["screen_band"] == "strong" and out["hits"][0]["ent_num"] and out["list_version"] and isinstance(out["thresholds_tuned_on_this_list"], bool)
    assert st.screen_name(st.ScreenInput(name="Sarah Johnson"))["screen_band"] == "none"
