import pytest

from app.scoring.engine import Candidate, apply_overrides, normalize_weights, score_pool

UP = {"perf": True, "tenure": True, "cost": False}


def c(eid, perf=3.0, tenure=5.0, cost=100.0, excluded=False):
    return Candidate(eid, {"perf": perf, "tenure": tenure, "cost": cost}, excluded,
                     "On medical leave" if excluded else None)


def by_id(scored):
    return {s.employee_id: s for s in scored}


def test_single_factor_min_max():
    out = by_id(score_pool([c(1, perf=1), c(2, perf=3), c(3, perf=5)], {"perf": 1}, UP, 1))
    assert (out[1].score, out[2].score, out[3].score) == (0.0, 50.0, 100.0)
    assert (out[1].rank, out[2].rank, out[3].rank) == (1, 2, 3)
    assert [out[i].selected for i in (1, 2, 3)] == [True, False, False]


def test_weighted_two_factors_known_values():
    # perf norms: 0, 1 ; tenure norms: 1, 0 ; weights 3:1 -> 0.75, 0.25
    out = by_id(score_pool([c(1, perf=2, tenure=10), c(2, perf=4, tenure=2)],
                           {"perf": 3, "tenure": 1}, UP, 1))
    assert out[1].score == 25.0 and out[1].contributions == {"perf": 0.0, "tenure": 25.0}
    assert out[2].score == 75.0 and out[2].contributions == {"perf": 75.0, "tenure": 0.0}
    assert out[1].selected and not out[2].selected


def test_lower_is_better_factor_is_inverted():
    out = by_id(score_pool([c(1, cost=200), c(2, cost=100)], {"cost": 1}, UP, 1))
    assert out[1].score == 0.0 and out[2].score == 100.0
    assert out[1].selected


def test_equal_values_normalise_to_half_and_ties_break_on_id():
    out = score_pool([c(7), c(3), c(5)], {"perf": 1}, UP, 2)
    assert [s.score for s in out] == [50.0, 50.0, 50.0]
    assert [s.employee_id for s in out] == [3, 5, 7]
    assert [s.selected for s in out] == [True, True, False]


def test_hard_excluded_never_selected_and_not_in_ranges():
    # Excluded employee has the worst perf but must be ignored entirely.
    out = by_id(score_pool([c(1, perf=0, excluded=True), c(2, perf=2), c(3, perf=4)], {"perf": 1}, UP, 5))
    assert out[1].excluded and out[1].score is None and out[1].rank is None and not out[1].selected
    assert out[2].score == 0.0 and out[3].score == 100.0


def test_zero_weights_ignored_and_rescaled():
    assert normalize_weights({"perf": 2, "tenure": 0, "cost": 2}, list(UP)) == {"perf": 0.5, "cost": 0.5}


@pytest.mark.parametrize("weights", [{"perf": 0}, {"perf": -1}, {"nope": 1}])
def test_invalid_weights(weights):
    with pytest.raises(ValueError):
        normalize_weights(weights, list(UP))


def test_overrides_cannot_select_excluded():
    scored = score_pool([c(1, excluded=True), c(2, perf=1), c(3, perf=5)], {"perf": 1}, UP, 1)
    final = apply_overrides(scored, {1: "include", 2: "exclude", 3: "include"})
    assert final == {1: False, 2: False, 3: True}
