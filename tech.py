"""Technology and infrastructure, place by place: power, fuel, factories, hospitals, the people who know how to run
them.  world.tech (per tile, 0..1): 1 = what the place had before the outbreak, 0 = nothing (hand tools, wood fires,
herbs) - one region can keep its grid running while the next has gone back to the plough.

Keeping it up   a district keeps its technology while there are people enough around it (TECH_REACH tiles) to run
                it: TECH_KEEP of the people who lived round it before keep everything going, fewer keep less.
                Land nobody governs keeps at most TECH_STATELESS (no grid without a state), a country's far
                provinces less (trade.supply: spare parts and fuel come from the centre) - overseas holdings
                excepted: they are on their own anyway.
Losing it       above what it can keep up, it decays (TECH_LOSS a day: machines break, fuel runs out, the
                engineers die) - fast where nobody is left at all (TECH_RUIN: ruins - down to what can be
                salvaged, TECH_SALVAGE).
Getting it back below what it can keep up it is rebuilt - slowly on its own (TECH_REBUILD), much faster where a
                better-off place is near to learn from (TECH_SPREAD x the gap: its own country's, across a border
                less, TECH_FOREIGN) and from trading partners (trade.py: TECH_TRADE x the gap in the countries'
                levels).  Restorationists rebuild faster (ideology.py).
What it does    (every effect is x 1 at the pre-outbreak level, so the outbreak itself plays out as before)
                materials x TECH_MAT[0] + TECH_MAT[1] x tech, food x TECH_FOOD[0] + .. (economy.py), killing zombies
                x TECH_FIGHT[0] + .. (guns and ammunition: engine._bites), sickness kills x 1 - TECH_MEDICINE x tech
                less (disease.py), and only districts with power fly (TECH_FLY: engine._airports), launch missiles
                (TECH_NUKES: nukes.py) or send ships across the sea (TECH_SAIL: expeditions, settlers, trade).
civ.tech is a country's level, by its people.
"""
import numpy as np

from civilization import box_sum

TECH_EVERY = 10
TECH_REACH = 6
TECH_KEEP = 0.35
TECH_FLOOR_POP = 60        # (people round a place before that count as at least this many: the empty steppe has no
                           #  factories to lose, and keeps what little it had)
TECH_STATELESS = 0.5
TECH_LOSS = 0.0012
TECH_RUIN = 0.005
TECH_SALVAGE = 0.2         # (what ruins keep: machines that can be got going again, books, tools - salvage)
TECH_REBUILD = 0.0012
TECH_SPREAD = 0.008
TECH_FOREIGN = 0.3
TECH_TRADE = 0.002
TECH_MAT = (0.35, 0.65)
TECH_FOOD = (0.8, 0.2)
TECH_FIGHT = (0.6, 0.4)
TECH_MEDICINE = 0.7
TECH_FLY = 0.5
TECH_NUKES = 0.6
TECH_SAIL = 0.25


def level(world):
    """world.tech, made on first use (everything at its pre-outbreak level)."""
    t = getattr(world, "tech", None)
    if t is None or t.shape != world.H.shape:
        t = world.tech = np.ones(world.H.shape, dtype=np.float32)
    return t


def mult(world, pair):
    """pair[0] + pair[1] x tech, per tile (None while every place is at its old level)."""
    t = getattr(world, "tech", None)
    if t is None or getattr(world, "_tech_full", True):
        return None
    return (pair[0] + pair[1] * t).astype(np.float32)


def at(world, rc):
    t = getattr(world, "tech", None)
    return 1.0 if t is None else float(t[rc])


def _before(world):
    b = getattr(world, "_tech_before", None)
    if b is None or b.shape != world.H.shape:
        b = world._tech_before = np.maximum(box_sum(np.maximum(world.H0, 0).astype(np.int64), TECH_REACH),
                                            TECH_FLOOR_POP).astype(np.float32)
    return b


def sustain(world):
    """0..1 per tile: what its district can keep running now."""
    H, O = world.H, world.O
    now = box_sum(np.where(world.land & (H > 10), H, 0).astype(np.int64), TECH_REACH).astype(np.float32)
    keep = np.clip(now / (TECH_KEEP * _before(world)), 0, 1)
    keep = np.where(O > 0, keep, np.minimum(keep, TECH_STATELESS))
    import trade
    sup = trade.supply(world)
    if sup is not None:
        keep = keep * (0.6 + 0.4 * sup)
    return keep.astype(np.float32)


def _nbr_max(t, O, wrap):
    """Highest level within 2 steps: among its own country's tiles, and among any."""
    from engine import shift
    best_same = t.copy()
    best_any = t.copy()
    for _ in range(2):
        bs, ba = best_same.copy(), best_any.copy()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            nb_s = shift(best_same, dr, dc, wrap, 0)
            nb_o = shift(O, dr, dc, wrap, -1)
            bs = np.maximum(bs, np.where(nb_o == O, nb_s, 0))
            ba = np.maximum(ba, shift(best_any, dr, dc, wrap, 0))
        best_same, best_any = bs, ba
    return best_same, best_any


def step(world):
    if world.ticks % TECH_EVERY or getattr(world, "H0", None) is None:
        return
    t = level(world)
    H, O = world.H, world.O
    days = float(TECH_EVERY)
    keep = sustain(world)
    lived = world.land & (H > 10)
    nobody = box_sum(lived.astype(np.int32), TECH_REACH) == 0
    # losing it
    keep = np.where(nobody, np.maximum(keep, TECH_SALVAGE), keep)
    over = t > keep
    loss = np.where(nobody, TECH_RUIN, TECH_LOSS) * days
    t[:] = np.where(over, np.maximum(keep, t - loss), t)
    # getting it back: on its own, and from those nearby who still have it
    same, any_ = _nbr_max(np.where(lived, t, 0).astype(np.float32), O, world.wrap)
    import ideology
    rate = np.ones(len(world.civs), dtype=np.float32)
    for c in world.civs:
        rate[c.id] = ideology.mod(c, "tech")
    r = rate[O]
    gain = (TECH_REBUILD * (keep - t) + TECH_SPREAD * (np.maximum(same - t, 0) + TECH_FOREIGN * np.maximum(any_ - t, 0)))
    gain = gain * r * days
    under = (t < keep) & lived
    t[:] = np.where(under, np.minimum(keep, t + np.maximum(gain, 0)), t)
    _trade_gain(world, t, days)
    t[~world.land] = 0
    world._tech_full = bool((t[lived] >= 0.999).all()) if lived.any() else True
    _civ_levels(world)


def _trade_gain(world, t, days):
    import trade
    routes = trade.routes(world)
    if not routes:
        return
    lv = {c.id: getattr(c, "tech", 1.0) for c in world.civs}
    boost = np.zeros(len(world.civs), dtype=np.float32)
    for k in routes:
        a, b = tuple(k)
        boost[a] = max(boost[a], lv.get(b, 0) - lv.get(a, 0))
        boost[b] = max(boost[b], lv.get(a, 0) - lv.get(b, 0))
    if not boost.any():
        return
    g = boost[world.O] * TECH_TRADE * days
    t += np.where((world.O > 0) & (world.H > 10), g, 0)
    np.minimum(t, 1.0, out=t)


def _civ_levels(world):
    n = len(world.civs)
    o = world.O.ravel()
    hp = np.where(world.H > 10, world.H, 0).ravel().astype(np.float64)
    pop = np.bincount(o, weights=hp, minlength=n)
    lv = np.bincount(o, weights=hp * world.tech.ravel(), minlength=n) / np.maximum(pop, 1)
    for c in world.civs:
        if c.id:
            c.tech = float(lv[c.id]) if pop[c.id] > 0 else getattr(c, "tech", 1.0)


def civ_level(c):
    return float(getattr(c, "tech", 1.0))
