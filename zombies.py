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

Hordes far from anyone (no prey within HUNT_REACH) still track people from much farther away (FAR_REACH tiles): a
coarse scent over the land (cells of FAR_CELL x FAR_CELL tiles, recomputed every FAR_EVERY days) gives each cell the
direction of the nearest reachable people, and hordes of at least FAR_MIN_Z drift that way - so a horde that has
eaten a coast bare heads inland for the next town instead of milling about until it starves.
"""
import numpy as np

from engine import shift
from civilization import DIRECTIONS

HUNT_REACH = 16           # how far (steps over land) the scent carries ...
SCENT_FADE = 0.82         # ... losing this share per step
SCENT_EVERY = 3           # ticks between recomputing the scent (it changes slowly)
HUNT_MIN_Z = 1            # even stragglers wander toward people (they end up at the border, not in a dead zone)
GOVERNED_SCENT = 0.4      # people on governed land smell this much compared with people on land nobody holds
HUNT_SHARE = 6            # a hunting tile sends 1/HUNT_SHARE of its zombies per tick
HUNT_CHANCE = 0.5
HUNT_UPHILL = 1.02        # only toward a neighbour whose scent is this much stronger
CLOSE_REACH = 6           # within this many steps of people the horde closes in hard (it can see / hear them):
CLOSE_CHANCE = 0.9        # ... nearly every tile moves every tick ...
CLOSE_SHARE = 4           # ... a quarter of its zombies at a time - more than spreading out again undoes, so zombies
                          #     mass at the border and press against it instead of thinning out in front of it
UNDEFENDED = 5            # defense below this on ungoverned land counts as undefended
FAR_REACH = 200           # tiles: how far hordes track people when nothing is close (coarse scent) ...
FAR_CELL = 6              # ... over cells of this many tiles square
FAR_EVERY = 10            # ticks between recomputing it
FAR_FADE = 0.88           # per cell step (x the cell's walkability)
FAR_MIN_Z = 15            # only hordes this big set off after a distant scent
FAR_CHANCE = 0.8          # per tick, such a horde tile sends ...
FAR_SHARE = 2             # ... 1/FAR_SHARE of its zombies a step that way: the horde moves as a body


def _max8(a, wrap):
    """Maximum over each tile and its 8 neighbours (a row pass, then a column pass; nothing beyond the edge - the
    values are never negative)."""
    m = a.copy()
    np.maximum(m[:, 1:], a[:, :-1], out=m[:, 1:])
    np.maximum(m[:, :-1], a[:, 1:], out=m[:, :-1])
    if wrap:
        np.maximum(m[:, 0], a[:, -1], out=m[:, 0])
        np.maximum(m[:, -1], a[:, 0], out=m[:, -1])
    r = m.copy()
    np.maximum(r[1:], m[:-1], out=r[1:])
    np.maximum(r[:-1], m[1:], out=r[:-1])
    return r


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
    # fading per step (faster over rough ground), and nothing at all off walkable land
    fade = (SCENT_FADE * np.sqrt(world.statics.move.reshape(world.H.shape)[win]) * walk).astype(np.float32)
    weight = np.where(O == 0, np.where(D < UNDEFENDED, 1.0, 0.5), GOVERNED_SCENT)
    prey = np.where(walk, np.maximum(H, 0) * weight, 0.0).astype(np.float32)
    s = prey.copy()
    close = prey > 0
    for i in range(HUNT_REACH):
        s = _max8(s, wrap)
        s *= fade
        np.maximum(s, prey, out=s)
        if i + 1 == CLOSE_REACH:
            close = s > 0
    cache[key] = (world.ticks, s, close, win)
    return s, close


_TURN = {i: [j for j, d in enumerate(DIRECTIONS)
              if 0 < abs(d[0] - DIRECTIONS[i][0]) + abs(d[1] - DIRECTIONS[i][1]) <= 1] for i in range(8)}


def step_toward(world, rr, cc, way):
    """The tile one step from each (rr, cc) in direction `way` (index into DIRECTIONS) - or, where that is water or a
    fortress wall, a step either side of it (round a bay, along a coast, past a fort).  Returns (tr, tc, ok)."""
    dirs = np.array(DIRECTIONS)
    rows, cols = world.Z.shape
    way = np.asarray(way, dtype=np.int64)
    tr, tc = rr + dirs[way, 0], cc + dirs[way, 1]
    if world.wrap:
        tc = tc % cols
    bad = np.ones(rr.size, dtype=bool)
    for attempt in range(3):
        inside = (tr >= 0) & (tr < rows) & (tc >= 0) & (tc < cols)
        trc, tcc = np.clip(tr, 0, rows - 1), np.clip(tc, 0, cols - 1)
        bad = ~inside | ~world.land[trc, tcc] | (world.D[trc, tcc] >= 7)
        if not bad.any() or attempt == 2:
            break
        alt = np.array([_TURN[int(x)][attempt % 2] for x in way[bad]], dtype=np.int64)
        tr[bad], tc[bad] = rr[bad] + dirs[alt, 0], cc[bad] + dirs[alt, 1]
        if world.wrap:
            tc[bad] %= cols
    return tr, tc, ~bad


def transport(world, rr, cc, tr, tc, amount):
    """Move `amount` zombies from each (rr, cc) to (tr, tc) at once.  A tile holds at most 255, but room counts the
    zombies leaving it in the same move - so a dense horde moves as a body instead of jamming (front and back move
    together).  Returns how many moved."""
    Z = world.Z
    if rr.size == 0:
        return 0
    flat = Z.reshape(-1)
    cols = Z.shape[1]
    src = rr * cols + cc
    dst = tr * cols + tc
    amount = np.minimum(np.maximum(amount, 0), flat[src]).astype(np.float64)
    import seasons                                       # (the frozen dead stay where they are: seasons.py)
    f = seasons.frozen(world)
    if f is not None:
        amount = np.floor(amount * (1.0 - f.reshape(-1)[src]))
    # (only the tiles involved: sending, receiving or both)
    uniq, inv = np.unique(np.concatenate([src, dst]), return_inverse=True)
    si, di = inv[:src.size], inv[src.size:]
    out = np.bincount(si, weights=amount, minlength=uniq.size)
    inflow = np.bincount(di, weights=amount, minlength=uniq.size)
    room = 255.0 - (flat[uniq] - out)
    scale = np.where(inflow > 0, np.clip(room / np.maximum(inflow, 1e-9), 0.0, 1.0), 1.0)
    moved = np.floor(amount * scale[di])
    net = np.bincount(di, weights=moved, minlength=uniq.size) - np.bincount(si, weights=moved, minlength=uniq.size)
    # (a tile can still overflow when part of its own zombies couldn't leave - their way was full: whatever would
    #  push it past 255 stays where it came from, instead of being cut off - lost - at the next clip)
    base = flat[uniq].astype(np.float64)
    for _ in range(6):
        over = np.maximum(base + net - 255.0, 0.0)
        if not over.any():
            break
        came = np.bincount(di, weights=moved, minlength=uniq.size)
        back = np.ceil(moved * np.where(came > 0, over / np.maximum(came, 1e-9), 0.0)[di])
        moved = np.maximum(moved - back, 0.0)
        net = (np.bincount(di, weights=moved, minlength=uniq.size)
               - np.bincount(si, weights=moved, minlength=uniq.size))
    flat[uniq] += np.rint(net).astype(Z.dtype)
    return int(moved.sum())


def hunt(world):
    from engine import active_windows
    total = 0
    for k, (win, wrap) in enumerate(active_windows(world, world.Z > 0, HUNT_REACH + 2)):
        total += _hunt(world, win, wrap, k)
    import hordes
    return total + hordes.step(world) + far_hunt(world)


def far_scent(world):
    """(direction, far) per coarse cell: the index into DIRECTIONS of the neighbouring cell with the strongest distant
    scent (-1: none), and whether the cell is far from all people (nothing within ~HUNT_REACH tiles)."""
    memo = getattr(world, "_far_scent", None)
    if memo is not None and world.ticks - memo[0] < FAR_EVERY:
        return memo[1], memo[2]
    k = FAR_CELL
    rows, cols = world.H.shape
    R, C = -(-rows // k), -(-cols // k)
    pad = ((0, R * k - rows), (0, C * k - cols))
    walk = world.land & (world.D < 7)
    prey = np.pad(np.where(walk, np.maximum(world.H, 0), 0).astype(np.float32), pad)
    landc = np.pad(walk.astype(np.float32), pad).reshape(R, k, C, k).mean(axis=(1, 3))
    move = np.pad(np.where(walk, world.statics.move.reshape(world.H.shape), 0).astype(np.float32), pad)
    movec = move.reshape(R, k, C, k).mean(axis=(1, 3)) / np.maximum(landc, 1e-6)
    P = prey.reshape(R, k, C, k).sum(axis=(1, 3))
    fade = (FAR_FADE * np.sqrt(np.clip(movec, 0, 1)) * (landc >= 0.4)).astype(np.float32)
    wrap = bool(world.wrap)
    s = P.copy()
    near = P > 0
    steps = max(1, FAR_REACH // k)
    for i in range(steps):
        s = _max8(s, wrap) * fade
        np.maximum(s, P, out=s)
        if i + 1 == max(1, HUNT_REACH // k):
            near = s > 0
    padded = np.full((R + 2, C + 2), -1.0, dtype=np.float32)
    padded[1:-1, 1:-1] = s
    if wrap:
        padded[1:-1, 0], padded[1:-1, -1] = s[:, -1], s[:, 0]
    vals = np.stack([padded[1 + dr:R + 1 + dr, 1 + dc:C + 1 + dc] * (1.0 + 1e-4 * (dr == 0 or dc == 0))
                     for dr, dc in DIRECTIONS])               # (a tie goes to the straight step, not a diagonal drift)
    best = vals.argmax(axis=0)
    way = np.where(vals.max(axis=0) > s * HUNT_UPHILL, best, -1).astype(np.int8)
    world._far_scent = (world.ticks, way, ~near)
    return way, ~near


def far_hunt(world):
    """Hordes with nobody near track the distant scent (see far_scent): a step toward the next cell that smells
    stronger."""
    Z = world.Z
    rr, cc = np.nonzero(Z >= FAR_MIN_Z)
    if rr.size == 0:
        return 0
    way, far = far_scent(world)
    gr, gc = rr // FAR_CELL, cc // FAR_CELL
    w = way[gr, gc]
    sel = far[gr, gc] & (w >= 0)
    if world.stochastic:
        sel &= world.rng.random(rr.size) < FAR_CHANCE
    rr, cc, w = rr[sel], cc[sel], w[sel]
    if rr.size == 0:
        return 0
    plan_ = getattr(world, "_horde_plan", None)          # (a horde on the march is moved by hordes.py)
    if plan_ is not None:
        k = plan_["k"]
        a = plan_["dirs"]
        mine = a[np.minimum(rr // k, a.shape[0] - 1), np.minimum(cc // k, a.shape[1] - 1)] >= 0
        rr, cc, w = rr[~mine], cc[~mine], w[~mine]
        if rr.size == 0:
            return 0
    tr, tc, ok = step_toward(world, rr, cc, w)
    rr, cc, tr, tc = rr[ok], cc[ok], tr[ok], tc[ok]
    if rr.size == 0:
        return 0
    mv = world.statics.move.reshape(world.H.shape)
    frac = world.rng.random(rr.size) if world.stochastic else np.full(rr.size, 0.5)
    a = np.floor(Z[rr, cc] // FAR_SHARE * mv[tr, tc] + frac).astype(np.int64)
    moved = transport(world, rr, cc, tr, tc, a)
    return moved


def _hunt(world, win, wrap, key):
    from engine import pad1
    Z, D = world.Z[win], world.D[win]                     # views: moves go straight into the map
    sc, close = scent(world, win, wrap, key)
    land = world.land[win]
    rr, cc = np.nonzero((Z >= HUNT_MIN_Z) & (sc > 0) & land)
    if rr.size == 0:
        return 0
    cl = close[rr, cc]
    keep = world.rng.random(rr.size, dtype=np.float32) < np.where(cl, CLOSE_CHANCE, HUNT_CHANCE)
    rr, cc, cl = rr[keep], cc[keep], cl[keep]
    if rr.size == 0:
        return 0
    # the neighbour with the strongest scent that can be walked into (only looked up where zombies are)
    p = pad1(np.where(land & (D < 7), sc, -np.inf).astype(np.float32), -np.inf, wrap)
    vals = np.stack([p[rr + 1 + dr, cc + 1 + dc] for dr, dc in DIRECTIONS])
    best = vals.argmax(axis=0)
    best_val = vals[best, np.arange(rr.size)]
    go = best_val > sc[rr, cc] * HUNT_UPHILL
    rr, cc, cl, best = rr[go], cc[go], cl[go], best[go]
    if rr.size == 0:
        return 0
    share = np.where(cl, CLOSE_SHARE, HUNT_SHARE)
    amount = np.minimum(np.maximum(Z[rr, cc] // share, 1), Z[rr, cc])
    mv = world.statics.move.reshape(world.H.shape)[win]
    frac = world.rng.random(rr.size) if world.stochastic else np.full(rr.size, 0.5)
    rows, cols = Z.shape
    dirs = np.array(DIRECTIONS)
    tr, tc = rr + dirs[best, 0], cc + dirs[best, 1]
    if wrap:
        tc %= cols
    inside = (tr >= 0) & (tr < rows) & (tc >= 0) & (tc < cols)
    rr, cc, tr, tc, amount, frac = rr[inside], cc[inside], tr[inside], tc[inside], amount[inside], frac[inside]
    into = np.minimum(np.floor(amount * mv[tr, tc] + frac), amount).astype(np.int64)      # rough ground slows them
    r0, c0 = win[0].start or 0, win[1].start or 0
    moved_total = transport(world, rr + r0, cc + c0, tr + r0, (tc + c0) % world.cols if wrap else tc + c0, into)
    return moved_total
