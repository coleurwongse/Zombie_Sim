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
                uninfected place on the same landmass - most a short way, some to a city or port further off (bigger
                cities likelier).  Some of them were bitten: that's how the infection turns up in a city far from the
                outbreak.
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
STRAY_SOURCES = 6          # ... up to this many threatened districts send a group off - a few more when much is
STRAY_PER_SOURCE = 300     # threatened: one more for every this many threatened districts ...
STRAY_MAX_SOURCES = 14     # ... up to this many
STRAY_FEAR = 60            # zombies within 4 tiles that make people leave on their own
STRAY_MIN_POP = 30
STRAY_GROUP = 10           # people per group (at most)
STRAY_RANGE = (4, 16)      # most groups go a short way (tiles) to somewhere quiet ...
STRAY_FAR = 0.25           # ... this share head for a city or port further off ...
STRAY_FAR_RANGE = (16, 60) # ... this far (tiles) - the bigger the city, the likelier
STRAY_TRIES = 6            # destinations tried per group
STRAY_BITTEN = 0.4         # share of the zombie:people ratio where they left that turns on arrival ...
STRAY_BASE = 0.01          # ... plus this (bites hidden from the others)
STRAY_BORDER = 0.5         # chance a group gets past a shut border
STRAY_SCREEN = 0.8         # a mobilized, adapted country catches up to this share of the bitten at its checkpoints

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
EXODUS_EVERY = 5           # mass exodus: every this many days the people of a country in trouble ...
EXODUS_DANGER = 0.45       # ... (danger at least this, or famine) ...
EXODUS_SAFER = 0.2         # ... flee into a neighbour at least this much safer (and fed), not at war with it:
EXODUS_REACH = 8           # those within this many tiles of the border,
EXODUS_SHARE = 0.10        # this share of them per round (x how bad it is),
EXODUS_INTO = 3            # onto its lived-on land within this many tiles of the border (no more than the land
EXODUS_ROOM = 1.3          #  holds: this x what each place is rebuilt to - restart.home).
EXODUS_CLOSED = 0.3        # A shut border lets this share through ...
EXODUS_PRESS = 1           # ... and the crowds at the crossing points knock its defenses down by this (either way)
EXODUS_UNREST = 0.4        # unrest added where they arrive (x arrivals / residents)
EXODUS_NOTE = 150          # (waves this big are told of in the log - once in a while per pair of countries)
EXODUS_BITTEN = 0.08       # share of the refugees bitten (x how exposed the people they left were) - they turn there
NO_GOVERNMENT_MORALE = 3   # how much restraint a tile with no civilization has


def _distance(world, land, safe, steps):
    """Steps (8-way, over `land`) from every tile to the nearest `safe` tile, up to `steps` (10**6 beyond).
    A 3x3 minimum done as a row pass then a column pass - same result as checking all 8 neighbours, half the work
    (in 16-bit integers, in place)."""
    INF = 30000
    dist = np.where(safe, 0, INF).astype(np.int16)
    wall = np.where(land, 0, INF).astype(np.int16)
    m, best = np.empty_like(dist), np.empty_like(dist)
    for i in range(steps):
        m[:] = dist
        np.minimum(m[:, 1:], dist[:, :-1], out=m[:, 1:])
        np.minimum(m[:, :-1], dist[:, 1:], out=m[:, :-1])
        best[:] = m
        np.minimum(best[1:], m[:-1], out=best[1:])
        np.minimum(best[:-1], m[1:], out=best[:-1])
        best += 1
        np.minimum(best, dist, out=best)
        np.maximum(best, wall, out=best)
        if i % 3 == 2 and np.array_equal(best, dist):
            break
        dist, best = best, dist
    out = dist.astype(np.int32)
    out[out >= INF] = 10 ** 6
    return out


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
           & world.land & (dist > 0) & (dist < 10 ** 6))
    rr, cc = np.nonzero(src)
    if rr.size == 0:
        return 0
    stay = world.rng.random(rr.size) >= EVAC_CHANCE
    src[rr[stay], cc[stay]] = False
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


def _places(world):
    """Cities and ports as (rows, cols, weight) arrays: where people travelling far are headed."""
    cache = getattr(world, "_stray_places", None)
    if cache is None:
        pts = {}
        for name, r, c, pop in world.cities:
            pts[(r, c)] = max(pts.get((r, c), 0.0), max(pop, 0.01))
        for r, c, size in getattr(world, "ports", []):
            pts[(r, c)] = pts.get((r, c), 0.0) + 0.05 * size
        if pts:
            rc = np.array(list(pts), dtype=np.int64)
            cache = (rc[:, 0], rc[:, 1], np.sqrt(np.array(list(pts.values()))))
        else:
            cache = (np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0))
        world._stray_places = cache
    return cache


def stragglers(world):
    """Small groups leave threatened districts for quiet, uninfected places (see the module notes): most a short way,
    some to a city or port further off."""
    H, Z, O = world.H, world.Z, world.O
    near4 = world.zombie_near(4)
    src = np.flatnonzero(((H >= STRAY_MIN_POP) & (near4 >= STRAY_FEAR) & world.land).ravel())
    if src.size == 0:
        return 0
    rng = world.rng
    k_src = min(STRAY_MAX_SOURCES, max(STRAY_SOURCES, src.size // STRAY_PER_SOURCE))
    if src.size > k_src:
        src = rng.choice(src, k_src, replace=False)
    near8 = world.zombie_near(8)
    mass = world.statics.landmass
    closed = getattr(world, "closed", set()) or set()
    pr, pc, pw = _places(world)
    Hf, Zf = H.ravel(), Z.ravel()
    moved = 0
    for k in src:
        r, c = divmod(int(k), world.cols)
        n = int(min(STRAY_GROUP, Hf[k] // 4))
        if n <= 0:
            continue
        far = pr.size > 0 and rng.random() < STRAY_FAR
        if far:                                          # a city or port within reach, bigger ones likelier
            dc = np.abs(pc - c)
            if world.wrap:
                dc = np.minimum(dc, world.cols - dc)
            d = np.hypot(pr - r, dc)
            ok = (d >= STRAY_FAR_RANGE[0]) & (d <= STRAY_FAR_RANGE[1])
            ok &= (mass[pr, pc] == mass[r, c]) & (near8[pr, pc] == 0)
            idx = np.flatnonzero(ok)
            if idx.size == 0:
                continue
            w = pw[idx] / pw[idx].sum()
            pick = rng.choice(idx, size=min(STRAY_TRIES, idx.size), replace=False, p=w)
            tr = pr[pick] + rng.integers(-1, 2, pick.size)
            tc = pc[pick] + rng.integers(-1, 2, pick.size)
        else:
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
            if dest:                                     # a mobilized country screens who comes in (better once
                dc_ = world.civs[int(dest)]               # it has learned how: resolve.py)
                p *= 1.0 - STRAY_SCREEN * min(1.0, dc_.alert * (0.5 + 0.5 * getattr(dc_, "resolve", 0.0)) * 1.5)
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


def exodus(world):
    """Mass exodus across international borders (EXODUS_*): returns how many fled."""
    import war
    civs = world.civs
    closed = getattr(world, "closed", set()) or set()
    total = 0
    H, O, D, Z = world.H, world.O, world.D, world.Z
    for (a, b), length in war.contacts(world).items():
        for src, dst in ((civs[a], civs[b]), (civs[b], civs[a])):
            if not (src.ai and dst.ai and not src.collapsed and not dst.collapsed and src.m and dst.m
                    and src.m.get("n") and dst.m.get("n")) or war.key(src.id, dst.id) in world.wars:
                continue
            ds = 1.0 if src.famine else src.danger(src.m)[0]
            dd = 1.0 if dst.famine else dst.danger(dst.m)[0]
            if max(ds, 1.0 if src.famine else 0.0) < EXODUS_DANGER or dd > ds - EXODUS_SAFER:
                continue
            win = war._pair_window(world, src.id, dst.id, EXODUS_REACH + 1)
            Hw, Ow, Dw, Zw = H[win], O[win], D[win], Z[win]
            theirs, mine = Ow == dst.id, Ow == src.id
            leave = mine & (Hw > 20) & (Zw * 2 < Hw) & (box_sum(theirs, EXODUS_REACH) > 0)
            arrive = theirs & (Hw > 10) & (box_sum(mine, EXODUS_INTO) > 0)
            if not leave.any() or not arrive.any():
                continue
            share = EXODUS_SHARE * min(1.0, (ds - EXODUS_SAFER) * 2.0)
            go = np.where(leave, np.floor(Hw * share), 0).astype(np.int64)
            n = int(go.sum())
            if n <= 0:
                continue
            shut = dst.id in closed
            through = int(n * (EXODUS_CLOSED if shut else 1.0))
            ar, ac = np.nonzero(arrive)
            Dw[ar, ac] = np.maximum(Dw[ar, ac] - EXODUS_PRESS, 1)          # (checkpoints overwhelmed)
            if through <= 0:
                continue
            go = np.floor(go * (through / n)).astype(np.int64)
            import restart
            cap = np.minimum(255, EXODUS_ROOM * restart.home(world)[win][ar, ac] + 15).astype(np.int64)
            room = np.maximum(cap - Hw[ar, ac].astype(np.int64), 0)
            if room.sum() <= 0:
                continue
            through = min(int(go.sum()), int(room.sum()))
            go = np.floor(go * (through / max(int(go.sum()), 1))).astype(np.int64)
            through = int(go.sum())
            Hw -= go.astype(Hw.dtype)
            put = np.floor(room * (through / room.sum())).astype(np.int64)
            put[0] += through - int(put.sum())
            bitten = np.floor(put * EXODUS_BITTEN * min(1.0, src.m.get("pop_exposure", 0.0) * 3 + 0.2)).astype(np.int64)
            Hw[ar, ac] += (put - bitten).astype(Hw.dtype)
            Zw[ar, ac] = np.minimum(Zw[ar, ac] + bitten, 255).astype(Zw.dtype)
            U = getattr(world, "U", None)
            if U is not None:
                Uw = U[win]
                Uw[ar, ac] += EXODUS_UNREST * put / np.maximum(Hw[ar, ac], 1)
            total += through
            if through >= EXODUS_NOTE:
                noted = world.__dict__.setdefault("_exodus_noted", {})
                if world.ticks - noted.get((src.id, dst.id), -10 ** 6) >= 60:
                    noted[(src.id, dst.id)] = world.ticks
                    why = "famine" if src.famine else "the zombies"
                    world.note(f"{world.people(through)} people flee {why} in {src.name} across the border into "
                               f"{dst.name}" + (" - past its shut border" if shut else ""))
                    marked = world.__dict__.setdefault("_exodus_marked", {})
                    if through >= 3 * EXODUS_NOTE and world.ticks - marked.get(src.id, -10 ** 6) >= 60:
                        marked[src.id] = world.ticks                # (the map: a country's big waves, now and then)
                        import globalaffairs
                        globalaffairs.mark(world, int(ar[0] + (win[0].start or 0)), int(ac[0] + (win[1].start or 0)),
                                           "refugees")
    return total


DECONGEST_EVERY = 3        # crowds disperse: every this many days, where no zombie is within DECONGEST_CALM tiles,
DECONGEST_CALM = 4         # a tile holding more than DECONGEST_OVER x what it is rebuilt to (+ DECONGEST_SLACK) -
DECONGEST_OVER = 1.3       # refugees stuck against a river, on a mountain, at a border - sends DECONGEST_SHARE of the
DECONGEST_SLACK = 15       # excess to the neighbouring land of its own government (or nobody's, for nobody's) that
DECONGEST_SHARE = 0.3      # has room (up to DECONGEST_FILL x what it is rebuilt to, + DECONGEST_FILL_SLACK): the
DECONGEST_FILL = 1.1       # camps empty into the countryside once the danger has passed
DECONGEST_FILL_SLACK = 8


def decongest(world):
    """Overcrowded tiles in calm country send people to neighbours with room (DECONGEST_*).  Returns how many moved."""
    import restart
    from terrain import habitable
    H, O = world.H, world.O
    hm = restart.home(world)
    calm = (world.zombie_near(DECONGEST_CALM) == 0) & world.land
    cap = DECONGEST_OVER * hm + DECONGEST_SLACK
    over = calm & (H > cap)
    if not over.any():
        return 0
    excess = np.where(over, np.ceil((H - cap) * DECONGEST_SHARE), 0).astype(np.int64)
    room = np.where(calm & habitable(world.T) & (H >= 0),
                    np.maximum(DECONGEST_FILL * hm + DECONGEST_FILL_SLACK - H, 0), 0).astype(np.int64)
    rows, cols = H.shape
    total = np.zeros(H.shape, dtype=np.int64)
    for dr, dc in DIRECTIONS:                        # (room next door, of the same government)
        sr, tr = _slices(rows, dr)
        sc, tc = _slices(cols, dc)
        total[sr, sc] += np.where(O[tr, tc] == O[sr, sc], room[tr, tc], 0)
    excess = np.minimum(excess, total)
    left = excess.copy()
    moved = 0
    for dr, dc in DIRECTIONS:
        sr, tr = _slices(rows, dr)
        sc, tc = _slices(cols, dc)
        share = np.where(O[tr, tc] == O[sr, sc], room[tr, tc], 0)
        amt = np.where(total[sr, sc] > 0, -(-excess[sr, sc] * share // np.maximum(total[sr, sc], 1)), 0)   # (rounded up)
        amt = np.minimum(np.minimum(amt, room[tr, tc]), left[sr, sc])
        left[sr, sc] -= amt
        amt = amt.astype(H.dtype)
        H[sr, sc] -= amt
        H[tr, tc] += amt
        room[tr, tc] -= amt
        moved += int(amt.sum())
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
        if world.ticks % EXODUS_EVERY == 0:
            world.last_exodus = exodus(world)
        if world.ticks % STRAY_EVERY == 0:
            world.last_strays = stragglers(world)
    else:
        world.last_panic = world.last_evac = world.last_refugees = 0
    if world.ticks % DECONGEST_EVERY == 0 and getattr(world, "H0", None) is not None:
        world.last_dispersed = decongest(world)       # (crowds disperse - with or without zombies about)

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
