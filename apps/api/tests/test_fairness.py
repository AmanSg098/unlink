from app.fairness.adverse_impact import adverse_impact


def test_four_fifths_known_values():
    rows = [("A", i < 1) for i in range(10)] + [("B", i < 4) for i in range(10)]
    a, b = adverse_impact(rows)
    assert (a.group, a.pool, a.selected, a.selection_rate, a.retention_rate) == ("A", 10, 1, 0.1, 0.9)
    assert a.impact_ratio == 1.0 and not a.flagged
    assert (b.retention_rate, b.impact_ratio) == (0.6, 0.6667)
    assert b.flagged


def test_exactly_at_threshold_not_flagged():
    rows = [("A", False)] * 10 + [("B", i < 2) for i in range(10)]  # B retention 0.8 / 1.0
    _, b = adverse_impact(rows)
    assert b.impact_ratio == 0.8 and not b.flagged


def test_small_sample_marked():
    stats = adverse_impact([("A", False)] * 4 + [("B", False)] * 5)
    assert [s.small_sample for s in stats] == [True, False]


def test_everyone_selected_gives_no_ratio():
    (a,) = adverse_impact([("A", True)] * 3)
    assert a.impact_ratio is None and not a.flagged
