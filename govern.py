"""Forms of government.

The original nations are "national" governments.  When a nation breaks apart (fracture.py) or survivors organize
(restart.py), each new state gets a form of government that suits where it came from:

  junta      military authoritarian.  Grows out of regions held by the army (fortified sites, garrisons, a strong
             army).  Trains soldiers fast, keeps order by force (less unrest, morale falls slowly), aggressive,
             reluctant to merge.
  democracy  a republic.  Grows out of well-fed, safe, urban regions.  Productive, recovers morale fast, peaceable,
             merges readily with kin.
  warlord    strongmen.  Grows out of starving, endangered, chaotic regions.  Poor economy, volatile morale,
             very aggressive, rarely merges.
  tribal     clans / councils.  Grows out of thinly populated countryside.  Self-sufficient in food, little industry,
             small army, very resilient morale, little unrest (few cities to riot in).

Every modifier is a multiplier (1.0 = like a national government).
"""
import re
import numpy as np

GOV = {
    #            food  mat   army  m_loss recover unrest aggr  merge
    "national": (1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 1.00),
    "junta":    (0.95, 1.00, 1.60, 0.70, 0.80, 0.60, 1.30, 0.60),
    "democracy": (1.08, 1.12, 0.80, 1.00, 1.40, 1.00, 0.60, 1.40),
    "warlord":  (0.85, 0.80, 1.30, 1.25, 0.90, 1.30, 1.80, 0.50),
    "tribal":   (1.15, 0.50, 0.70, 0.60, 1.00, 0.50, 0.90, 0.70),
}
KEYS = ("food", "materials", "army", "morale_loss", "recover", "unrest", "aggression", "merge")
LABEL = {"national": "", "junta": "junta", "democracy": "republic", "warlord": "warlords", "tribal": "clans"}


def mod(civ, key):
    return GOV.get(getattr(civ, "gov", "national"), GOV["national"])[KEYS.index(key)]


def choose(world, region, parent=None, sites=0):
    """Pick a form of government for a new state on `region` (bool mask).  Weighted at random by circumstances."""
    H, T = world.H, world.T
    pop = float(np.maximum(H[region], 0).sum())
    tiles = max(1, int(region.sum()))
    density = pop / tiles
    urban = float(((T == 6) | (T == 7))[region].mean())
    near = world.zombie_near(4)
    danger = float((np.maximum(H, 0) * (near >= 300))[region].sum()) / max(pop, 1.0)
    fed = 1.0
    army = 0.2
    if parent is not None:
        army = parent.military
        if parent.famine:
            fed = 0.0
        elif parent.food is not None and parent.food_use > 0:
            fed = min(1.0, parent.food / (30 * parent.food_use))
    w = {
        "junta": 0.3 + 1.2 * min(1.0, sites / 2.0) + 1.0 * army,
        "democracy": 0.2 + 1.2 * urban + 0.8 * fed - 1.5 * danger,
        "warlord": 0.2 + 1.2 * danger + 1.0 * (1.0 - fed),
        "tribal": 0.2 + 1.5 * max(0.0, 1.0 - density / 60.0) * (1.0 - urban),
    }
    names = list(w)
    p = np.array([max(0.02, w[k]) for k in names])
    if not world.stochastic:
        return names[int(np.argmax(p))]
    p = p ** 2 / (p ** 2).sum()                     # favour the best fit, but not always
    return names[int(world.rng.choice(len(names), p=p))]


def nearest_city(world, region):
    """Name of the named city closest to the population centre of `region` (None if the map has no names)."""
    cities = getattr(world, "cities", None)
    if not cities:
        return None
    rr, cc = np.nonzero(region)
    if rr.size == 0:
        return None
    wts = np.maximum(world.H[rr, cc], 1).astype(float)
    r0, c0 = float((rr * wts).sum() / wts.sum()), float((cc * wts).sum() / wts.sum())
    inside = [(n, r, c) for n, r, c, _ in cities if 0 <= r < region.shape[0] and 0 <= c < region.shape[1] and region[r, c]]
    pool = inside or [(n, r, c) for n, r, c, _ in cities]
    name, _, _ = min(pool, key=lambda x: (x[1] - r0) ** 2 + (x[2] - c0) ** 2)
    return name


def free_place(world, region, near=None):
    """The city a new state is named after: the biggest named city in `region` that no living government is already
    named after (or the one at / nearest `near`, its capital, if that's free) - else the nearest free city outside."""
    cities = getattr(world, "cities", None)
    if not cities:
        return None
    taken = {getattr(c, "place", None) for c in world.civs if not c.collapsed}
    inside = [(p, n, r, c) for n, r, c, p in cities if 0 <= r < region.shape[0] and 0 <= c < region.shape[1]
              and region[r, c] and n not in taken]
    if near is not None:
        at = [x for x in inside if abs(x[2] - near[0]) <= 1 and abs(x[3] - near[1]) <= 1]
        if at:
            return max(at)[1]
    if inside:
        return max(inside)[1]
    anyin = [(p, n) for n, r, c, p in cities if 0 <= r < region.shape[0] and 0 <= c < region.shape[1] and region[r, c]]
    if anyin:                                          # (all its cities taken: its own biggest, under another title)
        return max(anyin)[1]
    rr, cc = np.nonzero(region)
    if rr.size == 0:
        return None
    realm = realm_place(world, region)                 # no town of its own: "East Rhun", after the land it was part of
    if realm is not None and realm not in taken:
        return realm
    r0, c0 = (near if near is not None else (float(rr.mean()), float(cc.mean())))
    live = np.zeros(len(world.civs), dtype=bool)       # (never a city another living government holds - no "Barad-dur
    for o in world.civs:                               #  Clans" in Rhun while Mordor stands)
        live[o.id] = bool(o.id and not o.collapsed)
    O = world.O
    pool = [(n, r, c) for n, r, c, _ in cities if n not in taken and not (0 <= O[r, c] < len(live) and live[O[r, c]])]
    if not pool:
        return realm
    return min(pool, key=lambda x: (x[1] - r0) ** 2 + (x[2] - c0) ** 2)[0]


def realm_place(world, region):
    """A name for a region without a town of its own, after the country it belonged to before the outbreak: 'East
    Rhun', 'North Kazakhstan' (just the country's name if the region is most of it).  None if it was nobody's."""
    O0 = getattr(world, "O0", None)
    if O0 is None:
        return None
    own = O0[region]
    own = own[(own > 0) & (own < len(world.civs))]
    if own.size == 0:
        return None
    k = int(np.bincount(own).argmax())
    cache = world.__dict__.setdefault("_realm_shape", {})
    if k not in cache:
        rr, cc = np.nonzero(O0 == k)
        cache[k] = (float(rr.mean()), float(cc.mean()), float(rr.std()) + 1.0, float(cc.std()) + 1.0, rr.size,
                    re.sub(r"\s*\(.*?\)", "", world.civs[k].name).strip() or world.civs[k].name)
    r0, c0, sr, sc, size, base = cache[k]
    rr, cc = np.nonzero(region)
    if rr.size >= 0.6 * size:
        return base
    dr, dc = (rr.mean() - r0) / sr, (cc.mean() - c0) / sc
    if base.startswith("The "):                       # ("West Shire", not "West The Shire")
        base = base[4:]
    if max(abs(dr), abs(dc)) < 0.35:
        return f"Central {base}"
    ns = "North" if dr < 0 else "South"
    ew = "West" if dc < 0 else "East"
    if abs(dr) > 2 * abs(dc):
        return f"{ns} {base}"
    if abs(dc) > 2 * abs(dr):
        return f"{ew} {base}"
    return f"{ns}{ew.lower()} {base}"


def state_name(world, gov, region, civ_id, parent=None, near=None):
    """'Chengdu Junta', 'Republic of Wuhan', 'Lanzhou Warlords', 'Qinghai Clans'... or 'Junta 7' on maps without
    named places.  Named after the region's biggest city no other government is named after (its capital's city if
    it has one); the city is remembered as civ.place."""
    place = free_place(world, region, near)
    used = {c.name for c in world.civs}
    if civ_id < len(world.civs):
        world.civs[civ_id].place = place
    if place is None:
        base = {"junta": "Junta", "democracy": "Republic", "warlord": "Warlords", "tribal": "Clans",
                "national": "State"}[gov]
        return f"{base} {civ_id}"
    base = {"junta": f"{place} Junta", "democracy": f"Republic of {place}", "warlord": f"{place} Warlords",
            "tribal": f"{place} Clans", "national": f"Free {place}"}[gov]
    live = {c.name for c in world.civs if not c.collapsed}
    name, k = base, 0
    ordinals = ("Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh")
    while name in used:                                  # (refounded where an earlier state fell: "Second Republic ..")
        if k < len(ordinals) and base not in live:
            name = f"{ordinals[k]} {base}"
        else:
            name = f"{base} {k + 2}"
        k += 1
    return name
