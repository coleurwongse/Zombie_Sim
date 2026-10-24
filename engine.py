"""The per-tile rules, all tiles at once (numpy).  (It replaced the original game's tile-by-tile scan.)

Same rules as the original, with these differences:
  * synchronous: every tile reacts to the map as it was at the start of the pass (the scan updated tiles in place,
    so zombies could run several tiles - and bite again - in one tick in the scan direction); MOVE_PASSES movement
    passes per tick, the first BITE_ROUNDS each with a round of bites, make up for it;
  * water is water: nobody walks into the sea (people leave by boat, see boats.py) and zombies follow their own rules
    there (below) - before, people stepped into ocean tiles, got bitten there and left blobs of zombies out at sea;
  * highlands (between plains and mountains) bite and let zombies through a little less than plains; zombies also
    move more slowly into mountains, highlands, rainforest and (slowest) wetlands (terrain.MOVE);
  * only the window around the zombies is worked on (the rest of the map has nothing to update but defense).

Zombies in water
  land -> water    a few wander off the shore (more into shallow water than off a cliff into deep water)
  shallow water    they swim: come ashore readily (fast where there are people), drift along the coast, a few drift out
  deep water       stragglers drift (a random direction each pass); hordes (>= SEA_HORDE) swim for the nearest land
                   (along the pre-computed distance-to-land field); the deep sea slowly takes its share (SEA_LOSS)
"""
import numpy as np

from terrain import DEEP, SHALLOW, MOUNTAIN, HIGHLANDS, URBAN, MOVE

JITTER = 0.35
MOVE_PASSES = 4            # zombie movement passes per tick (synchronous moves are one tile per pass) ...
BITE_ROUNDS = 2            # ... the first this many each preceded by a round of bites
LATE_BITE = 1.0            # (later rounds bite at this share of the full rate)
MAX_OUT = 0.9              # a tile never sends more than this share of its zombies away in one pass
SWIM_MIN = 10              # zombies on a beach need to be at least this many before some wander into the water ...
SWIM_SHALLOW = 0.015       # ... this share per shallow neighbour per pass
SWIM_DEEP = 0.003          # ... or off a cliff into deep water
ASHORE_PEOPLE = 1 / 3.0    # shallow water -> land with people on it
ASHORE = 1 / 6.0           # shallow water -> empty land
ALONG_SHORE = 1 / 5.0      # shallow -> shallow (share of the difference)
OUT_TO_SEA = 1 / 12.0      # shallow -> deep (share of the difference)
DRIFT = 0.15               # deep water: share of a tile's zombies drifting one tile in a random direction per pass
SEA_HORDE = 3              # deep water: groups this big swim for land ...
HORDE_SWIM = 0.4           # ... this share of them per pass
SEA_LOSS = 0.004           # deep water: share lost per tick ...
STRAY_LOSS = 0.03          # ... and the chance a lone straggler (fewer than SEA_HORDE) is lost, per tick
STRAY_LANDWARD = 0.5       # a straggler drifts toward land this often (otherwise a random direction)
ZOMBIE_DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
SPREAD = 1 / 8.0             # zombies spread out toward a neighbour with fewer: this share of the difference per pass
                             # (more than 1/8 to each of 4 neighbours overshoots: crowded and empty tiles swap places
                             #  every pass and a horde turns into a checkerboard)
HUMAN_DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (-1, 1), (1, -1), (2, 0), (-2, 0), (0, 2), (0, -2))


def shift(a, dr, dc, wrap, fill=0):
    """out[r, c] = a[r + dr, c + dc]: every tile sees its neighbour at offset (dr, dc).  Rows never wrap; columns
    wrap around when `wrap` (a world map), otherwise `fill` is used beyond the edge."""
    if dc:
        if wrap:
            a = np.roll(a, -dc, axis=1)
        else:
            b = np.full_like(a, fill)
            if dc > 0:
                b[:, :-dc] = a[:, dc:]
            else:
                b[:, -dc:] = a[:, :dc]
            a = b
    if dr:
        b = np.full_like(a, fill)
        if dr > 0:
            b[:-dr] = a[dr:]
        else:
            b[-dr:] = a[:dr]
        a = b
    return a


def pad1(a, fill, wrap):
    """`a` with a one-tile border (columns wrapping round when `wrap`): nb(p, dr, dc) is then the neighbour at offset
    (dr, dc) of every tile as a view - like shift(), without copying the whole array for every direction."""
    p = np.empty((a.shape[0] + 2, a.shape[1] + 2), dtype=a.dtype)
    p[1:-1, 1:-1] = a
    p[0], p[-1] = fill, fill
    if wrap:
        p[1:-1, 0], p[1:-1, -1] = a[:, -1], a[:, 0]
    else:
        p[1:-1, 0], p[1:-1, -1] = fill, fill
    return p


def nb(p, dr, dc):
    return p[1 + dr:p.shape[0] - 1 + dr, 1 + dc:p.shape[1] - 1 + dc]


class Statics:
    """Things that depend only on the terrain, worked out once per map."""

    def __init__(self, world):
        T = world.T
        self.land = (T != DEEP) & (T != SHALLOW)
        self.land_idx = np.flatnonzero(self.land)               # flat indices of the land tiles
        self.shallow = T == SHALLOW
        self.deep = T == DEEP
        self.mountain = T == MOUNTAIN
        self.highlands = T == HIGHLANDS
        self.urban = T == URBAN
        self.move = MOVE[np.clip(T, 0, len(MOVE) - 1)].ravel()      # how readily zombies move onto each tile
        from labels import label
        self.landmass = label(self.land)[0]                     # which continent / island each land tile is on
        self.sea_dist = self._sea_distance(world)
        self.toward_land = self._toward_land(world)
        # flat index of the neighbour in every direction (-1 off the map; columns wrap on a world map)
        rows, cols = T.shape
        r, c = np.divmod(np.arange(T.size), cols)
        self.nbr = {}
        for dr, dc in set(HUMAN_DIRS) | set(ZOMBIE_DIRS) | {(-1, -1), (-1, 1), (1, -1), (1, 1)}:
            r2, c2 = r + dr, c + dc
            if world.wrap:
                c2 = c2 % cols
            bad = (r2 < 0) | (r2 >= rows) | (c2 < 0) | (c2 >= cols)
            self.nbr[(dr, dc)] = np.where(bad, -1, r2 * cols + c2).astype(np.int64)
        # 0 land, 1 shallow, 2 deep (one lookup instead of three in the movement rules)
        self.kind = np.where(self.land, 0, np.where(self.shallow, 1, 2)).astype(np.int8).ravel()

    def _sea_distance(self, world, steps=400):
        """Steps over water to the nearest land (0 on land)."""
        INF = 10 ** 6
        dist = np.where(self.land, 0, INF).astype(np.int32)
        for _ in range(steps):
            best = dist.copy()
            for dr, dc in ZOMBIE_DIRS:
                np.minimum(best, shift(dist, dr, dc, world.wrap, INF) + 1, out=best)
            best[self.land] = 0
            np.minimum(best, INF, out=best)
            if (best == dist).all():
                break
            dist = best
        return dist

    def _toward_land(self, world):
        """For each water tile, which of the 4 directions leads (most directly) to land: 0..3, or -1."""
        best = np.full(world.T.shape, 10 ** 7, dtype=np.int64)
        way = np.full(world.T.shape, -1, dtype=np.int8)
        for k, (dr, dc) in enumerate(ZOMBIE_DIRS):
            nd = shift(self.sea_dist, dr, dc, world.wrap, 10 ** 7).astype(np.int64)
            better = nd < best
            best = np.where(better, nd, best)
            way = np.where(better, k, way)
        way[self.land] = -1
        return way


def active_window(world, mask, margin):
    """(window, wrap): the rows / columns around every tile in `mask`, plus `margin` - or the whole width (wrapping if
    the map does) when that's most of it anyway.  (None, wrap) when the mask is empty."""
    rows = np.flatnonzero(mask.any(axis=1))
    if rows.size == 0:
        return None, world.wrap
    r0, r1 = max(0, rows[0] - margin), min(world.rows, rows[-1] + margin + 1)
    cols = np.flatnonzero(mask.any(axis=0))
    c0, c1 = cols[0] - margin, cols[-1] + margin + 1
    if c0 <= 0 or c1 >= world.cols or (c1 - c0) > 0.75 * world.cols:
        return (slice(r0, r1), slice(None)), world.wrap
    return (slice(r0, r1), slice(c0, c1)), False


BLOCK = 16


def active_windows(world, mask, margin):
    """Like active_window, but one window per separate cluster of `mask` (zombies on several continents don't make
    the whole world one window).  Clusters closer than about 2 x margin share a window; overlapping windows are merged,
    so no tile is in two windows and nothing can cross from one window into another within `margin` tiles."""
    from labels import label
    rows, cols = mask.shape
    B = BLOCK
    rb, cb = -(-rows // B), -(-cols // B)
    pad = np.zeros((rb * B, cb * B), dtype=bool)
    pad[:rows, :cols] = mask
    blocks = pad.reshape(rb, B, cb, B).any(axis=(1, 3))
    if not blocks.any():
        return []
    m = -(-margin // B)
    grown = blocks.copy()
    for _ in range(m):
        g = grown.copy()
        g[1:] |= grown[:-1]
        g[:-1] |= grown[1:]
        g[:, 1:] |= grown[:, :-1]                      # (windows don't wrap round the date line unless they
        g[:, :-1] |= grown[:, 1:]                       #  span most of the map anyway - close enough)
        grown = g
    lab, n = label(grown)
    boxes = []
    for k in range(1, n + 1):
        rr, cc = np.nonzero(lab == k)
        boxes.append([rr.min(), rr.max() + 1, cc.min(), cc.max() + 1])
    merged = True
    while merged:
        merged = False
        for i1 in range(len(boxes)):
            for j1 in range(i1 + 1, len(boxes)):
                a, bb = boxes[i1], boxes[j1]
                full_a, full_b = (a[2] == 0 and a[3] == cb), (bb[2] == 0 and bb[3] == cb)
                rows_meet = a[0] < bb[1] and bb[0] < a[1]
                if rows_meet and (full_a or full_b or (a[2] < bb[3] and bb[2] < a[3])):
                    boxes[i1] = [min(a[0], bb[0]), max(a[1], bb[1]), min(a[2], bb[2]), max(a[3], bb[3])]
                    del boxes[j1]
                    merged = True
                    break
            if merged:
                break
    out = []
    for r0, r1, c0, c1 in boxes:
        rs = slice(r0 * B, min(rows, r1 * B))
        if (c0 == 0 and c1 == cb) or (c1 - c0) * B > 0.75 * cols:
            out.append(((rs, slice(None)), world.wrap))
        else:
            out.append(((rs, slice(c0 * B, min(cols, c1 * B))), False))
    return out


def step(world, morale, kc, kp, unorg=(1.3, 1.3), resist=None, qfac=None, qheavy=60, closed=None):
    """One tick of the per-tile rules on world.H/Z/D (modified in place).  Returns the new knowledge value.
    The defense rules run on every tile; bites and movement only on the tiles that have zombies (gathered into short
    lists with their neighbours - the work grows with the outbreak, not with the size of the map)."""
    S = world.statics
    O = world.O
    H, Z, d = world.H, world.Z, world.D
    np.maximum(H, 0, out=H)
    np.maximum(Z, 0, out=Z)
    H[~S.land] = 0                                          # nobody lives in the sea

    # --- defense (the original rules) ---------------------------------------------------------------------------
    hasH = H > 0
    bump = hasH & (H > 122) & (O > 0) & (d < 5) & S.urban & (kc > 25)
    d[bump] += 2
    if kc == 25 or kc == 49:
        d[hasH] += 1
    c1 = hasH & (H < 50) & (d > 5)                         # (nested, as in the original: each only if the last)
    d[c1] = 5
    c2 = c1 & (H < 10)
    d[c2] = 2
    c3 = c2 & (H < 5)
    d[c3] = 1
    H[c3 & (H < 3)] = 0
    mo = np.asarray(morale)[O]
    low_m = hasH & (mo < d - 2)
    d[low_m] = mo[low_m]
    d[hasH] = np.clip(d[hasH], 1, 10)
    if kc < 50 and kc - kp < 1 and ((H > 20) & (Z > 5)).any():
        kc += 1
    Z[hasH & (d >= 7)] = 0                                 # a fortress kills whatever gets in

    if Z.any():
        g = _Grid(world, S, unorg, resist, qfac, qheavy, closed)
        h = H.ravel().astype(np.float32)
        z = Z.ravel().astype(np.float32)
        df = d.ravel()
        g.blocked = (df >= 7) & (h > 0)
        g.dd = np.maximum(df, 1).astype(np.float32)
        # bites and zombie movement, interleaved (the scan let zombies that had just arrived bite in the same tick)
        for p in range(MOVE_PASSES):
            if p < BITE_ROUNDS:
                _bites(g, h, z, 1.0 if p == 0 else LATE_BITE)
            _move_zombies(g, h, z)
        if kc > 5:                                       # people flee from zombies on their tile
            _move_people(g, h, z, df)
        H[:] = np.clip(np.rint(h), 0, 255).astype(np.int32).reshape(H.shape)
        Z[:] = np.clip(np.rint(z), 0, 255).astype(np.int32).reshape(Z.shape)

    if world.airports:
        _airports(world, H, Z, closed)
    np.clip(H, 0, 255, out=H)
    np.clip(Z, 0, 255, out=Z)
    return kc


class _Grid:
    """Flat views of the map for the sparse rules."""

    def __init__(self, world, S, unorg, resist, qfac, qheavy, closed):
        self.S, self.rng, self.stochastic = S, world.rng, world.stochastic
        self.n = world.H.size
        self.land = S.land.ravel()
        self.shallow = S.shallow.ravel()
        self.deep = S.deep.ravel()
        self.mountain = S.mountain.ravel()
        self.highlands = S.highlands.ravel()
        self.toward = S.toward_land.ravel()
        self.O = world.O.ravel()
        self.unorg = unorg
        self.resist = None if resist is None else resist.ravel()
        self.qfac = None if qfac is None else qfac.ravel()
        self.qheavy = qheavy
        meta = getattr(world, "meta", None) or {}
        self.virulence = getattr(world, "virulence", 1.0) * float(meta.get("virulence_scale", 1.0))
        import recovery                                  # (the recovery era: people know how to fight them)
        w = recovery.wary(world)                         # (and districts that have kept watch since)
        self.bite_mult = np.float32(1.0) if w is None else (1.0 - recovery.WARY_BITE * w).ravel()
        self.kill_mult = np.float32(1.0) if w is None else (1.0 + recovery.WARY_KILL * w).ravel()
        import seasons                                   # (the frozen dead: seasons.py)
        f = seasons.frozen(world)
        self.thaw = None
        if f is not None:
            self.bite_mult = self.bite_mult * (1.0 - seasons.FROZEN_BITE * f).ravel()
            self.kill_mult = self.kill_mult * (1.0 + seasons.FROZEN_KILL * f).ravel()
            self.thaw = (1.0 - f).ravel()
        import tech                                      # (guns and ammunition - or spears: tech.py; supply lines,
        import trade                                     #  trade.py; a creed's stance toward the dead, ideology.py)
        import ideology
        sup = trade.supply(world)
        for m in (tech.mult(world, tech.TECH_FIGHT), None if sup is None else 1.0 - trade.SUPPLY_FIGHT * (1.0 - sup),
                  ideology.kill_mult(world)):
            if m is not None:
                self.kill_mult = self.kill_mult * m.astype(np.float32).ravel()
        import hordes                                    # (organized hordes don't drift apart: hordes.COORD_DAMP)
        self.spread = np.float32(SPREAD * (1.0 - hordes.COORD_DAMP * hordes.coordination(world)))
        self.shut = None
        if closed:
            arr = np.zeros(len(world.civs), dtype=bool)
            arr[list(closed)] = True
            self.shut = arr[self.O]

    def rand(self, n):
        return self.rng.random(n, dtype=np.float32) if self.stochastic else np.full(n, 0.5, dtype=np.float32)

    def jitter(self, n):
        if not self.stochastic:
            return np.float32(1.0)
        j = self.rng.random(n, dtype=np.float32)
        j *= 2.0 * JITTER
        j += 1.0 - JITTER
        return j


def _bites(g, h, z, share):
    """People bitten (and zombies killed by the defenders) on every tile with both - the original formulas;
    `share` scales a later round within the same tick."""
    i = np.flatnonzero((z > 0) & (h > 0) & g.land)
    if i.size == 0:
        return
    hi, zi, dd = h[i], z[i], g.dd[i]
    bm = g.bite_mult if np.ndim(g.bite_mult) == 0 else g.bite_mult[i]
    km = g.kill_mult if np.ndim(g.kill_mult) == 0 else g.kill_mult[i]
    k = np.where(g.O[i] == 0, g.unorg[0], 1.0).astype(np.float32) * share * g.virulence * bm
    j1, j2 = g.jitter(i.size), g.jitter(i.size)
    mnt, hil = g.mountain[i], g.highlands[i]
    hz = hi * zi / dd
    bite = np.floor(hz / np.where(mnt, 255.0, np.where(hil, 140.0, 80.0)) * k * j1)
    kill = np.floor(zi / np.where(mnt, 20.0, np.where(hil, 90.0, 255.0)) * dd * dd * j2 * share * km)
    no = mnt & (hi <= 10)                                   # (the mountain rule needs more than 10 people)
    bite[no] = 0
    kill[no] = 0
    bite = np.minimum(bite, hi)
    h[i] = hi - bite
    z[i] = np.maximum(zi + bite - kill, 0)


_SWIM_RATE = np.array([0.0, SWIM_SHALLOW, SWIM_DEEP], dtype=np.float32)     # land -> land / shallow / deep
_SEA_RATE = np.array([0.0, ALONG_SHORE, OUT_TO_SEA], dtype=np.float32)       # shallow -> ... (share of the difference)


def _move_zombies(g, h, z):
    S = g.S
    src = np.flatnonzero(z > 0)
    if src.size == 0:
        return
    nz = z[src]
    ks = S.kind[src]
    lnd, shl, dep = ks == 0, ks == 1, ks == 2
    people = h > 5
    L, W = np.flatnonzero(lnd), np.flatnonzero(shl)          # zombies on land, in the shallows
    nl, nw = nz[L], nz[W]
    can_swim = (nl >= SWIM_MIN).astype(np.float32)
    out = np.zeros((4, src.size), dtype=np.float32)
    tgts = np.empty((4, src.size), dtype=np.int64)
    for k, d in enumerate(ZOMBIE_DIRS):
        t = S.nbr[d][src]
        valid = t >= 0
        tc = np.where(valid, t, 0)
        tgts[k] = tc
        a = out[k]
        # from land: onto land (toward people, or spreading out to where there are fewer), or into the water
        tl = tc[L]
        tk, z1, p1 = S.kind[tl], z[tl], people[tl]
        to_land = tk == 0
        a[L] = np.where(to_land, np.where(p1, nl * (1 / 5.0), np.maximum(nl - z1, 0) * g.spread) * S.move[tl],
                        nl * _SWIM_RATE[tk] * can_swim)
        if g.unorg[1] != 1.0:
            a[L] *= np.where(to_land & p1 & (g.O[tl] == 0), np.float32(g.unorg[1]), np.float32(1.0))
        # from the shallows: ashore, along the shore, or out to sea
        if W.size:
            tw = tc[W]
            tk, z1, p1 = S.kind[tw], z[tw], people[tw]
            ashore = nw * (ASHORE + (ASHORE_PEOPLE - ASHORE) * p1)
            a[W] = np.where(tk == 0, ashore, np.maximum(nw - z1, 0) * _SEA_RATE[tk])
            if g.unorg[1] != 1.0:
                a[W] *= np.where((tk == 0) & p1 & (g.O[tw] == 0), np.float32(g.unorg[1]), np.float32(1.0))
        if g.resist is not None:
            a *= g.resist[tc]
        if g.qfac is not None:
            a[:] = np.where(nz >= g.qheavy, a * g.qfac[tc], a)
        a[~(valid & ~g.blocked[tc])] = 0.0
    # deep water: drift (a random direction) and hordes swimming for land
    deep_i = np.flatnonzero(dep)
    if deep_i.size:
        r = g.rng.integers(0, 4, deep_i.size) if g.stochastic else np.zeros(deep_i.size, dtype=np.int64)
        tw = g.toward[src[deep_i]]
        landward = g.rand(deep_i.size) < STRAY_LANDWARD
        r = np.where(landward & (tw >= 0), tw, r)
        horde = (nz[deep_i] >= SEA_HORDE) & (tw >= 0)
        way = np.where(horde, tw, r)
        amt = np.where(horde, nz[deep_i] * HORDE_SWIM, nz[deep_i] * DRIFT)
        for k, d in enumerate(ZOMBIE_DIRS):
            t = S.nbr[d][src[deep_i]]
            ok = (way == k) & (t >= 0)
            ok &= ~g.blocked[np.where(t >= 0, t, 0)]
            out[k, deep_i] = np.where(ok, amt, out[k, deep_i])
    if g.thaw is not None:                               # (frozen stiff: they don't move)
        out *= g.thaw[src]
    tot = out.sum(axis=0)
    cap = nz * MAX_OUT
    scale = np.where(tot > cap, cap / np.maximum(tot, 1e-9), 1.0).astype(np.float32)
    out *= scale * g.jitter(src.size)
    out += g.rand(src.size)
    moved = np.floor(out, out=out)
    tot = moved.sum(axis=0)
    over = tot > nz
    if over.any():
        moved[:, over] = np.floor(moved[:, over] * (nz[over] / np.maximum(tot[over], 1e-9)))
        tot = moved.sum(axis=0)
    z[src] = nz - tot
    _scatter_add(z, tgts.ravel(), moved.ravel())
    if deep_i.size:
        dd_ = np.flatnonzero(g.deep & (z > 0))
        stray = z[dd_] < SEA_HORDE
        rate = np.where(stray, STRAY_LOSS, SEA_LOSS) / MOVE_PASSES
        loss = np.floor(z[dd_] * rate + (g.rand(dd_.size) if g.stochastic else 0.0))
        loss = np.where(stray & (g.rand(dd_.size) < STRAY_LOSS / MOVE_PASSES), z[dd_], loss)
        z[dd_] = np.maximum(z[dd_] - loss, 0)


def _scatter_add(a, idx, w):
    """a[idx] += w, summing repeats (np.add.at: fast in numpy 2)."""
    np.add.at(a, idx, w.astype(a.dtype, copy=False))


def _move_people(g, h, z, d):
    """The original flight rule: people on a tile with zombies send 1/8 to each neighbouring tile (up to two away)
    that is better defended, a mountain, or has fewer zombies - but only over land, and not into shut borders."""
    S = g.S
    src = np.flatnonzero((z > 5) & (h > 0) & g.land)
    if src.size == 0:
        return
    hs, zs, ds, ms = h[src], z[src], d[src], g.mountain[src]
    q = np.floor(hs / 8.0)
    jit = g.jitter(src.size)
    outs, tgts = [], []
    for dd in HUMAN_DIRS:
        t = S.nbr[dd][src]
        valid = t >= 0
        tc = np.where(valid, t, 0)
        go = valid & g.land[tc] & ((ds < d[tc] + 1) | (g.mountain[tc] & ~ms) | ((zs > z[tc]) & (ds <= d[tc])))
        if g.shut is not None:
            go &= ~(g.shut[tc] & (g.O[tc] != g.O[src]))
        outs.append(np.where(go, np.minimum(np.floor(q * jit), np.maximum(255 - h[tc], 0)), 0.0))
        tgts.append(tc)
    out = np.stack(outs)
    tot = out.sum(axis=0)
    scale = np.where(tot > hs, hs / np.maximum(tot, 1e-9), 1.0)
    out = np.floor(out * scale)
    h[src] = hs - out.sum(axis=0)
    _scatter_add(h, np.concatenate(tgts), out.ravel())


SCREENING = 0.85           # an alerted government screens passengers: flights out carry the infection this much less
TRAVEL_BAN = 0.5           # once the world is alarmed, flights between countries stop (this share of them)
LONG_HAUL = 0.1            # a long-haul flight (over LONG_HAUL_DEG) carries the infection this much as often as a short hop
LONG_HAUL_DEG = 25.0
TECH_FLY = 0.5             # (tech.TECH_FLY)
GROUNDED = 0.5             # a government in a zombie emergency grounds this share of flights from its infected airports


def _airports(world, H, Z, closed):
    """An infected airport flies the infection out (some of the time), or shuts once the zombies outnumber people.
    A government that shuts its borders shuts its airports both ways; one that is mobilized screens passengers; one in a
    zombie emergency grounds most flights (domestic ones too); and once the world is alarmed (world.alarm) flights
    between countries mostly stop."""
    O = world.O
    rnd = world.pyrng.random if world.stochastic else (lambda: 0.0)
    alert = np.array([getattr(c, "alert", 0.0) for c in world.civs])
    alarm = getattr(world, "alarm", 0.0)
    t = getattr(world, "tech", None)
    for (i, j), links in list(world.airports.items()):
        if not links:
            continue
        if t is not None and t[i, j] < TECH_FLY:          # (no power, no fuel: nothing flies - tech.py)
            continue
        z, h = Z[i, j], H[i, j]
        if z > 10 or (h < 5 and z > 0):
            if z > h:
                del world.airports[(i, j)]
                continue
            home = O[i, j]
            if closed and home in closed:
                continue                                  # its airports are shut
            p = 0.6 * (1.0 - SCREENING * alert[home])
            if home and not world.civs[home].peace:
                p *= 1.0 - GROUNDED
            far = LONG_HAUL_DEG / float(world.meta.get("res", 0.5)) if hasattr(world, "meta") else 10 ** 9
            for (r, c) in links:
                dest = O[r, c]
                if closed and dest in closed:
                    continue
                q = p * (1.0 - TRAVEL_BAN * alarm) if dest != home else p
                dc = abs(c - j)
                if world.wrap:
                    dc = min(dc, world.cols - dc)
                if (r - i) ** 2 + dc ** 2 > far * far:
                    q *= LONG_HAUL
                if Z[r, c] < 1 and rnd() < q:
                    Z[r, c] += 1
