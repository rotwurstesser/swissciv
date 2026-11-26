"""districts.json: what each city specialises in, from STATENT jobs by NOGA division (location quotients).

LQ = (city jobs in the district's divisions ÷ city jobs) ÷ (the same Swiss ratio). Same shape as the original
US file (docs/DATA_CONTRACTS.md), with NOGA 2008 division codes where the US file had NAICS codes.
"""

from __future__ import annotations

import json

from ..core.paths import WEB_DATA
from ..core.store import load_interim, write_web

REQUIRES = ["_economy", "bfs_statent", "cities.json"]
PRODUCES = ["districts.json"]

MIN_LQ, MIN_JOBS, MIN_SHARE = 1.25, 500, 0.01
SPEC_LQ, SPEC_JOBS = 3.0, 300
BADGE_LQ, BADGE_SHARE = 6.0, 0.03
MAX_PER_CITY = 5

NOGA = {
    1: "Crop and animal production", 2: "Forestry", 3: "Fishing", 8: "Quarrying", 10: "Food products", 11: "Beverages",
    13: "Textiles", 16: "Wood products", 17: "Paper", 18: "Printing", 19: "Refined petroleum", 20: "Chemicals",
    21: "Pharmaceuticals", 22: "Rubber and plastics", 23: "Glass, cement and ceramics", 24: "Basic metals",
    25: "Metal products", 26: "Electronics, optics and watches", 27: "Electrical equipment", 28: "Machinery",
    29: "Motor vehicles", 30: "Other transport equipment", 31: "Furniture", 32: "Other manufacturing (incl. medical devices)",
    33: "Repair and installation of machinery", 35: "Electricity and gas", 36: "Water supply", 37: "Sewerage",
    38: "Waste", 41: "Building construction", 42: "Civil engineering", 43: "Specialised construction",
    45: "Motor vehicle trade", 46: "Wholesale trade", 47: "Retail trade", 49: "Land transport (incl. rail)",
    50: "Water transport", 51: "Air transport", 52: "Warehousing and transport services", 53: "Postal and courier",
    55: "Accommodation", 56: "Restaurants and bars", 58: "Publishing", 59: "Film and music", 60: "Broadcasting",
    61: "Telecommunications", 62: "Software and IT services", 63: "Information services", 64: "Banking",
    65: "Insurance", 66: "Other financial services", 68: "Real estate", 69: "Legal and accounting",
    70: "Head offices and management consulting", 71: "Architecture and engineering", 72: "Research and development",
    73: "Advertising and market research", 74: "Other professional services", 75: "Veterinary", 77: "Rental and leasing",
    78: "Employment agencies", 79: "Travel agencies", 80: "Security", 81: "Building services", 82: "Office support",
    84: "Public administration and defence", 85: "Education", 86: "Health care", 87: "Residential care",
    88: "Social work", 90: "Arts", 91: "Libraries and museums", 92: "Gambling", 93: "Sports and recreation",
    94: "Associations", 95: "Repair of goods", 96: "Personal services", 97: "Households as employers",
    99: "International organisations",
}


def _d(id, name, color, emoji, divs, sub, badge, labels, description):
    return {"id": id, "name": name, "icon": f"d-{id}", "emoji": emoji, "color": color, "naics": [str(d) for d in divs],
            "own": [], "sub": {str(k): v for k, v in sub.items()}, "badge": {"id": badge[0], "label": badge[1], "labels": {str(k): v for k, v in labels.items()}},
            "description": description, "caveat": None}


CATALOG = [
    _d("campus", "Campus", "#4a7bd0", "🎓", [62, 63, 72, 85], {72: "Research labs", 62: "Software", 85: "Schools & universities"},
       ("scientific", "Knowledge city"), {72: "Research city", 62: "Tech city", 85: "College town"}, "Research, software and education."),
    _d("commercial_hub", "Commercial hub", "#d9a62e", "🏦", [64, 65, 66], {64: "Banks", 65: "Insurance", 66: "Asset management"},
       ("commercial", "Finance city"), {64: "Banking city", 65: "Insurance city", 66: "Finance city"}, "Banking, insurance and financial services."),
    _d("industrial_zone", "Industrial zone", "#b8653a", "🏭", range(10, 34),
       {21: "Pharma", 26: "Watches & electronics", 28: "Machinery", 20: "Chemicals", 10: "Food industry", 32: "Medical devices"},
       ("industrial", "Factory town"), {21: "Pharma city", 26: "Watch town", 28: "Machine town", 20: "Chemicals town", 10: "Food town", 32: "Medtech town"},
       "Manufacturing (NOGA 10–33)."),
    _d("harbor", "Harbor", "#2f7fb8", "⚓", [50], {50: "Shipping"}, ("maritime", "Port city"), {}, "Water transport: Rhine and lake shipping."),
    _d("theater_square", "Theater square", "#b06fd8", "🎭", [59, 60, 90, 91], {90: "Arts", 91: "Museums", 59: "Film & music", 60: "Broadcasting"},
       ("cultural", "Arts city"), {60: "Media city", 91: "Museum city"}, "Arts, museums, film and broadcasting."),
    _d("entertainment_complex", "Entertainment complex", "#e0645e", "🎿", [55, 92, 93], {55: "Hotels", 93: "Sports & mountain railways", 92: "Casinos"},
       ("entertainment", "Resort town"), {55: "Resort town", 93: "Sports town", 92: "Casino town"}, "Hotels, sports facilities, ski lifts and casinos."),
    _d("aerodrome", "Aerodrome", "#6aa0c8", "✈️", [51], {51: "Airlines"}, ("aviation", "Air hub"), {}, "Air transport."),
    _d("government_plaza", "Government plaza", "#7a8aa8", "🏛️", [84], {84: "Public administration"},
       ("governmental", "Government town"), {}, "Public administration (federal, cantonal and communal) and defence."),
    _d("embassy", "Diplomatic quarter", "#3aa58a", "🌐", [99], {99: "International organisations"},
       ("international", "International city"), {99: "International city"}, "International organisations and embassies (NOGA 99)."),
    _d("aqueduct", "Aqueduct & dam", "#4fb0c6", "💧", [35, 36], {35: "Power", 36: "Water"}, ("utility", "Utility town"), {35: "Power town"},
       "Electricity, gas and water supply."),
]
RULE_TEXT = (
    f"A district appears when its share of the city's jobs is at least {MIN_LQ}× the Swiss share (location quotient) "
    f"with at least {MIN_JOBS} jobs or {MIN_SHARE:.0%} of the city's jobs, or when one of its specialities has a quotient of "
    f"{SPEC_LQ:g} or more with at least {SPEC_JOBS} jobs. Districts are ranked by jobs above the Swiss norm; up to "
    f"{MAX_PER_CITY}. The badge is the strongest district (its speciality's nickname when that has a quotient of {SPEC_LQ:g}+), "
    f"unless a district has a quotient of {BADGE_LQ:g}+ and {BADGE_SHARE:.0%}+ of the city's jobs. Jobs from BFS STATENT, at the workplace."
)


def build() -> None:
    eco = load_interim("_economy")
    ent = load_interim("bfs_statent")
    cities = json.loads((WEB_DATA / "cities.json").read_text(encoding="utf-8"))
    divs = [int(c[3:5]) for c in ent["columns"][1:]]

    def div_jobs(members):
        tot, by = 0, {}
        for m in members:
            vals = ent["communes"].get(m)
            if not vals:
                continue
            tot += vals[0] or 0
            for d, v in zip(divs, vals[1:]):
                if v:
                    by[d] = by.get(d, 0) + v
        return tot, by

    nat_tot, nat = div_jobs(list(ent["communes"]))
    nat_share = {d: v / nat_tot for d, v in nat.items()}

    out_cities = {}
    for c in cities:
        tot, by = div_jobs(c["counties"])
        if not tot:
            out_cities[c["id"]] = None
            continue

        def lq(ds):
            e = sum(by.get(d, 0) for d in ds)
            ns = sum(nat_share.get(d, 0) for d in ds)
            return e, (e / tot) / ns if ns else 0

        dists = []
        for cat in CATALOG:
            ds = [int(x) for x in cat["naics"]]
            emp, q = lq(ds)
            best_sub = None
            for s in cat["sub"]:
                se, sq = lq([int(s)])
                if se >= SPEC_JOBS and sq > 1 and (best_sub is None or sq > best_sub[1]):
                    best_sub = (s, sq, se)
            broad = q >= MIN_LQ and (emp >= MIN_JOBS or emp / tot >= MIN_SHARE)
            spec = best_sub is not None and best_sub[1] >= SPEC_LQ
            if not (broad or spec):
                continue
            strength = max(emp - emp / q if q else 0, (best_sub[2] - best_sub[2] / best_sub[1]) if best_sub else 0)
            dists.append({"id": cat["id"], "lq": round(q, 2), "emp": emp, "share": round(emp / tot, 4), "avg_pay": None,
                          "sub": best_sub[0] if best_sub else None, "sub_lq": round(best_sub[1], 2) if best_sub else None,
                          "sub_emp": best_sub[2] if best_sub else None, "sub_lower_bound": False,
                          "via": "broad" if broad else "specialty", "strength": round(strength), "suppressed": 0, "lower_bound": False})
        dists.sort(key=lambda d: -d["strength"])
        dists = dists[:MAX_PER_CITY]
        badge = None
        if dists:
            extreme = [d for d in dists if d["lq"] >= BADGE_LQ and d["share"] >= BADGE_SHARE]
            d = extreme[0] if extreme else dists[0]
            cat = next(k for k in CATALOG if k["id"] == d["id"])
            label = cat["badge"]["labels"].get(d["sub"]) if d["sub"] and (d["sub_lq"] or 0) >= SPEC_LQ else None
            label = label or cat["badge"]["label"]
            if d["id"] == "government_plaza" and c.get("capital"):
                label = "Federal city"
            q, what = (d["sub_lq"], NOGA.get(int(d["sub"]), d["sub"])) if label != cat["badge"]["label"] and d["sub"] else (d["lq"], cat["name"])
            badge = {"id": cat["badge"]["id"], "label": label, "district": d["id"], "basis": "statent",
                     "text": f"{what}: {q:.1f}× the Swiss share of jobs"}
        top = sorted(((d, v, (v / tot) / nat_share[d]) for d, v in by.items() if v >= SPEC_JOBS and nat_share.get(d)), key=lambda t: -t[2])[:8]
        out_cities[c["id"]] = {
            "emp": tot, "avg_pay": None, "counties": [len(c["counties"]), len(c["counties"])],
            "top": [{"naics": str(d), "emp": v, "lq": round(q, 2), "avg_pay": None, "oty_pct": None, "suppressed": 0, "lower_bound": False} for d, v, q in top],
            "districts": dists, "badge": badge,
        }
    write_web("districts.json", {
        "version": 1, "vintage": f"BFS STATENT {ent['year']}", "year": ent["year"], "sources": ["bfs_statent"],
        "rule": {"min_lq": MIN_LQ, "min_jobs": MIN_JOBS, "min_share": MIN_SHARE, "specialty_lq": SPEC_LQ, "specialty_jobs": SPEC_JOBS,
                 "specialty_share": 0, "max_per_city": MAX_PER_CITY, "harbor_needs_water": False, "badge_lq": BADGE_LQ,
                 "badge_share": BADGE_SHARE, "college_share": None, "text": RULE_TEXT,
                 "county_note": "Communes are not scored separately."},
        "catalog": CATALOG,
        "industries": {str(d): {"title": NOGA.get(d, f"NOGA {d}"), "us_emp": v} for d, v in nat.items()},
        "national": {"emp": nat_tot, "avg_pay": None},
        "cities": out_cities, "counties": {},
    })
    print("    badges:", [(c["name"], (out_cities[c["id"]] or {}).get("badge", {}) and out_cities[c["id"]]["badge"]["label"]) for c in cities[:16]])
