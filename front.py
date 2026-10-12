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
ALERT_RATE = 0.01          # mobilization: a government that sees zombies in its region builds its line up over
ALERT_FADE = 0.002          # ~1/ALERT_RATE ticks (an outbreak catches everyone unprepared), and stands it down slowly
ALERT_ZOMBIES = 100
ALARM_ALERT = 0.3           # alert every government keeps once the world is fully alarmed
LINE_TILES = 40             # front tiles an average-sized government can man at full strength


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
        c.alert = min(1.0, c.alert + ALERT_RATE) if threat else max(0.0, c.alert - ALERT_FADE)
        if world.ticks >= c.traits.get("denial", 0):
            c.alert = max(c.alert, ALARM_ALERT * getattr(world, "alarm", 0.0))
        if c.military < LINE_MIN_ARMY or c.materials <= 0:
            continue
        troops = LINE_TILES * c.m.get("pop", 0) / getattr(world, "pop_ref", 1e9) if c.m else LINE_TILES
        cover = min(1.0, troops / max(c.front_len, 1)) ** 0.5
        s[c.id] = ((0.6 + 0.8 * c.strength) * min(1.0, c.military / FULL_ARMY) * min(1.0, c.materials / FULL_MATERIALS)
                   * (0.5 + c.morale / 20.0) * c.alert * cover)
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
    from engine import shift
    H, Z, O = world.H[win], world.Z[win], world.O[win]       # Z is a view: kills go straight into the map
    S = strength[O]
    manned = (S > 0) & (H > 10)
    for c in world.civs:                                   # districts being given up aren't manned
        rm = getattr(c, "retreat_mask", None)
        if rm is not None and c.ai and not c.collapsed and rm.shape == world.H.shape:
            manned &= ~rm[win]
    # front: manned tiles with a zombie-held neighbour that isn't the same government's
    front = np.zeros(H.shape, dtype=bool)
    zmask = Z >= FRONT_Z
    for dr, dc in DIRECTIONS:
        front |= shift(zmask, dr, dc, wrap, False) & (shift(O, dr, dc, wrap, -1) != O)
    front &= manned
    if not front.any():
        return 0
    near_front = np.zeros(H.shape, dtype=bool)
    for dr, dc in DIRECTIONS:
        near_front |= shift(front, dr, dc, wrap, False)
    behind = manned & ~front & near_front
    # the troops dig in: a manned front tile is defended (3 + 3 x strength: up to 6), cutting bites and killing
    # what gets in (the original defense rules)
    Dw = world.D[win]
    dig = np.where(front, (LINE_DEFENSE + 3 * S).astype(np.int32), 0)
    np.maximum(Dw, dig, out=Dw)
    rw = np.ones(H.shape)
    rw[front] = 1.0 - LINE_RESIST * S[front]
    rw[behind] = 1.0 - DEPTH_RESIST * S[behind]
    world.resist[win] = rw
    lw = np.zeros(H.shape)
    lw[front | behind] = LINE_PROT * S[front | behind]
    world.line_prot[win] = lw
    world.front[win] = front

    # fire: the strongest neighbouring front tile shoots at the zombies in front of it
    shooter = np.where(front, O, 0)
    shot_s = np.where(front, S, 0.0)
    for dr, dc in DIRECTIONS:
        f1 = shift(front, dr, dc, wrap, False)
        s1 = shift(S, dr, dc, wrap, 0.0)
        o1 = shift(O, dr, dc, wrap, 0)
        better = f1 & (s1 > shot_s) & (O != o1)
        shooter = np.where(better, o1, shooter)
        shot_s = np.where(better, s1, shot_s)
    target = (shooter > 0) & (Z > 0)
    if not target.any():
        return 0
    share = LINE_KILL * shot_s * world.jitter(0.25)
    frac = world.rng.random(Z.shape) if world.stochastic else 0.5      # fair rounding: a thin line kills a few, not 1/tile
    kills = np.where(target, np.minimum(Z, np.floor(Z * share + frac)), 0).astype(np.int64)
    n = len(world.civs)
    per = np.bincount(shooter[target], weights=kills[target], minlength=n)
    # nobody shoots more than its ammunition allows
    scale = np.ones(n)
    for k in np.flatnonzero(per):
        c = world.civs[k]
        cost = per[k] * LINE_COST
        if cost > c.materials:
            scale[k] = max(0.0, c.materials / cost)
    kills = (kills * scale[shooter]).astype(np.int32)
    Z -= kills
    per = np.bincount(shooter[target], weights=kills[target], minlength=n)
    total = 0
    for k in np.flatnonzero(per):
        c = world.civs[k]
        c.materials = max(0.0, c.materials - per[k] * LINE_COST)
        c.military = max(0.0, c.military - per[k] * LINE_ARMY)
        c.kills += int(per[k])
        c.line_kills = int(per[k])
        total += int(per[k])
    return total
