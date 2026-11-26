import csv
import io
import zipfile

from ..core.source import Source, SourceInfo

URL = "https://data.geo.admin.ch/ch.bfs.arealstatistik/arealstatistik-zeitreihe/arealstatistik-zeitreihe_2056.csv.zip"
FILE = "arealstatistik-zeitreihe_2056.csv.zip"
STEP_M = 400  # keep the hectare points on a 400 m lattice: about 65 points per 2 km hex


class BfsArealstatistik(Source):
    info = SourceInfo(
        id="bfs_arealstatistik",
        title="Land use statistics (Arealstatistik), land cover",
        publisher="Federal Statistical Office (FSO / BFS)",
        homepage="https://www.bfs.admin.ch/bfs/en/home/statistics/territory-environment/land-use-cover.html",
        license="Open use, source must be named (Source: FSO)",
        description="Land cover of every hectare of Switzerland (the most recent survey per point), read on a 400 m "
        "lattice. Each hex's cover (forest, pasture, cropland, urban, rock, glacier, ...) is its largest group.",
        used_for=["Land cover", "Glaciers", "Urban hexes"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force, expect_binary=True)

    def process(self):
        pts = []
        with zipfile.ZipFile(self.raw_dir / FILE) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
            rows = csv.reader(io.TextIOWrapper(z.open(name), encoding="utf-8-sig"), delimiter=";")
            head = next(rows)
            ie, in_ = head.index("E_COORD"), head.index("N_COORD")
            # Standard land-use nomenclature, 17 classes, newest survey first (the 2025 survey is still running,
            # so many points have it empty and fall back to 2018).
            cols = [head.index(f"AS{y}_17") for y in ("25", "18", "09", "97", "85")]
            for r in rows:
                e, n = int(r[ie]), int(r[in_])
                if e % STEP_M or n % STEP_M:
                    continue
                v = next((r[c] for c in cols if r[c] not in ("", "-1", "0")), None)
                if v is not None:
                    pts.append((e, n, int(v)))
        return {"vintage": "Arealstatistik 2013/18 and 2020/25 surveys (newest per point)", "_files": [FILE], "points": pts}
