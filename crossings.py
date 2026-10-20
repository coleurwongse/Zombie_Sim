"""Hordes crossing the water: now and then a big horde on a coast pushes a chunk of itself into the sea, and it makes
it across to another landmass - over the Channel, the Bering Strait, the Strait of Gibraltar, between islands, or
(less often) across an ocean.  It's one of the main ways the outbreak gets from continent to continent: over a game
each continent is usually reached several times and the big islands at least once.

Every CROSS_EVERY days one of the big hordes on a coast (at least CROSS_MIN zombies within 2 tiles; the bigger, the
likelier) may (CROSS_CHANCE) send off a chunk: CROSS_SHARE of the zombies around it, as a horde of CROSS_TILES tiles
that you can see on the map, swimming CROSS_SPEED tiles a day to a coast of another landmass (or, on the world map, another
continent) within CROSS_REACH
tiles over water - the nearest, but a landmass few hordes have reached yet before one many have (CROSS_NOVELTY), and
a shore with people on it first; a crossing longer than CROSS_SHORT goes ahead only CROSS_LONG of the time.  It
loses CROSS_LOSS of itself per day at sea and comes ashore as a horde.  At most CROSS_MAX are at sea at once, so the
oceans don't fill up with zombies.
"""
from collections import deque

import numpy as np

CROSS_EVERY = 2
CROSS_MIN = 300            # zombies within 2 tiles of the coastal tile
CROSS_CHANCE = 0.7         # per check, for a horde of 2 x CROSS_MIN on a coast (less for smaller ones)
CROSS_SHARE = 0.45         # of the zombies within 2 tiles of it
CROSS_TILES = (4, 16)      # the swimming horde covers this many tiles
CROSS_SPEED = 2            # tiles a day
CROSS_REACH = 80           # tiles over water at most ...
CROSS_SHORT = 12           # ... and a crossing longer than this is CROSS_LONG times as likely to be tried
CROSS_LONG = 0.5
CROSS_NOVELTY = 3.0        # a landmass counts as (1 + this x hordes that reached it already) times as far away ...
CROSS_NEW = 0.4            # ... and one no horde has reached yet as this much nearer (Krull, Fourecks, the
                           # Counterweight Continent: an island out on its own gets its turn)
CROSS_STRAIT = 4.0         # another country's coast on the same landmass (across the Channel) counts as this many
                           # times as far: hopping round a bay is a poor second to landing somewhere new
ACROSS = 3                 # another country's coast this much water away counts as across the sea (the Channel)
LANDING_TILES = 25         # a horde comes ashore spread over up to this many tiles of the shore
CROSS_LOSS = 0.01          # share lost per day at sea
CROSS_MAX = 6
CROSS_MAX_FROM = 2         # ... and at most this many from the same continent (so the busiest coasts - East Asia, East
                           # Africa - don't take every crossing: each continent with a horde on its coast gets its turn)
LANDING_GUARD = 3.0        # a shore counts as this many tiles further per level of protection above the ordinary (a
                           # horde swims round a fortified coast to land where it isn't held) ...
LANDING_BITES = 1.0        # ... and, coming ashore, bites this many people per zombie; they run inland and turn in
LANDING_BITE_REACH = 10    # BITE_TOWNS of the busiest places within this many tiles (up to half of each one's
BITE_TOWNS = 12            # people) - so a landing always starts an outbreak, even where the shore is held well
                           # enough to cut the horde itself down
SURPRISE_DAYS = 30         # a landing takes a country by surprise: for this many days its strikes and sweeps
SURPRISE_REACH = 12        # (civilization.py, aid.py) can't find the horde within this many tiles of where it came
                           # ashore yet - it gets inland and the country has a real outbreak on its hands, not a
                           # beach it can shell flat (its front line and its people still fight it, as anywhere)
LANDING_MIN = 25           # a landmass smaller than this (tiles) is no place to land: a rock, not an island
ISLAND_SHARE = 0.05        # a landmass with less than this share of all the land is an island (Britain .. Australia)
STRAND_MIN = 150           # an island with this many zombies and nobody left on it ...
STRAND_SHARE = 0.8         # ... sends this share of the zombies near its busiest shore into the sea every CROSS_EVERY
STRAND_MAX = 3             # days - at most this many from one island at sea at once (beyond CROSS_MAX)
MIN_EACH = 35              # (each tile of the swimming horde holds at least this many - so it shows)
# Hordes don't swim across lakes (water nobody can sail out of: the Caspian, the Sea of Rhun) - they walk round.


def stranded(world):
    """Islands with at least STRAND_MIN zombies and nobody living on them: {landmass id: zombies}.
    (Cached for the tick.)"""
    memo = getattr(world, "_stranded", None)
    if memo is not None and memo[0] == world.ticks:
        return memo[1]
    S = world.statics
    lm = S.landmass.ravel()
    n = int(lm.max()) + 1
    size = getattr(world, "_landmass_size", None)
    if size is None or size.size != n:
        size = world._landmass_size = np.bincount(lm, minlength=n)
    island = size < ISLAND_SHARE * float(S.land.sum())
    z = np.bincount(lm, weights=world.Z.ravel(), minlength=n)
    people = np.bincount(lm, weights=(world.H > 10).ravel(), minlength=n)
    out = {int(k): float(z[k]) for k in np.flatnonzero((z >= STRAND_MIN) & (people == 0) & island) if k > 0}
    world._stranded = (world.ticks, out)
    return out


def _leave_island(world, sea, mass, n_z):
    """The zombies of an island nobody lives on any more take to the sea - from its busiest shore, most of them."""
    S = world.statics
    if sum(1 for x in sea if x.get("island") == mass) >= STRAND_MAX:
        return
    land = S.land
    coast = land & _touches(~land) & (S.landmass == mass)
    near = world.zombie_near(3)
    cand = np.flatnonzero((coast & (near > 0)).ravel())
    if cand.size == 0:
        return
    r, c = divmod(int(cand[int(np.argmax(near.ravel()[cand]))]), world.cols)
    path = _route(world, r, c, inhabited=True)
    if path is None:
        return
    Z = world.Z
    r0, r1, c0, c1 = max(r - 3, 0), r + 4, max(c - 3, 0), c + 4
    patch = Z[r0:r1, c0:c1]
    take = np.floor(patch * STRAND_SHARE * (S.landmass[r0:r1, c0:c1] == mass)).astype(patch.dtype)
    n = int(take.sum())
    if n < MIN_EACH * CROSS_TILES[0]:
        return
    patch -= take
    size = int(np.clip(n // MIN_EACH, CROSS_TILES[0], CROSS_TILES[1]))
    sea.append(dict(path=path, i=0, z=float(n), size=size, start=(r, c), island=mass, key=getattr(world, "_cross_key", None)))
    if world.pyrng.random() < 0.25:
        from fracture import _place
        world.note(f"with nobody left to eat, a horde of {world.people(n)} leaves {_place(world, (r, c))} by sea")


def step(world):
    sea = world.__dict__.setdefault("crossings", [])
    _advance(world, sea)
    if world.ticks % CROSS_EVERY:
        return
    for mass, n_z in stranded(world).items():           # (islands eaten bare empty themselves into the sea)
        _leave_island(world, sea, mass, n_z)
    if sum(1 for x in sea if "island" not in x) >= CROSS_MAX:
        return
    S = world.statics
    land = S.land
    Z = world.Z
    near = world.zombie_near(2)
    coast = land & _touches(~land)
    cand = np.flatnonzero((coast & (near >= CROSS_MIN)).ravel())
    if cand.size == 0:
        return
    rows, cols = Z.shape
    reg = regions(world).ravel()[cand]
    busy = {}
    for x in sea:
        if "island" not in x and "from" in x:
            busy[x["from"]] = busy.get(x["from"], 0) + 1
    free = np.array([busy.get(int(g), 0) < CROSS_MAX_FROM for g in reg])
    cand, reg = cand[free], reg[free]
    if cand.size == 0:
        return
    vals = near.ravel()[cand].astype(np.float64)
    # (a continent first - each with a horde on its coast about as likely as the next - then a coast on it)
    groups, inv = np.unique(reg, return_inverse=True)
    if world.stochastic:
        top = np.zeros(groups.size)
        np.maximum.at(top, inv, vals)
        g = int(world.rng.choice(groups.size, p=np.sqrt(top) / np.sqrt(top).sum()))
        sub = np.flatnonzero(inv == g)
        i = int(sub[int(world.rng.choice(sub.size, p=vals[sub] / vals[sub].sum()))])
    else:
        i = int(np.argmax(vals))
    r, c = divmod(int(cand[i]), cols)
    chance = CROSS_CHANCE * min(1.0, vals[i] / (2.0 * CROSS_MIN))
    if world.pyrng.random() >= chance:
        return
    path = _route(world, r, c)
    if path is None:
        return
    if len(path) > CROSS_SHORT and world.pyrng.random() >= CROSS_LONG:
        return
    r0, r1, c0, c1 = max(r - 2, 0), r + 3, max(c - 2, 0), c + 3
    patch = Z[r0:r1, c0:c1]
    take = np.floor(patch * CROSS_SHARE).astype(patch.dtype)
    n = int(take.sum())
    size = int(np.clip(n // MIN_EACH, CROSS_TILES[0], CROSS_TILES[1]))
    if n < MIN_EACH * CROSS_TILES[0]:
        return
    patch -= take
    sea.append(dict(path=path, i=0, z=float(n), size=size, start=(r, c), key=getattr(world, "_cross_key", None),
                    **{"from": int(regions(world)[r, c])}))
    from fracture import _place
    world.note(f"a horde of {world.people(n)} takes to the water off {_place(world, (r, c))}")


def _touches(mask):
    out = np.zeros_like(mask)
    out[1:] |= mask[:-1]
    out[:-1] |= mask[1:]
    out[:, 1:] |= mask[:, :-1]
    out[:, :-1] |= mask[:, 1:]
    return out


def _route(world, r, c, inhabited=False):
    """The way over water from the coast at (r, c) to a coast of another landmass within CROSS_REACH steps: for every
    landmass in reach its nearest landing (a shore with people on it a little preferred); then the landmass that is
    nearest, counting one many hordes have reached already as further (CROSS_NOVELTY).  A list of water tiles ending
    with the landing, or None."""
    S = world.statics
    land = S.land
    mass = regions(world)
    rows, cols = land.shape
    home = int(mass[r, c])
    O0 = world.O0
    home_c = int(O0[r, c])
    lake = lakes(world)
    lm = S.landmass
    size = _landmass_size(world)
    peopled = np.bincount(lm.ravel(), weights=(world.H > 10).ravel(), minlength=size.size)
    alive = peopled > 0                                     # (zombies leaving an island eaten bare want people)
    from civilization import protection
    guard = LANDING_GUARD * np.maximum(protection(world) - 2.0, 0.0)
    lived = np.bincount(O0.ravel(), weights=(world.H > 10).ravel(), minlength=len(world.civs)) > 0
    prev = {}
    q = deque()
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        rr, cc = r + dr, (c + dc) % cols if world.wrap else c + dc
        if 0 <= rr < rows and 0 <= cc < cols and not land[rr, cc] and not lake[rr, cc]:
            prev[(rr, cc)] = None
            q.append((rr, cc, 1))
    best = {}                                               # landmass -> (score, water tile, landing)
    while q:
        rr, cc, d = q.popleft()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nr, nc = rr + dr, cc + dc
            if world.wrap:
                nc %= cols
            if not (0 <= nr < rows and 0 <= nc < cols):
                continue
            if land[nr, nc]:
                m = int(mass[nr, nc])
                if inhabited and not alive[S.landmass[nr, nc]]:
                    continue
                if size[lm[nr, nc]] < LANDING_MIN and peopled[lm[nr, nc]] < LANDING_MIN:    # (a rock)
                    continue
                if (m == home and d >= ACROSS and home_c and int(O0[nr, nc]) not in (0, home_c)
                        and lived[int(O0[nr, nc])]):
                    m = ("country", int(O0[nr, nc]))          # (another country across the water: the Channel -
                                                              #  while anyone lives there: else they walk round)
                if m != home:
                    score = (d - (4 if world.H[nr, nc] > 10 else 0)       # (a shore with people on it draws them,
                             + guard[nr, nc])                                 #  a fortified one doesn't)
                    if m not in best or score < best[m][0]:
                        best[m] = (score, (rr, cc), (nr, nc), d)
                continue
            if (nr, nc) in prev or d >= CROSS_REACH or lake[nr, nc]:
                continue
            prev[(nr, nc)] = (rr, cc)
            q.append((nr, nc, d + 1))
    if not best:
        return None
    reached = getattr(world, "_cross_reached", {})
    def far(k):
        n = reached.get(k, 0)
        return (max(best[k][3], 1) * (1.0 + CROSS_NOVELTY * n) * (CROSS_NEW if n == 0 else 1.0)
                * (CROSS_STRAIT if isinstance(k, tuple) else 1.0))
    m = min(best, key=far)
    _, water, landing, _ = best[m]
    world._cross_key = m
    path, cur = [landing], water
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    return _straighten(world, path[::-1])                   # water tiles from the start out, then the landing


def _line(a, b):
    """The tiles on the straight line from a to b (8-connected, a included, b included)."""
    (r0, c0), (r1, c1) = a, b
    n = max(abs(r1 - r0), abs(c1 - c0))
    if n == 0:
        return [a]
    return [(int(round(r0 + (r1 - r0) * i / n)), int(round(c0 + (c1 - c0) * i / n))) for i in range(n + 1)]


def _straighten(world, path):
    """The way over water as straight as the coasts allow: from each point on to the farthest point further along that
    can be seen over open water (a horde swims for the far shore, not along a staircase of sideways steps)."""
    land = world.statics.land
    cols = land.shape[1]
    water = path[:-1]                                       # (the last one is the landing, on land)
    if len(water) < 3:
        return path
    if world.wrap:                                          # (unwrap across the date line so lines are straight)
        base = water[0][1]
        water = [(r, base + ((c - base + cols // 2) % cols) - cols // 2) for r, c in water]
    out = [water[0]]
    i = 0
    while i < len(water) - 1:
        j = len(water) - 1
        while j > i + 1:
            if all(not land[r, c % cols] for r, c in _line(water[i], water[j])):
                break
            j -= 1
        out.extend(_line(water[i], water[j])[1:])
        i = j
    if world.wrap:
        out = [(r, c % cols) for r, c in out]
    return out + [path[-1]]


def _landmass_size(world):
    lm = world.statics.landmass
    size = getattr(world, "_landmass_size", None)
    if size is None or size.size != int(lm.max()) + 1:
        size = world._landmass_size = np.bincount(lm.ravel(), minlength=int(lm.max()) + 1)
    return size


def lakes(world):
    """Water tiles of enclosed water bodies (not the biggest one, not touching the edge of the map): lakes."""
    lk = getattr(world, "_lakes", None)
    if lk is not None and lk.shape == world.H.shape:
        return lk
    import labels
    wl, n = labels.label(~world.statics.land)
    size = np.bincount(wl.ravel(), minlength=n + 1)
    size[0] = 0
    open_ = set(np.unique(np.concatenate([wl[0], wl[-1], wl[:, 0], wl[:, -1]])).tolist())
    open_.add(int(np.argmax(size)))
    shut = np.array([i > 0 and i not in open_ for i in range(n + 1)])
    world._lakes = shut[wl]
    return world._lakes


def regions(world):
    """Per land tile, the 'shore' a crossing goes from or to: its landmass - and on the world map its continent too,
    so a horde can cross the Mediterranean, the Red Sea or the Caribbean to another continent of the same landmass."""
    reg = getattr(world, "_cross_regions", None)
    if reg is not None and reg.shape == world.H.shape:
        return reg
    S = world.statics
    reg = S.landmass.astype(np.int64) * 8
    meta = getattr(world, "meta", None) or {}
    if meta.get("real_pops") and meta.get("bounds"):
        import spread
        lon0, lon1, lat0, lat1 = meta["bounds"]
        lat = np.linspace(lat1, lat0, world.rows)[:, None] * np.ones((1, world.cols))
        lon = np.linspace(lon0, lon1, world.cols)[None, :] * np.ones((world.rows, 1))
        done = np.zeros(world.H.shape, dtype=bool)
        for k, (name, ((a0, a1, b0, b1), cuts)) in enumerate(spread.CONTINENTS.items()):
            m = (lon > a0) & (lon < a1) & (lat > b0) & (lat < b1) & ~done
            for c0, c1, d0, d1 in cuts:
                m &= ~((lon > c0) & (lon < c1) & (lat > d0) & (lat < d1))
            reg = np.where(m, reg + 1 + k, reg)
            done |= m
    world._cross_regions = reg
    return reg


_BLOB = sorted(((dr, dc) for dr in range(-2, 3) for dc in range(-2, 3) if (dr, dc) != (0, 0)),
               key=lambda d: (d[0] ** 2 + d[1] ** 2, d))


def tiles(world, x):
    """The water tiles the swimming horde `x` covers now (its head and the tiles around it)."""
    land = world.statics.land
    rows, cols = land.shape
    i = min(x["i"], len(x["path"]) - 2)
    hr, hc = x["path"][i]
    out = [(hr, hc)]
    for back in range(1, 3):                                # (a few tiles behind it on its way ...)
        if i - back >= 0:
            out.append(x["path"][i - back])
    for dr, dc in _BLOB:                                    # (... and the water round its head)
        if len(out) >= x["size"]:
            break
        rr, cc = hr + dr, (hc + dc) % cols if world.wrap else hc + dc
        if 0 <= rr < rows and 0 <= cc < cols and not land[rr, cc] and (rr, cc) not in out:
            out.append((rr, cc))
    return out[:x["size"]]


def _advance(world, sea):
    keep = []
    for x in sea:
        x["i"] += CROSS_SPEED
        x["z"] *= (1.0 - CROSS_LOSS)
        if x["i"] < len(x["path"]) - 1:
            keep.append(x)
            continue
        lr, lc = x["path"][-1]                              # ashore: the horde spreads out along the shore
        land = world.statics.land
        rows, cols = land.shape
        spots = [(lr + dr, (lc + dc) % cols if world.wrap else lc + dc) for dr, dc in [(0, 0)] + _BLOB]
        spots = [(rr, cc) for rr, cc in spots if 0 <= rr < rows and 0 <= cc < cols and land[rr, cc]]
        spots = ([t for t in spots if world.D[t] < 7] or spots)[:LANDING_TILES]     # (not into a fortress wall)
        z = int(x["z"])
        _bite(world, lr, lc, z)
        left = z
        for k, (rr, cc) in enumerate(spots):
            share = left // (len(spots) - k)
            put = min(share, 255 - int(world.Z[rr, cc]))
            world.Z[rr, cc] += put
            left -= put
        m = x.get("key")
        if m is None:
            m = int(regions(world)[lr, lc])
        reached = world.__dict__.setdefault("_cross_reached", {})
        reached[m] = reached.get(m, 0) + 1
        world.__dict__.setdefault("_cross_log", []).append((world.ticks, lr, lc))
        world._surprise = None
        from fracture import _place
        world.note(f"a horde of {world.people(z)} comes ashore near {_place(world, (lr, lc))}")
    sea[:] = keep


def surprise(world):
    """Tiles near a landing of the last SURPRISE_DAYS days (bool grid, or None if there are none): strikes and sweeps
    can't find the horde there yet.  Cached for the tick."""
    memo = getattr(world, "_surprise", None)
    if memo is not None and memo[0] == world.ticks:
        return memo[1]
    fresh = [(r, c) for t, r, c in getattr(world, "_cross_log", []) if world.ticks - t <= SURPRISE_DAYS]
    out = None
    if fresh:
        from civilization import within
        seed = np.zeros(world.H.shape, dtype=bool)
        for r, c in fresh:
            seed[r, c] = True
        out = within(world, seed, SURPRISE_REACH)
    world._surprise = (world.ticks, out)
    return out


def _bite(world, lr, lc, z):
    """A horde coming ashore bites LANDING_BITES people per zombie before anyone can stop it - and the bitten don't
    turn on the beach: they run, and turn in the towns behind it (BITE_TOWNS of the busiest places within
    LANDING_BITE_REACH tiles, at most half of each one's people): the outbreak starts behind the coast's defenses."""
    n = LANDING_BITES * z
    rows, cols = world.H.shape
    R = LANDING_BITE_REACH
    r0, r1 = max(lr - R, 0), min(lr + R + 1, rows)
    cs = np.arange(lc - R, lc + R + 1)
    cs = cs % cols if world.wrap else cs[(cs >= 0) & (cs < cols)]
    H = world.H[r0:r1][:, cs].astype(np.int64)
    yy, xx = np.nonzero(H > 10)
    if n <= 0 or yy.size == 0:
        return 0
    k = min(BITE_TOWNS, yy.size)
    wts = H[yy, xx].astype(np.float64) * np.where(world.D[r0:r1][:, cs][yy, xx] >= 7, 0.1, 1.0)   # (forts: seldom)
    pick = (world.rng.choice(yy.size, k, replace=False, p=wts / wts.sum()) if world.stochastic
            else np.argsort(-wts)[:k])
    yy, xx = yy[pick], xx[pick]
    room = H[yy, xx] // 2
    take = np.minimum(np.floor(room * min(1.0, n / max(room.sum(), 1))).astype(np.int64),
                      255 - world.Z[r0:r1][:, cs][yy, xx].astype(np.int64))
    take = np.maximum(take, 0)
    rr, cc = r0 + yy, cs[xx]
    world.H[rr, cc] -= take.astype(world.H.dtype)
    world.Z[rr, cc] += take.astype(world.Z.dtype)
    return int(take.sum())


def at_sea(world):
    """{(r, c): zombies} for the hordes swimming now (for the map)."""
    out = {}
    for x in getattr(world, "crossings", []):
        ts = tiles(world, x)
        for t in ts:
            out[t] = out.get(t, 0) + x["z"] / len(ts)
    return out
