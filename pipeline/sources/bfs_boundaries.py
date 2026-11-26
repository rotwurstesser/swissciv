from ..core.geo import load_geojson
from ..core.source import Source, SourceInfo

DATE = "2026-01-01"
BASE = (
    "https://data.geo.admin.ch/ch.bfs.historisierte-administrative_grenzen_g1/"
    f"historisierte-administrative_grenzen_g1_{DATE}/historisierte-administrative_grenzen_g1_{DATE}"
)
LAYERS = ["land", "kanton", "gemeinde", "see"]


def _rings(geom):
    t, c = geom["type"], geom["coordinates"]
    polys = [c] if t == "Polygon" else c if t == "MultiPolygon" else []
    return [[(round(x), round(y)) for x, y, *_ in ring] for poly in polys for ring in poly]


class BfsBoundaries(Source):
    info = SourceInfo(
        id="bfs_boundaries",
        title=f"Generalised administrative boundaries G1 ({DATE})",
        publisher="Federal Statistical Office (FSO / BFS)",
        homepage="https://www.bfs.admin.ch/bfs/en/home/services/geostat/swiss-federal-statistics-geodata/administrative-boundaries/generalized-boundaries-local-regional-authorities.html",
        license="Open use, source must be named (Source: FSO)",
        description="Outlines of Switzerland, the 26 cantons, the communes and the large lakes, as of "
        f"{DATE}, in LV95. They decide which canton and commune owns each hex and which hexes are lakes.",
        used_for=["Cantons", "Communes", "Lakes", "Border of Switzerland"],
    )

    def fetch(self, force=False):
        for layer in LAYERS:
            self.download(f"{BASE}_{layer}_2056.geojson", f"{DATE}/{layer}.geojson", force=force)

    def process(self):
        out = {"vintage": f"BFS G1 boundaries {DATE}", "_files": [f"{DATE}/{l}.geojson" for l in LAYERS]}
        for layer in LAYERS:
            feats = load_geojson(self.raw_dir / f"{DATE}/{layer}.geojson")
            out[layer] = [{"props": f["properties"], "rings": _rings(f["geometry"])} for f in feats]
        return out
