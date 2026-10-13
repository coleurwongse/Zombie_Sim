"""Drawing the hand-made maps (make_middleearth.py, make_beleriand.py).

Everything is laid out on a reference picture of the map, in its pixel coordinates (x east, y south), and rasterized
onto the tile grid:
  1. the ground: coasts, seas and lakes, ice, ranges, hills, forests and scattered woods, downs, marshes, deserts,
     rivers (marshy valleys, or open water) - every outline pushed in and out by smooth noise so nothing is a polygon;
  2. the realms: each grows outward from its towns over that ground (a cost-distance race), cheaply over open country,
     dearly over mountains, marshes and rivers - so borders settle on rivers and ridges and between towns, the way real
     borders do.  A realm's drawn outline (plus a margin) is where it may grow freely; beyond that it only spills a
     little way.  A small realm drawn round one town (a city state, a fief) takes the land around that town;
  3. the people: thickest in the towns, thinning out into the countryside (two scales: the town's fields, its
     region), with villages and hamlets dotted about.

A map module gives the lists - see make_middleearth.py and make_beleriand.py:
  ground   COAST, ISLANDS, WATER (lakes, bays), OPEN_RIVERS, RIVERS, MOUNTAINS ([points], width[, "hills"]), PEAKS,
           HILLS, FORESTS, WOODLAND, DOWNS, MARSHES, DESERTS, COLD ([(shape, terrain, share)]), NORTH (tundra, ice
           lines), AMP (how far outlines are pushed about), RIVER_WIDTH, FEN_WIDTH
  realms   REALMS (name, side = alliance or None, land, extra, rural, floor, army, gov, traits[, margin, spill,
           liege, reach - a town or fief grows from its towns inside its overlord's land, up to `reach`]),
           PLACES (name, realm, x, y, people, radius, garrison level), PORTS, WARS, RIVALS, OUTBREAK, START,
           REAL_POPULATION, SOURCE, MILES (per tile), WIDTH / HEIGHT / UNIT (reference pixels, pixels per tile)
"""
import heapq
import json
import os

import numpy as np
from PIL import Image, ImageDraw

import mapio
import terrain as TR
from make_world import fbm, dilate, blur
from terrain import (DEEP, SHALLOW, GRASS, FOREST, MOUNTAIN, DESERT, ICE, URBAN, SUBURBAN, HIGHLANDS, TUNDRA,
                     WETLAND)


class Canvas:
    """Shapes in reference-picture pixels, rasterized onto the tiles (`unit` pixels per tile, supersampled)."""

    def __init__(self, width, height, unit, ss=2):
        self.unit, self.ss = float(unit), ss
        self.cols, self.rows = int(width / unit), int(height / unit)
        self._fields = {}

    def _px(self, pts):
        return [(x / self.unit * self.ss, y / self.unit * self.ss) for x, y in pts]

    def _canvas(self):
        img = Image.new("L", (self.cols * self.ss, self.rows * self.ss), 0)
        return img, ImageDraw.Draw(img)

    def _down(self, img, thresh=0.5):
        a = np.asarray(img, dtype=np.float32).reshape(self.rows, self.ss, self.cols, self.ss).mean(axis=(1, 3))
        return a > 255 * thresh

    def poly(self, pts, thresh=0.5):
        img, d = self._canvas()
        d.polygon(self._px(pts), fill=255)
        return self._down(img, thresh)

    def disc(self, x, y, r):
        u, s = self.unit, self.ss
        img, d = self._canvas()
        d.ellipse([(x - r) / u * s, (y - r) / u * s, (x + r) / u * s, (y + r) / u * s], fill=255)
        return self._down(img, 0.4)

    def line(self, pts, width):
        img, d = self._canvas()
        w = max(1, int(width / self.unit * self.ss))
        p = self._px(pts)
        d.line(p, fill=255, width=w)
        for x, y in p:
            d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=255)
        return self._down(img, 0.4)

    def shape(self, s):
        """A polygon [(x, y), ...] or a circle (x, y, r)."""
        return self.disc(*s) if isinstance(s, tuple) else self.poly(s)

    def field(self, salt, cells=(8, 16, 32, 64)):
        """Smooth noise in 0..1, the same every time for the same salt."""
        key = (salt, cells)
        if key not in self._fields:
            self._fields[key] = fbm(np.random.default_rng(1000 + salt), self.rows, self.cols, cells=cells)
        return self._fields[key]

    def _warp_index(self, amp, salt):
        dy = (self.field(2 * salt) - 0.5) * 2 * amp
        dx = (self.field(2 * salt + 1) - 0.5) * 2 * amp
        rr = np.clip(np.rint(np.arange(self.rows)[:, None] + dy), 0, self.rows - 1).astype(int)
        cc = np.clip(np.rint(np.arange(self.cols)[None, :] + dx), 0, self.cols - 1).astype(int)
        return rr, cc

    def ragged(self, mask, amp=8.0, salt=0, roughness=0.3):
        """Natural-looking shapes: the shape is warped by smooth noise (its outline moves up to `amp` tiles in and
        out), then its edge roughened a little."""
        rr, cc = self._warp_index(amp, salt)
        warped = mask[rr, cc]
        if roughness <= 0:
            return warped
        fine = self.field(500 + salt, cells=(32, 64, 128))
        return blur(warped.astype(np.float64), 1.2, False) + roughness * 2 * (fine - 0.5) > 0.5

    def rc(self, x, y):
        return min(self.rows - 1, int(y / self.unit)), min(self.cols - 1, int(x / self.unit))


# ------------------------------------------------------------------------------------------------ the ground
def paint_terrain(cv, G, seed=7):
    """The terrain grid T, and the masks the realms and people need."""
    R, C = cv.rows, cv.cols
    A = getattr(G, "AMP", 1.0)
    rng = np.random.default_rng(seed)
    noise = fbm(rng, R, C, cells=(8, 16, 32, 64))
    noise2 = fbm(rng, R, C, cells=(12, 24, 48, 96))
    land = cv.ragged(cv.poly(G.COAST), 9 * A, salt=1, roughness=0.25)
    for i, pts in enumerate(getattr(G, "ISLANDS", [])):
        land |= cv.ragged(cv.poly(pts), 3 * A, salt=300 + i, roughness=0.2)
    lakes = np.zeros((R, C), dtype=bool)
    for i, pts in enumerate(G.WATER.values()):
        lakes |= cv.ragged(cv.poly(pts), 5 * A, salt=10 + i)
    land &= ~lakes
    T = np.where(land, GRASS, DEEP).astype(np.int32)
    north = getattr(G, "NORTH", None)
    if north:                                    # the cold north: tundra, and ice in the far north
        yy = (np.arange(R)[:, None] + 0.5) * cv.unit + np.zeros((1, C))
        wob = (noise - 0.5) * 120
        T[land & (yy + wob < north[0])] = TUNDRA
        T[land & (yy + wob < north[1]) & (noise2 < 0.6)] = ICE
    for i, (s_, ter, share) in enumerate(getattr(G, "COLD", [])):
        m = cv.ragged(cv.shape(s_), 10 * A, salt=330 + i)
        T[land & m & ((noise2 < share) if share < 1 else True)] = ter
    for i, (pts, share) in enumerate(G.DESERTS.values()):
        T[land & cv.ragged(cv.poly(pts), 18 * A, salt=20 + i) & (noise2 < share) & (T != ICE)] = DESERT
    for i, (s_, share) in enumerate(G.FORESTS.values()):
        m = cv.ragged(cv.shape(s_), 14 * A, salt=40 + i)
        T[land & m & ((noise < share) if share < 1 else True) & (T != DESERT) & (T != ICE)] = FOREST
    fine = fbm(np.random.default_rng(seed + 1), R, C, cells=(24, 48, 96, 192))
    fine2 = fbm(np.random.default_rng(seed + 2), R, C, cells=(20, 40, 80, 160))
    for i, (pts, share) in enumerate(G.WOODLAND.values()):
        m = cv.ragged(cv.poly(pts), 20 * A, salt=220 + i, roughness=0.2)
        T[land & m & (fine < np.quantile(fine, share)) & (T == GRASS)] = FOREST
    T[land & (fine2 > np.quantile(fine2, 1 - G.DOWNS)) & (T == GRASS)] = HIGHLANDS
    for i, s_ in enumerate(G.HILLS.values()):
        T[land & cv.ragged(cv.shape(s_), 9 * A, salt=60 + i) & (T != ICE)] = HIGHLANDS
    for i, spec in enumerate(G.MOUNTAINS.values()):
        pts, width = spec[0], spec[1]
        hills_only = len(spec) > 2 and spec[2] == "hills"
        T[land & cv.ragged(cv.line(pts, width * 1.4), 6 * A, salt=80 + i) & (T != MOUNTAIN)] = HIGHLANDS
        if not hills_only:
            T[land & cv.ragged(cv.line(pts, width * 0.7), 6 * A, salt=80 + i)] = MOUNTAIN
    for i, (x, y, r) in enumerate(G.PEAKS.values()):
        T[land & cv.ragged(cv.disc(x, y, r), 2 * A, salt=120 + i)] = MOUNTAIN
    for i, s_ in enumerate(G.MARSHES.values()):
        T[land & cv.ragged(cv.shape(s_), 5 * A, salt=140 + i) & (noise < 0.85) & (T != MOUNTAIN)] = WETLAND
    rivers = np.zeros((R, C), dtype=bool)
    rw, fw = getattr(G, "RIVER_WIDTH", 6), getattr(G, "FEN_WIDTH", 22)
    for i, pts in enumerate(G.RIVERS.values()):
        m = land & cv.ragged(cv.line(pts, rw), 7 * A, salt=160 + i, roughness=0) & (T != MOUNTAIN)
        T[m] = WETLAND
        rivers |= m
        # water-meadows and fens along the rivers, here and there
        T[land & cv.ragged(cv.line(pts, fw), 7 * A, salt=160 + i, roughness=0)
          & (fine2 < np.quantile(fine2, 0.3)) & (T == GRASS)] = WETLAND
    open_river = np.zeros((R, C), dtype=bool)
    for i, pts in enumerate(getattr(G, "OPEN_RIVERS", {}).values()):
        open_river |= cv.ragged(cv.line(pts, rw), 5 * A, salt=180 + i, roughness=0)
    T[open_river] = SHALLOW
    land = TR.is_land(T)
    # water: shallow along the coasts and in the lakes, deep further out
    sea = ~land
    T[sea & dilate(land, 1, False)] = SHALLOW
    T[lakes & sea] = SHALLOW
    return T, dict(land=land, rivers=rivers | open_river, open_river=open_river & ~land, noise=noise,
                   noise2=noise2, fine=fine, fine2=fine2)


# ------------------------------------------------------------------------------------------------ the realms
#                    deep grass forest mount desert ice  urban suburb shallow highl tundra wetl  rainf
STEP_COST = np.array([0.0, 1.0, 1.5,  9.0,  1.4,  5.0, 1.0,  1.0,  0.0,   2.2,  1.4,   2.6,  2.0])
RIVER_COST = 7.0        # crossing a river (on top of the ground's own cost)
OPEN_RIVER_COST = 14.0  # crossing a river that is open water
OUTSIDE = 4.0           # beyond a realm's own outline (and margin) every step costs this much more ...
MARGIN = 6              # tiles around a realm's outline it may still take as if its own
SPILL = 24.0            # ... and it stops when the extra cost would pass this
_NB8 = [(-1, -1, 1.414), (-1, 0, 1.0), (-1, 1, 1.414), (0, -1, 1.0), (0, 1, 1.0), (1, -1, 1.414), (1, 0, 1.0),
        (1, 1, 1.414)]


def travel_cost(cv, T, masks, salt=900, wander=0.4):
    """What it takes to cross each tile (open ground 1), and which tiles can be crossed at all."""
    f = 0.5 * cv.field(salt, cells=(8, 16, 32, 64, 128)) + 0.5 * cv.field(salt + 1, cells=(48, 96, 192))
    rough = 1.0 + 2 * wander * (f - 0.5) / max(float(np.std(f)) * 2.5, 1e-9)    # (borders wander, not run straight)
    rough = np.clip(rough, 0.15, 3.0)
    cost = STEP_COST[np.clip(T, 0, len(STEP_COST) - 1)] * rough
    cost += np.where(masks["rivers"], RIVER_COST, 0.0)
    cost[masks["open_river"]] = OPEN_RIVER_COST
    return cost, masks["land"] | masks["open_river"]


def districts(cv, T, masks, spacing, towns, seed=11):
    """The land cut into districts - shires, counties, valleys: cells grown from scattered centres (and every town)
    over the ground, so they are irregular and end at rivers and ridges.  Realms are made of whole districts."""
    rng = np.random.default_rng(seed)
    land = masks["land"]
    rr, cc = np.nonzero(land)
    k = max(1, int(land.sum() / float(spacing) ** 2))
    pick = rng.choice(rr.size, size=min(k, rr.size), replace=False)
    centres = list(zip(rr[pick].tolist(), cc[pick].tolist()))
    centres = list(dict.fromkeys(list(towns) + centres))       # (towns first: each town heads its own district)
    n = len(centres)
    return grow_realms(cv, T, masks, [None] * n, [[c] for c in centres], [0] * n, [0.0] * n, salt=950,
                       wander=0.8), n


def grow_realms(cv, T, masks, claims, seeds, margins, spills, reaches=None, salt=900, wander=0.4):
    """Every realm grows from its seed tiles at once, each tile going to whoever reaches it at the least cost
    (Dijkstra over the tiles).  claims[k]: realm k's outline; seeds[k]: its towns; reaches[k]: how far (in cost) it
    grows at most (a town's own land).  Returns the owner grid (0 = no realm reached it)."""
    rows, cols = T.shape
    n = rows * cols
    cost, passable = travel_cost(cv, T, masks, salt, wander)
    costl = cost.ravel().tolist()
    passl = passable.ravel().tobytes()
    every = b"" * n
    zones = [b""] + [every if m is None else dilate(m, mg, False).ravel().tobytes() for m, mg in zip(claims, margins)]
    spill = [0.0] + list(spills)
    reach = [0.0] + list(reaches or [float("inf")] * len(claims))
    lab = [0] * n
    heap = []
    for k, pts in enumerate(seeds, start=1):
        for r, c in pts:
            if passl[r * cols + c]:
                heap.append((0.0, 0.0, k, r * cols + c))
    heapq.heapify(heap)
    push, pop = heapq.heappush, heapq.heappop
    while heap:
        d, o, k, i = pop(heap)
        if lab[i]:
            continue
        lab[i] = k
        z, sp, far = zones[k], spill[k], reach[k]
        r, c = divmod(i, cols)
        for dr, dc, w in _NB8:
            rr, cc = r + dr, c + dc
            if rr < 0 or rr >= rows or cc < 0 or cc >= cols:
                continue
            j = rr * cols + cc
            if lab[j] or not passl[j]:
                continue
            step = costl[j] * w
            if d + step > far:
                continue
            if z[j]:
                push(heap, (d + step, o, k, j))
            else:
                step *= OUTSIDE
                if o + step <= sp:
                    push(heap, (d + step, o + step, k, j))
    return np.array(lab, dtype=np.int32).reshape(rows, cols)


def tidy(O, land, passes=2):
    """Specks and slivers smoothed away: a tile most of whose neighbours belong to one other realm joins it."""
    rows, cols = O.shape
    for _ in range(passes):
        p = np.pad(O, 1, constant_values=-1)
        nbrs = np.stack([p[1 + dr:rows + 1 + dr, 1 + dc:cols + 1 + dc] for dr, dc, _ in _NB8])
        same = (nbrs == O).sum(axis=0)
        srt = np.sort(nbrs, axis=0)
        # the most common neighbour label (runs in the sorted stack)
        best, best_n = srt[0].copy(), np.ones(O.shape, dtype=int)
        run = np.ones(O.shape, dtype=int)
        for i in range(1, 8):
            run = np.where(srt[i] == srt[i - 1], run + 1, 1)
            better = run > best_n
            best = np.where(better, srt[i], best)
            best_n = np.where(better, run, best_n)
        flip = land & (same <= 2) & (best_n >= 5) & (best >= 0)
        O = np.where(flip, best, O)
    return O


# ------------------------------------------------------------------------------------------------ everything
def build(G, seed=7):
    cv = Canvas(G.WIDTH, G.HEIGHT, G.UNIT)
    T, masks = paint_terrain(cv, G, seed)
    land = masks["land"]
    noise, noise2, fine, fine2 = masks["noise"], masks["noise2"], masks["fine"], masks["fine2"]
    R, C = T.shape
    names = [r["name"] for r in G.REALMS]
    by_name = {nm: k for k, nm in enumerate(names, start=1)}

    def place_rc(x, y):                          # (a harbour drawn just off the coast moves onto the land)
        r, c = cv.rc(x, y)
        if not land[r, c]:
            near = [(abs(dr) + abs(dc), r + dr, c + dc) for dr in range(-4, 5) for dc in range(-4, 5)
                    if 0 <= r + dr < R and 0 <= c + dc < C and land[r + dr, c + dc]]
            if near:
                _, r, c = min(near)
        return r, c

    # realms grow from their towns over the ground
    claims, seeds, margins, spills, reaches = [], [], [], [], []
    for k, realm in enumerate(G.REALMS, start=1):
        m = cv.shape(realm["land"]) if "land" in realm else np.zeros(T.shape, dtype=bool)
        pts = [place_rc(x, y) for name, rl, x, y, *_ in G.PLACES if rl == realm["name"]]
        for e in realm.get("extra", []):
            m |= cv.shape(e)
            if isinstance(e, tuple):
                pts.append(place_rc(e[0], e[1]))
        m = cv.ragged(m, min(10.0, max(2.0, np.sqrt(m.sum()) / 6)), salt=7, roughness=0.25)
        if not pts:                              # (no town drawn: its middle)
            rr, cc = np.nonzero(m & land)
            if rr.size:
                j = int(np.argmin((rr - rr.mean()) ** 2 + (cc - cc.mean()) ** 2))
                pts = [(int(rr[j]), int(cc[j]))]
        claims.append(m & land)
        seeds.append(pts)
        margins.append(int(realm.get("margin", getattr(G, "MARGIN", MARGIN))))
        spills.append(float(realm.get("spill", getattr(G, "SPILL", SPILL))))
        reaches.append(float(realm.get("reach", float("inf"))))
    for k, realm in enumerate(G.REALMS):         # a fief grows inside its overlord's land, as far as its reach
        if realm.get("liege"):
            lg = by_name[realm["liege"]] - 1
            claims[k] = claims[k] | claims[lg]
            margins[k] = max(margins[k], margins[lg])
    grown = grow_realms(cv, T, masks, claims, seeds, margins, spills, reaches)
    # realms are made of whole districts: each district goes to the realm holding most of it (a town's district always
    # to the town's realm) - so borders are the districts' edges, along rivers and ridges, irregular like real ones
    town_rc = {place_rc(x, y): by_name.get(rl, 0) for name, rl, x, y, *_ in G.PLACES}
    spacing = getattr(G, "DISTRICT_MILES", 35.0) / getattr(G, "MILES", 5.0)
    dist_map, nd = districts(cv, T, masks, spacing, list(town_rc))
    owner = np.zeros(nd + 1, dtype=np.int32)
    votes = np.zeros((nd + 1, len(G.REALMS) + 1))
    np.add.at(votes, (dist_map.ravel(), grown.ravel()), 1.0)
    owner[:] = votes.argmax(axis=1)
    for (r, c), k in town_rc.items():
        if k:
            owner[dist_map[r, c]] = k
    owner[0] = 0
    O = owner[dist_map]
    O[~land] = 0

    # people: farmland and towns; orc-hosts camp in desert and mountain, elves live in the woods
    miles = getattr(G, "MILES", 5.0)
    H = np.zeros(T.shape)
    pull = np.zeros(T.shape)
    for name, realm, x, y, people, radius, level in G.PLACES:
        r, c = place_rc(x, y)
        pull[r, c] += people * (1 + radius)
    pull = blur(pull, 25.0 / miles, False) / 40.0 + blur(pull, 90.0 / miles, False) / 6.0
    pull = np.clip(pull / max(float(np.quantile(pull[land], 0.97)), 1e-9), 0, 1.6)
    hamlets = np.where(fine > np.quantile(fine, 0.85), 1.6, 1.0)                    # villages and hamlets dotted about
    jit = (0.6 + 0.8 * noise2) * (0.75 + 0.5 * fine2) * hamlets
    for k, realm in enumerate(G.REALMS, start=1):
        m = (O == k) & TR.habitable(T)
        dens = np.maximum(TR.DENSITY[T], realm["floor"])
        H[m] = (realm["rural"] * dens * jit * (0.35 + 1.1 * pull))[m]
    wild = (O == 0) & TR.habitable(T)
    H[wild] = (getattr(G, "WILD_RURAL", 6) * TR.DENSITY[T] * jit * (0.5 + pull))[wild]     # a few in the wilds
    H = np.where(land, blur(H, 1.0, False), 0.0)                  # (no hard steps from one tile to the next)
    D = np.full(T.shape, 2, dtype=np.int32)
    capitals, cities, sites = {}, [], []
    for name, realm, x, y, people, radius, level in G.PLACES:
        r, c = place_rc(x, y)
        k = by_name.get(realm, 0)
        for dr in range(-radius, radius + 1):
            for dc in range(-radius, radius + 1):
                rr, cc = r + dr, c + dc
                if not (0 <= rr < R and 0 <= cc < C) or not land[rr, cc]:
                    continue
                ring = max(abs(dr), abs(dc))
                H[rr, cc] = max(H[rr, cc], people * (1.0 if ring == 0 else 0.75 if ring == 1 else 0.55))
                if T[rr, cc] not in (MOUNTAIN, ICE, WETLAND):
                    T[rr, cc] = URBAN if ring == 0 and people >= 150 else SUBURBAN if people >= 60 else T[rr, cc]
                if k:
                    O[rr, cc] = k
        if not land[r, c]:
            continue
        cities.append(dict(name=name, row=r, col=c, pop=round(people / 1000.0, 3)))
        if k and str(k) not in capitals:
            capitals[str(k)] = [r, c]
        if k and level:
            D[r, c] = max(D[r, c], min(level, 4))
            sites.append(dict(civ=k, row=r, col=c, level=level, radius=1 if radius else 0))
    H = np.clip(np.rint(H), 0, 255).astype(np.int32)
    H[~land] = 0
    for k, realm in enumerate(G.REALMS, start=1):                 # every realm has somewhere its people live
        if str(k) not in capitals:
            m = O == k
            if m.any():
                rr, cc = np.unravel_index(int(np.argmax(np.where(m, H, -1))), H.shape)
                capitals[str(k)] = [int(rr), int(cc)]
    if hasattr(G, "post"):                                        # anything special (Melian's Girdle ...)
        G.post(cv, T, O, D, H, by_name, sites)
    Z = np.zeros(T.shape, dtype=np.int32)
    pr, pc = next((c["row"], c["col"]) for c in cities if c["name"] == G.OUTBREAK)
    Z[pr, pc] = 40
    Z[pr, pc + 1] = 25
    ports = []
    for name, size in G.PORTS:
        ct = next(c for c in cities if c["name"] == name)
        ports.append([ct["row"], ct["col"], size])
    res = miles / 69.0                                            # (degrees per tile, as if it were the Earth)
    side = {r["name"]: r.get("side") for r in G.REALMS}
    alliances = {}
    for n_ in names:
        if side[n_]:
            alliances.setdefault(side[n_], []).append(by_name[n_])
    meta = dict(
        wrap=False, sea_min=0, res=res, bounds=[0.0, C * res, 30.0, 30.0 + R * res], start_date=G.START,
        names={str(k): nm for k, nm in enumerate(names, start=1)}, capitals=capitals, cities=cities, ports=ports,
        military={str(k): r["army"] for k, r in enumerate(G.REALMS, start=1)},
        governments={str(k): r["gov"] for k, r in enumerate(G.REALMS, start=1) if r["gov"] != "national"},
        traits={str(k): r["traits"] for k, r in enumerate(G.REALMS, start=1) if r["traits"]},
        nukes={}, wars=[[by_name[a], by_name[b]] for a, b in G.WARS],
        rivals=[[by_name[a], by_name[b]] for a, b in G.RIVALS],
        alliances=alliances, sites=sites, patient_zero=[pr, pc], outbreak=G.OUTBREAK,
        real_population=G.REAL_POPULATION, source=G.SOURCE)
    if getattr(G, "VIRULENCE_SCALE", 1.0) != 1.0:
        meta["virulence_scale"] = G.VIRULENCE_SCALE              # (the map's own bite: x --virulence)
    if getattr(G, "SETTLE_SCALE", 1.0) != 1.0:
        meta["settle_scale"] = G.SETTLE_SCALE
    return H, Z, D, T, O, {}, meta


def preview(folder, H, T, O):
    import render
    terr = TR.COLORS[T].astype(np.uint8)
    pal = np.array([render.civ_color(k) for k in range(int(O.max()) + 1)], dtype=np.float32)
    own = pal[O] * (0.35 + 0.65 * np.clip(H / 150.0, 0, 1))[..., None]
    own[TR.is_water(T)] = (0, 0, 60)
    img = np.concatenate([terr, own.astype(np.uint8)], axis=1)
    Image.fromarray(img).resize((img.shape[1] * 2, img.shape[0] * 2), Image.NEAREST).save(
        os.path.join(folder, "preview.png"))


def make(G, out):
    """Build the map described by module G and write it to folder `out`."""
    H, Z, D, T, O, A, meta = build(G)
    mapio.save_map(out, H, Z, D, T, O, A)
    with open(os.path.join(out, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    preview(out, H, T, O)
    pops = np.bincount(O.ravel(), weights=H.ravel(), minlength=len(G.REALMS) + 1)
    print(f"{T.shape[1]} x {T.shape[0]} tiles, {len(G.REALMS)} realms, {len(meta['cities'])} places, "
          f"{int(H.sum())} people")
    for k, r in enumerate(G.REALMS, start=1):
        print(f"  {r['name']:28s} {str(r.get('side')):22s} {int(pops[k]):7d} people, {int((O == k).sum()):5d} tiles")
    print("saved", out)
    return H, Z, D, T, O, meta
