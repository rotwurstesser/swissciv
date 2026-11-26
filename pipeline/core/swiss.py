"""The Swiss map frame: LV95 (EPSG:2056) metres ⇄ map km, plus WGS84 → LV95.

Map km: origin at the top-left of the map frame, y down. LV95 is already a planar metric grid, so the map is
LV95 shifted and flipped: x = (E - E0) / 1000, y = (N0 - N) / 1000.
"""

from __future__ import annotations

E0, N0 = 2_480_000, 1_302_000  # top-left corner of the map frame (LV95 metres)
E1, N1 = 2_842_000, 1_068_000  # bottom-right corner
WIDTH_KM = (E1 - E0) / 1000
HEIGHT_KM = (N0 - N1) / 1000
MARGIN_KM = 8.0
HEX_RADIUS_KM = 2.0

# Canton order = BFS canton number (1 = ZH … 26 = JU). Names in English where English has one.
CANTONS = [
    ("ZH", "Zürich"), ("BE", "Bern"), ("LU", "Lucerne"), ("UR", "Uri"), ("SZ", "Schwyz"), ("OW", "Obwalden"),
    ("NW", "Nidwalden"), ("GL", "Glarus"), ("ZG", "Zug"), ("FR", "Fribourg"), ("SO", "Solothurn"),
    ("BS", "Basel-Stadt"), ("BL", "Basel-Landschaft"), ("SH", "Schaffhausen"), ("AR", "Appenzell Ausserrhoden"),
    ("AI", "Appenzell Innerrhoden"), ("SG", "St. Gallen"), ("GR", "Graubünden"), ("AG", "Aargau"), ("TG", "Thurgau"),
    ("TI", "Ticino"), ("VD", "Vaud"), ("VS", "Valais"), ("NE", "Neuchâtel"), ("GE", "Geneva"), ("JU", "Jura"),
]


def lv95_to_map(e: float, n: float) -> tuple[float, float]:
    return (e - E0) / 1000.0, (N0 - n) / 1000.0


def map_to_lv95(x: float, y: float) -> tuple[float, float]:
    return E0 + x * 1000.0, N0 - y * 1000.0


def wgs84_to_lv95(lon: float, lat: float) -> tuple[float, float]:
    """swisstopo's approximate formulas (about 1 m accuracy over Switzerland)."""
    phi = (lat * 3600 - 169028.66) / 10000
    lam = (lon * 3600 - 26782.5) / 10000
    e = 2600072.37 + 211455.93 * lam - 10938.51 * lam * phi - 0.36 * lam * phi**2 - 44.54 * lam**3
    n = 1200147.07 + 308807.95 * phi + 3745.25 * lam**2 + 76.63 * phi**2 - 194.56 * lam**2 * phi + 119.79 * phi**3
    return e, n


def wgs84_to_map(lon: float, lat: float) -> tuple[float, float]:
    return lv95_to_map(*wgs84_to_lv95(lon, lat))
