"""mapcanvas: draw poster-style maps from OpenStreetMap data."""

import io
import random
import time

import geopandas as gpd
import osmnx as ox
import pandas as pd
from PIL import Image, ImageDraw, ImageFont
from shapely import MultiLineString, MultiPolygon, Point

ATTRIBUTION = "\u00a9 OpenStreetMap contributors \u00b7 made with love by Auric"

PRESETS = {
    "gallery": {
        "backdrop": "#EFECE4",
        "bg": "#F5F2EB",
        "water": "#B9C6C3",
        "green": "#DFE2D2",
        "building": ["#E8E3D8", "#E1DBCF", "#EDE9DF"],
        "road": "#6E6A61",
        "casing": "#F5F2EB",
        "accent": "#201D19",
    },
    "noir": {
        "backdrop": "#0B0B0E",
        "bg": "#121217",
        "water": "#16222E",
        "green": "#141D17",
        "building": ["#24242D", "#2B2B35", "#1D1D25"],
        "road": "#EDE8DD",
        "casing": "#121217",
        "accent": "#D9A441",
    },
    "blueprint": {
        "backdrop": "#08203A",
        "bg": "#0C2C4E",
        "water": "#071B31",
        "green": "#15486C",
        "building": ["#24598B", "#2C669B", "#1E4E7C"],
        "road": "#E9F2F9",
        "casing": "#0C2C4E",
        "accent": "#E9F2F9",
    },
    "sakura": {
        "backdrop": "#F6E7EB",
        "bg": "#FBEFF2",
        "water": "#A3CBD9",
        "green": "#D3E4CE",
        "building": ["#F0CBD5", "#F6D9E0", "#EABFCB"],
        "road": "#FFFFFF",
        "casing": "#DA96A9",
        "accent": "#5D3A45",
    },
    "cobalt": {
        "backdrop": "#EDE9DF",
        "bg": "#F6F3EC",
        "water": "#2450C0",
        "green": "#C2D4AC",
        "building": ["#DFD8C9", "#D5CDBB", "#E8E2D5"],
        "road": "#191712",
        "casing": "#F6F3EC",
        "accent": "#C23B2A",
    },
    "terracotta": {
        "backdrop": "#E8DED0",
        "bg": "#F3EAD9",
        "water": "#7FA8A3",
        "green": "#CFD6B4",
        "building": ["#D98B6A", "#C87A58", "#E0997A"],
        "road": "#3A322C",
        "casing": "#F3EAD9",
        "accent": "#A23B23",
    },
}

FEATURE_TAGS = {
    "building": True,
    "natural": ["water", "wood", "grassland"],
    "water": True,
    "waterway": True,
    "leisure": [
        "park",
        "garden",
        "golf_course",
        "nature_reserve",
        "pitch",
        "playground",
    ],
    "landuse": [
        "grass",
        "meadow",
        "forest",
        "village_green",
        "recreation_ground",
        "cemetery",
        "basin",
        "reservoir",
    ],
}

ROAD_WIDTH = {
    "motorway": 7.0,
    "motorway_link": 4.5,
    "trunk": 6.0,
    "trunk_link": 4.0,
    "primary": 5.0,
    "primary_link": 3.5,
    "secondary": 4.0,
    "secondary_link": 3.0,
    "tertiary": 3.2,
    "tertiary_link": 2.6,
    "unclassified": 2.2,
    "residential": 2.2,
    "living_street": 2.0,
    "service": 1.4,
    "pedestrian": 1.8,
    "track": 1.4,
    "footway": 1.0,
    "path": 1.0,
    "cycleway": 1.2,
}
ROAD_ORDER = {
    k: i
    for i, k in enumerate(
        [
            "motorway",
            "trunk",
            "primary",
            "secondary",
            "tertiary",
            "unclassified",
            "residential",
            "living_street",
            "pedestrian",
            "service",
            "track",
            "footway",
            "path",
            "cycleway",
        ]
    )
}

GREEN_LEISURE = {
    "park",
    "garden",
    "golf_course",
    "nature_reserve",
    "pitch",
    "playground",
}
GREEN_LANDUSE = {
    "grass",
    "meadow",
    "forest",
    "village_green",
    "recreation_ground",
    "cemetery",
}
WATER_LANDUSE = {"basin", "reservoir"}


class RenderError(Exception):
    pass


class _View:
    def __init__(self, cx, cy, half, size):
        self.xmin, self.ymax = cx - half, cy + half
        self.scale = size / (2 * half)

    def pt(self, x, y):
        return ((x - self.xmin) * self.scale, (self.ymax - y) * self.scale)


def _overpass(fn, *args, **kwargs):
    for attempt in (1, 2):
        try:
            return fn(*args, **kwargs)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(5)


_cache = {}


def fetch(place, dist):
    key = (place.strip().lower(), round(dist))
    if key not in _cache:
        lat, lon = ox.geocode(place)
        feats = _overpass(ox.features_from_point, (lat, lon), FEATURE_TAGS, dist)
        graph = _overpass(ox.graph_from_point, (lat, lon), dist, network_type="drive")
        _cache[key] = (lat, lon, feats, ox.graph_to_gdfs(graph, nodes=False))
    return _cache[key]


def _font(names, size):
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size)


def _polys(geom):
    if geom is None or geom.is_empty:
        return
    yield from (geom.geoms if isinstance(geom, MultiPolygon) else [geom])


def _lines(geom):
    if geom is None or geom.is_empty:
        return
    yield from (geom.geoms if isinstance(geom, MultiLineString) else [geom])


def _draw_tracked_centered(draw, cx, y, text, font, fill, tracking, halo=None):
    widths = [draw.textlength(ch, font=font) for ch in text]
    x = cx - (sum(widths) + tracking * (len(text) - 1)) / 2
    kw = (
        {}
        if halo is None
        else {"stroke_width": max(1, font.size // 8), "stroke_fill": halo}
    )
    for ch, w in zip(text, widths):
        draw.text((x, y), ch, font=font, fill=fill, **kw)
        x += w + tracking


def _col(gdf, name):
    return gdf[name] if name in gdf else pd.Series(index=gdf.index, dtype=object)


def render_scene(
    features,
    edges,
    center,
    dist,
    style,
    size=1600,
    circle=True,
    width_scale=1.0,
    title="",
    subtitle="",
):
    # Draw at twice the final size and scale down, so edges stay smooth.
    out_size, ss = size, 2
    size = out_size * ss

    feats = ox.projection.project_gdf(features) if len(features) else None
    crs = feats.crs if feats is not None else None
    roads = ox.projection.project_gdf(edges, to_crs=crs) if len(edges) else None
    if feats is None and roads is None:
        raise RenderError("No map data found for that area.")
    if crs is None:
        crs = roads.crs

    cx, cy = (
        gpd.GeoSeries([Point(center[1], center[0])], crs="EPSG:4326")
        .to_crs(crs)
        .iloc[0]
        .coords[0]
    )
    pad = 1.03 if circle else 1.0
    view = _View(cx, cy, dist * pad, size)
    k = size / 1600

    img = Image.new("RGB", (size, size), style["bg"])
    d = ImageDraw.Draw(img)

    if feats is not None:
        poly_mask = feats.geometry.type.isin(["Polygon", "MultiPolygon"])
        natural, waterc, landuse = (
            _col(feats, "natural"),
            _col(feats, "water"),
            _col(feats, "landuse"),
        )
        leisure, building = _col(feats, "leisure"), _col(feats, "building")

        def polys(mask):
            return feats.loc[mask & poly_mask, "geometry"]

        def fill_polys(series, color):
            for geom in series:
                for p in _polys(geom):
                    pts = [view.pt(x, y) for x, y in p.exterior.coords]
                    if len(pts) >= 3:
                        d.polygon(pts, fill=color)

        fill_polys(
            polys(natural.eq("water") | waterc.notna() | landuse.isin(WATER_LANDUSE)),
            style["water"],
        )

        w = max(2.0, 3.0 * k)
        for geom in feats.loc[_col(feats, "waterway").notna() & ~poly_mask, "geometry"]:
            for ln in _lines(geom):
                pts = [view.pt(x, y) for x, y in ln.coords]
                if len(pts) >= 2:
                    d.line(pts, fill=style["water"], width=round(w), joint="curve")

        fill_polys(
            polys(
                leisure.isin(GREEN_LEISURE)
                | landuse.isin(GREEN_LANDUSE)
                | natural.isin(["wood", "grassland"])
            ),
            style["green"],
        )
        tones = style["building"]
        if isinstance(tones, str):
            tones = [tones]
        rnd = random.Random(7)
        for geom in polys(building.notna() & building.ne("no")):
            tone = rnd.choice(tones)
            for p in _polys(geom):
                pts = [view.pt(x, y) for x, y in p.exterior.coords]
                if len(pts) >= 3:
                    d.polygon(pts, fill=tone)

    if roads is not None and "highway" in roads:
        hw = roads["highway"].map(lambda v: v[0] if isinstance(v, list) else v)
        rows = sorted(zip(hw, roads.geometry), key=lambda r: ROAD_ORDER.get(r[0], 9))
        segs = []
        for kind, geom in rows:
            pts_lines = [[view.pt(x, y) for x, y in ln.coords] for ln in _lines(geom)]
            pts_lines = [p for p in pts_lines if len(p) >= 2]
            if pts_lines:
                segs.append((ROAD_WIDTH.get(kind, 1.8) * k * width_scale, pts_lines))
        for w, pts_lines in segs:
            for pts in pts_lines:
                d.line(
                    pts, fill=style["casing"], width=round(w + 2.4 * k), joint="curve"
                )
        for w, pts_lines in segs:
            for pts in pts_lines:
                d.line(pts, fill=style["road"], width=max(1, round(w)), joint="curve")

    canvas = Image.new("RGB", (size, size), style["backdrop"])
    if circle:
        r = size * 0.415
        cxp, cyp = size / 2, size * 0.44
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse([cxp - r, cyp - r, cxp + r, cyp + r], fill=255)
        canvas.paste(img, (0, 0), mask)
        d = ImageDraw.Draw(canvas)
        d.ellipse(
            [cxp - r, cyp - r, cxp + r, cyp + r],
            outline=style["accent"],
            width=max(2, round(size / 220)),
        )
        ty, sy, ay = size * 0.895, size * 0.938, size * 0.968
    else:
        canvas = img
        d = ImageDraw.Draw(canvas)
        ty, sy, ay = size * 0.86, size * 0.915, size * 0.955

    halo = None if circle else style["bg"]
    if title:
        tf = _font(["arialbd.ttf", "arial.ttf"], round(size * 0.038))
        _draw_tracked_centered(
            d, size / 2, ty, title.upper(), tf, style["accent"], size * 0.012, halo
        )
    if subtitle:
        sf = _font(["segoeui.ttf", "arial.ttf"], round(size * 0.016))
        _draw_tracked_centered(
            d, size / 2, sy, subtitle.upper(), sf, style["accent"], size * 0.004, halo
        )
    af = _font(["segoeui.ttf", "arial.ttf"], round(size * 0.014))
    _draw_tracked_centered(d, size / 2, ay, ATTRIBUTION, af, style["accent"], 0, halo)

    if ss != 1:
        canvas = canvas.resize((out_size, out_size), Image.LANCZOS)

    noise = Image.effect_noise((out_size, out_size), 96).convert("L")
    canvas = Image.blend(canvas, Image.merge("RGB", (noise, noise, noise)), 0.05)

    buf = io.BytesIO()
    canvas.save(buf, "PNG")
    return buf.getvalue()


def render(place, dist, style, size=1600, circle=True, width_scale=1.0):
    try:
        lat, lon, feats, edges = fetch(place, dist)
    except RenderError:
        raise
    except Exception as e:
        raise RenderError(f"Could not fetch data for '{place}': {e}") from e
    subtitle = f"{abs(lat):.3f}\u00b0{'N' if lat >= 0 else 'S'}  {abs(lon):.3f}\u00b0{'E' if lon >= 0 else 'W'}  \u00b7  radius {dist / 1000:g} km"
    return render_scene(
        feats,
        edges,
        (lat, lon),
        dist,
        style,
        size,
        circle,
        width_scale,
        title=place,
        subtitle=subtitle,
    )


if __name__ == "__main__":
    from test_render import synthetic_scene

    feats, edges, center, dist = synthetic_scene()
    png = render_scene(feats, edges, center, dist, PRESETS["sakura"], size=800)
    with open("sample.png", "wb") as f:
        f.write(png)
    print(f"wrote sample.png ({len(png)} bytes) - synthetic demo, no network needed")
