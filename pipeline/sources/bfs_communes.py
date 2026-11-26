"""BFS commune statistics: typology (agglomerations, language regions), STATPOP, STATENT, education.

Several small BFS sources in one module; each is its own Source with its own Almanac entry.
"""

import csv
import re

from ..core.source import Source, SourceInfo

DGA = "https://data.geo.admin.ch"
BFS_HOME = "https://www.bfs.admin.ch/bfs/en/home.html"
BFS_LICENSE = "Open use, source must be named (Source: FSO)"


def _read_csv(path, delimiter=";"):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=delimiter))


def _num(v):
    if v in (None, "", "NA", "...", "X", "x"):
        return None
    try:
        f = float(v)
    except ValueError:
        return None
    return int(f) if f.is_integer() else f


class BfsTypology(Source):
    info = SourceInfo(
        id="bfs_typology",
        title="Spatial divisions of the communes (Raumgliederungen)",
        publisher="Federal Statistical Office (FSO / BFS)",
        homepage="https://www.agvchapp.bfs.admin.ch/en/typologies",
        license=BFS_LICENSE,
        description="For every commune: canton, district, its 2020 agglomeration (the map's cities), language region, "
        "urban/rural type and mountain-area flag, as of 2026-01-01.",
        used_for=["Cities (agglomerations)", "Language regions lens", "Urban / rural lens"],
    )
    URL = "https://www.agvchapp.bfs.admin.ch/api/communes/levels?date=01-01-2026"
    FILE = "levels_2026-01-01.csv"

    def fetch(self, force=False):
        self.download(self.URL, self.FILE, force=force)

    def process(self):
        rows = _read_csv(self.raw_dir / self.FILE, delimiter=",")
        keep = ["Name", "CantonId", "AGGL2020", "STADTE2020", "SPRGEB2020", "MONT2019", "STALAN2020", "GDETYP2020_9"]
        return {
            "vintage": "BFS spatial divisions, communes as of 2026-01-01",
            "_files": [self.FILE],
            "communes": {r["BfsCode"]: {k: (r[k] if k == "Name" else _num(r[k])) for k in keep} for r in rows},
        }


class BfsStatpop(Source):
    info = SourceInfo(
        id="bfs_statpop",
        title="Population and households statistics (STATPOP)",
        publisher="Federal Statistical Office (FSO / BFS)",
        homepage="https://www.bfs.admin.ch/bfs/en/home/statistics/population/surveys/statpop.html",
        license=BFS_LICENSE,
        description="Permanent resident population on 31 December, per commune (with age groups) and per hectare. "
        "City and canton populations are sums of their communes; hex density uses the hectare counts. Growth "
        "compares 2020 and 2025 on the 2025 communes.",
        used_for=["Population", "Density lens", "Growth", "Age"],
    )
    YEAR, BASE_YEAR = 2025, 2020

    def _url(self, year, kind):
        return f"{DGA}/ch.bfs.statistik-bevoelkerung_haushalte/statistik-bevoelkerung_haushalte_{year}/statistik-bevoelkerung_haushalte_{year}_{kind}_2056.csv"

    def fetch(self, force=False):
        self.download(self._url(self.YEAR, "gmde"), f"{self.YEAR}_gmde.csv", force=force)
        self.download(self._url(self.YEAR, "ha"), f"{self.YEAR}_ha.csv", force=force)
        self.download(self._url(self.BASE_YEAR, "ha"), f"{self.BASE_YEAR}_ha.csv", force=force)

    def process(self):
        gm = _read_csv(self.raw_dir / f"{self.YEAR}_gmde.csv")
        cols = [c for c in gm[0] if c.startswith(("BBTOT", "BBM", "BBW", "BB1", "BB2", "HPTOT"))]
        communes = {r["GDENR"]: {c: _num(r[c]) for c in cols} for r in gm}
        hect = {}
        for year in (self.YEAR, self.BASE_YEAR):
            pts = []
            with open(self.raw_dir / f"{year}_ha.csv", encoding="utf-8-sig", newline="") as f:
                rd = csv.reader(f, delimiter=";")
                head = next(rd)
                ie, in_, it = head.index("E_KOORD"), head.index("N_KOORD"), head.index("BBTOT")
                for r in rd:
                    v = _num(r[it])
                    if v:
                        pts.append((int(r[ie]), int(r[in_]), v))
            hect[str(year)] = pts
        return {
            "vintage": f"STATPOP {self.YEAR} (31 December), hectare counts {self.BASE_YEAR} and {self.YEAR}",
            "_files": [f"{self.YEAR}_gmde.csv", f"{self.YEAR}_ha.csv", f"{self.BASE_YEAR}_ha.csv"],
            "year": self.YEAR,
            "base_year": self.BASE_YEAR,
            "communes": communes,
            "hectares": hect,
        }


class BfsStatent(Source):
    info = SourceInfo(
        id="bfs_statent",
        title="Statistics of enterprise structure (STATENT)",
        publisher="Federal Statistical Office (FSO / BFS)",
        homepage="https://www.bfs.admin.ch/bfs/en/home/statistics/industry-services/surveys/statent.html",
        license=BFS_LICENSE,
        description="Jobs per commune by economic division (NOGA 2008, 2 digits), counted where the workplace is. "
        "The yields (Food, Production, Science, Culture) and the city districts and badges are built from them.",
        used_for=["Yields", "City districts and badges", "Jobs"],
    )
    YEAR = 2024
    URL = f"{DGA}/ch.bfs.betriebszaehlungen/betriebszaehlungen_{YEAR}/betriebszaehlungen_{YEAR}_gmde_2056.csv"

    def fetch(self, force=False):
        self.download(self.URL, f"{self.YEAR}_gmde.csv", force=force)

    def process(self):
        rows = _read_csv(self.raw_dir / f"{self.YEAR}_gmde.csv")
        cols = ["B08EMPT"] + [c for c in rows[0] if re.fullmatch(r"B08\d\dEMP", c)]
        return {
            "vintage": f"STATENT {self.YEAR} (provisional where BFS says so)",
            "_files": [f"{self.YEAR}_gmde.csv"],
            "year": self.YEAR,
            "columns": cols,
            "communes": {r["GDENR"]: [_num(r[c]) for c in cols] for r in rows},
        }


class BfsEducation(Source):
    info = SourceInfo(
        id="bfs_education",
        title="Educational attainment of the population (structural survey, pooled)",
        publisher="Federal Statistical Office (FSO / BFS)",
        homepage="https://www.bfs.admin.ch/bfs/en/home/statistics/education-science/educational-attainment.html",
        license=BFS_LICENSE,
        description="Share of residents aged 25 to 64 with tertiary education (university, university of applied "
        "sciences, higher vocational education), per commune.",
        used_for=["Degrees lens"],
    )
    YEAR = 2023
    URL = f"{DGA}/ch.bfs.bildungsstand/bildungsstand_{YEAR}/bildungsstand_{YEAR}_gmde_2056.csv"

    def fetch(self, force=False):
        self.download(self.URL, f"{self.YEAR}_gmde.csv", force=force)

    def process(self):
        rows = _read_csv(self.raw_dir / f"{self.YEAR}_gmde.csv")
        key = next(k for k in rows[0] if k.upper().startswith(("GDENR", "GMDE", "GEM")))
        return {
            "vintage": f"BFS educational attainment {self.YEAR}",
            "_files": [f"{self.YEAR}_gmde.csv"],
            "communes": {r[key]: _num(r.get("TERTIARY")) for r in rows},
        }
