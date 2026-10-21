"""The turning point: countries that survive the first shock adapt - and hordes with nothing left to eat waste away.

Resolve      a government that keeps fighting (zombies in its region) while it still holds a fair part of its
             people (MIN_HELD of its peak) adapts over about ADAPT_TICKS days: soldiers learn how to fight them,
             industry turns to the war, people stop panicking.  civ.resolve goes 0 -> 1 and strengthens its front
             line (front.py), its sweeps and strikes, its training, its morale (losses shrink, it can recover while
             the line merely holds) and its readiness to counter-attack (reclaim, offensive).  It fades slowly in
             peacetime.  So the outbreak does its damage first - a fresh outbreak meets a country at resolve 0 - and
             the fight turns later, if there's anything left to turn it with.
Turning      once resolve passes TURN_AT and the zombies around it have stopped growing, the country rallies
point        (morale +TURN_MORALE, noted in the log): from there on it fortifies, rebuilds and takes ground back.
Militias     on a living government's land, and patrols up to PATROL_REACH tiles beyond its people, hunt down lone
             stragglers (MILITIA_Z or fewer on a tile, no horde next to them); lone stragglers far from anyone starve
             fast (DUST_ROT).  Otherwise a thin dust of strays over an emptied continent keeps anyone resettling it.
None of this starts before ADAPT_START days: the outbreak first spreads at full speed over large parts of continents.
Starvation   zombies with no people within ROT_REACH tiles slowly waste away (ROT per day): hordes that have eaten
             a region bare thin out, which is what lets survivors retake it.  Zombies near people don't starve.
Terrain also matters for the line itself (front.py): a front on mountains, hills, marsh or desert, or behind a river
or the coast, holds far better - which is where the turning point usually comes.
"""
import numpy as np

from civilization import within, CALM_ZOMBIES

ADAPT_START = 70           # days into the outbreak before anyone has learned anything (it spreads at full speed till then)
ADAPT_TICKS = 80
RESOLVE_FADE = 0.003       # per day without a fight
MIN_HELD = 0.15            # share of its peak population it must still hold to keep adapting
TURN_AT = 0.6
TURN_MORALE = 3
ROT = 0.004                # share of the zombies far from any people lost per day
ROT_REACH = 4
ROT_EVERY = 5
MILITIA_Z = 3              # on a living government's land, groups of at most this many zombies (stragglers) ...
MILITIA = 0.5              # ... are hunted down: this chance per ROT_EVERY days (lone ones: no horde within 2 tiles)
PATROL_REACH = 6           # ... also on unclaimed land this close to a living government's people (patrols)
DUST_ROT = 0.2             # lone stragglers (MILITIA_Z or fewer) with nobody near starve this fast per ROT_EVERY days


def step(world):
    if world.ticks < ADAPT_START:
        return
    for c in world.civs:
        if not c.ai or c.collapsed or c.is_anarchy or not c.m:
            continue
        r = getattr(c, "resolve", 0.0)
        fighting = c.m.get("zone_z", 0) >= CALM_ZOMBIES
        held = c.m.get("pop", 0) >= MIN_HELD * max(c.peak_pop, 1.0)
        if fighting and held:
            r = min(1.0, r + 1.0 / ADAPT_TICKS)
        elif not fighting:
            r = max(0.0, r - RESOLVE_FADE)
        c.resolve = r
        if (r >= TURN_AT and fighting and not getattr(c, "turned", False) and c.m.get("growth", 0.0) <= 0.0
                and c.morale >= 3):
            c.turned = True
            c.morale = min(10, c.morale + TURN_MORALE)
            world.note(f"TURNING POINT: {c.name} holds the line and starts to push back")
        elif not fighting and r < 0.2:
            c.turned = False
    if world.ticks % ROT_EVERY == 0:
        rot(world)


def rot(world):
    Z = world.Z
    if not Z.any():
        return
    # stragglers in governed land are hunted down by militias and patrols (a country at peace has no front line)
    live = np.zeros(len(world.civs), dtype=bool)
    for c in world.civs:
        live[c.id] = bool(c.id and c.ai and not c.collapsed)
    # (and on the unclaimed land around their people: patrols - this is what lets them resettle it)
    from engine import active_window
    win, _ = active_window(world, Z > 0, max(ROT_REACH, PATROL_REACH) + 1)
    if win is None:
        return
    Zw = Z[win]
    stray = (Zw > 0) & (Zw <= MILITIA_Z) & (world.zombie_near(2)[win] <= 2 * MILITIA_Z)
    patrolled = live[world.O[win]] | within(world, live[world.O[win]] & (world.H[win] > 10), PATROL_REACH, win)
    rr, cc = np.nonzero(stray & patrolled)
    if rr.size:
        hit = (world.rng.random(rr.size) < MILITIA) if world.stochastic else np.ones(rr.size, dtype=bool)
        Zw[rr[hit], cc[hit]] = 0
    alone = ~within(world, world.H[win] > 10, ROT_REACH, win) & world.land[win]
    rr, cc = np.nonzero((Zw > 0) & (Zw <= MILITIA_Z) & alone)      # stragglers with nothing to eat: soon gone
    if rr.size:
        hit = (world.rng.random(rr.size) < DUST_ROT) if world.stochastic else np.zeros(rr.size, dtype=bool)
        Zw[rr[hit], cc[hit]] = 0
    lone = (Zw > 0) & alone
    import hordes                                       # (zombies holding taken land near people don't starve)
    lone &= ~hordes.occupied(world)[win]
    import zombies                                      # (a horde on the march toward people isn't starving yet)
    way, far = zombies.far_scent(world)
    k = zombies.FAR_CELL
    gr = np.arange(win[0].start or 0, (win[0].start or 0) + Zw.shape[0]) // k
    gc = np.arange(win[1].start or 0, (win[1].start or 0) + Zw.shape[1]) // k
    lone &= ~(way[np.ix_(gr, gc)] >= 0)
    plan_ = getattr(world, "_horde_plan", None)          # (nor is a horde marching on a target: hordes.py)
    if plan_ is not None:
        hk = plan_["k"]
        R, C = plan_["shape"]
        hr = np.minimum(np.arange(win[0].start or 0, (win[0].start or 0) + Zw.shape[0]) // hk, R - 1)
        hc = np.minimum(np.arange(win[1].start or 0, (win[1].start or 0) + Zw.shape[1]) // hk, C - 1)
        lone &= ~(plan_["dirs"][np.ix_(hr, hc)] >= 0)
    rr, cc = np.nonzero(lone)
    if rr.size == 0:
        return
    z = Zw[rr, cc]
    frac = world.rng.random(rr.size) if world.stochastic else 0.5
    Zw[rr, cc] = z - np.minimum(z, np.floor(z * ROT * ROT_EVERY + frac).astype(z.dtype))


def r(civ):
    """A government's resolve (0..1)."""
    return getattr(civ, "resolve", 0.0)
