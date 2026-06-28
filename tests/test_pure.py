"""Unit tests for the deterministic, dependency-free helpers."""

from rmsp import publish, routing


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
