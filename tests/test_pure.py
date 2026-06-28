"""Unit tests for the deterministic, dependency-free helpers."""

import pytest

from rmsp import demand, geojson, layers, publish, routing, subpoints, tiles
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


def test_levels_from_height_when_levels_missing():
    # ~95% of RMSP buildings carry `height` but not `building:levels`; height ÷ 3.2
    # must drive the floor count so vertical density is not lost.
    assert subpoints._levels({"height": "32"}) == 10.0  # 32 m / 3.2
    assert subpoints._levels({"height": "9.6 m"}) == pytest.approx(3.0)
    assert subpoints._levels({"height": "80;90"}) == 25.0  # multi-value -> first
    # explicit levels still win over height
    assert subpoints._levels({"building:levels": "5", "height": "100"}) == 5.0
    # unparseable height -> single storey; tower height clamped to the cap
    assert subpoints._levels({"height": "tall"}) == 1.0
    assert subpoints._levels({"height": "10000"}) == float(settings.bldg_levels_cap)


def test_building_weight_scales_with_height():
    side = 0.001
    ring = [[0, 0], [side, 0], [side, side], [0, side], [0, 0]]
    area, _, _ = subpoints._ring_area_centroid(ring)
    res_flat, _ = subpoints.building_weight({"building": "house"}, area)
    res_tower, _ = subpoints.building_weight({"building": "house", "height": "32"}, area)
    # a 32 m (~10-storey) tower carries ~10x the same-footprint single storey
    assert abs(res_tower - 10 * res_flat) < 1e-6


def test_levels_alt_height_tags():
    # building:height / est_height are parsed like height when height is absent
    assert subpoints._levels({"building:height": "32"}) == 10.0  # 32 m / 3.2
    assert subpoints._levels({"est_height": "9.6"}) == pytest.approx(3.0)


def test_levels_typology_default_when_untagged():
    # no levels and no height -> per-typology default, not a flat single storey
    assert subpoints._levels({"building": "apartments"}) == 6.0
    assert subpoints._levels({"building": "office"}) == 4.0
    # unlisted class still falls back to one storey
    assert subpoints._levels({"building": "house"}) == 1.0


def test_levels_height_beats_typology_default():
    # an explicit height tag wins over the typology default
    assert subpoints._levels({"building": "apartments", "height": "32"}) == 10.0


def test_density_mult_lookup():
    assert subpoints._density_mult("apartments")[0] == settings.res_density_mult["apartments"]
    assert subpoints._density_mult("warehouse")[1] == settings.job_density_mult["warehouse"]
    # unlisted class -> default multiplier on both axes
    assert subpoints._density_mult("yes") == (
        settings.density_mult_default, settings.density_mult_default,
    )


def test_building_weight_typology_density():
    # same footprint + same floors: apartments concentrate residents above a house
    side = 0.001
    ring = [[0, 0], [side, 0], [side, side], [0, side], [0, 0]]
    area, _, _ = subpoints._ring_area_centroid(ring)
    res_house, _ = subpoints.building_weight({"building": "house", "building:levels": "1"}, area)
    res_flats, _ = subpoints.building_weight(
        {"building": "apartments", "building:levels": "1"}, area
    )
    assert abs(res_flats - settings.res_density_mult["apartments"] * res_house) < 1e-6
    # offices carry more jobs per m² than warehouses of the same footprint
    _, job_office = subpoints.building_weight({"building": "office", "building:levels": "1"}, area)
    _, job_wh = subpoints.building_weight(
        {"building": "warehouse", "building:levels": "1"}, area
    )
    ratio = settings.job_density_mult["office"] / settings.job_density_mult["warehouse"]
    assert job_office == pytest.approx(ratio * job_wh)


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


def test_cnefe_classify():
    # housing espécies -> residential only; establishments -> job only; skipped -> nothing
    assert subpoints._cnefe_classify(1) == (1.0, 0.0)  # domicílio particular
    assert subpoints._cnefe_classify(2) == (3.0, 0.0)  # coletivo (weighted ×3)
    assert subpoints._cnefe_classify(3) == (0.0, 1.0)  # estabelecimento
    assert subpoints._cnefe_classify(6) == (0.0, 1.0)
    assert subpoints._cnefe_classify(7) == (0.0, 0.0)  # under construction


def test_read_lines_range_partitions_losslessly(tmp_path):
    p = tmp_path / "lines.txt"
    rows = [f"{i},{i * 2},{i % 3}" for i in range(500)]
    p.write_text("\n".join(rows) + "\n")
    # union of every chunk == the whole file, no dups, no gaps, regardless of split count
    for n in (1, 3, 8, 17):
        seen = []
        for s, e in geojson.chunk_offsets(p, n):
            seen += [r.decode() for r in geojson.read_lines_range(p, s, e)]
        assert seen == rows


def test_merge_subpoints_sums_partials():
    # two chunks touch the same (zone, cell); weights and weighted centroid must combine
    key = (5, (1, 2))
    a = {key: [2.0, 0.0, 2.0 * 10.0, 2.0 * 20.0, 2.0]}
    b = {key: [0.0, 1.0, 1.0 * 10.0, 1.0 * 20.0, 1.0]}
    out = subpoints._merge_subpoints([a, b])
    assert list(out) == [5]
    sp = out[5][0]
    assert sp.res_w == 2.0 and sp.job_w == 1.0
    assert sp.lng == 10.0 and sp.lat == 20.0  # weighted centroid of coincident points
    assert sp.id == "z5c0"


def test_cnefe_chunk_aggregates(tmp_path, monkeypatch):
    # fake zone index: everything is zone 7; verify weights land in one cell
    monkeypatch.setattr(subpoints, "load_zone_index", lambda _shp: (lambda lng, lat: 7, {}))
    p = tmp_path / "cnefe.csv"
    s = "350000000000001"  # setor (4th column)
    p.write_text(f"-46.6,-23.5,1,{s}\n-46.6,-23.5,3,{s}\n-46.6,-23.5,7,{s}\n")  # res, job, skipped
    # no census weights -> espécie weights (res 1, job 1, espécie 7 dropped)
    acc = subpoints._cnefe_chunk(p, 0, p.stat().st_size, tmp_path / "zones")
    assert len(acc) == 1
    res_w, job_w, _wl, _wt, w = next(iter(acc.values()))
    assert res_w == 1.0 and job_w == 1.0 and w == 2.0
    # with census weights -> residential takes the per-setor weight; jobs keep espécie weight
    acc2 = subpoints._cnefe_chunk(p, 0, p.stat().st_size, tmp_path / "z", {s: 5.0}, 0.0)
    res_w2, job_w2, *_ = next(iter(acc2.values()))
    assert res_w2 == 5.0 and job_w2 == 1.0


def test_largest_remainder_conserves_total():
    assert sum(demand._largest_remainder([1, 1, 2], 4)) == 4
    assert sum(demand._largest_remainder([3.0, 1.0], 100)) == 100
    assert demand._largest_remainder([1, 1], 0) == [0, 0]
    assert demand._largest_remainder([], 5) == []
    # proportional: weight 3:1 over 100 -> 75:25
    assert demand._largest_remainder([3.0, 1.0], 100) == [75, 25]
