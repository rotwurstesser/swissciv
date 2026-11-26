"""The map itself: hex grid, cantons, communes, lakes, relief, land cover, rivers.

Also saves interim "_world" (grid + per-cell canton/commune/water/cover) so the other builders can drop their data
onto the same hexes.
"""

from __future__ import annotations

import math
from collections import Counter

from ..core.geo import Shape, ShapeIndex
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, save_interim, write_web
from ..core.swiss import CANTONS, HEIGHT_KM, HEX_RADIUS_KM, MARGIN_KM, WIDTH_KM, lv95_to_map, wgs84_to_map

REQUIRES = ["bfs_boundaries", "swisstopo_dhm", "bfs_arealstatistik", "natural_earth", "bfs_statpop"]
PRODUCES = ["_world", "world.json"]

WATER, FOREIGN = -1, -2
LAND, OCEAN, COAST, LAKE = range(4)
LAKE_ELEV = -40  # lakes have no depth data here; a fixed shallow value keeps the water art in its lake tones
SHORE_MIN_POP = 500  # residents that make a mostly-lake hex a lakeside settlement instead of water
SHORE_MIN_LAND_SAMPLES = 2  # of the 7 samples; below this the hex has no shore to put the people on

WATER_TABLE = [
    {"id": LAND, "name": "Land", "rule": "Most of the hex's 7 sample points (centre + 6) are outside the BFS G1 lakes."},
    {"id": OCEAN, "name": "Ocean", "color": "#1b4266", "rule": "Not used: Switzerland has no sea."},
    {"id": COAST, "name": "Coast", "color": "#2d6d97", "rule": "Not used."},
    {"id": LAKE, "name": "Lake", "color": "#3a80b0", "rule": f"At least 4 of the hex's 7 sample points fall in a BFS G1 lake (lakes over about 5 km², border lakes in full), unless the hex holds {SHORE_MIN_POP}+ residents and at least {SHORE_MIN_LAND_SAMPLES} land samples (a lakeside village or city)."},
]
WATER_NOTE = ("Lakes are the BFS generalised (G1) lake outlines; smaller lakes and rivers are narrower than a hex and "
              "are land. A mostly-lake hex with residents on its shore stays land, so lakeside villages show on the map.")

FLAT, HILLS, MOUNTAINS, PEAKS = range(4)
RELIEF_TABLE = [
    {"id": FLAT, "name": "Flat", "rule": "Height spread (standard deviation) inside the hex under 30 m."},
    {"id": HILLS, "name": "Hills", "rule": "Height spread ≥ 30 m."},
    {"id": MOUNTAINS, "name": "Mountains", "rule": "Height spread ≥ 110 m, or mean height ≥ 1,400 m."},
    {"id": PEAKS, "name": "Peaks", "rule": "Mean height ≥ 2,200 m, or highest point ≥ 3,000 m with a spread ≥ 200 m (high Alps)."},
]
RELIEF_NOTE = "From swisstopo DHM25/200 heights read every 400 m (about 70 samples per hex)."

URBAN_MIN_PCT = 30
# Arealstatistik standard nomenclature (17 classes) → map groups.
AS17_GROUP = {
    1: "developed", 2: "developed", 3: "developed", 4: "developed", 5: "grass", 6: "crop", 7: "crop", 8: "pasture",
    9: "alpine", 10: "forest", 11: "shrub", 12: "forest", 15: "alpine", 16: "barren", 17: "ice",
}
COVER = [
    (1, "forest_deciduous", "Deciduous forest", "#4f7a35", "Forest is the largest group and the hex's mean height is under 700 m."),
    (2, "forest_evergreen", "Conifer forest", "#2f5a3a", "Forest is the largest group and the hex's mean height is 1,100 m or more."),
    (3, "forest_mixed", "Mixed forest", "#43703f", "Forest is the largest group, mean height 700 to 1,100 m."),
    (4, "scrub", "Brush forest", "#7c8f4a", "Brush forest (Gebüschwald) is the largest group."),
    (5, "grassland", "Alpine pasture & meadow", "#a9b35a", "Alpine farmland, unproductive vegetation and parks are the largest group."),
    (6, "pasture", "Meadows & pasture", "#8fb04e", "Meadows and farm pastures are the largest group."),
    (7, "cropland", "Arable land & vineyards", "#c2b84e", "Arable land, orchards, vineyards and horticulture are the largest group."),
    (8, "wetland", "Wetland", "#4f8a6e", "Not used at this scale."),
    (9, "urban", "Settlement", "#8a8378", f"Settlement and transport areas are ≥ {URBAN_MIN_PCT}% of the hex's land, whatever else is there."),
    (10, "barren", "Rock & scree", "#bfae95", "Bare land (rock, scree, sand) is the largest group."),
    (11, "ice", "Glacier & firn", "#e8eef2", "Glaciers and perpetual snow are the largest group."),
]
COVER_NOTE = (
    "From the BFS land use statistics (Arealstatistik, newest survey per hectare point), read on a 400 m lattice. "
    "Lakes and rivers are ignored; shares are of the remaining land points. Foreign hexes have no land cover."
)
GROUP_ID = {"shrub": 4, "alpine": 5, "grass": 5, "pasture": 6, "crop": 7, "barren": 10, "ice": 11}
PCT = {"forest": ("forest",), "crop": ("crop",), "pasture": ("pasture",), "grass": ("grass", "alpine"),
       "shrub": ("shrub",), "wetland": (), "developed": ("developed",)}


def classify_relief(mean: float, std: float, top: float) -> int:
    if mean >= 2200 or (top >= 3000 and std >= 200):
        return PEAKS
    if std >= 110 or mean >= 1400:
        return MOUNTAINS
    if std >= 30:
        return HILLS
    return FLAT


def dominant_cover(counts: Counter, land: int, mean_elev: float) -> int:
    if not land:
        return 0
    if round(100 * counts["developed"] / land) >= URBAN_MIN_PCT:
        return 9
    groups = {g: n for g, n in counts.items() if g != "developed"}
    if not groups:
        return 9
    g = max(groups, key=lambda k: (groups[k], k))
    if g == "forest":
        return 1 if mean_elev < 700 else 3 if mean_elev < 1100 else 2
    return GROUP_ID[g]


def majority(values: list, centre):
    counts = Counter(values)
    top = max(counts.values())
    tied = [v for v in counts if counts[v] == top]
    return centre if centre in tied else tied[0]


def simplify(points, min_km):
    out = [points[0]]
    for p in points[1:-1]:
        if math.dist(p, out[-1]) >= min_km:
            out.append(p)
    out.append(points[-1])
    return out


def build() -> None:
    b = load_interim("bfs_boundaries")
    dhm = load_interim("swisstopo_dhm")
    areal = load_interim("bfs_arealstatistik")
    ne = load_interim("natural_earth")
    statpop = load_interim("bfs_statpop")

    grid = HexGrid.covering(WIDTH_KM, HEIGHT_KM, HEX_RADIUS_KM)
    print(f"    grid {grid.cols}×{grid.rows} = {grid.size} hexes of {HEX_RADIUS_KM:g} km")

    def shape(rings):
        return Shape([[lv95_to_map(e, n) for e, n in r] for r in rings])

    by_nr = {f["props"]["KTNR"]: f for f in b["kanton"]}
    canton_idx = ShapeIndex([shape(by_nr[k + 1]["rings"]) for k in range(len(CANTONS))], cell_km=20)
    communes = sorted(b["gemeinde"], key=lambda f: f["props"]["GDENR"])
    commune_idx = ShapeIndex([shape(c["rings"]) for c in communes], cell_km=5)
    lake_idx = ShapeIndex([shape(l["rings"]) for l in b["see"]], cell_km=10)

    r = HEX_RADIUS_KM
    offsets = [(0.0, 0.0)] + [(0.6 * r * math.cos(math.radians(60 * k - 30)), 0.6 * r * math.sin(math.radians(60 * k - 30))) for k in range(6)]
    owner = [FOREIGN] * grid.size
    water = [LAND] * grid.size
    county = [-1] * grid.size
    county_samples: list[list[int]] = [[] for _ in range(grid.size)]

    # Residents per hex before the lake mask: a lakeside village can sit in a hex whose samples are mostly lake.
    raw_cell_pop = [0] * grid.size
    for e, n, v in statpop["hectares"][str(statpop["year"])]:
        c = grid.cell_at(*lv95_to_map(e + 50, n + 50))
        if c >= 0:
            raw_cell_pop[c] += v

    reclassified = 0
    for i in range(grid.size):
        cx, cy = grid.center(*grid.col_row(i))
        kinds = []
        for dx, dy in offsets:
            x, y = cx + dx, cy + dy
            if lake_idx.locate(x, y) >= 0:
                kinds.append("lake")
            else:
                kinds.append(canton_idx.locate(x, y))  # -1 = outside Switzerland
        lake_n = kinds.count("lake")
        land = [k for k in kinds if k != "lake"]
        ch = [k for k in land if k >= 0]
        shore = (lake_n >= 4 and raw_cell_pop[i] >= SHORE_MIN_POP
                 and len(ch) >= SHORE_MIN_LAND_SAMPLES and len(ch) * 2 >= len(land))
        if lake_n >= 4 and not shore:
            water[i], owner[i] = LAKE, WATER
            continue
        if len(ch) * 2 >= len(land) and ch:
            owner[i] = majority(ch, kinds[0])
            smp = [commune_idx.locate(cx + dx, cy + dy) for dx, dy in offsets]
            county_samples[i] = smp
            same = [k for k in smp if k >= 0 and communes[k]["props"]["KTNR"] == owner[i] + 1]
            if same:
                county[i] = smp[0] if smp[0] in same else Counter(same).most_common(1)[0][0]
            if shore:
                reclassified += 1
    if reclassified:
        print(f"    shore: {reclassified} lake hexes kept as land ({SHORE_MIN_POP}+ residents, >= {SHORE_MIN_LAND_SAMPLES} land samples)")

    # --- elevation and relief --------------------------------------------------------------------
    samples: list[list[int]] = [[] for _ in range(grid.size)]
    e0, n0, step = dhm["e0"], dhm["n0"], dhm["step"]
    for ri, row in enumerate(dhm["rows"]):
        for ci, v in enumerate(row):
            if v is None:
                continue
            c = grid.cell_at(*lv95_to_map(e0 + ci * step, n0 - ri * step))
            if c >= 0:
                samples[c].append(v)
    elev, elev_max, relief = [0] * grid.size, [0] * grid.size, [FLAT] * grid.size
    for i in range(grid.size):
        s = samples[i]
        if water[i] == LAKE:
            elev[i] = LAKE_ELEV
            continue
        if not s:
            # outside the height model: borrow the neighbours' mean
            nb = [v for j in grid.neighbours(i) for v in samples[j]]
            s = nb
        if not s:
            continue
        m = sum(s) / len(s)
        sd = math.sqrt(max(0.0, sum(v * v for v in s) / len(s) - m * m))
        elev[i], elev_max[i] = round(m), max(s)
        relief[i] = classify_relief(m, sd, max(s))
    print("    relief:", dict(Counter(relief[i] for i in range(grid.size) if owner[i] >= 0)))

    # --- land cover --------------------------------------------------------------------------------
    counts = [Counter() for _ in range(grid.size)]
    for e, n, v in areal["points"]:
        g = AS17_GROUP.get(v)
        if g is None:
            continue
        c = grid.cell_at(*lv95_to_map(e, n))
        if c >= 0:
            counts[c][g] += 1
    cover = [0] * grid.size
    pct = {k: [0] * grid.size for k in PCT}
    for i in range(grid.size):
        if owner[i] < 0:
            continue
        land = sum(counts[i].values())
        cover[i] = dominant_cover(counts[i], land, elev[i])
        if land:
            for k, gs in PCT.items():
                pct[k][i] = round(100 * sum(counts[i][g] for g in gs) / land)
    print("    cover:", dict(Counter(cover[i] for i in range(grid.size) if owner[i] >= 0)))

    # --- residents per hex (STATPOP hectare counts): city tiles are sized by them --------------------
    cell_pop = [raw_cell_pop[i] if owner[i] >= 0 else 0 for i in range(grid.size)]

    # --- rivers --------------------------------------------------------------------------------------
    rivers = []
    for rv in ne["rivers"]:
        pts = [wgs84_to_map(lon, lat) for lon, lat in rv["line"]]
        pts = [p for p in pts if -5 <= p[0] <= WIDTH_KM + 5 and -5 <= p[1] <= HEIGHT_KM + 5]
        if len(pts) < 2:
            continue
        pts = simplify(pts, 0.8)
        if len(pts) >= 2:
            rivers.append({"name": rv["name"], "rank": min(int(rv["rank"]), 9), "pts": [round(v, 2) for p in pts for v in p]})

    cover_table = [{"id": 0, "key": "none", "name": "None", "rule": "Water, foreign land, or no land-cover points."}] + [
        {"id": cid, "key": key, "name": name, "color": color, "rule": rule} for cid, key, name, color, rule in COVER
    ]
    tables = {"water": WATER_TABLE, "relief": RELIEF_TABLE, "cover": cover_table,
              "notes": {"water": WATER_NOTE, "relief": RELIEF_NOTE, "cover": COVER_NOTE}}
    states_out = [{"fips": str(k + 1), "abbr": abbr, "name": name} for k, (abbr, name) in enumerate(CANTONS)]
    counties_out = [{"geoid": str(c["props"]["GDENR"]), "name": c["props"]["GDENAME"]} for c in communes]
    write_web("world.json", {
        "version": 2, "grid": grid.to_dict(), "width": WIDTH_KM, "height": HEIGHT_KM, "margin": MARGIN_KM,
        "owner": owner, "county": county, "elev": elev, "elev_max": elev_max, "water": water, "relief": relief,
        "cover": cover, "pct": pct, "pop": cell_pop, "tables": tables, "states": states_out, "counties": counties_out, "rivers": rivers,
    })
    save_interim("_world", {
        "grid": grid.to_dict(), "owner": owner, "county": county, "county_samples": county_samples,
        "states": [s["fips"] for s in states_out], "counties": [c["geoid"] for c in counties_out],
        "water": water, "cover": cover, "pct": pct, "elev": elev,
    })
