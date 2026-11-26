"""Cities (agglomerations), cantons and the nation: population, jobs, yields, GDP, growth.

Writes cities.json, states.json (cantons) and nation.json, and the interim "_economy" (per-commune figures)
for the lens and district builders.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict

from ..core.hexgrid import HexGrid
from ..core.store import load_interim, save_interim, write_web
from ..core.swiss import CANTONS, lv95_to_map

REQUIRES = ["_world", "bfs_boundaries", "bfs_typology", "bfs_statpop", "bfs_statent", "bfs_gdp", "bfs_education"]
PRODUCES = ["_economy", "cities.json", "states.json", "nation.json"]

CAPITAL_AGGLO = 351  # Bern
MIN_TOWN_POP = 10_000
# The map art sizes city tiles and banners for US metro populations; Swiss agglomerations are about 3x smaller
# for the same role (Zürich is the country's metropolis). The browser multiplies populations by this for the art only.
POP_SCALE = 3  # a commune outside every agglomeration gets its own banner from this size

# NOGA 2008 divisions → industry keys (same keys as the original US map where they match).
INDUSTRIES = [
    ("agriculture", "Agriculture, forestry & fishing", range(1, 4)),
    ("mining", "Mining & quarrying", range(5, 10)),
    ("manufacturing", "Manufacturing", range(10, 34)),
    ("utilities", "Energy & water supply, waste", range(35, 40)),
    ("construction", "Construction", range(41, 44)),
    ("wholesale", "Wholesale trade", (45, 46)),
    ("retail", "Retail trade", (47,)),
    ("transportation", "Transport & storage", range(49, 54)),
    ("accommodation", "Hotels & restaurants", (55, 56)),
    ("information", "Information & communication", range(58, 64)),
    ("finance", "Banking & insurance", range(64, 67)),
    ("real_estate", "Real estate", (68,)),
    ("professional", "Professional, scientific & technical", range(69, 76)),
    ("admin", "Administrative & support services", range(77, 83)),
    ("public_admin", "Public administration", (84,)),
    ("education", "Education", (85,)),
    ("health", "Health & social work", range(86, 89)),
    ("arts", "Arts, entertainment & recreation", range(90, 94)),
    ("other", "Other services", range(94, 100)),
]
STATENT_NOTE = "jobs at the workplace (BFS STATENT 2024)"
YIELDS = [
    {"key": "food", "icon": "y-food", "emoji": "🌾", "label": "Food", "color": "#7fbf3f", "unit": "workers",
     "industries": ["agriculture"], "description": f"Jobs in agriculture, forestry and fishing, {STATENT_NOTE}."},
    {"key": "production", "icon": "y-production", "emoji": "⚙️", "label": "Production", "color": "#d9823b", "unit": "workers",
     "industries": ["manufacturing", "construction", "mining", "utilities"],
     "description": f"Jobs in manufacturing, construction, mining and energy, {STATENT_NOTE}."},
    {"key": "gold", "icon": "y-gold", "emoji": "💰", "label": "Gold", "color": "#f2c94c", "unit": "usd", "industries": [],
     "description": "Gross domestic product per year in Swiss francs (BFS, by canton). BFS publishes no GDP below the "
     "canton, so a city's or commune's GDP is its canton's GDP split by its share of the canton's jobs (STATENT): an "
     "estimate that assumes the same output per job everywhere in a canton."},
    {"key": "science", "icon": "y-science", "emoji": "🔬", "label": "Science", "color": "#4fa3e0", "unit": "workers",
     "industries": ["professional", "information"],
     "description": f"Jobs in professional, scientific and technical services and in information and communication, {STATENT_NOTE}."},
    {"key": "culture", "icon": "y-culture", "emoji": "🎭", "label": "Culture", "color": "#b06fd8", "unit": "workers",
     "industries": ["arts"], "description": f"Jobs in arts, entertainment and recreation, {STATENT_NOTE}."},
]


def econ(pop, jobs: dict, gdp, gdp_year, growth, growth_years) -> dict:
    y = {}
    for yd in YIELDS:
        if yd["key"] == "gold":
            y["gold"] = round(gdp) if gdp is not None else None
        else:
            y[yd["key"]] = sum(jobs.get(k) or 0 for k in yd["industries"]) if jobs else None
    return {
        "population": pop, "employed": jobs.get("_total") if jobs else None, "yields": y,
        "jobs": {k: jobs.get(k) for k, _, _ in INDUSTRIES} if jobs else None,
        "median_income": None, "median_rent": None, "home_value": None, "unemployment": None, "rent_burden": None,
        "gdp": round(gdp) if gdp is not None else None, "gdp_year": gdp_year, "gdp_estimated": None,
        "growth": growth, "growth_years": growth_years,
    }


def add_ranks(rows: list, keys: list) -> None:
    def val(r, k):
        if k == "gdp_per_capita":
            return r["gdp"] / r["population"] if r.get("gdp") and r.get("population") else None
        if k in ("population", "gdp", "growth"):
            return r.get(k)
        return (r.get("yields") or {}).get(k)

    for r in rows:
        r["ranks"] = {}
    for k in keys:
        have = sorted((r for r in rows if val(r, k) is not None), key=lambda r: (-val(r, k), -(r["population"] or 0)))
        for n, r in enumerate(have, 1):
            r["ranks"][k] = n
        for r in rows:
            r["ranks"].setdefault(k, None)


def build() -> None:
    world = load_interim("_world")
    grid = HexGrid(**world["grid"])
    owner, water = world["owner"], world["water"]
    b = load_interim("bfs_boundaries")
    typ = load_interim("bfs_typology")["communes"]
    pop_d = load_interim("bfs_statpop")
    ent = load_interim("bfs_statent")
    gdp_d = load_interim("bfs_gdp")
    year, base_year, gdp_year = pop_d["year"], pop_d["base_year"], gdp_d["year"]
    growth_years = [base_year, year]

    # --- per commune ---------------------------------------------------------------------------
    gde = {str(f["props"]["GDENR"]): f["props"] for f in b["gemeinde"] if f["props"]["KTNR"]}
    col_div = [None] + [int(c[3:5]) for c in ent["columns"][1:]]
    div_key = {d: k for k, _, ds in INDUSTRIES for d in ds}
    jobs = {}
    for nr, vals in ent["communes"].items():
        j = defaultdict(int)
        j["_total"] = vals[0] or 0
        for d, v in zip(col_div[1:], vals[1:]):
            if v and d in div_key:
                j[div_key[d]] += v
        jobs[nr] = dict(j)
    pop = {nr: (v.get("BBTOT") or 0) for nr, v in pop_d["communes"].items()}
    canton_of = {nr: p["KTNR"] - 1 for nr, p in gde.items()}
    for nr, t in typ.items():
        canton_of.setdefault(nr, (t["CantonId"] or 1) - 1)
    canton_jobs = defaultdict(int)
    for nr, j in jobs.items():
        if nr in canton_of:
            canton_jobs[canton_of[nr]] += j["_total"]
    commune_gdp = {nr: gdp_d["cantons"][canton_of[nr]] * j["_total"] / canton_jobs[canton_of[nr]]
                   for nr, j in jobs.items() if nr in canton_of and canton_jobs[canton_of[nr]]}

    # hectare populations per cell (for growth and footprints)
    cell_pop = {}
    for yr, pts in pop_d["hectares"].items():
        cp = [0] * grid.size
        for e, n, v in pts:
            c = grid.cell_at(*lv95_to_map(e + 50, n + 50))
            if c >= 0:
                cp[c] += v
        cell_pop[yr] = cp

    # --- cities: agglomerations, plus towns outside them -------------------------------------
    groups = defaultdict(list)
    for nr, t in typ.items():
        if t["AGGL2020"]:
            groups[t["AGGL2020"]].append(nr)
        elif pop.get(nr, 0) >= MIN_TOWN_POP:
            groups[int(nr)].append(nr)
    communes = world["counties"]
    cidx = {g: k for k, g in enumerate(communes)}
    samples = world["county_samples"]
    taken = {}
    cities = []
    for code, members in sorted(groups.items(), key=lambda kv: -sum(pop.get(m, 0) for m in kv[1])):
        members = [m for m in members if m in gde]
        if not members:
            continue
        p = sum(pop.get(m, 0) for m in members)
        core = max(members, key=lambda m: pop.get(m, 0))
        props = gde[core]
        x, y = lv95_to_map(props["E_CNTR"], props["N_CNTR"])
        mset = {cidx[m] for m in members if m in cidx}
        footprint = sorted(i for i in range(grid.size) if owner[i] >= 0 and sum(s in mset for s in samples[i]) >= 4)
        # banner cell: the land cell at the core commune's centre, else the nearest free land cell
        cell = grid.cell_at(x, y)
        cands = sorted((i for i in (footprint or range(grid.size)) if owner[i] >= 0),
                       key=lambda i: math.dist(grid.center(*grid.col_row(i)), (x, y)))
        if cell < 0 or owner[cell] < 0 or cell in taken:
            cell = next((i for i in cands if i not in taken), cands[0] if cands else cell)
        if cell not in footprint:
            footprint = sorted(set(footprint) | {cell})
        taken[cell] = code
        j = defaultdict(int)
        for m in members:
            for k, v in jobs.get(m, {}).items():
                j[k] += v
        g = sum(commune_gdp.get(m, 0) for m in members)
        p0 = sum(cell_pop[str(base_year)][i] for i in footprint)
        p1 = sum(cell_pop[str(year)][i] for i in footprint)
        growth = round(p1 / p0 - 1, 4) if p0 and abs(p1 / p0 - 1) < 0.25 else None
        cants = sorted({CANTONS[canton_of[m]][0] for m in members}, key=lambda a: [c[0] for c in CANTONS].index(a))
        name = props["GDENAME"]
        is_agglo = bool(typ.get(core, {}).get("AGGL2020"))
        cities.append({
            "id": str(code), "name": name,
            "full": f"Agglomeration {name}" if is_agglo else f"{name} (town outside an agglomeration)",
            "states": cants, "metro": is_agglo, "capital": code == CAPITAL_AGGLO,
            "x": round(x, 2), "y": round(y, 2), "cell": cell,
            **econ(p, dict(j), g, gdp_year, growth, growth_years),
            "gdp_estimated": ["all"],
            "counties": sorted(members, key=int), "footprint": footprint, "pop_series": None,
        })
    cities.sort(key=lambda c: -c["population"])
    keys = ["population", "gdp", "gdp_per_capita", "growth"] + [y["key"] for y in YIELDS]
    add_ranks(cities, keys)
    for c in cities:
        lp = math.log(max(c["population"], 1))
        c["peers"] = [o["id"] for o in sorted((o for o in cities if o is not c), key=lambda o: abs(math.log(max(o["population"], 1)) - lp))[:5]]
    write_web("cities.json", cities)
    print(f"    {len(cities)} cities ({sum(c['metro'] for c in cities)} agglomerations); top: {[c['name'] for c in cities[:8]]}")

    # --- cantons --------------------------------------------------------------------------------
    states = []
    for k, (abbr, name) in enumerate(CANTONS):
        members = [nr for nr, ci in canton_of.items() if ci == k and nr in gde]
        j = defaultdict(int)
        for m in members:
            for kk, v in jobs.get(m, {}).items():
                j[kk] += v
        cells = [i for i in range(grid.size) if owner[i] == k]
        p0 = sum(cell_pop[str(base_year)][i] for i in cells)
        p1 = sum(cell_pop[str(year)][i] for i in cells)
        land = None
        if cells:
            land = {key: round(sum(world["pct"][key][i] for i in cells) / len(cells) / 100, 3) for key in world["pct"]}
        label = None
        if cells:
            xs = [grid.center(*grid.col_row(i)) for i in cells]
            cx, cy = sum(p[0] for p in xs) / len(xs), sum(p[1] for p in xs) / len(xs)
            label = {"x": round(cx, 1), "y": round(cy, 1), "angle": 0, "size": round(max(3.0, min(14.0, math.sqrt(len(cells)) * 0.9)), 1)}
        states.append({
            "fips": str(k + 1), "abbr": abbr, "name": name,
            **econ(sum(pop.get(m, 0) for m in members), dict(j), gdp_d["cantons"][k], gdp_year,
                   round(p1 / p0 - 1, 4) if p0 else None, growth_years),
            "land": land, "energy": None, "label": label,
        })
    add_ranks(states, [y["key"] for y in YIELDS])
    for s in states:
        s["ranks"] = {k: v for k, v in s["ranks"].items()}
    write_web("states.json", states)

    # --- nation ---------------------------------------------------------------------------------
    jn = defaultdict(int)
    for j in jobs.values():
        for k, v in j.items():
            jn[k] += v
    tot0, tot1 = sum(cell_pop[str(base_year)]), sum(cell_pop[str(year)])
    write_web("nation.json", {
        "vintage": f"STATPOP {year}, STATENT {ent['year']}", "year": year, "gdp_vintage": f"BFS GDP by canton, {gdp_year}",
        "nation": econ(sum(pop.values()), dict(jn), gdp_d["national"], gdp_year, round(tot1 / tot0 - 1, 4), growth_years),
        "yields": YIELDS, "industries": {k: label for k, label, _ in INDUSTRIES},
        "currency": "CHF",
        "pop_scale": POP_SCALE,
    })
    save_interim("_economy", {"jobs": jobs, "pop": pop, "canton_of": canton_of, "cell_pop": cell_pop,
                              "year": year, "base_year": base_year,
                              "city_members": {c["id"]: c["counties"] for c in cities}})
