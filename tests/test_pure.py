"""Unit tests for the deterministic, dependency-free helpers."""

from rmsp import layers, routing, tiles


def test_bldg_height_from_height_tag():
    assert tiles._bldg_height({"height": "12.5"}) == 12.5
    assert tiles._bldg_height({"height": "30 m"}) == 30.0
    assert tiles._bldg_height({"height": "18;24"}) == 18.0  # multi-value -> first


def test_bldg_height_from_levels():
    assert tiles._bldg_height({"building:levels": "10"}) == 32.0  # 10 × 3.2 m
    assert tiles._bldg_height({"building:levels": "2"}) == 6.4


def test_bldg_height_missing_or_bad():
    assert tiles._bldg_height({}) is None
    assert tiles._bldg_height({"height": "tall"}) is None
    assert tiles._bldg_height({"building:levels": "n/a"}) is None


def test_foundation_depth():
    # the game reads buildings_index `f` / tiles `foundationDepth` as basement levels
    assert layers.foundation_depth({}) == 1  # default
    assert layers.foundation_depth({"building:levels": "40"}) == 1  # above-ground ≠ depth
    assert layers.foundation_depth({"building:levels:underground": "3"}) == 3
    assert layers.foundation_depth({"building:levels:underground": "2.5"}) == 2
    assert layers.foundation_depth({"depth": "0"}) == 1  # max(1, …)
    assert layers.foundation_depth({"building:levels:underground": "x"}) == 1


def test_label_classes_partition():
    # the three label layers must not overlap and cover the extracted place classes
    seen = set()
    for classes in tiles._LABEL_CLASSES.values():
        assert not (seen & classes)
        seen |= classes
    assert {"city", "town", "suburb", "neighbourhood"} <= seen


def test_road_class():
    assert layers.road_class("motorway") == "highway"
    assert layers.road_class("trunk_link") == "highway"
    assert layers.road_class("primary") == "major"
    assert layers.road_class("tertiary_link") == "major"
    assert layers.road_class("residential") == "minor"
    assert layers.road_class("") == "minor"
    assert layers.road_class("footway") == "minor"


def test_ring_area_m2_unit_cell():
    # ~0.0009° square near São Paulo ≈ 0.0009*110900 × 0.0009*101900 ≈ 9156 m²
    side = 0.0009
    ring = [[0, 0], [side, 0], [side, side], [0, side], [0, 0]]
    area = layers.ring_area_m2(ring)
    assert 8000 < area < 10500


def test_grid_cells_single_cell():
    cs = 0.0009
    items = [{"b": [0.0, 0.0, 0.0002, 0.0002]}]  # bbox fits in one cell
    cells = layers._grid_cells(items, 0.0, 0.0, cs)
    assert cells == [[0, 0, 0]]


def test_grid_cells_spans_multiple():
    cs = 0.001
    items = [{"b": [0.0, 0.0, 0.0025, 0.0]}]  # spans gx 0..2
    cells = layers._grid_cells(items, 0.0, 0.0, cs)
    gxs = sorted(c[0] for c in cells)
    assert gxs == [0, 1, 2]
    assert all(c[2] == 0 for c in cells)  # all reference item 0


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
