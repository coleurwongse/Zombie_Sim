"""Zombies hunt people.

The horde is drawn to people: every tile with zombies that smells prey sends a share of its zombies one step
uphill, toward the neighbour with the strongest scent.  The scent spreads over walkable land only (not across water,
not through fortresses), fading with every step, so zombies only head for people they can actually reach - they don't
pile up on a beach or against a fortress wall because there are people on the far side of it.
People on land nobody governs (no organized defense) smell strongest; people on governed land smell too
(GOVERNED_SCENT), so hordes come up to a nation's actual border and press against it instead of stopping in a dead
zone in front of it.  Standing fortifications (defense 7) give off no scent.  Rough ground carries the scent badly (mountains hardly at
all: terrain.MOVE), so hordes follow passes and valleys round a range rather than over it - and hunting zombies move
into rough ground more slowly too.  Zombies are conserved.
"""
import numpy as np

from engine import shift
from civilization import DIRECTIONS

HUNT_REACH = 16           # how far (steps over land) the scent carries ...
SCENT_FADE = 0.82         # ... losing this share per step
SCENT_EVERY = 3           # ticks between recomputing the scent (it changes slowly)
HUNT_MIN_Z = 1            # even stragglers wander toward people (they end up at the border, not in a dead zone)
GOVERNED_SCENT = 0.4      # people on governed land smell this much compared with people on land nobody holds
HUNT_SHARE = 12           # a hunting tile sends 1/HUNT_SHARE of its zombies per tick
HUNT_CHANCE = 0.25
HUNT_UPHILL = 1.02        # only toward a neighbour whose scent is this much stronger
CLOSE_REACH = 6           # within this many steps of people the horde closes in hard (it can see / hear them):
CLOSE_CHANCE = 0.9        # ... nearly every tile moves every tick ...
CLOSE_SHARE = 4           # ... a quarter of its zombies at a time - more than spreading out again undoes, so zombies
                          #     mass at the border and press against it instead of thinning out in front of it
UNDEFENDED = 5            # defense below this on ungoverned land counts as undefended


def _max8(a, wrap):
    """Maximum over each tile and its 8 neighbours (a row pass, then a column pass)."""
    m = np.maximum(a, np.maximum(shift(a, 0, 1, wrap, 0.0), shift(a, 0, -1, wrap, 0.0)))
    return np.maximum(m, np.maximum(shift(m, 1, 0, wrap, 0.0), shift(m, -1, 0, wrap, 0.0)))


def scent(world, win, wrap, key=0):
    """(scent, close) inside the window: the prey scent over walkable land, and where people are within CLOSE_REACH
    steps.  Recomputed every SCENT_EVERY ticks (or when the window changes)."""
    cache = getattr(world, "_scent", None)
    if cache is None:
        cache = world._scent = {}
    hit = cache.get(key)
    if hit is not None and world.ticks - hit[0] < SCENT_EVERY and hit[3] == win:
        return hit[1], hit[2]
    H, D, O = world.H[win], world.D[win], world.O[win]
    walk = world.land[win] & (D < 7)
    fade = (SCENT_FADE * np.sqrt(world.statics.move.reshape(world.H.shape)[win])).astype(np.float32)
    weight = np.where(O == 0, np.where(D < UNDEFENDED, 1.0, 0.5), GOVERNED_SCENT)
    prey = np.where(walk, np.maximum(H, 0) * weight, 0.0).astype(np.float32)
    s = prey.copy()
    close = prey > 0
    for i in range(HUNT_REACH):
        s = np.where(walk, np.maximum(prey, fade * _max8(s, wrap)), 0.0).astype(np.float32)
        if i + 1 == CLOSE_REACH:
            close = s > 0
    cache[key] = (world.ticks, s, close, win)
    return s, close


def hunt(world):
    from engine import active_windows
    total = 0
    for k, (win, wrap) in enumerate(active_windows(world, world.Z > 0, HUNT_REACH + 2)):
        total += _hunt(world, win, wrap, k)
    return total


def _hunt(world, win, wrap, key):
    Z, D = world.Z[win], world.D[win]                     # views: moves go straight into the map
    sc, close = scent(world, win, wrap, key)
    if not sc.any():
        return 0
    land = world.land[win]
    src = ((Z >= HUNT_MIN_Z) & (sc > 0) & land
           & (world.rng.random(Z.shape) < np.where(close, CLOSE_CHANCE, HUNT_CHANCE)))
    if not src.any():
        return 0
    share = np.where(close, CLOSE_SHARE, HUNT_SHARE)
    ok = land & (D < 7)
    cand = np.full((8,) + Z.shape, -np.inf, dtype=np.float32)
    for i, (dr, dc) in enumerate(DIRECTIONS):
        cand[i] = np.where(shift(ok, dr, dc, wrap, False), shift(sc, dr, dc, wrap, 0.0), -np.inf)
    best = cand.argmax(axis=0)
    best_val = np.take_along_axis(cand, best[None], 0)[0]
    go = src & (best_val > sc * HUNT_UPHILL)
    rr, cc = np.nonzero(go)
    if rr.size == 0:
        return 0
    amount = np.minimum(np.maximum(Z[rr, cc] // share[rr, cc], 1), Z[rr, cc])
    way = best[rr, cc]
    mv = world.statics.move.reshape(world.H.shape)[win]
    frac = world.rng.random(rr.size) if world.stochastic else np.full(rr.size, 0.5)
    rows, cols = Z.shape
    moved_total = 0
    for i, (dr, dc) in enumerate(DIRECTIONS):
        k = np.flatnonzero(way == i)
        if k.size == 0:
            continue
        sr, sc = rr[k], cc[k]
        tr, tc = sr + dr, sc + dc
        if wrap:
            tc %= cols
        inside = (tr >= 0) & (tr < rows) & (tc >= 0) & (tc < cols)
        sr, sc, tr, tc, a, f = sr[inside], sc[inside], tr[inside], tc[inside], amount[k][inside], frac[k][inside]
        into = np.floor(a * mv[tr, tc] + f).astype(Z.dtype)        # rough ground slows them
        moved = np.minimum(np.minimum(into, a), np.maximum(255 - Z[tr, tc], 0)).astype(Z.dtype)
        Z[sr, sc] -= moved
        np.add.at(Z, (tr, tc), moved)
        moved_total += int(moved.sum())
    return moved_total
