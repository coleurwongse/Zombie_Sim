"""Individual behaviour: what ordinary people do regardless of what their government decides.

Runs once per tick (only when the world is created with ai=True), before civilizations act.

  Panic flight  people near a lot of zombies, with little protection, flee toward safer neighbouring
                tiles - across borders, into unowned land, into fortified places - whether or not
                their civilization wants them to.
  Unrest        fear builds up in dense places (cities most of all); it builds faster the weaker the
                government's grip (low morale, or no government at all) and fades when things calm down.
  Riots         unrest past RIOT_AT in a city or dense tile: defenses weaken, some people die, unrest
                spreads to neighbouring tiles, the government's morale takes a hit.  Repeated riots of people
                who are AFRAID (zombies close by, little protection) make the district break away from its
                government (it becomes unowned: anarchy).  Hunger riots hurt, but don't break a country up.
  Refugees      people pouring into a district raise its unrest (crowding, rumours, shortages).
  Stragglers    small groups from threatened districts strike out on their own - by car, on foot, smuggled across
                borders whatever the government says (shut borders only stop some of them) - to some quiet,
                uninfected place far away on the same landmass.  Some of them were bitten: that's how the infection
                turns up in the middle of big untouched regions.
"""
import numpy as np

from terrain import is_land, is_water

import govern
from civilization import NEAR_RADIUS, DIRECTIONS, flow_away, protection, box_sum, _slices

PANIC_NEAR = 600           # zombies in the 9x9 box around a tile that scare people into running
PANIC_MIN_POP = 20
PANIC_SHARE = 6            # a panicking tile sends 1/PANIC_SHARE of its people per tick
PANIC_CHANCE = 0.6         # at most this share of scared tiles flee on a given tick (at full fear)
PANIC_IMPROVEMENT = 0.7    # only toward a neighbour at least this much safer

STRAY_EVERY = 2            # stragglers: every this many ticks ...
STRAY_SOURCES = 8          # ... up to this many threatened districts send a group off
STRAY_FEAR = 60            # zombies within 4 tiles that make people leave on their own
STRAY_MIN_POP = 30
STRAY_GROUP = 10           # people per group (at most)
STRAY_RANGE = (6, 30)      # tiles travelled
STRAY_TRIES = 6            # random destinations tried per group
STRAY_BITTEN = 0.4         # share of the zombie:people ratio where they left that turns on arrival ...
STRAY_BASE = 0.01          # ... plus this (bites hidden from the others)
STRAY_BORDER = 0.5         # chance a group gets past a shut border

UNREST_DECAY = 0.9
UNREST_GAIN = 0.5
RIOT_AT = 1.0
RIOT_MIN_POP = 40
RIOT_CITY_POP = 150        # tiles at least this dense, or urban/suburban terrain, can riot
RIOT_DEATHS = 0.05         # share of people lost in a riot
RIOT_SPREAD = 0.25         # unrest added to each neighbour of a rioting tile
RIOT_SECEDE = 3.0          # accumulated riots after which a tile leaves its civilization
RIOT_TILES_PER_HIT = 5     # every this many rioting tiles costs their civilization 1 morale ...
RIOT_MAX_HIT = 2           # ... up to this much per tick
FAMINE_UNREST = 0.05       # unrest added every tick to every tile of a civilization in famine
REFUGEE_UNREST = 0.6       # unrest added per (arrivals / residents) this tick, beyond a 5% trickle
SECEDE_FEAR = 0.3          # only riots with at least this much fear count toward a district breaking away
REFUGE_SAFE_NEAR = 25      # a tile is 'safe' when fewer zombies than this are within 4 tiles
REFUGE_RANGE = 25          # refugees can find shelter at most this many steps away
REFUGE_REFRESH = 3         # ticks between recomputing the route-to-safety map
REFUGEE_SHARE = 3          # a hopeless tile sends 1/REFUGEE_SHARE of its people (at least one) each tick
EVAC_LOOK = 8              # people watch for hordes this far out (tiles)
EVAC_TRIGGER = 350         # zombies within EVAC_LOOK that make a growing horde alarming ...
EVAC_GROWTH = 1.12         # ... when it has grown this much since EVAC_COMPARE ticks ago
EVAC_COMPARE = 4
EVAC_NEAR_TRIGGER = 120    # or this many within 4 tiles
EVAC_MIN_POP = 40
EVAC_TRUST = 5             # protection at/above this (fortified, mountain) keeps people in place
EVAC_SHARE = 3             # a leaving tile sends 1/EVAC_SHARE of its people per tick
EVAC_CHANCE = 0.75
EVAC_SAFE_NEAR = 40        # a safe destination has fewer zombies than this within EVAC_LOOK
EVAC_RANGE = 40
EVAC_REFRESH = 4
NO_GOVERNMENT_MORALE = 3   # how much restraint a tile with no civilization has


def _distance(world, land, safe, steps):
    """Steps (8-way, over `land`) from every tile to the nearest `safe` tile, up to `steps` (10**6 beyond).
    A 3x3 minimum done as a row pass then a column pass - same result as checking all 8 neighbours, half the work."""
    INF = 10 ** 6
    dist = np.where(safe, 0, INF).astype(np.int32)
    blocked = ~land
    for _ in range(steps):
        m = dist.copy()
        np.minimum(m[:, 1:], dist[:, :-1], out=m[:, 1:])
        np.minimum(m[:, :-1], dist[:, 1:], out=m[:, :-1])
        best = m.copy()
        np.minimum(best[1:], m[:-1], out=best[1:])
        np.minimum(best[:-1], m[1:], out=best[:-1])
        best = np.minimum(best + 1, dist)
        best[best > INF] = INF
        best[blocked] = INF
        if (best == dist).all():
            break
        dist = best
    return dist


def windows(world):
    """The parts of the map anything in this module can happen in: around the zombies, plus the farthest anyone walks
    to safety.  (Empty if there are no zombies.)  Cached per tick."""
    cache = getattr(world, "_people_win", None)
    if cache is not None and cache[0] == world.ticks:
        return cache[1]
    from engine import active_windows
    wins = [w for w, _ in active_windows(world, world.zombie_near(EVAC_LOOK) > 0, EVAC_RANGE + 2)]
    world._people_win = (world.ticks, wins)
    return wins


def _windowed_distance(world, safe, steps):
    """_distance over land, worked out only inside windows(); outside them everything is safe (0)."""
    land = world.land
    dist = np.where(land, 0, 10 ** 6).astype(np.int32)
    for win in windows(world):
        dist[win] = _distance(world, land[win], safe[win], steps)
    return dist


def _flow(world, src, ok, share, cost, improvement, min_move=0):
    return flow_away(world, src, ok, share, cost, improvement, min_move=min_move)


def refuge_distance(world):
    """Steps (8-way, over land) from every tile to the nearest safe tile; cached for REFUGE_REFRESH ticks."""
    cache = getattr(world, "_refuge", None)
    if cache is not None and world.ticks - cache[0] < REFUGE_REFRESH:
        return cache[1]
    safe = world.land & (world.zombie_near(NEAR_RADIUS) < REFUGE_SAFE_NEAR)
    dist = _windowed_distance(world, safe, REFUGE_RANGE)
    world._refuge = (world.ticks, dist)
    return dist


def evac_distance(world):
    """Like refuge_distance, but 'safe' means no sizeable horde within 8 tiles (or a held fortress), and people
    will walk a long way to get there."""
    cache = getattr(world, "_evac", None)
    if cache is not None and world.ticks - cache[0] < EVAC_REFRESH:
        return cache[1]
    near8 = world.zombie_near(EVAC_LOOK)
    safe = world.land & ((near8 < EVAC_SAFE_NEAR) | ((protection(world) >= 7) & (near8 < 600)))
    dist = _windowed_distance(world, safe, EVAC_RANGE)
    world._evac = (world.ticks, dist)
    return dist


def mass_evacuation(world):
    """People who see a horde coming don't wait to be overrun: whole districts leave for somewhere safer,
    far away if need be, whatever their government says.  Fortified places that are holding keep their people."""
    H = world.H
    near8, near4 = world.zombie_near(EVAC_LOOK), world.zombie_near(NEAR_RADIUS)
    prev = getattr(world, "_evac_prev", None)
    if prev is None or world.ticks - prev[0] >= EVAC_COMPARE:
        world._evac_prev = (world.ticks, near8.copy())
    if prev is None:
        coming = near8 >= 2 * EVAC_TRIGGER
    else:
        coming = (near8 >= EVAC_TRIGGER) & (near8 > prev[1] * EVAC_GROWTH + 20)
    alarm = (coming | (near4 >= EVAC_NEAR_TRIGGER)) & (near8 >= 150)
    dist = evac_distance(world)
    # people who trust the walls stay: held fortification sites and ground the army or terrain really protects
    src = (alarm & (H >= EVAC_MIN_POP) & (protection(world) < EVAC_TRUST) & ~world.fort_mask()
           & (is_land(world.T)) & (dist > 0) & (dist < 10 ** 6))
    src &= world.rng.random(H.shape) < EVAC_CHANCE
    if not src.any():
        return 0
    ok = world.land & (dist < 10 ** 6)
    return _flow(world, src, ok, EVAC_SHARE, dist, 1.0, min_move=2)


def refugees(world):
    """People in tiles that zombies have mostly taken over (even a single survivor) walk toward the nearest
    safe land.  Nobody has to give the order."""
    H, Z = world.H, world.Z
    dist = refuge_distance(world)
    src = (H > 0) & (Z > 0) & (Z * 2 >= H) & (dist > 0) & (dist < 10 ** 6)
    if not src.any():
        return 0
    ok = world.land & (dist < 10 ** 6)
    return _flow(world, src, ok, REFUGEE_SHARE, dist, 1.0, min_move=1)


def stragglers(world):
    """Small groups leave threatened districts for quiet, uninfected places far away (see the module notes)."""
    H, Z, O = world.H, world.Z, world.O
    near4 = world.zombie_near(4)
    src = np.flatnonzero(((H >= STRAY_MIN_POP) & (near4 >= STRAY_FEAR) & world.land).ravel())
    if src.size == 0:
        return 0
    rng = world.rng
    if src.size > STRAY_SOURCES:
        src = rng.choice(src, STRAY_SOURCES, replace=False)
    near8 = world.zombie_near(8)
    mass = world.statics.landmass
    closed = getattr(world, "closed", set()) or set()
    Hf, Zf = H.ravel(), Z.ravel()
    moved = 0
    for k in src:
        r, c = divmod(int(k), world.cols)
        n = int(min(STRAY_GROUP, Hf[k] // 4))
        if n <= 0:
            continue
        dist = rng.uniform(*STRAY_RANGE, STRAY_TRIES)
        ang = rng.uniform(0, 2 * np.pi, STRAY_TRIES)
        tr = np.rint(r + dist * np.sin(ang)).astype(int)
        tc = np.rint(c + dist * np.cos(ang)).astype(int)
        if world.wrap:
            tc %= world.cols
        for r2, c2 in zip(tr, tc):
            if not (0 <= r2 < world.rows and 0 <= c2 < world.cols):
                continue
            if (mass[r2, c2] != mass[r, c] or not world.land[r2, c2] or near8[r2, c2] > 0
                    or not 20 <= H[r2, c2] < 240):
                continue
            dest, home = O[r2, c2], O[r, c]
            if dest != home and dest in closed and world.pyrng.random() >= STRAY_BORDER:
                break                                    # turned back at the border
            ratio = min(1.0, Zf[k] / max(Hf[k], 1))
            p = min(1.0, ratio * STRAY_BITTEN + STRAY_BASE)
            bitten = int(rng.binomial(n, p)) if world.stochastic else int(n * p)
            Hf[k] -= n
            H[r2, c2] += n - bitten
            Z[r2, c2] += bitten
            moved += n
            if bitten and dest != home and dest and world.pyrng.random() < 0.05:
                from fracture import _place
                world.note(f"refugees slip into {world.civs[int(dest)].name} near {_place(world, (int(r2), int(c2)))}"
                           f" - {bitten} of them were bitten")
            break
    return moved


def step(world):
    H, D, T, O = world.H, world.D, world.T, world.O
    near = world.zombie_near(NEAR_RADIUS)
    prot = protection(world)

    nf = near.astype(np.float32)
    p10 = np.minimum(prot, 10).astype(np.float32)
    fear = np.clip(nf / PANIC_NEAR, 0, 1.5) * (1 - p10 / 10)
    h_before = H.copy()

    # --- panic flight -------------------------------------------------------------------
    scared = (near >= PANIC_NEAR) & (H >= PANIC_MIN_POP) & (prot < 7) & is_land(T)
    flee = scared & (world.rng.random(H.shape) < np.minimum(fear, 1.0) * PANIC_CHANCE)
    safety = nf * (1 - p10 / 12.0)                            # safer = fewer zombies, better protected
    if windows(world):
        world.last_panic = _flow(world, flee, world.land, PANIC_SHARE, safety, PANIC_IMPROVEMENT)
        if world.ticks % 2 == 0:                  # (mass evacuations every other tick - half the work)
            world.last_evac = mass_evacuation(world)
        world.last_refugees = refugees(world)
        if world.ticks % STRAY_EVERY == 0:
            world.last_strays = stragglers(world)
    else:
        world.last_panic = world.last_evac = world.last_refugees = 0

    # --- unrest and riots (worked out on land only: nobody riots at sea) ----------------------
    li = world.statics.land_idx
    Hl, Ol, Tl = H.ravel()[li], O.ravel()[li], T.ravel()[li]
    morale = np.array([NO_GOVERNMENT_MORALE if c.is_anarchy else c.morale for c in world.civs], dtype=np.float32)
    restraint = np.clip(morale[Ol], 0, 10) / 10.0
    temper = np.array([1.0 if c.is_anarchy else govern.mod(c, "unrest") for c in world.civs], dtype=np.float32)[Ol]
    density = (np.clip(Hl / 255.0, 0, 1) + 0.5 * (Tl == 6)).astype(np.float32)
    famine_c = np.array([c.famine for c in world.civs], dtype=np.float32)
    famine = famine_c[Ol]
    hb = h_before.ravel()[li]
    arrivals = np.clip((Hl - hb) / np.maximum(hb, 20) - 0.05, 0, 1).astype(np.float32)     # refugees pouring in
    fear_l = fear.ravel()[li].astype(np.float32)
    U = world.U.ravel()
    U[li] = (U[li] * UNREST_DECAY
             + temper * (UNREST_GAIN * fear_l * (1 - 0.7 * restraint) * density
                         + FAMINE_UNREST * famine * density + REFUGEE_UNREST * arrivals * density))

    can_riot = (Tl == 6) | (Tl == 7) | (Hl >= RIOT_CITY_POP)
    riot_l = (U[li] >= RIOT_AT) & (Hl >= RIOT_MIN_POP) & can_riot & ((fear_l > 0.3) | (famine > 0))
    riot = np.zeros(H.shape, dtype=bool)
    riot.ravel()[li] = riot_l
    famine = famine_c[O]
    if riot.any():
        riot &= ~world.fort_mask()                    # a garrison keeps order inside its walls
    world.riot = riot
    world.last_riots = int(riot.sum())
    if riot.any():
        D[riot] = np.maximum(D[riot] - 1, 1)
        H[riot] -= (H[riot] * RIOT_DEATHS).astype(np.int32)
        world.U[riot] *= 0.5
        neighbours = box_sum(riot, 1) - riot
        world.U += RIOT_SPREAD * (neighbours > 0)
        world.R += riot & (fear >= SECEDE_FEAR)          # hunger riots don't break the country up
        per = np.bincount(O[riot], minlength=len(world.civs))
        for k in np.flatnonzero(per):
            civ = world.civs[k]
            if civ.ai and not civ.collapsed:
                civ.riot_hit += min(RIOT_MAX_HIT, int(per[k]) // RIOT_TILES_PER_HIT)
        secede = world.R >= RIOT_SECEDE
        if secede.any():
            O[secede] = 0
            world.R[secede] = 0
    world.R *= 0.98
