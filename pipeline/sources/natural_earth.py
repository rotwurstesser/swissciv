from ..core.geo import geojson_lines, load_geojson
from ..core.source import Source, SourceInfo

TAG = "v5.1.2"  # pinned release: content cannot change under the same URL
BASE = f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{TAG}/geojson"
BBOX = (5.5, 45.5, 11.0, 48.2)  # lon/lat window around Switzerland
FILES = ["ne_10m_rivers_lake_centerlines", "ne_10m_rivers_europe"]


class NaturalEarth(Source):
    info = SourceInfo(
        id="natural_earth",
        title="Natural Earth 1:10m rivers (with the European supplement)",
        publisher="Natural Earth",
        homepage="https://www.naturalearthdata.com/",
        license="Public domain",
        description=f"Major rivers (Rhine, Rhône, Aare, Reuss, Inn, Ticino ...), pinned to release {TAG}. Map art, "
        "not a hydrological network.",
        used_for=["Rivers"],
    )

    def fetch(self, force=False):
        for name in FILES:
            self.download(f"{BASE}/{name}.geojson", f"{TAG}/{name}.geojson", force=force)

    def process(self):
        rivers = []
        x0, y0, x1, y1 = BBOX
        for name in FILES:
            for f in load_geojson(self.raw_dir / f"{TAG}/{name}.geojson"):
                p = f["properties"]
                for line in geojson_lines(f["geometry"]):
                    if any(x0 <= lon <= x1 and y0 <= lat <= y1 for lon, lat in line):
                        rivers.append({"name": p.get("name") or p.get("name_en") or "", "rank": p.get("scalerank") or 9,
                                       "featurecla": p.get("featurecla") or "", "line": line})
        return {"vintage": f"Natural Earth {TAG}", "_files": [f"{TAG}/{n}.geojson" for n in FILES], "rivers": rivers}
