from ..core.source import Source, SourceInfo
from ._util import xlsx_rows

URL = "https://dam-api.bfs.admin.ch/hub/api/dam/assets/36251919/master"
FILE = "gdp_canton.xlsx"


class BfsGdp(Source):
    info = SourceInfo(
        id="bfs_gdp",
        title="Gross domestic product by canton",
        publisher="Federal Statistical Office (FSO / BFS)",
        homepage="https://www.bfs.admin.ch/bfs/en/home/statistics/national-economy/national-accounts/gross-domestic-product-canton.html",
        license="Open use, source must be named (Source: FSO)",
        description="GDP per canton in million francs at current prices (newest year, provisional). BFS publishes no "
        "GDP for communes or agglomerations: a city's Gold is its cantons' GDP split by its share of the canton's jobs.",
        used_for=["Gold yield"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force, expect_binary=True)

    def process(self):
        rows = list(xlsx_rows(self.raw_dir / FILE))
        head = next(r for r in rows if r.get("A") == "Canton")
        col = max((k for k, v in head.items() if k != "A" and v), key=lambda k: (len(k), k))
        year = head[col].rstrip("p")
        start = next(i for i, r in enumerate(rows) if (r.get("A") or "").startswith("En millions"))
        cantons = [float(rows[start + 1 + k][col]) * 1e6 for k in range(26)]
        total = float(rows[start + 27][col]) * 1e6
        return {"vintage": f"BFS GDP by canton, {year} (provisional)", "_files": [FILE], "year": int(year),
                "cantons": cantons, "national": total}
