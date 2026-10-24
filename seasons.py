"""Seasons: the year turns.  Snow in the north (and the mountains), harvests that come in summer and autumn, and hard
winters.

Climate (cold(), worked out once per map): how snowy a place's winters are, 0..1.  On the world maps by latitude
(COLD_LAT_FROM degrees and up, full at COLD_LAT_FULL) - on the hand-drawn maps by meta "climate": "north" (the top of
the map is the cold north: Forodwaith, Angband) or "hub" (the Discworld: cold at the Hub - meta "hub_at" - warm at the Rim) - plus the
ground: tundra and ice, and mountains and highlands at any latitude.  The southern hemisphere has its winter in July.

Snow (snow(), per tile, 0..1, every day): where the winter is cold enough for the place - a place with cold 1 lies
under snow most of the year, one with cold 0.3 only in the depth of winter.

Frozen dead (frozen()): in snow the dead freeze - up to FREEZE_MAX of them where the snow lies deep: they can't move
(engine, zombies.transport: hordes stand still), they hardly bite (FROZEN_BITE) and they are much easier to kill
(FROZEN_KILL).  Wherever people live within CULL_REACH of them, the people go out in the snow and smash the frozen
dead where they stand (CULL_*: at most CULL_MAX_DAY of them a day - a winter clears a good part of the dead round the
towns, never all of them, and none out in the wilds).  In the spring thaw they wake up again.

Harvests (harvest()): food grows with the season - nothing under the snow, the most in late summer - x 1 on average
over the year: a country that fed itself still does, but has to get through the winter on what it stored (larger
stores where winters are long: economy.py).  The tropics hardly notice.
Winter hardship (economy.py, disease.py): people eat more in the cold (WINTER_EAT), heating costs materials
(FUEL_SHARE of the country's income, x the share of its people under snow) - a country out of materials in the snow
loses people to the cold (EXPOSURE) - and sickness spreads faster indoors.  The north gets the frozen dead; it pays for
them in famine, cold and fever.
"""
import datetime

import numpy as np

from terrain import TUNDRA, ICE, MOUNTAIN, HIGHLANDS

COLD_LAT_FROM = 42.0       # (degrees: no snow to speak of nearer the equator than this, at sea level) ...
COLD_LAT_FULL = 70.0       # ... full winters from here
COLD_NORTH = (0.6, 1.0)    # meta climate "north": cold from this share of the way up the map (0 = bottom) to full
COLD_HUB = (0.35, 0.05)    # meta climate "hub": cold within this share of the map's half-width of the centre, full at
COLD_GROUND = {TUNDRA: 0.9, ICE: 1.0, MOUNTAIN: 0.45, HIGHLANDS: 0.2}    # ... the second; the ground adds this (smoothed)
COLD_SMOOTH = 3
WINTER_PEAK = 15           # (day of the year: mid-January in the north, mid-July in the south)
SNOW_RAMP = 0.3            # snow comes in over this much of the winter curve ...
SNOW_COLD = 0.8            # ... once it is past 1 - this x cold
FREEZE_FROM = 0.2          # snow deeper than this freezes the dead ...
FREEZE_FULL = 0.75         # ... FREEZE_MAX of them from here
FREEZE_MAX = 0.97
FROZEN_BITE = 0.9          # a frozen zombie bites this much less ...
FROZEN_KILL = 2.5          # ... and is (1 + this) x as easy to kill (engine._bites)
CULL_EVERY = 2
CULL_REACH = 3
CULL_RATE = 0.004          # frozen dead smashed per tile per day per person within reach (people up to 4 x the dead) ...
CULL_MAX_DAY = 0.008       # ... but at most this share of a tile's dead a day
CULL_MIN_H = 20
HARVEST_SWING = (0.15, 0.6)  # food grows 1 +- (this + that x cold) over the year (the snow: nothing)
WINTER_EAT = 0.15          # people under full snow eat this much more
FUEL_SHARE = 0.3           # heating: this share of a country's materials income, x the share of its people under snow
EXPOSURE = 0.002           # share of the people under snow lost to the cold each day where there is no fuel (x snow)
EXPOSURE_WILD = 0.0006     # ... and of people nobody governs (they burn wood; x snow)


def _lat_rows(world):
    b = world.meta.get("bounds") if getattr(world, "meta", None) else None
    if not b:
        return None
    return b[3] - (np.arange(world.rows) + 0.5) * float(world.meta.get("res", 0.5))


def _climate(world):
    meta = getattr(world, "meta", None) or {}
    c = meta.get("climate")
    if c:
        return c
    b = meta.get("bounds")
    if b and b[1] - b[0] >= 300:
        return "lat"
    return None


def cold(world):
    """0..1 per tile: how snowy its winters are (worked out once)."""
    c = getattr(world, "_cold", None)
    if c is not None and c.shape == world.H.shape:
        return c
    rows, cols = world.H.shape
    kind = _climate(world)
    base = np.zeros((rows, cols), dtype=np.float32)
    if kind == "lat":
        lat = _lat_rows(world)
        base[:] = np.clip((np.abs(lat) - COLD_LAT_FROM) / (COLD_LAT_FULL - COLD_LAT_FROM), 0, 1)[:, None]
    elif kind == "north":
        up = 1.0 - (np.arange(rows) + 0.5) / rows
        base[:] = np.clip((up - COLD_NORTH[0]) / (COLD_NORTH[1] - COLD_NORTH[0]), 0, 1)[:, None]
    elif kind == "hub":
        rr, cc = np.indices((rows, cols))
        hr, hc = (getattr(world, "meta", None) or {}).get("hub_at", (rows / 2.0, cols / 2.0))
        d = np.hypot(rr - hr, cc - hc) / (min(rows, cols) / 2.0)
        base[:] = np.clip((COLD_HUB[0] - d) / (COLD_HUB[0] - COLD_HUB[1]), 0, 1)
    ground = np.zeros((rows, cols), dtype=np.float32)
    for t, v in COLD_GROUND.items():
        ground[world.T == t] = v
    from civilization import box_sum
    k = (2 * COLD_SMOOTH + 1) ** 2 * 1000.0               # (box_sum counts in integers: in thousandths)
    ground = box_sum(np.rint(ground * 1000).astype(np.int32), COLD_SMOOTH) / k
    base = box_sum(np.rint(base * 1000).astype(np.int32), COLD_SMOOTH) / k if kind is not None else base
    c = np.clip(np.maximum(base, ground) + 0.5 * np.minimum(base, ground), 0, 1).astype(np.float32)
    c[~world.statics.land] = 0
    world._cold = c
    return c


def _south(world):
    s = getattr(world, "_south_rows", None)
    if s is None or s.shape[0] != world.rows:
        lat = _lat_rows(world) if _climate(world) == "lat" else None
        s = world._south_rows = (lat < 0) if lat is not None else np.zeros(world.rows, dtype=bool)
    return s


def winter_curve(world, tick=None):
    """(north, south): 0 in midsummer .. 1 in midwinter, for today."""
    d = world.start_date + datetime.timedelta(days=world.ticks if tick is None else tick)
    doy = d.timetuple().tm_yday
    a = 0.5 + 0.5 * np.cos(2 * np.pi * (doy - WINTER_PEAK) / 365.25)
    return float(a), float(1.0 - a)


def _today(world):
    memo = getattr(world, "_season_memo", None)
    if memo is not None and memo[0] == world.ticks and memo[1].shape == world.H.shape:
        return memo
    n, s = winter_curve(world)
    w = np.where(_south(world), s, n).astype(np.float32)[:, None]            # (rows, 1)
    cd = cold(world)
    snow = _snow(cd, w)
    frozen = (np.clip((snow - FREEZE_FROM) / (FREEZE_FULL - FREEZE_FROM), 0, 1) * FREEZE_MAX).astype(np.float32)
    if _climate(world) is None:
        swing = (HARVEST_SWING[1] * cd).astype(np.float32)
    else:
        swing = (HARVEST_SWING[0] + HARVEST_SWING[1] * cd).astype(np.float32)
    harvest = np.clip(1.0 - swing * (2.0 * w - 1.0), 0, None) * (1.0 - snow) * _norm(world)
    world._season_memo = memo = (world.ticks, snow, frozen, harvest.astype(np.float32), w)
    return memo


def _snow(cd, w):
    return (np.clip((w - (1.0 - SNOW_COLD * cd)) / SNOW_RAMP, 0, 1) * (cd > 0.12)).astype(np.float32)


def _norm(world):
    """Per tile: what makes its harvests come to 1 x a year's eating, winter appetite included (worked out once, by
    cold, from a whole year's curve)."""
    nm = getattr(world, "_harvest_norm", None)
    if nm is not None and nm.shape == world.H.shape:
        return nm
    cd = cold(world)
    levels = np.linspace(0, 1, 101, dtype=np.float32)[:, None]
    w = (0.5 + 0.5 * np.cos(2 * np.pi * (np.arange(365) - WINTER_PEAK) / 365.25)).astype(np.float32)[None, :]
    sn = _snow(levels, w)
    lo, hi = (HARVEST_SWING if _climate(world) is not None else (0.0, HARVEST_SWING[1]))
    raw = np.clip(1.0 - (lo + hi * levels) * (2.0 * w - 1.0), 0, None) * (1.0 - sn)
    table = (1.0 + WINTER_EAT * sn.mean(axis=1)) / np.maximum(raw.mean(axis=1), 1e-3)
    nm = world._harvest_norm = table[np.clip(np.rint(cd * 100), 0, 100).astype(np.int64)].astype(np.float32)
    return nm


def store_days(cold_share):
    """Days of food a country stores, by how cold its people live (economy.FOOD_CAP_TICKS at least): almost enough
    to see an ordinary winter through - a bad harvest, a war, the dead in the fields, and it isn't."""
    return max(0.0, 0.95 * (30.0 + 230.0 * cold_share))


def snow(world):
    return _today(world)[1]


def frozen(world):
    """0..1 per tile: the share of the dead there frozen stiff (None: nowhere)."""
    f = _today(world)[2]
    return f if f.any() else None


def harvest(world):
    """Food grown today x, per tile (1 on average over the year)."""
    return _today(world)[3]


def season_name(world):
    n, _ = winter_curve(world)
    d = world.start_date + datetime.timedelta(days=world.ticks)
    m = d.month
    north = ("winter", "winter", "spring", "spring", "spring", "summer", "summer", "summer", "autumn", "autumn",
             "autumn", "winter")[m - 1]
    return north


def step(world):
    f = frozen(world)
    total = float(world.Z.sum())
    froze = float((world.Z * f).sum()) if f is not None else 0.0
    world.frozen_dead = froze
    was = getattr(world, "_frozen_was", 0.0)
    if total > 200:                                       # (the log: the dead freeze, the dead wake)
        if froze >= 0.25 * total and was < 0.25 * total and froze > 300:
            world.note(f"winter: the snow freezes the dead in the cold lands ({world.people(froze)} frozen stiff) - "
                       "the towns go out to smash them")
        elif froze < 0.08 * total and was >= 0.08 * total and was > 300:
            world.note(f"spring thaw: the frozen dead wake up again ({world.people(was)} that were frozen)")
    world._frozen_was = froze
    world.last_culled = 0
    if f is not None and world.ticks % CULL_EVERY == 0:
        world.last_culled = _cull(world, f)


def _cull(world, f):
    Z, H = world.Z, world.H
    hit = (Z > 0) & (f > 0.3)
    if not hit.any():
        return 0
    from engine import active_windows
    from civilization import box_sum
    total = 0
    for win, wrap in active_windows(world, hit, CULL_REACH + 1):
        Zw, Hw, fw = Z[win], H[win], f[win]
        people = box_sum(np.where(world.land[win] & (Hw > 10), Hw, 0).astype(np.int32), CULL_REACH)
        m = hit[win] & (people >= CULL_MIN_H)
        if not m.any():
            continue
        z = Zw[m].astype(np.float64)
        want = fw[m] * CULL_RATE * np.minimum(people[m], 4 * z) * CULL_EVERY
        cap = z * CULL_MAX_DAY * CULL_EVERY
        rnd = world.rng.random(z.size) if world.stochastic else 0.5
        kill = np.minimum(z, np.floor(np.minimum(want, cap) + rnd))
        Zw[m] = (z - kill).astype(Zw.dtype)
        total += int(kill.sum())
    return total


def winter_load(world):
    """Per government id: the share of its people under snow (x how deep).  Cached for the day."""
    memo = getattr(world, "_wload", None)
    if memo is not None and memo[0] == world.ticks and memo[1].size == len(world.civs):
        return memo[1]
    sn = snow(world)
    n = len(world.civs)
    o = world.O.ravel()
    hp = np.maximum(world.H, 0).ravel().astype(np.float64)
    pop = np.bincount(o, weights=hp, minlength=n)
    cold_pop = np.bincount(o, weights=hp * sn.ravel(), minlength=n) if sn.any() else np.zeros(n)
    out = cold_pop / np.maximum(pop, 1)
    world._wload = (world.ticks, out)
    return out
