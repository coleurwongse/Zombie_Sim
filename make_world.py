"""Generates a map from Natural Earth data (data/natural_earth/*.geojson): the whole world, or a region of it.

    python make_world.py                         maps/world      whole world, half a degree per tile (720 x 324)
    python make_world.py --res 0.25 --out maps/world_hd           twice as fine (4x the tiles - slow)
    python make_world.py --region asia --res 0.25 --out maps/asia_hd
    python make_world.py --region 26,150,-11,78 --out maps/asia   lon0,lon1,lat0,lat1

Built from Natural Earth (public domain, naturalearthdata.com): land, lakes, glaciers, country borders and population
estimates, named mountain ranges / plateaus / deserts, ~7300 cities, ~900 airports, ~1000 ports.  On top of that
(world_data.py): armies, nuclear arsenals, the wars being fought, rebel-held regions, a few terrain corrections.

  terrain    deep / shallow water (the shelf next to the coast, and lakes); polar ice and big glaciers; mountain ranges
             (cores are mountains, rims highlands; old low ranges are highlands); plateaus are highlands; deserts;
             tundra north of the tree line; forest by climate zone; the rest grass.  Cities urban / suburban.
  people     each country's population spread over its land by terrain and distance to its cities, then squeezed into
             0..255 per tile the same way as the other maps; every country starts able to feed itself.
  meta.json  names, capitals, cities, ports, army strength, warheads, wars, governments of rebel-held regions; wrap
             around for a whole-world map.  airports.json: every airport flies to its nearest neighbours, hubs to
             hubs further away.
The outbreak starts at Wushan on the Three Gorges reservoir (World War Z); --outbreak lon,lat to move it.
"""
import argparse
import json
import math
import os

import numpy as np
from PIL import Image, ImageDraw

import mapio
import terrain as TR
import world_data as W
from terrain import (DEEP, SHALLOW, GRASS, FOREST, MOUNTAIN, DESERT, ICE, URBAN, SUBURBAN, HIGHLANDS, TUNDRA, WETLAND,
                     RAINFOREST)

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "natural_earth")
REGIONS = {"world": (-180.0, 180.0, -78.0, 84.0),
           "asia": (26.0, 150.0, -11.0, 78.0), "europe": (-25.0, 45.0, 34.0, 72.0),
           "americas": (-170.0, -30.0, -56.0, 75.0), "africa": (-20.0, 55.0, -36.0, 38.0)}
PATIENT_ZERO = (109.9, 31.0)


def load(name):
    with open(os.path.join(DATA, name + ".geojson"), encoding="utf-8") as f:
        return json.load(f)["features"]


def rings(geom):
    """Yields (exterior, [holes]) for a Polygon / MultiPolygon geometry."""
    if geom is None:
        return
    if geom["type"] == "Polygon":
        polys = [geom["coordinates"]]
    elif geom["type"] == "MultiPolygon":
        polys = geom["coordinates"]
    else:
        return
    for p in polys:
        yield p[0], p[1:]


class Grid:
    def __init__(self, lon0, lon1, lat0, lat1, res, ss):
        self.lon0, self.lon1, self.lat0, self.lat1, self.res, self.ss = lon0, lon1, lat0, lat1, res, ss
        self.cols = int(round((lon1 - lon0) / res))
        self.rows = int(round((lat1 - lat0) / res))
        self.lon = lon0 + (np.arange(self.cols) + 0.5) * res
        self.lat = lat1 - (np.arange(self.rows) + 0.5) * res
        self.LON, self.LAT = np.meshgrid(self.lon, self.lat)
        self.wrap = (lon1 - lon0) >= 359.9
        km = res * 111.32
        self.area = km * km * np.cos(np.radians(self.LAT))           # km2 per tile
        self.tile_km = km

    def rc(self, lon, lat):
        r = int((self.lat1 - lat) / self.res)
        c = int((lon - self.lon0) / self.res)
        return r, c

    def inside(self, lon, lat):
        return self.lon0 <= lon < self.lon1 and self.lat0 < lat <= self.lat1

    def _px(self, ring, ss):
        return [((x - self.lon0) / self.res * ss, (self.lat1 - y) / self.res * ss) for x, y in ring]

    def canvas(self, ss=None, mode="L"):
        ss = ss or self.ss
        img = Image.new(mode, (self.cols * ss, self.rows * ss), 0)
        return img, ImageDraw.Draw(img), ss

    def down(self, img, ss, thresh=0.5):
        a = np.asarray(img, dtype=np.float32).reshape(self.rows, ss, self.cols, ss).mean(axis=(1, 3))
        return a > 255 * thresh

    def fill(self, geoms, thresh=0.5):
        """Rasterize Polygon / MultiPolygon geometries (holes respected) into a coverage mask."""
        img, d, ss = self.canvas()
        for g in geoms:
            for ext, holes in rings(g):
                d.polygon(self._px(ext, ss), fill=255)
                for h in holes:
                    d.polygon(self._px(h, ss), fill=0)
        return self.down(img, ss, thresh)

    def poly(self, pts, thresh=0.5):
        return self.fill([{"type": "Polygon", "coordinates": [pts]}], thresh)


def shift(a, dr, dc, wrap, fill=0):
    import engine
    return engine.shift(a, dr, dc, wrap, fill)


def dilate(mask, n, wrap):
    out = mask.copy()
    for _ in range(n):
        m = out.copy()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            m |= shift(out, dr, dc, wrap, False)
        out = m
    return out


def erode(mask, n, wrap):
    return ~dilate(~mask, n, wrap)


def blur(a, sigma_tiles, wrap):
    """Gaussian blur (separable, numpy only)."""
    r = max(1, int(3 * sigma_tiles))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / max(sigma_tiles, 1e-6)) ** 2)
    k /= k.sum()
    out = np.zeros_like(a, dtype=np.float64)
    for i, w in enumerate(k):
        out += w * shift(a, 0, i - r, wrap, 0.0)
    out2 = np.zeros_like(out)
    for i, w in enumerate(k):
        out2 += w * shift(out, i - r, 0, False, 0.0)
    return out2


def fbm(rng, rows, cols, cells=(8, 16, 32, 64), weights=(1.0, 0.6, 0.35, 0.2)):
    out = np.zeros((rows, cols))
    for c, w in zip(cells, weights):
        ny, nx = max(2, int(c * rows / cols)), c
        g = rng.random((ny + 1, nx + 1))
        ys, xs = np.linspace(0, ny, rows), np.linspace(0, nx, cols)
        y0, x0 = np.minimum(ys.astype(int), ny - 1), np.minimum(xs.astype(int), nx - 1)
        fy, fx = ys - y0, xs - x0
        fy, fx = (fy * fy * (3 - 2 * fy))[:, None], (fx * fx * (3 - 2 * fx))[None, :]
        a, b = g[y0][:, x0], g[y0][:, x0 + 1]
        cc, d = g[y0 + 1][:, x0], g[y0 + 1][:, x0 + 1]
        out += w * (a * (1 - fy) * (1 - fx) + b * (1 - fy) * fx + cc * fy * (1 - fx) + d * fy * fx)
    out /= sum(weights)
    return (out - out.min()) / (out.max() - out.min() + 1e-12)


# ------------------------------------------------------------------------------------------------------- terrain
def tree_line(lon, lat):
    """Latitude north of which it's tundra (by longitude: Eurasia, North America) - a smooth curve, not steps."""
    eurasia = np.interp(lon, [-30, 20, 45, 70, 90, 110, 140, 180], [69.0, 69.5, 68.0, 67.0, 69.0, 70.0, 70.5, 69.0])
    namer = np.interp(lon, [-180, -160, -140, -120, -100, -88, -75, -60, -30],
                      [67.0, 67.5, 67.5, 66.5, 63.0, 59.0, 58.5, 58.0, 58.0])
    return np.where((lon < -30) | (lon > 180), namer, eurasia)


def forest_share(lon, lat):
    f = np.full(lon.shape, 0.12)
    alat = np.abs(lat)
    f = np.where(alat < 10, 0.7, f)                                            # equatorial rain forest
    f = np.where((alat >= 10) & (alat < 23), 0.35, f)                         # monsoon / savanna woodland
    f = np.where((lat >= 50) & (lat < 70), 0.75, f)                           # boreal (both continents)
    f = np.where((lat >= 45) & (lat < 56) & (lon > -12) & (lon < 45), 0.3, f)  # European farmland & woods
    f = np.where((lat >= 30) & (lat < 47) & (lon > -95) & (lon < -66), 0.45, f)   # eastern North America
    f = np.where((lat >= 38) & (lat < 60) & (lon > -130) & (lon < -119), 0.75, f)  # Pacific north-west
    f = np.where((lat >= 22) & (lat < 30) & (lon > 104) & (lon < 121), 0.5, f)  # south China hills
    f = np.where((lat >= 31) & (lat < 46) & (lon > 127) & (lon < 146), 0.6, f)  # Korea, Japan
    f = np.where((lat >= 42) & (lat < 50) & (lon > 125) & (lon < 145), 0.65, f)  # Manchuria, Russian Far East
    f = np.where((lat > -32) & (lat < -12) & (lon > -55) & (lon < -34), 0.4, f)  # Atlantic forest
    f = np.where((lat > -40) & (lat < -15) & (lon > 145) & (lon < 154), 0.4, f)  # eastern Australia
    f = np.where((lat > -47) & (lat < -34) & (lon > 166) & (lon < 179), 0.45, f)  # New Zealand
    f = np.where((lat > -55) & (lat < -38) & (lon > -76) & (lon < -71), 0.6, f)  # southern Chile
    return f


def warp(G, mask, amp_deg, seed):
    """A hand-drawn area made natural: its outline is pushed in and out by smooth noise (up to amp_deg degrees)."""
    rng = np.random.default_rng(seed)
    amp = amp_deg / G.res

    def push():                                   # (spread over the full -amp..amp, not bunched near 0)
        f = fbm(rng, G.rows, G.cols, cells=(24, 48, 96, 192))
        return np.clip((f - f.mean()) / (2.0 * f.std() + 1e-12), -1.0, 1.0) * amp
    dy, dx = push(), push()
    rr = np.clip(np.rint(np.arange(G.rows)[:, None] + dy), 0, G.rows - 1).astype(int)
    cc = np.rint(np.arange(G.cols)[None, :] + dx).astype(int)
    cc = cc % G.cols if G.wrap else np.clip(cc, 0, G.cols - 1)
    return mask[rr, cc]


def _uniform(field):
    """A noise field remapped so its values are spread evenly over 0..1 (by rank)."""
    out = np.empty(field.size)
    out[np.argsort(field, axis=None)] = np.linspace(0.0, 1.0, field.size)
    return out.reshape(field.shape)


def soft(G, mask, deg, seed):
    """An area with a natural edge: pushed about by noise, then blended over about `deg` degrees with a patchy
    fringe (bits of it scattered just outside, gaps just inside) - no hard or straight edges."""
    rng = np.random.default_rng(seed)
    b = blur(warp(G, mask, deg, seed).astype(np.float64), 0.5 * deg / G.res, G.wrap)
    n = _uniform(fbm(rng, G.rows, G.cols, cells=(32, 64, 128, 256, 512), weights=(0.6, 0.8, 1.0, 1.0, 0.6)))
    return b > 0.1 + 0.8 * n


def _line(G, pts, width):
    img, d, ss = G.canvas()
    w = max(1, int(width / G.res * ss))
    p = G._px(pts, ss)
    d.line(p, fill=255, width=w)
    for x, y in p:
        d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=255)
    return G.down(img, ss)


def build_terrain(G, land, rng):
    T = np.where(land, GRASS, DEEP).astype(np.int32)
    feats = load("ne_50m_geography_regions_polys")
    noise = fbm(rng, G.rows, G.cols, cells=(16, 32, 64, 128))
    wob = (fbm(rng, G.rows, G.cols, cells=(8, 16, 32), weights=(1.0, 0.6, 0.4)) - 0.5) * 7.0
    wob2 = (fbm(rng, G.rows, G.cols, cells=(8, 16, 32), weights=(1.0, 0.6, 0.4)) - 0.5) * 7.0
    f = forest_share(G.LON + wob2, G.LAT + wob)
    for ft in feats:
        p = ft["properties"]
        if p["FEATURECLA"] in ("Basin", "Foothills") and p["NAME"] in ("CONGO BASIN", "AMAZON BASIN", "SELVAS"):
            f = np.where(warp(G, G.fill([ft["geometry"]]), 1.5, 600), 0.85, f)
    f = blur(f, 2.5 / G.res, G.wrap)                    # (woods thin out gradually: no straight forest edges)
    woods = _uniform(fbm(rng, G.rows, G.cols, cells=(24, 48, 96, 192, 384), weights=(0.5, 0.8, 1.0, 0.8, 0.5)))
    T[land & (woods < f)] = FOREST                      # (f is the share of the ground that's wooded, in patches)
    deserts = [ft["geometry"] for ft in feats if ft["properties"]["FEATURECLA"] == "Desert"
               and ft["properties"]["NAME"] not in W.NOT_DESERT]
    desert = np.zeros(land.shape, bool)
    for i, geom in enumerate(deserts):                    # (the bigger the desert, the wider its fringe)
        area = G.fill([geom])
        if area.any():
            desert |= soft(G, area, float(np.clip(np.sqrt(area.sum()) * G.res / 5.0, 1.5, 4.0)), 610 + i)
    for i, pts in enumerate(W.EXTRA_DESERTS.values()):
        desert |= warp(G, G.poly(pts), 1.2, 300 + i)
    T[land & desert] = DESERT
    for ft in feats:                                                      # river deltas and the Nile stay green
        if ft["properties"]["FEATURECLA"] == "Delta":
            T[land & G.fill([ft["geometry"]], 0.3)] = GRASS
    nile = G.poly([(30.8, 31.5), (32.4, 31.4), (31.6, 30.0), (31.4, 27.5), (32.9, 25.2), (33.1, 23.8), (32.6, 23.8),
                   (32.4, 25.0), (31.0, 27.4), (31.0, 30.0)], 0.3)
    T[land & nile] = GRASS
    patchy = _uniform(fbm(rng, G.rows, G.cols, cells=(16, 32, 64, 128)))
    for ft in feats:
        p = ft["properties"]
        if p["FEATURECLA"] == "Plateau" and p["NAME"] not in ("Polar Plateau",):
            area = G.fill([ft["geometry"]])
            deg = float(np.clip(np.sqrt(area.sum()) * G.res / 4.0, 1.5, 6.0))    # (big plateaus: wider fringes)
            m = land & soft(G, area, deg, 620) & (patchy < 0.72)
            T[m & (T != DESERT)] = HIGHLANDS
    for ft in feats:
        p = ft["properties"]
        if p["FEATURECLA"] != "Range/mtn":
            continue
        m = land & warp(G, G.fill([ft["geometry"]], 0.35), 0.5, 630)
        if not m.any():
            continue
        if p["NAME"] in W.LOW_RANGES:
            T[m] = HIGHLANDS
            continue
        core = erode(m, 1, G.wrap)
        if core.sum() < 0.15 * m.sum():
            core = m
        T[m] = HIGHLANDS
        T[core] = MOUNTAIN
    for pts, width in W.MOUNTAINS:                          # ranges Natural Earth doesn't outline (Korea, Japan...)
        if not any(G.inside(lon, lat) for lon, lat in pts):
            continue
        rim = land & _line(G, pts, width * 1.2)
        core = land & _line(G, pts, width * 0.5)
        T[rim & (T != MOUNTAIN) & (T != DESERT)] = HIGHLANDS
        T[core] = MOUNTAIN
    tibet = G.poly([(78.5, 35.5), (88.0, 36.0), (94.0, 35.6), (100.0, 33.5), (101.5, 32.0), (98.5, 29.0),
                    (92.5, 29.2), (84.5, 30.0), (79.5, 32.0)])
    T[land & tibet & (noise < 0.55) & (T != DESERT)] = MOUNTAIN
    T[land & tibet & (T == GRASS)] = HIGHLANDS
    # rainforest: forest in the humid tropics
    humid = (np.abs(G.LAT + 0.3 * wob) < 10) & ~((G.LON + wob2 > 33) & (G.LON - wob2 < 52))
    for ft in feats:
        if ft["properties"]["NAME"] in ("CONGO BASIN", "AMAZON BASIN", "SELVAS"):
            humid |= G.fill([ft["geometry"]])
    for area in W.RAINFOREST.values():
        if len(area) == 4 and not isinstance(area[0], tuple):
            lo0, lo1, la0, la1 = area
            x, y = G.LON + 0.5 * wob, G.LAT + 0.5 * wob
            humid |= (x > lo0) & (x < lo1) & (y > la0) & (y < la1)
        else:
            humid |= warp(G, G.poly(area), 0.8, 400 + len(area))
    humid = soft(G, humid, 2.5, 450)                      # (no straight edges)
    T[land & humid & (T == FOREST)] = RAINFOREST
    # the tree line: a wavering band a few degrees wide where forest and tundra are patchily mixed
    tl = tree_line(G.LON, G.LAT) + 5.0 * (_uniform(fbm(rng, G.rows, G.cols, cells=(6, 12, 24, 48))) - 0.5)
    mix = np.clip((G.LAT - tl + 3.0) / 6.0, 0.0, 1.0)
    speckle = _uniform(fbm(rng, G.rows, G.cols, cells=(64, 128, 256, 512), weights=(0.5, 1.0, 1.0, 0.7)))
    T[land & (speckle < mix) & (T != MOUNTAIN)] = TUNDRA
    # wetlands: marshes, swamps and bogs (a share of each area, patchy)
    wet_noise = fbm(rng, G.rows, G.cols, cells=(24, 48, 96, 192))
    soft_ = land & ~np.isin(T, (MOUNTAIN, DESERT, ICE, TUNDRA))
    for ft in feats:
        share = W.WETLAND_REGIONS.get(ft["properties"]["NAME"])
        if share:
            T[soft_ & soft(G, G.fill([ft["geometry"]], 0.3), 2.0, 640) & (wet_noise < share)] = WETLAND
    for i, (pts, share) in enumerate(W.WETLANDS.values()):
        T[soft_ & soft(G, G.poly(pts, 0.3), 1.0, 500 + i) & (wet_noise < share)] = WETLAND
    T[land & soft(G, G.LAT < -52, 1.5, 660) & (T != MOUNTAIN)] = TUNDRA
    glac = load("ne_50m_glaciated_areas")
    ice = G.fill([g["geometry"] for g in glac], 0.5) & land & (np.abs(G.LAT) > 55)
    T[ice] = ICE
    T[land & (G.LAT < -60)] = ICE                                         # Antarctica
    # water: the shelf next to the coast and lakes are shallow, the rest deep
    lakes = G.fill([ft["geometry"] for ft in load("ne_50m_lakes") if ft["properties"].get("scalerank", 9) <= 5], 0.5)
    shelf = ~land & dilate(land, max(1, int(round(0.5 / G.res))), G.wrap)
    T[shelf] = SHALLOW
    T[lakes] = SHALLOW
    return T


# ------------------------------------------------------------------------------------------------------- countries
def build_countries(G, land, T):
    feats = load("ne_50m_admin_0_countries")
    img, d, _ = G.canvas(ss=1, mode="I")
    units = []
    for ft in feats:
        p = ft["properties"]
        name = W.NAME_FIX.get(p["NAME"], p["NAME"])
        if name == "Antarctica":
            continue
        units.append(dict(name=name, sov=W.NAME_FIX.get(p["SOVEREIGNT"], p["SOVEREIGNT"]), pop=float(p["POP_EST"] or 0),
                          geom=ft["geometry"], admin=p["ADMIN"]))
    units.sort(key=lambda u: -u["pop"])
    for k, u in enumerate(units, start=1):
        for ext, holes in rings(u["geom"]):
            d.polygon(G._px(ext, 1), fill=k)
            for h in holes:
                d.polygon(G._px(h, 1), fill=0)
    O = np.asarray(img, dtype=np.int32).copy()
    # small islands the 1x raster missed: supersample just those
    miss = land & (O == 0)
    if miss.any():
        for k, u in enumerate(units, start=1):
            m = G.fill([u["geom"]], 0.15) & miss
            O[m] = k
            miss &= ~m
    O[~land] = 0
    O[land & (G.LAT < -60)] = 0
    # land still unclaimed goes to the nearest country
    for _ in range(6):
        todo = land & (O == 0) & (G.LAT > -60)
        if not todo.any():
            break
        grow = O.copy()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            sh = shift(O, dr, dc, G.wrap, 0)
            grow = np.where((grow == 0) & (sh > 0), sh, grow)
        O = np.where(todo, grow, O)
    # tiny dependencies join their sovereign; empty units vanish; ids renumbered 1..n
    counts = np.bincount(O.ravel(), minlength=len(units) + 1)
    by_name = {u["name"]: k for k, u in enumerate(units, start=1)}
    for k, u in enumerate(units, start=1):
        if (counts[k] and u["sov"] != u["name"] and u["sov"] in by_name and (counts[k] < 25 or u["pop"] < 2e5)
                and u["name"] not in W.KEEP_SEPARATE):
            O[O == k] = by_name[u["sov"]]
    counts = np.bincount(O.ravel(), minlength=len(units) + 1)
    keep = [k for k in range(1, len(units) + 1) if counts[k] > 0]
    remap = np.zeros(len(units) + 1, dtype=np.int32)
    names, pops = [], []
    for new, k in enumerate(keep, start=1):
        remap[k] = new
        names.append(units[k - 1]["name"])
        pops.append(units[k - 1]["pop"])
    O = remap[O]
    if len(names) > 250:
        raise SystemExit("too many countries for the 8-bit owner layer")
    return O, names, pops


# ------------------------------------------------------------------------------------------------------- people
def build_cities(G, land, T, O, min_pop):
    feats = load("ne_10m_populated_places_simple")
    cities = []
    for ft in feats:
        p = ft["properties"]
        lon, lat, pop = p["longitude"], p["latitude"], (p["pop_max"] or 0) / 1e6
        if pop < min_pop or not G.inside(lon, lat):
            continue
        r, c = G.rc(lon, lat)
        if not (0 <= r < G.rows and 0 <= c < G.cols):
            continue
        if not land[r, c]:
            best = None
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    r2, c2 = r + dr, (c + dc) % G.cols if G.wrap else c + dc
                    if 0 <= r2 < G.rows and 0 <= c2 < G.cols and land[r2, c2]:
                        k = dr * dr + dc * dc
                        if best is None or k < best[0]:
                            best = (k, r2, c2)
            if best is None:
                continue
            r, c = best[1], best[2]
        cities.append(dict(name=p["name"], row=int(r), col=int(c), pop=round(pop, 3), lon=lon, lat=lat,
                           capital=bool(p.get("adm0cap")), country=p.get("adm0name")))
    cities.sort(key=lambda c: -c["pop"])
    return cities


def rural_people(G, T, O, cities, pops, rng):
    n = len(pops)
    hab = TR.DENSITY[T] * (O > 0)
    grav = np.zeros(T.shape)
    for ct in cities:
        grav[ct["row"], ct["col"]] += ct["pop"]
    grav = blur(grav, 150.0 / G.tile_km, G.wrap)
    grav /= max(grav.max(), 1e-9)
    w = hab * (0.15 + np.sqrt(grav) * 3.0) * (0.6 + 0.8 * fbm(rng, G.rows, G.cols, cells=(24, 48, 96)))
    city_pop = np.zeros(n + 1)
    for ct in cities:
        city_pop[O[ct["row"], ct["col"]]] += ct["pop"] * 1e6
    d = np.zeros(T.shape)
    wa = w * G.area
    tot = np.bincount(O.ravel(), weights=wa.ravel(), minlength=n + 1)
    for k in range(1, n + 1):
        rural = max(pops[k - 1] - city_pop[k], 0.25 * pops[k - 1])
        if tot[k] > 0:
            m = O == k
            d[m] = rural * w[m] / tot[k]
    d *= (0.5 / G.res) ** 2                   # per tile at half a degree: finer maps keep the same density per tile
    return np.rint(150.0 * (d / (d + 250.0)) ** 0.55).astype(np.int32)


def place_city_tiles(G, H, T, D, land, cities):
    rr, cc = np.indices(H.shape)
    for ct in cities:
        r, c, pop = ct["row"], ct["col"], ct["pop"]
        core_r = max(0.3, 7.0 * math.sqrt(pop) / G.tile_km)
        sub_r = core_r * 2.3 + 0.4
        if pop < 0.3:
            if T[r, c] not in (MOUNTAIN, ICE):
                T[r, c] = SUBURBAN
            H[r, c] = max(H[r, c], int(80 + 150 * pop))
            continue
        r0, r1 = max(0, int(r - sub_r - 1)), min(G.rows, int(r + sub_r + 2))
        c0, c1 = int(c - sub_r - 1), int(c + sub_r + 2)
        cols = np.arange(c0, c1) % G.cols if G.wrap else np.arange(max(c0, 0), min(c1, G.cols))
        sub_rr, sub_cc = np.meshgrid(np.arange(r0, r1), cols, indexing="ij")
        dist = np.hypot(sub_rr - r, np.where(G.wrap, ((sub_cc - c + G.cols // 2) % G.cols) - G.cols // 2, sub_cc - c))
        lp = math.log10(pop)
        okl = land[sub_rr, sub_cc]
        sub = okl & (dist <= sub_r) & ~np.isin(T[sub_rr, sub_cc], (MOUNTAIN, ICE, URBAN))
        core = okl & (dist <= core_r)
        T[sub_rr[sub], sub_cc[sub]] = SUBURBAN
        H[sub_rr[sub], sub_cc[sub]] = np.maximum(H[sub_rr[sub], sub_cc[sub]],
                                                 np.clip(115 + 25 * lp - 12 * dist[sub], 60, 200).astype(np.int32))
        T[sub_rr[core], sub_cc[core]] = URBAN
        T[r, c] = URBAN
        H[sub_rr[core], sub_cc[core]] = np.maximum(H[sub_rr[core], sub_cc[core]],
                                                   np.clip(205 + 25 * lp - 10 * dist[core], 160, 255).astype(np.int32))
        H[r, c] = max(H[r, c], int(np.clip(205 + 25 * lp, 160, 255)))
        D[sub_rr[core], sub_cc[core]] = np.maximum(D[sub_rr[core], sub_cc[core]], 3)


def balance_food(H, T, O, n):
    import economy
    for _ in range(10):
        changed = False
        h = H.astype(float)
        prod = np.bincount(O.ravel(), weights=(TR.FOOD_YIELD[T] * np.minimum(h, 40) / 40 * (h > economy.MIN_POP)).ravel(),
                           minlength=n + 1)
        use = np.bincount(O.ravel(), weights=h.ravel(), minlength=n + 1) * economy.FOOD_PER_PERSON
        for k in range(1, n + 1):
            if use[k] > 0 and prod[k] < 1.05 * use[k]:
                s = max(0.5, prod[k] / (1.08 * use[k]))
                m = (O == k) & (H > 41)
                H[m] = np.maximum(np.rint(H[m] * s), 41).astype(np.int32)
                changed = True
        if not changed:
            break


# ------------------------------------------------------------------------------------------------------- airports, ports
def great_km(a, b):
    lo1, la1, lo2, la2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    x = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(min(1.0, math.sqrt(x)))


def nearest_land(G, land, lon, lat, reach=2):
    r, c = G.rc(lon, lat)
    best = None
    for dr in range(-reach, reach + 1):
        for dc in range(-reach, reach + 1):
            r2, c2 = r + dr, c + dc
            if G.wrap:
                c2 %= G.cols
            if 0 <= r2 < G.rows and 0 <= c2 < G.cols and land[r2, c2]:
                k = dr * dr + dc * dc
                if best is None or k < best[0]:
                    best = (k, r2, c2)
    return None if best is None else (best[1], best[2])


def continent(lon, lat):
    """Rough continent of a point (for intercontinental air routes)."""
    if lon < -30:
        return "north america" if lat > 12 else "south america"
    if lon > 110 and lat < -10:
        return "oceania"
    if lon < 60 and lat < 35 and not (lon > 34 and lat > 12):
        return "africa"
    if lon < 45 and lat >= 35:
        return "europe"
    return "asia"


def build_airports(G, land, near=3, hub_near=6, hub_far=3, per_continent=2):
    aps = []
    for ft in load("ne_10m_airports"):
        p = ft["properties"]
        typ = (p.get("type") or "").lower()
        if typ.strip() == "military" or ft["geometry"]["type"] != "Point":
            continue
        lon, lat = ft["geometry"]["coordinates"][:2]
        if not G.inside(lon, lat):
            continue
        rc = nearest_land(G, land, lon, lat)
        if rc is None:
            continue
        hub = "major" in typ or (p.get("scalerank") or 9) <= 4
        aps.append(dict(lon=lon, lat=lat, rc=rc, hub=hub, name=p.get("name")))
    links = {}

    def link(a, b):
        if a["rc"] == b["rc"]:
            return
        links.setdefault(a["rc"], set()).add(b["rc"])
        links.setdefault(b["rc"], set()).add(a["rc"])

    for a in aps:
        ds = sorted((great_km((a["lon"], a["lat"]), (b["lon"], b["lat"])), i) for i, b in enumerate(aps) if b is not a)
        for _, i in ds[:near]:
            link(a, aps[i])
        if a["hub"]:
            hubs = [(dkm, i) for dkm, i in ds if aps[i]["hub"]]
            for _, i in hubs[:hub_near]:
                link(a, aps[i])
            far = [(dkm, i) for dkm, i in hubs if dkm > 4000]
            for _, i in far[:hub_far]:
                link(a, aps[i])
            # intercontinental routes: the nearest hubs on every other continent (Shanghai - Los Angeles, Lagos -
            # London, Sao Paulo - Madrid ...)
            home = continent(a["lon"], a["lat"])
            seen = {}
            for _, i in hubs:
                k = continent(aps[i]["lon"], aps[i]["lat"])
                if k != home and seen.get(k, 0) < per_continent:
                    seen[k] = seen.get(k, 0) + 1
                    link(a, aps[i])
    return {k: sorted(v) for k, v in links.items()}, len(aps)


def build_ports(G, land):
    ports = {}
    for ft in load("ne_10m_ports"):
        if ft["geometry"]["type"] != "Point":
            continue
        lon, lat = ft["geometry"]["coordinates"][:2]
        if not G.inside(lon, lat):
            continue
        rc = nearest_land(G, land, lon, lat)
        if rc is None:
            continue
        size = max(1, 10 - int(ft["properties"].get("scalerank") or 9))      # 1 small .. ~7 huge
        ports[rc] = max(ports.get(rc, 0), size)
    return [[r, c, s] for (r, c), s in sorted(ports.items())]


# ------------------------------------------------------------------------------------------------------- build
def build(region="world", res=0.5, seed=11, outbreak=PATIENT_ZERO, min_city=0.1):
    lon0, lon1, lat0, lat1 = REGIONS[region] if isinstance(region, str) else region
    ss = 3 if res >= 0.4 else 2
    G = Grid(lon0, lon1, lat0, lat1, res, ss)
    rng = np.random.default_rng(seed)
    print(f"grid {G.cols} x {G.rows} ({G.cols * G.rows} tiles), wrap={G.wrap}")
    land = G.fill([ft["geometry"] for ft in load("ne_50m_land")], 0.45)
    lakes = G.fill([ft["geometry"] for ft in load("ne_50m_lakes") if ft["properties"].get("scalerank", 9) <= 5], 0.5)
    land &= ~lakes
    T = build_terrain(G, land, rng)
    land = TR.is_land(T)
    O, names, pops = build_countries(G, land, T)
    n = len(names)
    print(f"{n} countries, {int(land.sum())} land tiles")
    cities = build_cities(G, land, T, O, min_city)
    H = np.where(land & (T != ICE), rural_people(G, T, O, cities, pops, rng), 0).astype(np.int32)
    D = np.full(H.shape, 2, dtype=np.int32)
    place_city_tiles(G, H, T, D, land, cities)
    H[~land] = 0
    H[O == 0] = np.minimum(H[O == 0], 5)
    balance_food(H, T, O, n)
    H = np.clip(H, 0, 255)

    # capitals: Natural Earth's capitals where the country owns the tile, else its biggest city
    capitals = {}
    for ct in cities:
        k = int(O[ct["row"], ct["col"]])
        if k and ct["capital"] and str(k) not in capitals:
            capitals[str(k)] = [ct["row"], ct["col"]]
    for ct in cities:
        k = int(O[ct["row"], ct["col"]])
        if k and str(k) not in capitals:
            capitals[str(k)] = [ct["row"], ct["col"]]
    for k, (r, c) in ((int(k), rc) for k, rc in capitals.items()):
        D[r, c] = max(D[r, c], 4)

    # rebel-held and occupied regions, wars
    by_name = {nm: k for k, nm in enumerate(names, start=1)}
    governments, wars, parents = {}, [], {}
    real = list(pops)                                    # real populations (Natural Earth), followed through splits
    for sp in W.SPLITS:
        if sp["of"] not in by_name:
            continue
        a = by_name[sp["of"]]
        m = (O == a) & G.poly(sp["poly"], 0.3)
        if not m.any():
            continue
        moved = real[a - 1] * float(H[m].sum()) / max(float(H[O == a].sum()), 1.0)
        real[a - 1] -= moved
        if "to" in sp:
            if sp["to"] not in by_name:
                continue
            b = by_name[sp["to"]]
            real[b - 1] += moved
        else:
            names.append(sp["new"])
            b = len(names)
            governments[str(b)] = sp["gov"]
            parents[str(b)] = a
            pops.append(float(H[m].sum()))
            real.append(moved)
            rows, cols = np.nonzero(m)
            j = int(np.argmax(H[rows, cols]))
            capitals[str(b)] = [int(rows[j]), int(cols[j])]
        O[m] = b
        if sp.get("war"):
            wars.append([a, b])
    for a, b in W.WARS:
        if a in by_name and b in by_name:
            wars.append([by_name[a], by_name[b]])
    rivals = [[by_name[a], by_name[b]] for a, b in W.RIVALS if a in by_name and b in by_name]
    military = {str(k): W.MILITARY.get(nm, round(0.15 + 0.2 * min(1.0, math.log10(max(p, 1e4)) / 9.0), 2))
                for k, (nm, p) in enumerate(zip(names, pops), start=1)}
    nukes = {str(by_name[nm]): v for nm, v in W.NUKES.items() if nm in by_name}
    traits = {str(by_name[nm]): t for nm, t in W.TRAITS.items() if nm in by_name}

    Z = np.zeros(H.shape, dtype=np.int32)
    if G.inside(*outbreak):
        r, c = G.rc(*outbreak)
        cand = np.argwhere(land & (H >= 40) & (T != MOUNTAIN))
        dd = (cand[:, 0] - r) ** 2 + np.minimum(abs(cand[:, 1] - c), G.cols - abs(cand[:, 1] - c)) ** 2
        zr, zc = map(int, cand[int(np.argmin(dd))])
        Z[zr, zc] = 40
        Z[zr, (zc + 1) % G.cols] = 25
        pz = [zr, zc]
    else:
        pz = None
    airports, n_ap = build_airports(G, land)
    ports = build_ports(G, land)
    meta = dict(wrap=G.wrap, sea_min=0, res=res, bounds=[lon0, lon1, lat0, lat1],
                names={str(k): nm for k, nm in enumerate(names, start=1)}, capitals=capitals,
                cities=[dict(name=ct["name"], row=ct["row"], col=ct["col"], pop=ct["pop"]) for ct in cities
                        if ct["pop"] >= 0.15],
                ports=ports, military=military, nukes=nukes, wars=wars, rivals=rivals, governments=governments, parents=parents, traits=traits,
                real_pops={str(k): round(p) for k, p in enumerate(real, start=1)},
                patient_zero=pz, source="Natural Earth (public domain) + world_data.py")
    print(f"{len(cities)} cities, {n_ap} airports ({len(airports)} airport tiles), {len(ports)} ports, "
          f"{len(wars)} wars, {int(H.sum())} people")
    return H, Z, D, T, O, airports, meta, G


def preview(folder, H, T, O):
    import render
    terr = TR.COLORS[T].astype(np.uint8)
    pal = np.array([render.civ_color(k) for k in range(int(O.max()) + 1)], dtype=np.float32)
    own = pal[O] * (0.35 + 0.65 * np.clip(H / 150.0, 0, 1))[..., None]
    own[TR.is_water(T)] = (0, 0, 60)
    img = np.concatenate([terr, own.astype(np.uint8)], axis=0)
    scale = max(1, 1600 // T.shape[1])
    Image.fromarray(img).resize((img.shape[1] * scale, img.shape[0] * scale), Image.NEAREST).save(
        os.path.join(folder, "preview.png"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="generate a map from Natural Earth data")
    ap.add_argument("--region", default="world", help="world, asia, europe, americas, africa or lon0,lon1,lat0,lat1")
    ap.add_argument("--res", type=float, default=0.5, help="degrees per tile (0.5 default, 0.25 = 4x the tiles)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--outbreak", default=None, help="lon,lat of patient zero (default: Three Gorges)")
    ap.add_argument("--min-city", type=float, default=0.1, help="smallest city placed (millions)")
    opt = ap.parse_args()
    region = opt.region if opt.region in REGIONS else tuple(float(v) for v in opt.region.split(","))
    outbreak = tuple(float(v) for v in opt.outbreak.split(",")) if opt.outbreak else PATIENT_ZERO
    out = opt.out or os.path.join("maps", opt.region if isinstance(region, str) else "custom")
    H, Z, D, T, O, AP, meta, G = build(region, opt.res, opt.seed, outbreak, opt.min_city)
    mapio.save_map(out, H, Z, D, T, O, AP)
    with open(os.path.join(out, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    preview(out, H, T, O)
    print("saved", out)
