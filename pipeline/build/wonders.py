"""wonders.json (national landmarks on the map) and per-city landmark lists (cities.json "landmarks").

Landmarks are KGS A objects (federal inventory of cultural property of national importance), ranked by their
Wikidata sitelink count: how many Wikipedia (and sister project) editions describe them.
"""

from __future__ import annotations

from collections import Counter

from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web
from ..core.swiss import lv95_to_map

REQUIRES = ["_world", "bfs_boundaries", "kgs_inventory", "wikidata_kgs", "cities.json"]
PRODUCES = ["wonders.json", "landmarks.json"]

N_NATIONAL = 40
MAX_PER_HEX = 2
VISIBLE_KINDS = {"sacred", "civic", "transport", "fortress", "residence", "other"}  # not archaeology or collections
MOTIF = {"sacred": "spire", "civic": "rotunda", "transport": "arch", "fortress": "brickhall", "residence": "brickhall", "other": "obelisk"}
KIND_NAME = {"sacred": "Church or monastery", "civic": "Public building", "transport": "Bridge or transport site",
             "fortress": "Castle or fortification", "residence": "House, palace or castle", "other": "Monument"}
RULE_NATIONAL = (
    f"The {N_NATIONAL} buildings of the federal inventory of cultural property of national importance (KGS, A objects) "
    "with articles in the most Wikipedia and sister-project editions (Wikidata sitelinks), at most "
    f"{MAX_PER_HEX} per hex. Archaeological sites and collections are left out. Ties: lower KGS number first."
)
RULE_CITY = (
    "A city's landmarks: the KGS A objects in its communes with the most Wikidata sitelinks (5 for the 10 largest "
    "cities, 3 for the others). Archaeological sites and collections are left out; whole old towns are listed as areas."
)


def build() -> None:
    world = load_interim("_world")
    grid = HexGrid(**world["grid"])
    kgs = load_interim("kgs_inventory")
    wd = load_interim("wikidata_kgs")["by_kgs"]
    import json
    from ..core.paths import WEB_DATA

    cities = json.loads((WEB_DATA / "cities.json").read_text(encoding="utf-8"))

    objs = []
    for o in kgs["objects"]:
        kinds = [k for k in o["kinds"] if k in VISIBLE_KINDS]
        if not kinds:
            continue
        w = wd.get(str(o["nr"])) or {}
        x, y = lv95_to_map(o["e"], o["n"])
        objs.append({**o, "kind": kinds[0], "sitelinks": w.get("sitelinks", 0), "qid": w.get("qid"),
                     "name_en": w.get("en"), "x": round(x, 3), "y": round(y, 3), "cell": grid.cell_at(x, y)})
    objs.sort(key=lambda o: (-o["sitelinks"], o["nr"]))

    # national wonders
    per_hex = Counter()
    wonders = []
    seen = set()  # one Wikidata item can carry two KGS numbers (e.g. both ends of a viaduct)
    for o in objs:
        if o["area"] or o["cell"] < 0 or per_hex[o["cell"]] >= MAX_PER_HEX or (o["qid"] and o["qid"] in seen):
            continue
        seen.add(o["qid"])
        per_hex[o["cell"]] += 1
        rank = len(wonders) + 1
        name = o["name_en"] or o["name"]
        wonders.append({
            "id": f"kgs-{o['nr']}", "name": name, "short": name, "kind": "landmark", "motif": MOTIF[o["kind"]],
            "rule": "kgs_top", "rank": rank, "curated": False,
            "metrics": {"sitelinks": o["sitelinks"], "kgs": o["nr"], "type": KIND_NAME[o["kind"]], "wikidata": o["qid"]},
            "x": o["x"], "y": o["y"], "cell": o["cell"], "cells": None, "county": None, "cbsa": None,
            "state": o["canton"], "listed_as": o["name"],
        })
        if len(wonders) >= N_NATIONAL:
            break
    write_web("wonders.json", {
        "version": 1, "vintage": {"landmarks": kgs.get("vintage") or "KGS", "ranking": load_interim("wikidata_kgs").get("vintage") or "Wikidata"},
        "sources": ["kgs_inventory", "wikidata_kgs"],
        "rules": [{"id": "kgs_top", "kind": "landmark", "kinds": ["landmark"], "text": RULE_NATIONAL}],
        "national": {}, "wonders": wonders,
    })

    # landmarks per city (by commune name + canton: the KGS file names the commune, not its number)
    by_commune = {}
    b = load_interim("bfs_boundaries")
    gde = {str(f["props"]["GDENR"]): (f["props"]["GDENAME"], f["props"]["KTKZ"]) for f in b["gemeinde"]}
    key_to_nr = {(n.split(" (")[0], kt): nr for nr, (n, kt) in gde.items()}
    for o in objs:
        nr = key_to_nr.get((o["commune"], o["canton"]))
        if nr:
            by_commune.setdefault(nr, []).append(o)
    out = {}
    for rank, c in enumerate(cities):
        n = 5 if rank < 10 else 3
        pool, qids = [], set()
        for o in sorted((o for m in c["counties"] for o in by_commune.get(m, [])), key=lambda o: (-o["sitelinks"], o["nr"])):
            if not (o["qid"] and o["qid"] in qids):
                qids.add(o["qid"])
                pool.append(o)
        out[c["id"]] = [{"name": o["name_en"] or o["name"], "name_local": o["name"], "kgs": o["nr"], "sitelinks": o["sitelinks"], "type": KIND_NAME[o["kind"]],
                         "area": o["area"], "x": o["x"], "y": o["y"], "cell": o["cell"], "wikidata": o["qid"], "egid": o["egid"][:1]}
                        for o in pool[:n]]
    write_web("landmarks.json", {"version": 1, "sources": ["kgs_inventory", "wikidata_kgs"], "rule": RULE_CITY, "cities": out})
    print(f"    {len(wonders)} national wonders; landmarks for {sum(1 for v in out.values() if v)} of {len(out)} cities;"
          f" Bern: {[l['name'] for l in out.get('351', [])]}")
