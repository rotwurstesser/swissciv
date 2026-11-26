"""Landmarks: the federal inventory of cultural property (KGS, A objects) and Wikidata sitelink counts."""

import io
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile

from ..core.source import Source, SourceInfo

KGS_URL = "https://data.geo.admin.ch/ch.babs.kulturgueter/kulturgueter/kulturgueter_2056.xtf.zip"
KGS_FILE = "kulturgueter_2056.xtf.zip"

# Top-level KGS object codes (catalogue "Objektcode", first digit) → map kind.
KIND = {"1": "sacred", "2": "civic", "3": "transport", "4": "fortress", "5": "residence", "6": "archaeology", "7": "other", "8": "collection"}


def _local(tag: str) -> str:
    # INTERLIS XTF tags are dotted (Model.Topic.Class), sometimes namespaced: keep the last part.
    return tag.rsplit("}", 1)[-1].rsplit(".", 1)[-1]


class KgsInventory(Source):
    info = SourceInfo(
        id="kgs_inventory",
        title="Swiss Inventory of Cultural Property of National Importance (KGS, A objects)",
        publisher="Federal Office for Civil Protection (FOCP / BABS)",
        homepage="https://www.babs.admin.ch/en/the-swiss-inventory-of-cultural-property-of-national-and-regional-importance",
        license="Open use, source must be named (Source: BABS)",
        description="Buildings, sites and collections of national importance with their official position. A city's "
        "landmarks are the inventory's buildings in its core commune, ranked by Wikidata sitelinks.",
        used_for=["City landmarks", "National wonders"],
    )

    def fetch(self, force=False):
        self.download(KGS_URL, KGS_FILE, force=force, expect_binary=True)

    def process(self):
        with zipfile.ZipFile(self.raw_dir / KGS_FILE) as z:
            xtf = next(n for n in z.namelist() if n.endswith(".xtf"))
            catname = next(n for n in z.namelist() if "Catalogue" in n and n.endswith(".xml"))
            codes = {}
            for el in ET.parse(z.open(catname)).iter():
                if _local(el.tag) == "Objektarten_Catalogue":
                    c = next((x.text for x in el.iter() if _local(x.tag) == "Objektcode"), None)
                    codes[el.get("TID")] = c or ""
            objects = []
            for _, el in ET.iterparse(z.open(xtf)):
                if _local(el.tag) != "KGS_Objekt":
                    continue
                f = {}
                refs, egids = [], []
                for x in el.iter():
                    t = _local(x.tag)
                    if t == "Reference":
                        refs.append(x.get("REF"))
                    elif t == "EGID" and x.text and x.text.strip():
                        egids.append(int(x.text))
                    elif t in ("C1", "C2", "Objekt_Nr", "Beschreibung", "Gemeinde", "Kanton", "Signatur_Typ", "KGS_Kategorie"):
                        f[t] = (x.text or "").strip()
                el.clear()
                if not f.get("C1"):
                    continue
                tops = sorted({codes.get(r, "")[:1] for r in refs if codes.get(r)})
                objects.append({
                    "nr": int(f["Objekt_Nr"]), "name": f.get("Beschreibung", ""), "commune": f.get("Gemeinde", ""),
                    "canton": f.get("Kanton", ""), "e": round(float(f["C1"])), "n": round(float(f["C2"])),
                    "area": f.get("Signatur_Typ") == "Flaechenobjekt", "kinds": [KIND[t] for t in tops if t in KIND],
                    "egid": egids,
                })
        m = re.search(r"(\d{4}\.\d\d\.\d\d)", xtf)
        return {"vintage": f"KGS inventory {m.group(1) if m else ''}".strip(), "_files": [KGS_FILE], "objects": objects}


SPARQL = """PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX wikibase: <http://wikiba.se/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?kgs ?item ?sl ?en ?de WHERE {
  ?item wdt:P381 ?kgs ; wikibase:sitelinks ?sl .
  OPTIONAL { ?item rdfs:label ?en FILTER(lang(?en) = "en") }
  OPTIONAL { ?item rdfs:label ?de FILTER(lang(?de) = "de") }
}"""


class WikidataKgs(Source):
    info = SourceInfo(
        id="wikidata_kgs",
        title="Wikidata: items with a Swiss cultural property number",
        publisher="Wikidata (Wikimedia Foundation), queried through the QLever mirror (University of Freiburg)",
        homepage="https://www.wikidata.org/wiki/Property:P381",
        license="CC0 1.0 (public domain dedication)",
        description="For each KGS number: the Wikidata item, its English label and its sitelink count (how many "
        "Wikipedia and sister-project editions have an article). Sitelinks rank the landmarks; counts drift over time.",
        used_for=["Landmark ranking", "English landmark names"],
    )
    FILE = "kgs_sitelinks.json"

    def fetch(self, force=False):
        # QLever's Wikidata mirror (University of Freiburg): the official query service rate-limits hard.
        url = "https://qlever.dev/api/wikidata?query=" + urllib.parse.quote(SPARQL)
        self.download(url, self.FILE, force=force, headers={"Accept": "application/sparql-results+json"})

    def process(self):
        data = json.loads((self.raw_dir / self.FILE).read_text(encoding="utf-8"))
        best = {}
        for b in data["results"]["bindings"]:
            try:
                kgs = int(b["kgs"]["value"])
            except ValueError:
                continue
            row = {"qid": b["item"]["value"].rsplit("/", 1)[-1], "sitelinks": int(b["sl"]["value"]),
                   "en": b.get("en", {}).get("value"), "de": b.get("de", {}).get("value")}
            if kgs not in best or row["sitelinks"] > best[kgs]["sitelinks"]:
                best[kgs] = row
        from ..core.fetch import read_manifest

        when = read_manifest(self.id).get(self.FILE, {}).get("retrieved", "")[:10]
        return {"vintage": f"Wikidata, retrieved {when}", "_files": [self.FILE], "by_kgs": {str(k): v for k, v in best.items()}}
