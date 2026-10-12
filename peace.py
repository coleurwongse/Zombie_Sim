"""After the war: when the zombies are (practically) gone, a government stands down and civilization re-forms.

Peacetime       every government starts out at peace (civ.peace); the first zombies in its region declare an emergency.
Emergency over  a government whose region (its land + REGION_REACH tiles around it) has held at most PEACE_Z zombies,
                with no horde (WATCH_Z) within WATCH tiles of its people, for PEACE_AFTER ticks declares the emergency
                over (civ.peace).  A new outbreak in the region
                (above PEACE_EXIT_Z) puts it back on a war footing.
Stand down      while at peace:
                  * forts that haven't seen a zombie within FORT_REGION tiles for FORT_QUIET ticks are dismantled one
                    at a time (KEEP_SITES are kept as a standing garrison - the ones closest to the capital);
                  * military defense on land with no zombies around wears back down to normal (DEMOB_EVERY);
                  * the army is partly demobilized (down to PEACE_ARMY), which frees materials.
Back to town    people displaced into the countryside, outposts and fort settlements drift back into the cities, wherever
                the cities have room (urban / suburban tiles below what they held before the outbreak, and below
                URBAN_FULL of what they can hold): rural tiles with more people than before send a
                small share of their people every few ticks one step along the road to the nearest city with room.
"""
import numpy as np

from terrain import is_land, is_water

from civilization import flow_away, FORT_REGION

PEACE_Z = 40
PEACE_AFTER = 60
PEACE_EXIT_Z = 200
WATCH = 20                 # ... and no horde within this many tiles of its people either (a quiet border with an
WATCH_Z = 300              #     empty mountain range in front of it is not peace while the horde is next door)
EVERY = 4
FORT_QUIET = 80
KEEP_SITES = 1
DEMOB_EVERY = 20
DEMOB_FLOOR = 3
PEACE_ARMY = 0.35
ALARM_ARMY = 0.4           # ... plus this x the world's alarm: with the world in flames nobody disbands its army
DEMOB_RATE = 0.002
URBAN_FULL = 0.85
URBAN_SHARE = 25           # a crowded rural tile sends 1/URBAN_SHARE of its people toward town per step ...
URBAN_MIN = 60             # ... if it has more than this many (and more than URBAN_RURAL of what its land holds:
URBAN_RURAL = 0.6          #     refugee camps, fort settlements; farms keep the hands they need)
URBAN_RANGE = 40
URBAN_REFRESH = 24


def _cap():
    import restart
    return restart.CAP


def step(world):
    for civ in world.civs:
        if not civ.ai or civ.collapsed or civ.is_anarchy or not civ.m:
            continue
        zone = civ.m.get("zone_z", 0)
        if zone <= PEACE_Z or civ.peace:
            win = civ.m.get("win") or (slice(None), slice(None))
            mine = (world.O[win] == civ.id) & (world.H[win] > 10)
            watch = int(world.zombie_near(WATCH)[win][mine].max()) if mine.any() else 0
            if watch > (3 if civ.peace else 1) * WATCH_Z:
                zone = max(zone, PEACE_EXIT_Z + 1)
        if civ.peace:
            if zone > PEACE_EXIT_Z:
                civ.peace = False
                civ.calm_ticks = 0
                civ.emergencies = getattr(civ, "emergencies", 0) + 1
                world.note(f"{civ.name}: zombies are back - the emergency is on again" if civ.emergencies > 1 else
                           f"{civ.name}: the outbreak reaches it - a state of emergency")
            continue
        civ.calm_ticks = civ.calm_ticks + 1 if zone <= PEACE_Z and civ.m.get("n", 0) else 0
        if civ.calm_ticks >= PEACE_AFTER:
            civ.peace = True
            world.note(f"{civ.name} declares the emergency over and starts to rebuild")
    if world.ticks % EVERY:
        return
    calm = [c for c in world.civs if c.ai and c.peace and not c.collapsed]
    if not calm:
        return
    for civ in calm:
        if getattr(civ, "emergencies", 1):           # (never had an emergency: nothing to stand down from)
            _stand_down(world, civ)
    _urbanize(world, calm)


def _stand_down(world, civ):
    near = world.zombie_near(FORT_REGION)
    for s in civ.sites:
        s["quiet"] = s.get("quiet", 0) + EVERY if near[s["center"]] == 0 else 0
    if len(civ.sites) > KEEP_SITES:
        cap = civ.capital or civ.sites[0]["center"]
        keep = sorted(civ.sites, key=lambda s: (s["center"][0] - cap[0]) ** 2 + (s["center"][1] - cap[1]) ** 2)[:KEEP_SITES]
        idle = [s for s in civ.sites if s not in keep and s["quiet"] >= FORT_QUIET and not s.get("standing")]
        if idle:
            s = idle[0]
            civ.sites.remove(s)
            for rc in s["tiles"]:
                world.D[rc] = min(world.D[rc], DEMOB_FLOOR)
            if not s.get("noted"):
                world.note(f"{civ.name} dismantles a fort at ({s['center'][0]},{s['center'][1]}) - no longer needed")
    civ.bases = []
    if world.ticks % DEMOB_EVERY == 0:
        win = world.bbox(civ.id)
        D = world.D[win]                                   # (a view)
        mask = np.zeros(world.D.shape, dtype=bool)
        for s in civ.sites:
            for rc in s["tiles"]:
                mask[rc] = True
        stand = (world.O[win] == civ.id) & (D > DEMOB_FLOOR) & ~mask[win] & (world.zombie_near(8)[win] == 0)
        D[stand] -= 1
    floor = army_floor(world)
    if civ.military > floor:
        civ.military = max(floor, civ.military - DEMOB_RATE)


def army_floor(world):
    """The army a government keeps (and may draft up to) in peacetime: more while the world is alarmed."""
    return PEACE_ARMY + ALARM_ARMY * getattr(world, "alarm", 0.0)


def _urbanize(world, calm):
    from people import _distance
    H, T, O = world.H, world.T, world.O
    ids = np.zeros(len(world.civs), dtype=bool)
    ids[[c.id for c in calm]] = True
    home = ids[O]
    cap = _cap()[T]
    town = (T == 6) | (T == 7)
    safe = world.zombie_near(4) == 0
    h0 = getattr(world, "H0", None)
    before = cap if h0 is None else np.maximum(h0, 1)
    room = town & (H < np.minimum(URBAN_FULL * cap, before)) & safe & is_land(T) & (home | (O == 0))
    if not room.any():
        return 0
    cache = getattr(world, "_urban", None)
    if cache is None or world.ticks - cache[0] >= URBAN_REFRESH:
        dist = _distance(world, is_land(T), room, URBAN_RANGE)
        world._urban = cache = (world.ticks, dist)
    dist = cache[1]
    src = (home & ~town & (H > np.maximum(URBAN_MIN, URBAN_RURAL * cap)) & (H > 1.1 * before) & safe & (dist > 0)
           & (dist < 10 ** 6))                    # (people displaced from somewhere: more than lived here before)
    if not src.any():
        return 0
    ok = is_land(T) & (dist < 10 ** 6) & (home | (O == 0))
    return flow_away(world, src, ok, URBAN_SHARE, dist, 1.0, min_move=1)
