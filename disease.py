"""Disease: epidemics of the ordinary kind - typhus in the refugee camps, cholera where the water works have stopped,
influenza in a cold winter.  They kill more than the dead do in some years.

world.sick (per tile, 0..1): the share of its people ill now; world.immune: the share that has had it and is immune
for a while (it wears off: IMMUNE_FADE).  Every EVERY days, per tile:
  catching   BETA x the sickness on the tile and round it (NEAR_WEIGHT) x crowding (people / CROWD_REF, CROWD_RANGE)
             x the season (WINTER_SICK x snow, FLU_SEASON x the winter everywhere: people huddle indoors) x hunger
             (HUNGER_SICK in a country in famine or rationing, or nobody's land) x 1 - SANITATION x tech (clean water,
             sewers, doctors) x the share not yet immune;
  getting    RECOVER of the sick a day are well again (immune);
  better
  dying      MORTALITY x the epidemic's own virulence x the sick a day - x (1 - tech.TECH_MEDICINE x tech): where
             medicine is gone a fever kills as it did centuries ago; x HUNGER_DEATH where people are starving.
New epidemics (SEED_*): every SEED_EVERY days, maybe one breaks out where conditions are worst - crowded camps and
cities, famine, winter, no medicine, the dead lying unburied (zombies killed nearby) - with a virulence of its own.
Across borders it travels with people (the neighbouring tiles; a shut border slows it, CLOSED_SPREAD) and with trade
(trade.py: TRADE_CARRY).  A country with many sick loses heart (SICK_MORALE) and grows unstable (motives.py); fewer
children are born (restart.grow).
"""
import numpy as np

EVERY = 2
BETA = 0.22
NEAR_WEIGHT = 0.35
CROWD_REF = 120.0
CROWD_RANGE = (0.15, 1.6)
WINTER_SICK = 0.9
FLU_SEASON = 0.25
HUNGER_SICK = 1.4
SANITATION = 0.45
RECOVER = 1 / 12.0
IMMUNE_FADE = 1 / 900.0
MORTALITY = 0.012          # (x virulence: about IFR = this / RECOVER: 14% where there is no medicine at all)
HUNGER_DEATH = 1.6
CLOSED_SPREAD = 0.3
SEED_EVERY = 10
SEED_CHANCE = 0.35         # x how bad the worst place is (0..1)
SEED_MIN_POP = 80
SEED_SICK = 0.02
VIRULENCE = (0.5, 1.6)
SICK_MORALE = 0.03         # a country with this share of its people ill loses a point of morale (every SEED_EVERY days)
TRADE_CARRY = 0.12         # (trade.py) per route per check, an epidemic with this many sick travels to the partner
DONE_AT = 30               # an epidemic with fewer sick than this (people) is over
NAMES_REAL = ("cholera", "typhus", "influenza", "dysentery", "measles", "typhoid", "diphtheria", "plague",
              "tuberculosis", "meningitis")
NAMES_FANTASY = ("the grey fever", "the wasting sickness", "the coughing plague", "marsh fever", "the sweating sickness",
                 "the red flux", "the shaking ague", "the black cough", "the pox", "the winter fever")


def _arrays(world):
    s = getattr(world, "sick", None)
    if s is None or s.shape != world.H.shape:
        world.sick = np.zeros(world.H.shape, dtype=np.float32)
        world.immune = np.zeros(world.H.shape, dtype=np.float32)
        world.virul = np.zeros(world.H.shape, dtype=np.float32)
        world.eid = np.zeros(world.H.shape, dtype=np.int16)
        world.epidemics = []
    return world.sick, world.immune, world.virul, world.eid


def _hungry_by(world):
    """Per government id: 1 in famine, 0.5 on short rations (and nobody's land: nobody feeding the camps)."""
    n = len(world.civs)
    h = np.zeros(n, dtype=np.float32)
    for c in world.civs:
        if c.id and c.ai and not c.collapsed:
            h[c.id] = 1.0 if c.famine else (0.5 if getattr(c, "rationing", False) else 0.0)
    h[0] = 0.5
    return h


def _hungry(world):
    return _hungry_by(world)[world.O]


def _conditions(world, win, sick_w):
    """Per tile of window `win`: how readily sickness spreads (x BETA), and how deadly it is (x MORTALITY)."""
    import seasons
    import tech
    H = np.maximum(world.H[win], 0).astype(np.float32)
    crowd = np.clip(H / CROWD_REF, *CROWD_RANGE)
    sn = seasons.snow(world)[win]
    w = np.broadcast_to(seasons._today(world)[4], world.H.shape)[win]
    season = 1.0 + WINTER_SICK * sn + FLU_SEASON * w
    hungry = _hungry_by(world)[world.O[win]]
    t = tech.level(world)[win]
    spread = crowd * season * (1.0 + (HUNGER_SICK - 1.0) * hungry) * (1.0 - SANITATION * t)
    deadly = (1.0 - tech.TECH_MEDICINE * t) * (1.0 + (HUNGER_DEATH - 1.0) * hungry)
    return spread.astype(np.float32), deadly.astype(np.float32)


def step(world):
    if not getattr(world, "ai", True) or getattr(world, "H0", None) is None:
        return
    sick, immune, virul, eid = _arrays(world)
    if world.ticks % SEED_EVERY == 0:
        _seed(world)
        _report(world)
    if world.ticks % EVERY:
        return
    world.last_sick_deaths = 0
    if immune.any():
        immune -= np.float32(IMMUNE_FADE * EVERY)
        np.maximum(immune, 0, out=immune)
    if not sick.any():
        return
    from engine import active_windows
    closed = np.zeros(len(world.civs), dtype=bool)
    for c in world.civs:
        closed[c.id] = c.id in getattr(world, "closed", set())
    per = np.zeros(len(world.epidemics) + 1)
    for win, wrap in active_windows(world, sick > 0, 3):
        _advance(world, win, wrap, closed, per)
    world.last_sick_deaths = int(per.sum())
    for k, d in enumerate(per[1:]):
        if d:
            world.epidemics[k]["deaths"] += float(d)
    _morale(world)


def _advance(world, win, wrap, closed, per):
    """One step of the epidemics inside window `win` (it holds every sick tile there, plus a margin)."""
    from engine import shift
    sick, immune, virul, eid = world.sick[win], world.immune[win], world.virul[win], world.eid[win]
    H, O = world.H[win], world.O[win]
    land = world.land[win] & (H > 0)
    spread, deadly = _conditions(world, win, sick)
    # sickness round each tile (people-weighted: a crowded sick town next door counts more than an empty one)
    hp = np.maximum(H, 0).astype(np.float32)
    ill = sick * hp
    near_ill = np.zeros_like(ill)
    near_pop = np.zeros_like(ill)
    near_v = virul.copy()
    near_e = eid.copy()
    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nb_o = shift(O, dr, dc, wrap, -1)
        damp = np.where((nb_o != O) & (closed[O] | closed[np.maximum(nb_o, 0)]), CLOSED_SPREAD, 1.0)
        near_ill += shift(ill, dr, dc, wrap, 0) * damp
        near_pop += shift(hp, dr, dc, wrap, 0)
        nv = shift(virul, dr, dc, wrap, 0)
        stronger = (shift(sick, dr, dc, wrap, 0) > 0.002) & (nv > near_v)
        near_v = np.where(stronger, nv, near_v)
        near_e = np.where(stronger, shift(eid, dr, dc, wrap, 0), near_e)
    pressure = (1 - NEAR_WEIGHT) * sick + NEAR_WEIGHT * near_ill / np.maximum(near_pop, 1)
    v = np.where(sick > 0.002, virul, near_v)
    e = np.where(sick > 0.002, eid, near_e)
    susceptible = np.clip(1.0 - sick - immune, 0, 1)
    catch = BETA * v * spread * pressure * susceptible * EVERY
    better = sick * min(1.0, RECOVER * EVERY)
    new = np.where(land, np.clip(sick + catch - better, 0, 1), 0).astype(np.float32)
    dying = sick * MORTALITY * virul * deadly * EVERY
    deaths = np.floor(hp * dying + (world.rng.random(H.shape, dtype=np.float32) if world.stochastic else 0.5))
    deaths = np.minimum(np.where(land, deaths, 0), hp).astype(np.int32)
    H -= deaths
    if deaths.any():
        d = deaths > 0
        per += np.bincount(eid[d], weights=deaths[d], minlength=per.size)[:per.size]
    immune += np.where(land, better, 0).astype(np.float32)
    np.clip(immune, 0, 1, out=immune)
    new[new < 0.0005] = 0
    sick[:] = new
    virul[:] = np.where(new > 0, v, 0)
    eid[:] = np.where(new > 0, e, 0)


def _risk(world):
    """0..1 per tile: how likely an epidemic is to break out there."""
    import seasons
    import tech
    H = np.maximum(world.H, 0).astype(np.float32)
    import restart
    home = restart.home(world).astype(np.float32)
    crowded = np.clip((H - 1.1 * home) / np.maximum(home, 30), 0, 1)
    city = np.clip(H / 255.0, 0, 1)
    hungry = _hungry(world)
    sn = seasons.snow(world)
    _, _, _, _, w = seasons._today(world)
    dead = np.clip(world.zombie_near(2) / 200.0, 0, 1)
    nomed = 1.0 - tech.level(world)
    r = (0.35 * crowded + 0.15 * city + 0.25 * hungry + 0.15 * sn + 0.1 * w + 0.15 * dead) * (0.4 + 0.6 * nomed)
    r[(H < SEED_MIN_POP) | ~world.land] = 0
    r *= 1.0 - np.clip(world.immune, 0, 1)
    return r


def _seed(world):
    r = _risk(world)
    top = float(r.max())
    if top <= 0 or world.pyrng.random() >= SEED_CHANCE * min(1.0, top / 0.5):
        return
    flat = r.ravel()
    best = np.argpartition(flat, -50)[-50:] if flat.size > 50 else np.arange(flat.size)
    best = best[flat[best] > 0.5 * top]
    w = flat[best] / flat[best].sum()
    i = int(world.rng.choice(best, p=w)) if world.stochastic else int(best[np.argmax(w)])
    rr, cc = divmod(i, world.cols)
    outbreak(world, rr, cc)


def outbreak(world, r, c, virulence=None, name=None, via=None):
    sick, immune, virul, eid = _arrays(world)
    if virulence is None:
        lo, hi = VIRULENCE
        virulence = lo + (hi - lo) * (world.pyrng.random() ** 1.5 if world.stochastic else 0.4)
    real = getattr(world, "meta", {}).get("real_population", 8.2e9) > 1e9 if hasattr(world, "meta") else True
    name = name or world.pyrng.choice(NAMES_REAL if real else NAMES_FANTASY)
    if len(world.epidemics) >= 32000:
        return None
    ep = dict(id=len(world.epidemics) + 1, name=name, r=int(r), c=int(c), born=world.ticks, deaths=0.0,
              virulence=float(virulence), noted=False, over=False)
    world.epidemics.append(ep)
    r0, r1, c0, c1 = max(r - 1, 0), r + 2, max(c - 1, 0), c + 2
    sick[r0:r1, c0:c1] = np.maximum(sick[r0:r1, c0:c1], np.where(world.land[r0:r1, c0:c1], SEED_SICK, 0))
    virul[r0:r1, c0:c1] = np.where(sick[r0:r1, c0:c1] > 0, virulence, virul[r0:r1, c0:c1])
    eid[r0:r1, c0:c1] = np.where(sick[r0:r1, c0:c1] > 0, ep["id"], eid[r0:r1, c0:c1])
    from fracture import _place
    place = _place(world, (r, c))
    ep["place"] = place
    o = int(world.O[r, c])
    where = f"{place}" + (f" ({world.civs[o].name})" if o else "")
    how = f" - carried by trade from {via}" if via else ""
    world.war_note(f"EPIDEMIC: {name} breaks out in {where}{how}", log=True)
    import globalaffairs
    globalaffairs.mark(world, r, c, "epidemic")
    return ep


def _report(world):
    """Epidemics that have burned out: told of in the log with their dead."""
    eps = getattr(world, "epidemics", None)
    if not eps:
        return
    live = np.bincount(world.eid.ravel(), weights=(world.sick * np.maximum(world.H, 0)).ravel(),
                       minlength=len(eps) + 1)
    for ep in eps:
        if ep["over"]:
            continue
        if live[ep["id"]] < DONE_AT and world.ticks - ep["born"] >= 20:
            ep["over"] = True
            if ep["deaths"] >= 20:
                world.war_note(f"the {ep['name']} around {ep.get('place', '?')} dies down - "
                               f"{world.people(ep['deaths'])} dead", log=ep["deaths"] >= 200)


def _morale(world):
    if world.ticks % SEED_EVERY:
        return
    n = len(world.civs)
    o = world.O.ravel()
    hp = np.maximum(world.H, 0).ravel().astype(np.float64)
    pop = np.bincount(o, weights=hp, minlength=n)
    ill = np.bincount(o, weights=hp * world.sick.ravel(), minlength=n)
    share = ill / np.maximum(pop, 1)
    for c in world.civs:
        if c.id and c.ai and not c.collapsed:
            c.sick_share = float(share[c.id])
            if share[c.id] >= SICK_MORALE and c.morale > 3:
                c.riot_hit += 1


def sick_share(c):
    return float(getattr(c, "sick_share", 0.0))


def carry(world, a, b):
    """Trade route a - b: an epidemic in one may travel to the other's capital (trade.py)."""
    if not getattr(world, "epidemics", None):
        return
    for src, dst in ((a, b), (b, a)):
        if sick_share(src) * (src.m.get("pop", 0) if src.m else 0) < 50 or dst.capital is None:
            continue
        if world.pyrng.random() < TRADE_CARRY and world.sick[dst.capital] < 0.01:
            v, name = _worst(world, src)
            if v is not None:
                outbreak(world, *dst.capital, virulence=v, name=name, via=src.name)
            return


def _worst(world, c):
    """(virulence, name) of the worst epidemic in country `c` now (None, None if none)."""
    m = (world.O == c.id) & (world.sick > 0.01)
    if not m.any():
        return None, None
    i = int(np.argmax(np.where(m, world.sick * np.maximum(world.H, 0), -1)))
    k = int(world.eid.ravel()[i])
    name = world.epidemics[k - 1]["name"] if 0 < k <= len(world.epidemics) else None
    return float(world.virul.ravel()[i]), name
