"""lenses.json: hex colourings from Swiss data. Hectare data is summed per hex; commune data is spread to hexes
through each hex's 7 sample points (centre + 6), equal weight per point."""

from __future__ import annotations

import math
import re

from ..core.store import load_interim, write_web

REQUIRES = ["_world", "_economy", "bfs_typology", "bfs_education", "federal_votes"]
PRODUCES = ["lenses.json"]

HEX_AREA_KM2 = 3 * math.sqrt(3) / 2 * 2.0**2
GROUPS = [{"id": "people", "name": "People"}, {"id": "prosperity", "name": "Prosperity"},
          {"id": "knowledge", "name": "Knowledge"}, {"id": "politics", "name": "Politics"}, {"id": "land", "name": "Land"}]
LANG = [("german", "German", "#c8643b"), ("french", "French", "#4f7cc0"), ("italian", "Italian", "#2f9e95"), ("romansh", "Romansh", "#e3b23c")]
URBAN = [("urban", "Urban", "#8a5bb5"), ("intermediate", "Intermediate (peri-urban)", "#e3b23c"), ("rural", "Rural", "#6aa84f")]


def pct_domain(vals, lo=2, hi=98):
    v = sorted(x for x in vals if x is not None)
    if not v:
        return [0, 1]
    a, b = v[int(len(v) * lo / 100)], v[min(len(v) - 1, int(len(v) * hi / 100))]
    return [a, b if b > a else a + 1]


def build() -> None:
    world = load_interim("_world")
    eco = load_interim("_economy")
    typ = load_interim("bfs_typology")["communes"]
    edu = load_interim("bfs_education")["communes"]
    votes = load_interim("federal_votes")
    owner, samples, communes = world["owner"], world["county_samples"], world["counties"]
    n = len(owner)

    def spread(by_commune: dict, digits=4):
        out = []
        for i in range(n):
            if owner[i] < 0:
                out.append(None)
                continue
            vals = [by_commune.get(communes[k]) for k in samples[i] if k >= 0]
            vals = [v for v in vals if v is not None]
            out.append(round(sum(vals) / len(vals), digits) if vals else None)
        return out

    def category(by_commune: dict):
        out = []
        for i in range(n):
            if owner[i] < 0:
                out.append(None)
                continue
            vals = [by_commune.get(communes[k]) for k in samples[i] if k >= 0]
            vals = [v for v in vals if v is not None]
            out.append(max(set(vals), key=lambda v: (vals.count(v), v == vals[0])) if vals else None)
        return out

    lenses = []
    p1, p0 = eco["cell_pop"][str(eco["year"])], eco["cell_pop"][str(eco["base_year"])]
    dens = [round(p1[i] / HEX_AREA_KM2, 1) if owner[i] >= 0 else None for i in range(n)]
    lenses.append({"id": "density", "group": "people", "name": "Population", "icon": "l-people", "emoji": "👥",
                   "unit": "residents / km²", "format": "int", "scale": "log", "higher_is": "neutral",
                   "ramp": ["#1b1035", "#4b2377", "#9a3b8a", "#e0645e", "#f9b24a", "#fff3a8"], "source": "bfs_statpop",
                   "description": f"Permanent residents per km², from the STATPOP {eco['year']} hectare counts summed per hex.",
                   "values": dens, "domain": pct_domain([d for d in dens if d and d > 0.5])})
    growth = [round(p1[i] / p0[i] - 1, 4) if owner[i] >= 0 and p0[i] >= 200 else None for i in range(n)]
    lenses.append({"id": "growth", "group": "people", "name": "Growth", "icon": "l-growth", "emoji": "📈",
                   "unit": f"population change {eco['base_year']}–{eco['year']}", "format": "pct", "scale": "linear",
                   "higher_is": "neutral", "ramp": ["#3b0a1e", "#93405f", "#d9d0c0", "#7cc29a", "#2f8f83", "#0b4a4e"],
                   "source": "bfs_statpop", "note": "Hexes with fewer than 200 residents in the first year are not shown.",
                   "description": f"Change in permanent residents per hex between {eco['base_year']} and {eco['year']} (STATPOP hectare counts).",
                   "values": growth, "domain": [-0.08, 0.16]})
    lang_ids = {1: 0, 2: 1, 3: 2, 4: 3}
    lenses.append({"id": "language", "group": "people", "name": "Language", "icon": "l-language", "emoji": "🗣️",
                   "unit": "language region", "format": "category", "scale": "linear", "higher_is": "neutral",
                   "categories": [{"id": k, "name": nm, "color": c} for k, nm, c in LANG], "ramp": [c for _, _, c in LANG],
                   "domain": [0, len(LANG) - 1], "source": "bfs_typology",
                   "description": "The commune's language region (BFS 2020): the language most residents speak there.",
                   "values": category({nr: lang_ids.get(t["SPRGEB2020"]) for nr, t in typ.items()})})
    lenses.append({"id": "urbanity", "group": "people", "name": "Urban / rural", "icon": "l-urban", "emoji": "🏘️",
                   "unit": "commune type", "format": "category", "scale": "linear", "higher_is": "neutral",
                   "categories": [{"id": k, "name": nm, "color": c} for k, nm, c in URBAN], "ramp": [c for _, _, c in URBAN],
                   "domain": [0, len(URBAN) - 1], "source": "bfs_typology",
                   "description": "BFS urban/rural typology of the commune (2020): urban, intermediate or rural.",
                   "values": category({nr: (t["STALAN2020"] - 1) if t["STALAN2020"] in (1, 2, 3) else None for nr, t in typ.items()})})
    jobs_per = {}
    for nr, j in eco["jobs"].items():
        p = eco["pop"].get(nr)
        if p and p >= 100:
            jobs_per[nr] = j["_total"] / p
    jp = spread(jobs_per, 3)
    lenses.append({"id": "jobs", "group": "prosperity", "name": "Jobs", "icon": "l-jobs", "emoji": "💼",
                   "unit": "jobs per resident", "format": "float", "scale": "log", "higher_is": "neutral",
                   "ramp": ["#0b1d2e", "#164a6e", "#2a7fc1", "#7cc0e8", "#f6e27f", "#fffbe0"], "source": "bfs_statent",
                   "description": "Jobs in the commune (STATENT, at the workplace) divided by its residents (STATPOP). Above 1: a work centre people commute into.",
                   "values": jp, "domain": pct_domain(jp)})
    ed = spread({nr: (v / 100 if v is not None else None) for nr, v in edu.items()}, 3)
    lenses.append({"id": "bachelors", "group": "knowledge", "name": "Degrees", "icon": "l-degrees", "emoji": "🎓",
                   "unit": "residents 25–64 with tertiary education", "format": "pct", "scale": "linear", "higher_is": "good",
                   "ramp": ["#08203e", "#0f4c81", "#2a7fc1", "#5fa8e0", "#a6d1f2", "#eaf5ff"], "source": "bfs_education",
                   "description": "Share of residents aged 25 to 64 with a tertiary degree (university, university of applied sciences or higher vocational education), per commune.",
                   "values": ed, "domain": pct_domain(ed)})
    for k, b in enumerate(votes["ballots"]):
        title = b["title"].get("de") or ""
        m = re.search(r"«\s*(.+?)\s*»", title)
        short = m.group(1) if m else title
        yes = spread({nr: (r[0] / 100 if r[0] is not None else None) for nr, r in b["communes"].items()}, 3)
        lenses.append({"id": f"vote{k + 1}", "group": "politics", "name": f"Vote: {short[:36]}{'…' if len(short) > 36 else ''}",
                       "icon": "l-vote", "emoji": "🗳️", "unit": "yes share", "format": "pct", "scale": "linear", "higher_is": "neutral",
                       "ramp": ["#8e1b1b", "#d0583b", "#f2d6a2", "#9cc5e0", "#3d7fbf", "#173f78"], "source": "federal_votes",
                       "note": f"Nationwide: {b['yes']:.1f}% yes, {'accepted' if b['accepted'] else 'rejected'}.",
                       "description": f"{title} — yes share per commune ({b['title'].get('de', '')}).",
                       "values": yes, "domain": [0.1, 0.9]})
    turnout = spread({nr: (r[1] / 100 if r[1] is not None else None) for nr, r in votes["ballots"][0]["communes"].items()}, 3)
    lenses.append({"id": "turnout", "group": "politics", "name": "Turnout", "icon": "l-turnout", "emoji": "✉️",
                   "unit": "share of voters who voted", "format": "pct", "scale": "linear", "higher_is": "good",
                   "ramp": ["#1a0a2e", "#3f1d6b", "#6a3fa0", "#9a72c9", "#c9a9e6", "#f3e8ff"], "source": "federal_votes",
                   "description": f"Turnout per commune at the federal vote of {votes['date']}.", "values": turnout, "domain": pct_domain(turnout)})
    pct = world["pct"]
    for lid, name, emoji, keys, ramp in [
        ("forest", "Forest", "🌲", ["forest"], ["#0b1f0f", "#14401c", "#1f6b2b", "#3a9443", "#7fc07a", "#d5efcd"]),
        ("farmland", "Farmland", "🚜", ["crop", "pasture"], ["#141d05", "#2f4510", "#557019", "#84a02a", "#b8cf55", "#eef7b8"]),
        ("developed", "Built-up", "🏙️", ["developed"], ["#121218", "#2c2c3c", "#4b4b66", "#727294", "#a3a3c2", "#e2e2f0"]),
    ]:
        vals = [round(sum(pct[k][i] for k in keys) / 100, 2) if owner[i] >= 0 else None for i in range(n)]
        lenses.append({"id": lid, "group": "land", "name": name, "icon": f"l-{lid}", "emoji": emoji, "unit": "share of land",
                       "format": "pct", "scale": "linear", "higher_is": "neutral", "ramp": ramp, "source": "bfs_arealstatistik",
                       "description": f"Share of the hex's land in this use (BFS Arealstatistik).", "values": vals, "domain": pct_domain(vals)})
    write_web("lenses.json", {"vintage": f"STATPOP {eco['year']}, BFS typologies, votes {votes['date']}", "groups": GROUPS, "lenses": lenses})
