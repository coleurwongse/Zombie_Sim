"""The front line: a government's army holds its actual border.

Every tick, each government with an army mans its FRONT - its populated tiles that touch zombie-held ground that
isn't its own.  How well the line holds depends on its STRENGTH: army strength, materials (ammunition) and morale.

  * zombies moving into a front-line tile are cut down to (1 - LINE_RESIST x strength) of what would get in, and
    into the tiles just behind it to (1 - DEPTH_RESIST x strength) - kernel `resist`;
  * the troops shoot whatever presses against the line: a share of the zombies on the front tiles and on the
    tiles right in front of them dies every tick (costs materials and a little army strength);
  * people behind a held line feel protected (protection bonus, see civilization.protection), so they don't flee
    or evacuate: the border stays populated instead of an empty no-man's-land opening up in front of the horde.

The line has to be mobilized first: a government's ALERT rises from 0 while there are zombies in its region (so a
fresh outbreak meets no line at all) and falls back slowly once they're gone.  Once the whole world is alarmed
(world.alarm, sim.py) nobody stands down completely: every government keeps at least ALARM_ALERT x the world's alarm.

A line has to be manned: a government has troops for about LINE_TILES x (its people / an average government's people)
tiles of front.  A longer front is held more thinly (strength x sqrt(troops / front length)) - a small country can't
hold a long border on its own, and a big one isn't held by the same handful of soldiers as a small one.

Hordes still push against the line and a big enough one breaks through (zombie movement is only slowed), and a
government in retreat doesn't man the districts it is giving up.  Everything is vectorized over all governments
at once (no per-government loops over the map).
"""
import numpy as np

from civilization import DIRECTIONS, _slices

FRONT_Z = 1                 # zombies on a neighbouring tile that make a tile 'front line'
LINE_MIN_ARMY = 0.03
LINE_RESIST = 0.5
DEPTH_RESIST = 0.25
LINE_KILL = 0.035           # share of zombies on / in front of the line killed per tick at full strength
LINE_COST = 0.003           # materials per zombie killed
LINE_ARMY = 0.000004        # army strength lost per zombie killed
LINE_PROT = 3.0             # protection a fully held line gives the people behind it
LINE_DEFENSE = 2            # defense of a manned front tile (+3 at full strength)
FULL_ARMY = 0.8             # army strength at which the line is fully manned
FULL_MATERIALS = 10.0
ALERT_RATE = 0.016         # mobilization: a government that sees zombies in its region builds its line up over
ALERT_FADE = 0.002          # ~1/ALERT_RATE ticks (an outbreak catches everyone unprepared), and stands it down slowly
ALERT_ZOMBIES = 100
VETERAN_ALERT = 4.0         # a government that has come through an outbreak (peace.py) mobilizes (1 + this) x as fast
ALARM_ALERT = 0.3           # alert every government keeps once the world is fully alarmed
LINE_TILES = 60             # front tiles an average-sized government can man at full strength
RESOLVE_LINE = 1.6          # a government that has adapted to the fight (resolve.py) holds its line this much better
SURPRISE_LINE = 0.3         # the line's strength where a horde has just come ashore (crossings.SURPRISE_DAYS)
LINE_CAP = 2.2              # (line strength beyond 1: a hardened line on good ground)
TERRAIN_LINE = 0.9          # a line on rough ground holds better: x (1 + TERRAIN_LINE x (1 - terrain.MOVE)) ...
WATER_LINE = 0.3            # ... and + this behind a river, lake or the coast


def line_terrain(world):
    """Per tile: how much the ground helps a front line there (1 = open ground).  Worked out once per map."""
    cache = getattr(world, "_line_terrain", None)
    if cache is None or cache.shape != world.H.shape:
        from engine import pad1, nb
        S = world.statics
        move = S.move.reshape(world.H.shape)
        water = pad1(~S.land, False, world.wrap)
        wet = np.zeros(world.H.shape, dtype=bool)
        for dr, dc in DIRECTIONS:
            wet |= nb(water, dr, dc)
        cache = world._line_terrain = (1.0 + TERRAIN_LINE * (1.0 - move) + WATER_LINE * (wet & S.land)).astype(
            np.float32)
    return cache


def _any_neighbour(mask):
    out = np.zeros_like(mask)
    rows, cols = mask.shape
    for dr, dc in DIRECTIONS:
        sr, tr = _slices(rows, dr)
        sc, tc = _slices(cols, dc)
        out[tr, tc] |= mask[sr, sc]
    return out


def strengths(world):
    """Per government id: 0..1, how well it can man its line right now."""
    s = np.zeros(len(world.civs))
    for c in world.civs:
        if not c.ai or c.collapsed or c.is_anarchy:
            continue
        threat = c.m.get("zone_z", 0) >= ALERT_ZOMBIES if c.m else False
        if world.ticks < c.traits.get("denial", 0):
            threat = False                                 # a cover-up: officially, nothing is happening
        # (a country that has been through an outbreak and stood down mobilizes fast the next time: peace.py)
        rate = ALERT_RATE * (1.0 + VETERAN_ALERT * bool(getattr(c, "veteran", False)))
        c.alert = min(1.0, c.alert + rate) if threat else max(0.0, c.alert - ALERT_FADE)
        if world.ticks >= c.traits.get("denial", 0):
            c.alert = max(c.alert, ALARM_ALERT * getattr(world, "alarm", 0.0))
        if c.military < LINE_MIN_ARMY or c.materials <= 0:
            continue
        troops = LINE_TILES * c.m.get("pop", 0) / getattr(world, "pop_ref", 1e9) if c.m else LINE_TILES
        cover = min(1.0, troops / max(c.front_len, 1)) ** 0.5
        s[c.id] = ((0.6 + 0.8 * c.strength) * min(1.0, c.military / FULL_ARMY) * min(1.0, c.materials / FULL_MATERIALS)
                   * (0.5 + c.morale / 20.0) * c.alert * cover * (1.0 + RESOLVE_LINE * getattr(c, "resolve", 0.0)))
    return s


def step(world):
    from engine import active_windows
    # how long each government's front was last tick (it sets how thinly the next one is held)
    prev = world.front
    lens = np.bincount(world.O[prev], minlength=len(world.civs)) if prev is not None else np.zeros(len(world.civs))
    for c in world.civs:
        c.front_len = int(lens[c.id]) if c.id < len(lens) else 0
    strength = strengths(world)
    world.resist = None
    world.line_prot = None
    world.front = None
    if not strength.any():
        return 0
    world.resist = np.ones(world.H.shape, dtype=np.float32)
    world.line_prot = np.zeros(world.H.shape, dtype=np.float32)
    world.front = np.zeros(world.H.shape, dtype=bool)
    total = 0
    for win, wrap in active_windows(world, world.Z >= FRONT_Z, 3):
        total += _window(world, strength, win, wrap)
    return total


def _window(world, strength, win, wrap):
    from engine import pad1, nb
    H, Z, O = world.H[win], world.Z[win], world.O[win]       # Z is a view: kills go straight into the map
    S = np.minimum(strength[O] * line_terrain(world)[win], LINE_CAP)    # (rough ground and rivers help the line)
    import crossings
    hidden = crossings.surprise(world)                     # (a fresh landing: the line there isn't ready yet)
    if hidden is not None:
        S = np.where(hidden[win], S * SURPRISE_LINE, S)
    manned = (S > 0) & (H > 10)
    for c in world.civs:                                   # districts being given up aren't manned
        rm = getattr(c, "retreat_mask", None)
        if rm is not None and c.ai and not c.collapsed and rm.shape == world.H.shape:
            manned &= ~rm[win]
    # front: manned tiles with a zombie-held neighbour that isn't the same government's
    front = np.zeros(H.shape, dtype=bool)
    zp, op = pad1(Z >= FRONT_Z, False, wrap), pad1(O, -1, wrap)
    for dr, dc in DIRECTIONS:
        front |= nb(zp, dr, dc) & (nb(op, dr, dc) != O)
    front &= manned
    if not front.any():
        return 0
    near_front = np.zeros(H.shape, dtype=bool)
    fp = pad1(front, False, wrap)
    for dr, dc in DIRECTIONS:
        near_front |= nb(fp, dr, dc)
    behind = manned & ~front & near_front
    # the troops dig in: a manned front tile is defended (3 + 3 x strength: up to 6), cutting bites and killing
    # what gets in (the original defense rules)
    Dw = world.D[win]
    dig = np.where(front, np.minimum(LINE_DEFENSE + 3 * S, 6).astype(np.int32), 0)
    np.maximum(Dw, dig, out=Dw)
    rw = np.ones(H.shape, dtype=np.float32)
    rw[front] = np.maximum(1.0 - LINE_RESIST * S[front], 0.08)
    rw[behind] = np.maximum(1.0 - DEPTH_RESIST * S[behind], 0.3)
    world.resist[win] = rw
    lw = np.zeros(H.shape, dtype=np.float32)
    lw[front | behind] = LINE_PROT * np.minimum(S[front | behind], 1.0)
    world.line_prot[win] = lw
    world.front[win] = front

    # fire: the strongest neighbouring front tile shoots at the zombies in front of it (worked out only on the tiles
    # with zombies at or next to the line)
    rr, cc = np.nonzero((front | near_front) & (Z > 0))
    if rr.size == 0:
        return 0
    f0 = front[rr, cc]
    o0 = O[rr, cc]
    shooter = np.where(f0, o0, 0)
    shot_s = np.where(f0, S[rr, cc], 0.0)
    sp, op0 = pad1(S, 0.0, wrap), pad1(O, 0, wrap)
    for dr, dc in DIRECTIONS:
        r1, c1 = rr + 1 + dr, cc + 1 + dc
        f1, s1, o1 = fp[r1, c1], sp[r1, c1], op0[r1, c1]
        better = f1 & (s1 > shot_s) & (o0 != o1)
        shooter = np.where(better, o1, shooter)
        shot_s = np.where(better, s1, shot_s)
    target = shooter > 0
    if not target.any():
        return 0
    rr, cc, shooter, shot_s = rr[target], cc[target], shooter[target], shot_s[target]
    zt = Z[rr, cc]
    share = LINE_KILL * shot_s * world.jitter(0.25)
    frac = world.rng.random(rr.size, dtype=np.float32) if world.stochastic else 0.5   # fair rounding: a thin
    kills = np.minimum(zt, np.floor(zt * share + frac)).astype(np.int64)               # line kills a few, not 1/tile
    n = len(world.civs)
    per = np.bincount(shooter, weights=kills, minlength=n)
    # nobody shoots more than its ammunition allows
    scale = np.ones(n)
    for k in np.flatnonzero(per):
        c = world.civs[k]
        cost = per[k] * LINE_COST
        if cost > c.materials:
            scale[k] = max(0.0, c.materials / cost)
    kills = (kills * scale[shooter]).astype(np.int32)
    Z[rr, cc] -= kills
    per = np.bincount(shooter, weights=kills, minlength=n)
    total = 0
    for k in np.flatnonzero(per):
        c = world.civs[k]
        c.materials = max(0.0, c.materials - per[k] * LINE_COST)
        c.military = max(0.0, c.military - per[k] * LINE_ARMY)
        c.kills += int(per[k])
        c.line_kills = int(per[k])
        total += int(per[k])
    return total
