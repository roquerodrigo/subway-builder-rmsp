"""Unit tests for the deterministic, dependency-free helpers."""

from rmsp import demand_filter, publish, routing


def test_publish_config_required_fields():
    # the registry rejects a map whose config.json lacks code/version or a numeric
    # initialViewState (scripts/lib/integrity.ts + map-demand-stats extraction)
    cfg = publish._config("2.3.4")
    assert cfg["code"] == "RMSP"
    assert cfg["version"] == "2.3.4"
    ivs = cfg["initialViewState"]
    assert set(ivs) == {"latitude", "longitude", "zoom", "bearing"}
    assert all(isinstance(ivs[k], (int, float)) for k in ivs)


def test_rdp_keeps_endpoints_drops_collinear():
    line = [[0, 0], [1, 0.0001], [2, 0], [3, 0.0001], [4, 0]]
    out = routing.rdp(line, eps=0.01)  # tolerance >> deviations -> straight
    assert out == [[0, 0], [4, 0]]


def test_rdp_keeps_sharp_corner():
    line = [[0, 0], [1, 1], [2, 0]]  # a clear peak
    out = routing.rdp(line, eps=0.1)
    assert [1, 1] in out
    assert len(out) == 3


def test_rdp_short_path_unchanged():
    assert routing.rdp([[0, 0], [1, 1]], eps=0.001) == [[0, 0], [1, 1]]


def _demand():
    return {
        "points": [
            {"id": "A", "location": [0, 0], "jobs": 0, "residents": 10, "popIds": ["p1", "p2"]},
            {"id": "B", "location": [1, 1], "jobs": 10, "residents": 0, "popIds": []},
            {"id": "C", "location": [2, 2], "jobs": 3, "residents": 0, "popIds": []},
        ],
        "pops": [
            {"id": "p1", "size": 7, "residenceId": "A", "jobId": "B", "drivingDistance": 5000},
            {"id": "p2", "size": 3, "residenceId": "A", "jobId": "C", "drivingDistance": 800},
        ],
    }


def test_prune_drops_short_commutes_and_rebuilds_points():
    pruned = demand_filter.prune_short_commutes(_demand(), 1000)
    # the 800 m commute p2 (and its now-demand-less destination C) is gone
    assert [p["id"] for p in pruned["pops"]] == ["p1"]
    assert {p["id"] for p in pruned["points"]} == {"A", "B"}


def test_prune_reindexes_popids_residents_jobs():
    pruned = demand_filter.prune_short_commutes(_demand(), 1000)
    by_id = {p["id"]: p for p in pruned["points"]}
    assert by_id["A"]["popIds"] == ["p1"]  # p2 removed from the index
    assert by_id["A"]["residents"] == 7  # recomputed from survivors, not the original 10
    assert by_id["B"]["jobs"] == 7


def test_prune_zero_threshold_keeps_everything():
    pruned = demand_filter.prune_short_commutes(_demand(), 0)
    assert len(pruned["pops"]) == 2
    assert len(pruned["points"]) == 3
