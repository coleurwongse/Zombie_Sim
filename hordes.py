"""Hordes: big bodies of zombies that go for the best prey within reach, and move on it as one.

Every PLAN_EVERY days the land is looked at on a coarse grid (cells of about CELL_DEG degrees) and one attraction
field is worked out for the whole map - like a landscape the hordes walk downhill on:

  prey      people in a cell, cities (CITY_POP+ a tile) counting CITY_WEIGHT times over, less where it is well
            defended - a big, soft city is the prize, not just whatever is nearest; cells with at least VALUE_MIN;
  ground    the cost of getting there: rough ground (terrain.MOVE) and defended ground (forts, a manned front line,
            above the ordinary: DEFENSE_COST) are expensive, water impassable - so hordes go round mountain ranges
            and round an army's line rather than into it;
  pull      each cell's height is the cheapest way to any prey, a richer prey counting as nearer (by NEAR_COST x
            2 ln(richest / its value)), up to RANGE_DEG away.  Each cell also remembers which prey it leads to.

Each tick every horde tile (HORDE_Z zombies or more) sends MARCH_SHARE x coordination of its zombies one step
downhill - all of a horde together, so it moves as a body.  Hordes fragment and merge on their own: a horde lying
across the watershed between two cities splits and goes for both; hordes heading for the same city run together.
Within ENCIRCLE_CELLS of its prey a horde spreads round it: each part of it (FLANK field: whole stretches of the horde
pick the same side) swings out to its side, ENCIRCLE_WIDTH cells off, before closing in - a pincer, the town
encircled and attacked from several sides; once at the people the ordinary hunt (zombies.py) takes over.

world.coordination (0..1, main.py --coordination, default 0.8): how organized the hordes are.  0: no marching at all
(zombies only spread out and follow their noses - pure diffusion); 1: perfectly coordinated (every horde tile
marches, none straggle, none spread out: engine.SPREAD is scaled by 1 - COORD_DAMP x coordination).
"""
import numpy as np

import labels
from civilization import DIRECTIONS

COORDINATION = 0.8
CELL_DEG = 2.0             # coarse cells of about this many degrees (world_lite: 4 tiles, world: 6) ...
CELLS_ACROSS = 45          # ... but at least this many cells across the map (Middle-earth: 8 tiles, Beleriand: 6)
PLAN_EVERY = 8
HORDE_Z = 6                # tiles with this many zombies march with their horde (a coarse cell averaging this many
                           # per land tile counts as horde ground, for the log)
RANGE_DEG = 70.0           # how far a horde looks for prey
NEAR_COST = 8.0            # (cells of open ground): a prey e^2 times as rich counts as 2 x this nearer
CITY_POP = 150
CITY_WEIGHT = 3.0
DEFENSE_COST = 1.2         # extra cost of a cell per unit of protection above the ordinary (forts 7, mountains 5) ...
BASE_DEFENSE = 2.0         # ... (every district has 2)
VALUE_MIN = 60             # a target must hold at least this many people
MARCH_SHARE = 0.9          # x coordination: share of a horde tile's zombies that marches a step ...
MARCH_PASSES = 2           # ... this many times a day (a horde covers 1-1.5 tiles a day)
ENCIRCLE_CELLS = 5         # within this many cells of its target a horde spreads round it ...
ENCIRCLE_WIDTH = 1.5       # ... its halves swinging out this many cells to either side before closing in
STAY_RATIO = 1.5           # when a horde moves on to a bigger prize, a nation it leaves behind within STAY_CELLS keeps
STAY_CELLS = 12            # this many zombies per person of it for itself - the part of the horde nearest it: that
STAY_MIN = 20              # stays and finishes it off (cells with STAY_MIN people or more), the rest marches on ...
STAY_MAX = 0.5             # ... but at most this share of the zombies heading for one prize stay behind
ENGAGED = 2                # tiles within this many of people don't march on: they're attacking
COORD_DAMP = 0.75          # engine.SPREAD x (1 - this x coordination)
NOTE_MIN = 3000            # hordes this big are reported when they turn on a new city


def coordination(world):
    return float(getattr(world, "coordination", COORDINATION))


def _k(world):
    res = float((getattr(world, "meta", None) or {}).get("res", 0.5))
    fine = max(4, max(world.H.shape) // CELLS_ACROSS)        # (small maps: at least CELLS_ACROSS cells across)
    return max(2, min(int(round(CELL_DEG / res)), fine))


def coarse_sum(world, a, k):
    rows, cols = a.shape
    R, C = -(-rows // k), -(-cols // k)
    p = np.zeros((R * k, C * k), dtype=np.float32)
    p[:rows, :cols] = a
    return p.reshape(R, k, C, k).sum(axis=(1, 3))


def _statics(world, k):
    cache = getattr(world, "_horde_statics", None)
    if cache is not None and cache[0] == k:
        return cache[1], cache[2]
    S = world.statics
    land = S.land.astype(np.float32)
    landc = coarse_sum(world, land, k)
    move = coarse_sum(world, np.where(S.land, S.move.reshape(world.H.shape), 0).astype(np.float32), k)
    frac = landc / (k * k)
    terrain = np.where(frac >= 0.35, 1.0 / np.clip(move / np.maximum(landc, 1e-6), 0.1, 1.0), np.inf)
    world._horde_statics = (k, terrain.astype(np.float64), np.maximum(landc, 1.0))
    return terrain, np.maximum(landc, 1.0)


def _downhill(dist, wrap):
    """Per cell, the index into DIRECTIONS of the neighbour with the lowest `dist` (-1 where none is lower)."""
    R, C = dist.shape
    p = np.full((R + 2, C + 2), np.inf)
    p[1:-1, 1:-1] = dist
    if wrap:
        p[1:-1, 0], p[1:-1, -1] = dist[:, -1], dist[:, 0]
    vals = np.stack([p[1 + dr:R + 1 + dr, 1 + dc:C + 1 + dc] - 1e-6 * (dr == 0 or dc == 0) for dr, dc in DIRECTIONS])
    best = vals.argmin(axis=0)
    return np.where(vals.min(axis=0) < dist, best, -1).astype(np.int8)


def _flank(world):
    """A smooth fixed -1 / +1 field: which side a stretch of horde swings round when it closes in (whole parts of a
    horde take the same side, so it splits into two arms - a pincer)."""
    f = getattr(world, "_horde_flank", None)
    if f is None or f.shape != world.H.shape:
        from civilization import jag
        f = world._horde_flank = np.where(jag(world) >= 0, 1.0, -1.0).astype(np.float32)
    return f


def plan(world):
    """Work out the attraction field (see the module doc).  Stores world._horde_plan."""
    k = _k(world)
    terrain, landc = _statics(world, k)
    wrap = bool(world.wrap)
    from civilization import protection
    H = np.maximum(world.H, 0)
    Hc = coarse_sum(world, H, k)
    cityc = coarse_sum(world, np.where(H >= CITY_POP, H, 0), k)
    prot = np.maximum(coarse_sum(world, np.clip(protection(world), 0, 10), k) / landc - BASE_DEFENSE, 0.0)
    cost = terrain + DEFENSE_COST * prot
    value = (Hc + CITY_WEIGHT * cityc) / (1.0 + prot / 3.0)
    prey = (Hc >= VALUE_MIN) & np.isfinite(terrain) & (value > 0)
    # an island eaten bare: its shore draws its zombies (crossings.py takes them to sea from there)
    import crossings
    lost = crossings.stranded(world)
    if lost:
        S = world.statics
        shore = S.land & crossings._touches(~S.land) & np.isin(S.landmass, list(lost))
        sc = (coarse_sum(world, shore.astype(np.float32), k) > 0) & np.isfinite(terrain)
        value = np.where(sc & ~prey, 5.0 * VALUE_MIN, value)
        prey |= sc
    world._horde_plan = None
    if not prey.any():
        return
    res = float((getattr(world, "meta", None) or {}).get("res", 0.5))
    limit = RANGE_DEG / (res * k)
    start = np.where(prey, 2.0 * NEAR_COST * np.log(value.max() / np.maximum(value, 1e-9)), np.inf)
    R, C = cost.shape
    if wrap:                                            # (three copies side by side: paths across the date line)
        pot, lab = relax_from(np.tile(cost, (1, 3)), np.tile(start, (1, 3)), limit)
        pot, lab = pot[:, C:2 * C], lab[:, C:2 * C]
        lab = np.where(lab >= 0, (lab // (3 * C)) * C + (lab % (3 * C)) % C, -1)     # (back to the one map)
    else:
        pot, lab = relax_from(cost, start, limit)
    # the nearest people, whatever they're worth (for the part of a horde that stays to finish them off)
    near = (Hc >= STAY_MIN) & np.isfinite(terrain)
    nstart = np.where(near, 0.0, np.inf)
    if wrap:
        npot, nlab = relax_from(np.tile(cost, (1, 3)), np.tile(nstart, (1, 3)), STAY_CELLS)
        npot, nlab = npot[:, C:2 * C], nlab[:, C:2 * C]
        nlab = np.where(nlab >= 0, (nlab // (3 * C)) * C + (nlab % (3 * C)) % C, -1)
    else:
        npot, nlab = relax_from(cost, nstart, STAY_CELLS)
    world._horde_plan = dict(k=k, pot=pot, dirs=_downhill(pot, wrap), prey=lab, shape=(R, C),
                             near_dirs=_downhill(npot, wrap), near_prey=nlab, near_pot=npot,
                             **_groups(world, k, near, Hc))
    _report(world, k, lab)


def _groups(world, k, near, Hc):
    """Who the people in each cell belong to, for the rear guard: the nation holding most of them there (people nobody
    governs: each cell on its own) - near_group per cell, and near_need per group (STAY_RATIO x its people)."""
    R, C = Hc.shape
    n = len(world.civs)
    H = np.maximum(world.H, 0).astype(np.float64)
    rows, cols = H.shape
    cell = (np.minimum(np.arange(rows) // k, R - 1)[:, None] * C + np.minimum(np.arange(cols) // k, C - 1)[None, :])
    O = np.minimum(world.O, n - 1).astype(np.int64)
    by = np.bincount((cell * n + O).ravel(), weights=H.ravel(), minlength=R * C * n).reshape(R * C, n)
    by[:, 0] = 0.0
    owner = by.argmax(axis=1)
    owner[by.max(axis=1) <= 0] = 0
    group = np.where(owner > 0, owner, n + np.arange(R * C))
    group = np.where(near.ravel(), group, -1)
    need = np.bincount(np.maximum(group, 0), weights=np.where(group >= 0, Hc.ravel(), 0.0), minlength=n + R * C)
    return dict(near_group=group, near_need=STAY_RATIO * need)


def _report(world, k, lab):
    """Tell of the big hordes that turn on a new city (now and then)."""
    Zc = coarse_sum(world, np.where(world.statics.land, world.Z, 0), k)
    _, landc = _statics(world, k)
    body, n = labels.label(Zc >= HORDE_Z * landc)
    if n == 0:
        return
    sizes = np.bincount(body.ravel(), weights=Zc.ravel(), minlength=n + 1)
    prev = getattr(world, "_horde_targets", {})
    now = {}
    C = lab.shape[1]
    for j in np.flatnonzero(sizes >= NOTE_MIN):
        if j == 0:
            continue
        t = lab[body == j]
        t = t[t >= 0]
        if t.size == 0:
            continue
        top = int(np.bincount(t).argmax())
        now[int(j)] = top
        if top not in prev.values() and world.pyrng.random() < 0.15:
            from fracture import _place
            world.note(f"a horde of {world.people(sizes[j])} turns toward "
                       f"{_place(world, (int((top // C + 0.5) * k), int((top % C + 0.5) * k)))}")
    world._horde_targets = now


def relax_from(cost, start, limit):
    """Cheapest way from the sources to every cell (8 neighbours; a step costs the mean of the two cells, x1.41
    diagonally; inf cells can't be entered), each source starting at its own height `start` (inf: not a source) and
    reaching at most `limit` beyond it.  Returns (height, which source each cell leads to - its flat index, -1 none).
    Updated in place, so it settles in a few passes."""
    R, C = cost.shape
    dist = start.astype(np.float64).copy()
    lab = np.where(np.isfinite(dist), np.arange(R * C).reshape(R, C), -1)
    moves = []
    for dr, dc in DIRECTIONS:
        ts = (slice(max(dr, 0), R + min(dr, 0)), slice(max(dc, 0), C + min(dc, 0)))
        fs = (slice(max(-dr, 0), R + min(-dr, 0)), slice(max(-dc, 0), C + min(-dc, 0)))
        moves.append((ts, fs, 0.5 * (cost[fs] + cost[ts]) * (1.4142 if dr and dc else 1.0)))
    for _ in range(2 * (R + C)):
        changed = False
        for ts, fs, step in moves:
            cand = dist[fs] + step
            better = cand < dist[ts] - 1e-9
            if better.any():
                dist[ts][better] = cand[better]
                lab[ts][better] = lab[fs][better]
                changed = True
        if not changed:
            break
    base = np.where(lab >= 0, start.ravel()[np.maximum(lab, 0)], 0.0)    # (how far from its own source)
    far = (lab < 0) | (dist - base > limit)
    dist[far], lab[far] = np.inf, -1
    return dist, lab


def march(world):
    """Move every horde tile one step on its way (see the module doc): toward its prize - but the rear guard
    (_rear_guard) toward the people the horde would otherwise leave behind."""
    plan_ = getattr(world, "_horde_plan", None)
    c = coordination(world)
    if plan_ is None or c <= 0:
        return 0
    k = plan_["k"]
    Z = world.Z
    # (zombies at people - on them or next to them - are busy eating: they attack, the hunt moves them; zombies.py)
    from civilization import box_sum
    engaged = box_sum(world.H > 10, ENGAGED) > 0
    rr, cc = np.nonzero((Z >= HORDE_Z) & world.statics.land & ~engaged)
    if rr.size == 0:
        return 0
    R, C = plan_["shape"]
    gr, gc = np.minimum(rr // k, R - 1), np.minimum(cc // k, C - 1)
    base = Z[rr, cc].astype(np.float64) * MARCH_SHARE * c
    moved = 0
    way = _close_in(world, rr, cc, plan_["dirs"][gr, gc].astype(np.int64), plan_["prey"][gr, gc],
                    (plan_["dirs"][gr, gc] >= 0) & (plan_["prey"][gr, gc] >= 0), k, C)
    ok = (plan_["dirs"][gr, gc] >= 0) & (plan_["prey"][gr, gc] >= 0)
    stay = _rear_guard(world, plan_, rr, cc, gr, gc)
    if stay.any():                                       # (the rear guard: it goes for the people left near it)
        nw = plan_["near_dirs"][gr, gc].astype(np.int64)
        nok = stay & (nw >= 0) & (plan_["near_prey"][gr, gc] >= 0)
        nw = _close_in(world, rr, cc, nw, plan_["near_prey"][gr, gc], nok, k, C)
        way = np.where(stay, nw, way)
        ok = np.where(stay, nok, ok)
    ways = [(way, ok, 1.0)]
    stray_rng = c < 1.0 and world.stochastic
    from zombies import step_toward, transport
    for way, ok, share in ways:
        if not ok.any():
            continue
        sr, sc, w_ = rr[ok], cc[ok], way[ok].copy()
        if stray_rng:                                     # (less coordinated: some of them wander off on their own)
            stray = world.rng.random(sr.size) < 0.5 * (1.0 - c)
            w_[stray] = world.rng.integers(0, 8, int(stray.sum()))
        tr, tc, fine = step_toward(world, sr, sc, w_)
        frac = world.rng.random(int(fine.sum())) if world.stochastic else np.full(int(fine.sum()), 0.5)
        mv = world.statics.move.reshape(world.H.shape)[tr[fine], tc[fine]]
        amount = np.floor(base[ok][fine] * share * mv + frac).astype(np.int64)
        moved += transport(world, sr[fine], sc[fine], tr[fine], tc[fine], amount)
    return moved


def _rear_guard(world, plan_, rr, cc, gr, gc):
    """Which horde tiles stay behind: for each nation (or group of people nobody governs) within STAY_CELLS that the
    horde is leaving (its prize is somewhere else), the horde tiles nearest to it, up to STAY_RATIO zombies per person
    of it - and at most STAY_MAX of the zombies heading for each prize.  The same tiles stay day after day (they only
    get nearer), so the rear guard is a body of its own, not a share that drifts off."""
    out = np.zeros(rr.size, dtype=bool)
    if "near_group" not in plan_:
        return out
    lab, prize = plan_["near_prey"][gr, gc], plan_["prey"][gr, gc]
    grp = np.where(lab >= 0, plan_["near_group"][np.maximum(lab, 0)], -1)
    pgrp = np.where(prize >= 0, plan_["near_group"][np.maximum(prize, 0)], -2)
    cand = np.flatnonzero((grp >= 0) & (grp != pgrp))
    if cand.size == 0:
        return out
    z_all = world.Z[rr, cc].astype(np.float64)
    d = plan_["near_pot"][gr[cand], gc[cand]]
    pick = _fill(grp[cand], d, z_all[cand], plan_["near_need"])
    cand = cand[pick]
    if cand.size == 0:
        return out
    pz = np.maximum(prize, -1) + 1                       # (no prize: group 0)
    cap = STAY_MAX * np.bincount(pz, weights=z_all, minlength=int(pz.max()) + 1)
    keep = _fill(pz[cand], plan_["near_pot"][gr[cand], gc[cand]], z_all[cand], cap)
    out[cand[keep]] = True
    return out


def _fill(group, dist, z, need):
    """Per group, the members nearest first until the group's need (need[group]) is met: a bool mask."""
    order = np.lexsort((dist, group))
    g, zz = group[order], z[order]
    csum = np.cumsum(zz)
    start = np.r_[0, np.flatnonzero(g[1:] != g[:-1]) + 1]
    before = np.repeat(np.r_[0.0, csum[start[1:] - 1]], np.diff(np.r_[start, g.size]))
    take = np.zeros(group.size, dtype=bool)
    take[order[(csum - before - zz) < need[g]]] = True
    return take


def _close_in(world, rr, cc, way, prey, ok, k, C):
    """Within ENCIRCLE_CELLS of its prey a horde swings round it on both sides, then closes in (a pincer)."""
    dirs = np.array(DIRECTIONS)
    dang = np.arctan2(dirs[:, 0], dirs[:, 1])
    p = np.maximum(prey, 0)
    goal = np.stack([(p // C + 0.5) * k, (p % C + 0.5) * k], axis=1)
    pos = np.stack([rr, cc], axis=1).astype(np.float64)
    vec = goal - pos
    if world.wrap:
        width = C * k
        vec[:, 1] = (vec[:, 1] + width / 2) % width - width / 2
    dist = np.hypot(vec[:, 0], vec[:, 1])
    close = ok & (dist <= ENCIRCLE_CELLS * k) & (dist > 0.5 * k)
    if close.any():
        u = vec[close] / dist[close][:, None]
        perp = np.stack([-u[:, 1], u[:, 0]], axis=1)
        side = _flank(world)[rr[close], cc[close]][:, None]
        wide = np.clip((dist[close] - 0.75 * k) / (ENCIRCLE_WIDTH * k), 0.0, 1.0)[:, None]
        head = u + side * perp * 1.6 * wide                  # (far out: mostly round; near: straight in)
        ang = np.arctan2(head[:, 0], head[:, 1])
        diff = np.abs(((ang[:, None] - dang[None, :]) + np.pi) % (2 * np.pi) - np.pi)
        way = way.copy()
        way[close] = diff.argmin(axis=1)
    return way


def step(world):
    if world.ticks % PLAN_EVERY == 0 or getattr(world, "_horde_plan", None) is None:
        plan(world)
    return sum(march(world) for _ in range(MARCH_PASSES))
