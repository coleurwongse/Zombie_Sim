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


def state_name(world, gov, region, civ_id, parent=None):
    """'Chengdu Junta', 'Republic of Wuhan', 'Lanzhou Warlords', 'Qinghai Clans'... or 'Junta 7' on maps without
    named places."""
    place = nearest_city(world, region)
    used = {c.name for c in world.civs}
    if place is None:
        base = {"junta": "Junta", "democracy": "Republic", "warlord": "Warlords", "tribal": "Clans",
                "national": "State"}[gov]
        return f"{base} {civ_id}"
    base = {"junta": f"{place} Junta", "democracy": f"Republic of {place}", "warlord": f"{place} Warlords",
            "tribal": f"{place} Clans", "national": f"Free {place}"}[gov]
    name, k = base, 2
    while name in used:
        name, k = f"{base} {k}", k + 1
    return name
