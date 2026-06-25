"""Unit tests for the deterministic, dependency-free helpers."""

from rmsp import demand, layers, publish, routing, subpoints, tiles
from rmsp.config import settings


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


def test_publish_config_required_fields():
    # the registry rejects a map whose config.json lacks code/version or a numeric
    # initialViewState (scripts/lib/integrity.ts + map-demand-stats extraction)
    cfg = publish._config("2.3.4")
    assert cfg["code"] == "RMSP"
    assert cfg["version"] == "2.3.4"
    ivs = cfg["initialViewState"]
    assert set(ivs) == {"latitude", "longitude", "zoom", "bearing"}
    assert all(isinstance(ivs[k], (int, float)) for k in ivs)


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


# ----------------------------------------------------------- demand sub-points
def test_classify_building_types():
    assert subpoints.classify({"building": "apartments"}) == (1.0, 0.0)
    assert subpoints.classify({"building": "house"}) == (1.0, 0.0)
    assert subpoints.classify({"building": "office"}) == (0.0, 1.0)
    assert subpoints.classify({"building": "industrial"}) == (0.0, 1.0)


def test_classify_tag_signals():
    # a shop/amenity on an otherwise-generic building marks it a workplace
    assert subpoints.classify({"building": "yes", "shop": "bakery"}) == (0.0, 1.0)
    assert subpoints.classify({"building": "yes", "amenity": "school"}) == (0.0, 1.0)
    # parking amenity is not a workplace signal
    assert subpoints.classify({"building": "yes", "amenity": "parking"}) == settings.mixed_use_split
    # residence with a ground-floor shop: mostly residential, a little job
    assert subpoints.classify({"building": "apartments", "shop": "kiosk"}) == (0.8, 0.2)
    # unknown / building=yes with no signal -> configured split
    assert subpoints.classify({"building": "yes"}) == settings.mixed_use_split


def test_levels_clamped():
    assert subpoints._levels({"building:levels": "10"}) == 10.0
    assert subpoints._levels({}) == 1.0
    assert subpoints._levels({"building:levels": "n/a"}) == 1.0
    assert subpoints._levels({"building:levels": "3;5"}) == 3.0
    assert subpoints._levels({"building:levels": "9999"}) == float(settings.bldg_levels_cap)


def test_ring_area_centroid_unit_square():
    side = 0.002
    ring = [[0, 0], [side, 0], [side, side], [0, side], [0, 0]]
    area, cx, cy = subpoints._ring_area_centroid(ring)
    assert abs(area - side * side) < 1e-12
    assert abs(cx - side / 2) < 1e-9 and abs(cy - side / 2) < 1e-9


def test_building_weight_splits_floor_area():
    side = 0.001
    ring = [[0, 0], [side, 0], [side, side], [0, side], [0, 0]]
    area, _, _ = subpoints._ring_area_centroid(ring)
    res_w, job_w = subpoints.building_weight({"building": "house", "building:levels": "2"}, area)
    assert job_w == 0.0 and res_w > 0
    # 2 floors doubles the residential weight
    res1, _ = subpoints.building_weight({"building": "house"}, area)
    assert abs(res_w - 2 * res1) < 1e-6


def test_largest_remainder_conserves_total():
    assert sum(demand._largest_remainder([1, 1, 2], 4)) == 4
    assert sum(demand._largest_remainder([3.0, 1.0], 100)) == 100
    assert demand._largest_remainder([1, 1], 0) == [0, 0]
    assert demand._largest_remainder([], 5) == []
    # proportional: weight 3:1 over 100 -> 75:25
    assert demand._largest_remainder([3.0, 1.0], 100) == [75, 25]
