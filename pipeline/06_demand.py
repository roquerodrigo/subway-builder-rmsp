#!/usr/bin/env python3
"""demand_data.json.gz — built from the real Pesquisa OD 2017 (Metrô SP).

points: one per OD-2017 zone whose centroid falls inside the city bbox, with
        real residents (sum of person expansion FE_PESS by home zone) and jobs
        (FE_PESS by workplace zone ZONATRA1).
pops:   real home-based work/education trips aggregated by (origin, dest) zone,
        size = sum of trip expansion FE_VIA, with reported duration/distance.
"""
import json, gzip, os, math, collections
import shapefile  # pyshp
from shapely.geometry import shape as shp_shape
from pyproj import CRS, Transformer
from dbfread import DBF
import config

# Pesquisa Origem-Destino 2023 do Metrô-SP (mesma codificação/campos da 2017).
ZONES_SHP = os.path.join(config.SOURCES, "od2023", "Site_190225",
                         "002_Site Metro Mapas_190225", "Shape", "Zonas_2023")
OD_DBF = os.path.join(config.SOURCES, "od2023", "Site_190225",
                      "Banco2023_divulgacao_190225.dbf")
# Para usar a OD 2017, troque pelos caminhos abaixo:
#   ZONES_SHP = .../od2017/OD-2017/Mapas-OD2017/Shape-OD2017/Zonas_2017_region
#   OD_DBF    = .../od2017/OD-2017/Banco de Dados-OD2017/OD_2017_v1.dbf
OUT = os.path.join(config.OUT, "demand_data.json")

HOME = 8
WORK = {1, 2, 3}        # trabalho: indústria / comércio / serviços
EDU = {4}               # educação
JOB_MOTIVES = WORK | EDU
MIN_POP_SIZE = 15


def load_zone_centroids():
    """zone number -> (lng, lat, name) for zones with centroid inside bbox."""
    with open(ZONES_SHP + ".prj") as f:
        crs_src = CRS.from_wkt(f.read())
    to_wgs = Transformer.from_crs(crs_src, "EPSG:4326", always_xy=True).transform
    sf = shapefile.Reader(ZONES_SHP, encoding="latin-1")
    flds = [f[0] for f in sf.fields[1:]]
    zones = {}
    for sr in sf.iterShapeRecords():
        rec = dict(zip(flds, sr.record))
        num = int(rec["NumeroZona"])
        geo = sr.shape.__geo_interface__
        try:
            c = shp_shape(geo).centroid
            lng, lat = to_wgs(c.x, c.y)
        except Exception:
            continue
        if config.in_bbox(lng, lat):
            zones[num] = (round(lng, 5), round(lat, 5), rec.get("NomeZona") or str(num))
    return zones


def haversine_m(lng1, lat1, lng2, lat2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lng2 - lng1)
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def speed_kmh(km):
    if km < 6: return 18.0
    if km < 15: return 26.0
    if km < 30: return 38.0
    return 48.0


def main():
    zones = load_zone_centroids()
    print(f"zones in bbox: {len(zones)}")

    residents = collections.defaultdict(float)
    jobs = collections.defaultdict(float)
    seen_person = set()
    # od[(o,d)] = [sum_size, sum_dist_w, sum_dur_w]
    od = collections.defaultdict(lambda: [0.0, 0.0, 0.0])

    def as_int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    nrows = 0
    for r in DBF(OD_DBF, encoding="latin-1", raw=False):
        nrows += 1
        # person-level accumulation (once per unique person)
        pkey = (r.get("ID_DOM"), r.get("ID_FAM"), r.get("ID_PESS"))
        if pkey not in seen_person:
            seen_person.add(pkey)
            fp = r.get("FE_PESS") or 0.0
            hz = as_int(r.get("ZONA"))
            if hz in zones and fp:
                residents[hz] += fp
            wz = as_int(r.get("ZONATRA1"))
            if wz in zones and fp:
                jobs[wz] += fp
        # trip-level accumulation (home -> work/education)
        fv = r.get("FE_VIA") or 0.0
        if not fv:
            continue
        mo, md = as_int(r.get("MOTIVO_O")), as_int(r.get("MOTIVO_D"))
        if mo != HOME or md not in JOB_MOTIVES:
            continue
        o, d = as_int(r.get("ZONA_O")), as_int(r.get("ZONA_D"))
        if o is None or d is None or o == d or o not in zones or d not in zones:
            continue
        dist = r.get("DISTANCIA") or 0.0
        dur = r.get("DURACAO") or 0.0
        e = od[(o, d)]
        e[0] += fv
        e[1] += (dist or 0.0) * fv
        e[2] += (dur or 0.0) * fv

    print(f"rows: {nrows}  persons: {len(seen_person)}  od pairs: {len(od)}")

    points = []
    for z, (lng, lat, name) in sorted(zones.items()):
        points.append({
            "id": f"z{z}",
            "location": [lng, lat],
            "jobs": int(round(jobs.get(z, 0.0))),
            "residents": int(round(residents.get(z, 0.0))),
            "popIds": [],
        })
    by_id = {p["id"]: p for p in points}

    pops = []
    seq = 0
    total = 0
    for (o, d), (size_f, distw, durw) in od.items():
        size = int(round(size_f))
        if size < MIN_POP_SIZE:
            continue
        olng, olat, _ = zones[o]
        dlng, dlat, _ = zones[d]
        dist_m = distw / size_f if size_f else 0.0
        if dist_m < 100:
            dist_m = max(300.0, haversine_m(olng, olat, dlng, dlat) * 1.42)
        dur_min = durw / size_f if size_f else 0.0
        secs = int(round(dur_min * 60)) if dur_min > 0 else int(
            round(dist_m / (speed_kmh(dist_m / 1000) * 1000 / 3600)))
        seq += 1
        pid = f"p{seq:05d}"
        pops.append({
            "id": pid,
            "size": size,
            "residenceId": f"z{o}",
            "jobId": f"z{d}",
            "drivingSeconds": secs,
            "drivingDistance": int(round(dist_m)),
            # Route geometry for map://paths/<city>/<popId>. Straight line
            # residence->job by default; replace with real road routes via
            # route_paths.py (OSRM) for road-following lines.
            "drivingPath": [[olng, olat], [dlng, dlat]],
        })
        # A pop must be listed on BOTH endpoints: the residence point (Residents
        # tab) and the job point (Workers tab). The game's Workers panel reads
        # point.popIds filtered by jobId, so omitting the job side leaves every
        # employment zone's arrival/departure histogram empty.
        by_id[f"z{o}"]["popIds"].append(pid)
        by_id[f"z{d}"]["popIds"].append(pid)
        total += size

    demand = {"points": points, "pops": pops}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(demand, f, ensure_ascii=False, separators=(",", ":"))
    with gzip.open(OUT + ".gz", "wt", encoding="utf-8") as f:
        json.dump(demand, f, ensure_ascii=False, separators=(",", ":"))

    print(f"points={len(points)} pops={len(pops)} commuters={total:,}")
    print(f"residents total={int(sum(residents.values())):,} "
          f"jobs total={int(sum(jobs.values())):,}")
    print(f"  -> {OUT}.gz ({os.path.getsize(OUT + '.gz')/1e6:.2f} MB)")


if __name__ == "__main__":
    main()
