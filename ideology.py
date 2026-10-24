"""Ideologies and cults: now and then a country is carried away by a creed - not often.

Creeds (civ.ideology; CREEDS):
  faith        zealots: the outbreak was a judgement.  Morale that doesn't break, a bigger army, aggressive; distrusts
               the unbelievers.  Grows out of famine, plague and hard winters.
  restoration  restorationists: rebuild the old world - its machines, its medicine, its borders.  Technology rebuilt
               fast (tech.py), merges readily, trades.  Grows where much was lost but enough people are left to try.
  purity       purifiers: a hard, armed creed of cleansing - every zombie and everyone who might turn.  Kills zombies
               better (PURITY_KILL), militarist, expansionist, hostile to everyone.  Grows out of juntas and warlords
               at war.
  commune      communards: land, bread and each other.  Feeds itself well, hardly fights, peaceable.  Grows in the
               countryside (clans, villages) after hard times.
  risen        a death cult - the Children of the Risen: the dead are holy, the bitten blessed.  Its people won't harm
               the dead (RISEN_KILL) - a cult country is a hole in the defences.  Only ever a cult that took over.
How a country comes to one:
  revolution   a revolution (globalaffairs.py) brings a creed to power with REVOLT_CREED (the one that fits what drove
               it);
  founding     a new state takes one up with FOUND_CREED;
  cults        a cult (CULT_*) springs up in a desperate place - famine, plague, the snow and no fuel, an unstable or
               no government - and grows while things stay bad (CULT_GROW), shrinks under a secure government that
               cracks down (CULT_SUPPRESS); once strong enough it takes over its country (a theocracy, when its host
               is unstable enough: CULT_TAKEOVER) or breaks away with the land around it (CULT_REACH) - at most
               CULTS_MAX at once;
  spreading    a zealous creed (faith, purity) may win over an unstable neighbour (SPREAD_CHANCE).
And it fades: every check a creed may lose its hold (FADE_CHANCE, x how secure and settled the country now is).
Creeds also colour diplomacy (affinity: the same creed draws together, a zealous one against everyone else).
"""
import numpy as np

import motives

EVERY = 30
#                food  mat   army  m_loss recover unrest aggr  merge  tech
CREEDS = {
    "faith":       (1.00, 0.90, 1.20, 0.65, 1.10, 0.80, 1.30, 0.50, 0.7),
    "restoration": (1.00, 1.10, 1.00, 1.00, 1.10, 1.00, 0.90, 1.30, 2.5),
    "purity":      (0.95, 1.00, 1.35, 0.80, 0.90, 0.80, 1.50, 0.40, 1.0),
    "commune":     (1.12, 0.85, 0.80, 0.90, 1.10, 0.80, 0.60, 1.10, 0.9),
    "risen":       (0.90, 0.70, 0.80, 0.50, 1.00, 0.60, 1.20, 0.20, 0.5),
}
KEYS = ("food", "materials", "army", "morale_loss", "recover", "unrest", "aggression", "merge", "tech")
LABEL = {"faith": "zealots", "restoration": "restorationists", "purity": "purifiers", "commune": "communards",
         "risen": "death cult"}
TAG = {"faith": "Fa", "restoration": "Rs", "purity": "Pu", "commune": "Co", "risen": "Dc"}
MILITARISM = {"faith": 0.2, "purity": 0.35, "commune": -0.3, "restoration": 0.0, "risen": 0.1}
AMBITION = {"faith": 0.1, "purity": 0.25, "commune": -0.25, "restoration": 0.1, "risen": 0.0}
ZEALOUS = ("faith", "purity", "risen")
SAME = 0.35                # affinity: the same creed
AGAINST = -0.25            # a zealous creed toward anyone else (and they toward it)
PURITY_KILL = 1.25
RISEN_KILL = 0.4
REVOLT_CREED = 0.2
FOUND_CREED = 0.03
CULT_CHANCE = 0.05         # per check, where conditions are worst
CULTS_MAX = 3              # (x land / crime.RINGS_LAND, at least 1)
CULT_MISERY = 0.35         # (how bad things must be: famine, sickness, snow without fuel, unrest)
CULT_MIN_POP = 60
CULT_GROW = 0.12           # strength per check x misery around it
CULT_SUPPRESS = 0.15       # ... less this x the host's security x army
CULT_TAKEOVER = 0.5        # (host instability for a cult to take the country over)
CULT_REACH = 6
RISEN_SHARE = 0.25         # share of cults that are death cults
SPREAD_CHANCE = 0.02
FADE_CHANCE = 0.03
NAMES = {
    "faith": ("the Church of the Last Days", "the Brethren of the Reckoning", "the Faithful Remnant",
              "the Covenant of {p}", "the Order of the Burning Lamp", "the Penitents of {p}"),
    "restoration": ("the Restoration League", "the Society for the Old World", "the Engineers of {p}"),
    "purity": ("the Purifiers", "the Cleansing Brotherhood", "the White Hand of {p}", "the Iron Covenant"),
    "commune": ("the Commune of {p}", "the Brotherhood of the Plough", "the Free Fields"),
    "risen": ("the Children of the Risen", "the Communion of the Dead", "the Grey Pilgrims", "the Kin of the Hungry"),
}


def creed(c):
    return getattr(c, "ideology", None)


def mod(c, key):
    k = creed(c)
    if k is None or k not in CREEDS:
        return 1.0
    return CREEDS[k][KEYS.index(key)]


def affinity(a, b):
    x, y = creed(a), creed(b)
    if x is None and y is None:
        return 0.0
    if x == y:
        return SAME
    if x in ZEALOUS or y in ZEALOUS:
        return AGAINST
    return 0.0


def militarism(c):
    return MILITARISM.get(creed(c), 0.0)


def ambition(c):
    return AMBITION.get(creed(c), 0.0)


def kill_mult(world):
    """Per tile: how a creed changes the killing of zombies (None: nowhere)."""
    if not any(creed(c) in ("purity", "risen") for c in world.civs if not c.collapsed):
        return None
    m = np.ones(len(world.civs), dtype=np.float32)
    for c in world.civs:
        m[c.id] = PURITY_KILL if creed(c) == "purity" else RISEN_KILL if creed(c) == "risen" else 1.0
    return m[world.O]


def cults(world):
    return world.__dict__.setdefault("cults", [])


def adopt(world, c, k, how):
    old = creed(c)
    c.ideology = k
    c.ideology_since = world.ticks
    if k is None:
        world.war_note(f"{c.name}: the {LABEL.get(old, old)} lose their hold - the creed fades")
        return
    world.war_note(f"CREED: {c.name} {how} - {LABEL[k]} now hold power")
    if c.capital is not None:
        import globalaffairs
        globalaffairs.mark(world, *c.capital, "creed")


def fitting(world, c):
    """The creed that fits what a country has been through."""
    import disease
    import tech
    hard = (1.0 if c.famine else 0.0) + 4 * disease.sick_share(c) + 0.5 * motives.instability(c)
    lost = 1.0 - tech.civ_level(c)
    import war
    scores = {
        "faith": hard + 0.2,
        "restoration": 1.5 * lost + (0.3 if c.gov in ("democracy", "national") else 0.0),
        "purity": (0.6 if c.gov in ("junta", "warlord") else 0.0) + (0.4 if war.at_war(world, c.id) else 0.0)
                  + 0.3 * motives.militarism(c),
        "commune": (0.6 if c.gov == "tribal" else 0.0) + 0.5 * war.scarcity(c) + 0.1,
    }
    w = np.array([max(0.01, v) for v in scores.values()])
    keys = list(scores)
    if world.stochastic:
        return keys[int(world.rng.choice(len(keys), p=w / w.sum()))]
    return keys[int(np.argmax(w))]


def on_revolution(world, c):
    """Called after a revolution in `c` (globalaffairs.py)."""
    if creed(c) is None and world.pyrng.random() < REVOLT_CREED:
        adopt(world, c, fitting(world, c), "is swept by a new creed in the revolution")
    elif creed(c) is not None and world.pyrng.random() < 0.5:
        adopt(world, c, None, "")


def step(world):
    if world.ticks % EVERY or not getattr(world, "ai", True):
        return
    live = [c for c in world.civs if c.id and c.ai and not c.collapsed and c.m and c.m.get("n")]
    calm = motives.settled(world)
    for c in live:
        if not getattr(c, "_creed_checked", False):       # (a new state: maybe it takes up a creed from the start)
            c._creed_checked = True
            if c.successor and world.ticks - c.founded <= EVERY and creed(c) is None \
                    and world.pyrng.random() < FOUND_CREED:
                adopt(world, c, fitting(world, c), "is founded on a creed")
                continue
        k = creed(c)
        if k is not None:
            sec = motives.security(world, c)
            if world.pyrng.random() < FADE_CHANCE * (0.3 + sec) * (2.0 - calm) * (2.0 if k == "risen" else 1.0):
                adopt(world, c, None, "")
                if c.gov == "theocracy":
                    c.gov = "national"
            continue
    _spread(world, live)
    _cults(world, live)


def _spread(world, live):
    import war
    touching = war.contacts(world)
    by_id = {c.id: c for c in live}
    for (a, b), n in touching.items():
        if n < war.MIN_BORDER:
            continue
        for x, y in ((a, b), (b, a)):
            cx, cy = by_id.get(x), by_id.get(y)
            if cx is None or cy is None or creed(cx) not in ("faith", "purity") or creed(cy) is not None:
                continue
            if world.pyrng.random() < SPREAD_CHANCE * motives.instability(cy) * motives.settled(world) ** 0:
                adopt(world, cy, creed(cx), f"is won over by its neighbour's creed ({cx.name})")


def _cap(world):
    import crime
    land = int(world.statics.land.sum())
    return int(max(1, min(CULTS_MAX, round(CULTS_MAX * land / crime.RINGS_LAND))))


def _misery(world):
    """0..1 per tile: how desperate life is there."""
    import disease
    import seasons
    hungry = disease._hungry(world)
    sick = np.clip(world.sick * 6, 0, 1) if getattr(world, "sick", None) is not None else 0
    U = np.clip(world.U / 2.0, 0, 1) if getattr(world, "U", None) is not None else 0
    nofuel = np.zeros(len(world.civs), dtype=np.float32)
    for c in world.civs:
        if c.id and not c.collapsed and c.materials < 5:
            nofuel[c.id] = 1.0
    cold = seasons.snow(world) * nofuel[world.O]
    inst = np.zeros(len(world.civs), dtype=np.float32)
    for c in world.civs:
        inst[c.id] = motives.instability(c) if c.id else 0.6
    return np.clip(0.35 * hungry + 0.3 * sick + 0.2 * U + 0.2 * cold + 0.3 * inst[world.O], 0, 1)


def _cults(world, live):
    cs = cults(world)
    for g in cs:
        if g["alive"]:
            _grow(world, g)
    alive = [g for g in cs if g["alive"]]
    if len(alive) >= _cap(world) or world.ticks < 120:
        return
    if world.pyrng.random() >= CULT_CHANCE * motives.settled(world) ** 0.5:
        return
    mis = _misery(world)
    mis[(world.H < CULT_MIN_POP) | ~world.land] = 0
    for g in alive:
        mis[max(0, g["r"] - 30):g["r"] + 31, max(0, g["c"] - 30):g["c"] + 31] = 0
    top = float(mis.max())
    if top < CULT_MISERY:
        return
    flat = mis.ravel()
    best = np.flatnonzero(flat >= max(CULT_MISERY, 0.8 * top))
    i = int(world.pyrng.choice(list(best)))
    r, c = divmod(i, world.cols)
    k = "risen" if world.pyrng.random() < RISEN_SHARE else world.pyrng.choice(["faith", "faith", "purity", "commune"])
    from fracture import _place
    place = _place(world, (r, c))
    name = world.pyrng.choice(NAMES[k]).format(p=place)
    host = int(world.O[r, c])
    g = dict(name=name, creed=k, r=int(r), c=int(c), host=host, strength=0.2, born=world.ticks, alive=True,
             place=place)
    cs.append(g)
    where = place + (f" ({world.civs[host].name})" if host else "")
    world.war_note(f"CULT: {name} ({LABEL[k]}) gather followers around {where}")
    import globalaffairs
    globalaffairs.mark(world, r, c, "cult")


def _grow(world, g):
    r, c = g["r"], g["c"]
    if world.H[r, c] <= 10 or world.Z[r, c] > world.H[r, c]:
        g["alive"] = False
        world.war_note(f"CULT: {g['name']} are scattered - their town is gone", log=False)
        return
    host = int(world.O[r, c])
    g["host"] = host
    hc = world.civs[host] if host else None
    mis = float(_misery(world)[max(0, r - 3):r + 4, max(0, c - 3):c + 4].mean())
    down = 0.0
    if hc is not None and not hc.collapsed and hc.m and hc.m.get("n"):
        down = CULT_SUPPRESS * motives.security(world, hc) * min(1.0, 0.5 + hc.military)
        if creed(hc) == g["creed"]:
            down = 0.0
    g["strength"] += CULT_GROW * (mis + 0.15) - down
    if g["strength"] <= 0:
        g["alive"] = False
        world.war_note(f"CULT: {g['name']} dwindle away" + (f" ({hc.name} cracks down)" if down > 0.05 else ""))
        return
    if g["strength"] >= 1.0:
        g["alive"] = False
        if hc is not None and not hc.collapsed and motives.instability(hc) >= CULT_TAKEOVER and hc.m:
            _take_over(world, g, hc)
        else:
            _break_away(world, g, hc)


def _take_over(world, g, hc):
    import govern
    old = hc.name
    hc.gov = "theocracy"
    hc.place = None
    region = world.O == hc.id
    hc.name = govern.state_name(world, "theocracy", region, hc.id, near=hc.capital)
    hc._revolution = world.ticks
    hc.instability = 0.2
    hc.morale = max(hc.morale, 6)
    adopt(world, hc, g["creed"], f"falls to {g['name']} (was {old})")


def _break_away(world, g, hc):
    import govern
    import economy
    from civilization import steps
    r, c = g["r"], g["c"]
    host = hc.id if hc is not None else 0
    rr0, cc0 = max(r - CULT_REACH - 2, 0), max(c - CULT_REACH - 2, 0)
    w = (slice(rr0, r + CULT_REACH + 3), slice(cc0, c + CULT_REACH + 3))
    start = np.zeros(world.H[w].shape, dtype=bool)
    start[r - rr0, c - cc0] = True
    reach = CULT_REACH if host == 0 else CULT_REACH // 2
    near = steps(start, reach, through=world.statics.land[w]) <= reach
    Ow = world.O[w]
    take = near & world.statics.land[w] & ((Ow == 0) | (Ow == host)) & (world.H[w] > 10)
    if int(take.sum()) < 3:
        world.war_note(f"CULT: {g['name']} never find the following to take power", log=False)
        return
    civ = world.add_civ(morale=8)
    if civ is None:
        return
    mask = np.zeros(world.H.shape, dtype=bool)
    mask[w] = take
    civ.successor, civ.founded = True, world.ticks
    civ.root = civ.id
    civ.gov = "theocracy"
    civ.split_from = host or None
    civ.military = 0.4
    civ.strength = 0.5
    civ.materials = 20.0
    pop = int(np.maximum(world.H[mask], 0).sum())
    civ.food = pop * economy.FOOD_PER_PERSON * 45
    world.O[mask] = civ.id
    world.last_owner[mask] = civ.id
    civ.capital = (r, c)
    civ.name = govern.state_name(world, "theocracy", mask, civ.id, near=(r, c))
    civ._creed_checked = True
    civ.ideology, civ.ideology_since = g["creed"], world.ticks
    world.war_note(f"CULT: {g['name']} break away and found {civ.name} ({LABEL[g['creed']]}, "
                   f"{world.people(pop)} people)" + (f", out of {hc.name}" if hc is not None else ""))
    import globalaffairs
    globalaffairs.mark(world, r, c, "creed")
    if hc is not None and not hc.collapsed:
        import war
        war.maybe_civil_war(world, hc, civ, "it won't let the cult take its land")


def active(world):
    return [g for g in cults(world) if g["alive"]]
