import io
import zipfile

from ..core.source import Source, SourceInfo

URL = "https://data.geo.admin.ch/ch.swisstopo.digitales-hoehenmodell_25/data.zip"
FILE = "dhm25_200.zip"
STEP = 2  # keep every 2nd cell of the 200 m grid: 400 m samples, about 60 per 2 km hex


class SwisstopoDhm(Source):
    info = SourceInfo(
        id="swisstopo_dhm",
        title="DHM25/200 digital height model",
        publisher="Federal Office of Topography swisstopo",
        homepage="https://www.swisstopo.admin.ch/en/height-model-dhm25-200m",
        license="Free use with source reference (©swisstopo), swisstopo open geodata terms",
        description="Terrain heights on a 200 m grid over Switzerland and the bordering terrain, read every 400 m. "
        "Each hex's relief (flat, hills, mountains, peaks) comes from the mean, spread and maximum of its samples.",
        used_for=["Relief (hills, mountains, peaks)", "Snow on high ranges", "Hill-shading"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force, expect_binary=True)

    def process(self):
        with zipfile.ZipFile(self.raw_dir / FILE) as z:
            name = next(n for n in z.namelist() if n.lower().endswith(".asc"))
            text = io.TextIOWrapper(z.open(name), encoding="ascii")
            head = {}
            for _ in range(6):
                k, v = text.readline().split()
                head[k.lower()] = float(v)
            ncols, nrows, size = int(head["ncols"]), int(head["nrows"]), head["cellsize"]
            nodata = head.get("nodata_value", -9999)
            # The header names the lower-left corner of the grid in LV03. LV95 = LV03 + (2,000,000, 1,000,000).
            corner = "xllcorner" in head
            x0 = head["xllcorner" if corner else "xllcenter"] + 2_000_000 + (size / 2 if corner else 0)
            y0 = head["yllcorner" if corner else "yllcenter"] + 1_000_000 + (size / 2 if corner else 0)
            # Grid rows may wrap over several text lines: read the values as one stream.
            vals = text.read().split()
            rows = []
            for r in range(0, nrows, STEP):
                line = vals[r * ncols:(r + 1) * ncols]
                rows.append([None if float(v) == nodata else round(float(v)) for v in line[::STEP]])
        # Row 0 of the file is the north edge.
        return {
            "vintage": "DHM25/200 (200 m grid, read every 400 m)",
            "_files": [FILE],
            "e0": x0,  # LV95 easting of column 0
            "n0": y0 + (nrows - 1) * size,  # LV95 northing of row 0
            "step": size * STEP,
            "rows": rows,
        }
