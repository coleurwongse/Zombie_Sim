"""Forms of government.

The original nations are "national" governments.  When a nation breaks apart (fracture.py) or survivors organize
(restart.py), each new state gets the form of government that best fits where it came from (see choose): the
political tradition of its old country first, then what it breaks away from, then its circumstances:

  junta      military authoritarian.  Grows out of regions held by the army (fortified sites, garrisons, a strong
             army).  Trains soldiers fast, keeps order by force (less unrest, morale falls slowly), aggressive,
             reluctant to merge.
  democracy  a republic.  Grows out of well-fed, safe, urban regions.  Productive, recovers morale fast, peaceable,
             merges readily with kin.
  warlord    strongmen.  Grows out of starving, endangered, chaotic regions.  Poor economy, volatile morale,
             very aggressive, rarely merges.
  tribal     clans / councils.  Grows out of thinly populated countryside.  Self-sufficient in food, little industry,
             small army, very resilient morale, little unrest (few cities to riot in).
  syndicate  a criminal proto-state (crime.py: pirates, a cartel, a militia that took over).  Never chosen for a new
             state: a crime ring becomes one.  Strong army, trades well, unruly, very aggressive, hardly ever merges.
  theocracy  rule by a creed's priesthood (ideology.py: a cult that took over, or broke away).  Never chosen for a new
             state either.  Disciplined, resilient, aggressive, wary of merging.

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
    "syndicate": (0.90, 1.15, 1.40, 1.10, 0.90, 1.20, 1.60, 0.30),
    "theocracy": (1.00, 0.90, 1.20, 0.70, 1.10, 0.70, 1.30, 0.40),
}
KEYS = ("food", "materials", "army", "morale_loss", "recover", "unrest", "aggression", "merge")
LABEL = {"national": "", "junta": "junta", "democracy": "republic", "warlord": "warlords", "tribal": "clans",
         "syndicate": "criminal state", "theocracy": "theocracy"}


def mod(civ, key):
    import ideology                                      # (and its creed, if it has one: ideology.py)
    return GOV.get(getattr(civ, "gov", "national"), GOV["national"])[KEYS.index(key)] * ideology.mod(civ, key)


# What political tradition a region inherits from the country it belonged to before the outbreak (world map; on the
# hand-drawn maps a realm's own starting government is its tradition).  Rough, deliberately: established democracies,
# fragile states (no working government for years, militias, clans), and - the rest - authoritarian states.
DEMOCRACIES = {
    "United States", "Canada", "Mexico", "Brazil", "Argentina", "Chile", "Uruguay", "Paraguay", "Peru", "Colombia",
    "Ecuador", "Bolivia", "Costa Rica", "Panama", "Dominican Republic", "Jamaica", "Trinidad and Tobago", "Guyana",
    "Suriname", "Guatemala", "Honduras", "El Salvador", "Belize", "Bahamas",
    "United Kingdom", "Ireland", "Iceland", "Norway", "Sweden", "Finland", "Denmark", "Estonia", "Latvia", "Lithuania",
    "Poland", "Germany", "Netherlands", "Belgium", "Luxembourg", "France", "Spain", "Portugal", "Italy", "Malta",
    "Switzerland", "Austria", "Czech Republic", "Czechia", "Slovakia", "Slovenia", "Croatia", "Hungary", "Romania",
    "Bulgaria", "Greece", "Cyprus", "Moldova", "Ukraine", "Georgia", "Armenia", "Montenegro", "North Macedonia",
    "Albania", "Serbia", "Bosnia and Herzegovina", "Kosovo", "Israel",
    "India", "Nepal", "Bhutan", "Sri Lanka", "Bangladesh", "Mongolia", "Japan", "South Korea", "Taiwan",
    "Philippines", "Indonesia", "Malaysia", "Timor-Leste", "East Timor", "Papua New Guinea", "Australia",
    "New Zealand", "Fiji", "Solomon Islands", "Vanuatu",
    "South Africa", "Botswana", "Namibia", "Lesotho", "Mauritius", "Ghana", "Senegal", "Cabo Verde", "Cape Verde",
    "Zambia", "Malawi", "Kenya", "Madagascar", "Liberia", "Sierra Leone", "Benin", "Tunisia",
}
FRAGILE = {
    "Somalia", "Somaliland", "South Sudan", "Sudan", "Rapid Support Forces", "Yemen", "Houthis", "Afghanistan",
    "DR Congo", "Democratic Republic of the Congo", "Central African Republic", "Chad", "Syria", "Haiti", "Libya",
    "Mali", "Burkina Faso", "Niger", "Ethiopia", "Iraq", "Myanmar", "Myanmar Resistance", "Eritrea", "Burundi",
    "Guinea-Bissau", "Mozambique", "Cameroon", "Lebanon", "Palestine", "Gaza", "Western Sahara",
}
HERITAGE_BIAS = {          # tradition -> how much it favours each form of government in a new state
    "democratic":    {"democracy": 1.2, "junta": 0.0, "warlord": 0.0, "tribal": 0.1},
    "authoritarian": {"democracy": 0.1, "junta": 1.0, "warlord": 0.3, "tribal": 0.1},
    "fragile":       {"democracy": 0.0, "junta": 0.3, "warlord": 0.9, "tribal": 0.7},
    "mixed":         {"democracy": 0.4, "junta": 0.4, "warlord": 0.3, "tribal": 0.3},
}
CONTINUITY = 0.5           # a region tends to keep the form of government of the state it breaks away from
CHOICE_NOISE = 0.15        # (the best fit wins - give or take this much: close calls can go either way)


def tradition(world, civ):
    """The political tradition behind government `civ`: that of the country it descends from (its root)."""
    root = world.civs[civ.root] if civ is not None and civ.root is not None and civ.root < len(world.civs) else civ
    if root is None:
        return "mixed"
    seen = set()                                        # (a settlers' colony is its own root: its founders' tradition)
    while getattr(root, "name0", None) is None and root.split_from is not None and root.id not in seen:
        seen.add(root.id)
        nxt = world.civs[root.split_from]
        root = world.civs[nxt.root] if nxt.root is not None else nxt
    cached = getattr(root, "_tradition", None)
    if cached:
        return cached
    name = getattr(root, "name0", None) or root.name
    if (getattr(world, "meta", None) or {}).get("real_pops"):
        t = "democratic" if name in DEMOCRACIES else "fragile" if name in FRAGILE else "authoritarian"
    else:                                               # (hand-drawn maps: the realm's own government is its tradition)
        t = {"democracy": "democratic", "junta": "authoritarian", "warlord": "fragile",
             "tribal": "fragile"}.get(getattr(root, "gov0", root.gov), "mixed")
    root._tradition = t
    return t


def choose(world, region, parent=None, sites=0):
    """A form of government for a new state on `region` (bool mask): the one that fits best -

      tradition    the political tradition of the country the region belonged to (DEMOCRACIES / FRAGILE / the rest
                   authoritarian; on hand-drawn maps the realm's own government) - the biggest single factor;
      continuity   the form of government of the state it breaks away from (CONTINUITY);
      the army     garrisons in the region and a strong army holding it together amid danger -> a junta;
      chaos        famine, or a horde at the gates -> warlords;
      prosperity   safe, fed, urban -> a republic;
      the land     thinly peopled countryside -> clans.

    The best fit wins, give or take a little (CHOICE_NOISE)."""
    H, T = world.H, world.T
    pop = float(np.maximum(H[region], 0).sum())
    tiles = max(1, int(region.sum()))
    density = pop / tiles
    urban = float(((T == 6) | (T == 7))[region].mean())
    near = world.zombie_near(4)
    danger = min(1.0, float((np.maximum(H, 0) * (near >= 300))[region].sum()) / max(pop, 1.0) * 2.0)
    fed = 1.0
    army = 0.2
    if parent is not None:
        army = min(1.0, parent.military)
        if parent.famine:
            fed = 0.0
        elif parent.food is not None and parent.food_use > 0:
            fed = min(1.0, parent.food / (30 * parent.food_use))
    else:                                               # (survivors organizing: whose land was it?)
        prev = world.last_owner[region] if getattr(world, "last_owner", None) is not None else np.zeros(0)
        prev = prev[prev > 0]
        if prev.size:
            parent_like = world.civs[int(np.bincount(prev).argmax())]
            parent = parent_like if parent_like.id else None
    rural = max(0.0, 1.0 - density / 60.0) * (1.0 - urban)
    held = min(1.0, sites / 2.0)
    w = {
        "junta": 0.9 * held + 0.6 * army * (0.4 + danger),
        "democracy": 0.8 * urban + 0.6 * fed * (1.0 - danger) - 0.4 * danger,
        "warlord": 0.9 * (1.0 - fed) + 0.7 * danger,
        "tribal": 1.0 * rural,
    }
    trad = tradition(world, parent) if parent is not None else "mixed"
    for k, v in HERITAGE_BIAS[trad].items():
        w[k] += v
    if parent is not None and getattr(parent, "gov", "national") in w:
        w[parent.gov] += CONTINUITY
    names = list(w)
    score = np.array([w[k] for k in names])
    if world.stochastic:
        score = score + world.rng.normal(0.0, CHOICE_NOISE, len(names))
    return names[int(np.argmax(score))]


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


NEAR_CITY = 15             # tiles: a region without a town of its own is named after a free one this close ...
NAME_REACH = 3             # tiles: a city this close to a new state's land, nobody's, can still name it


def free_place(world, region, near=None):
    """The city a new state is named after: the biggest named city in `region` that no living government is already
    named after (or the one at / nearest `near`, its capital, if that's free) - else the nearest free city outside."""
    cities = getattr(world, "cities", None)
    if not cities:
        return None
    taken = {getattr(c, "place", None) for c in world.civs if not c.collapsed}
    # (a city at the region's edge counts too, if nobody governs it: when a country falls apart its besieged big
    #  cities often fall into anarchy and are cut out of the regions around them - the region is still that city's)
    from civilization import box_sum
    edge = (box_sum(region, NAME_REACH) > 0) & (world.O == 0)
    inside = [(p, n, r, c) for n, r, c, p in cities if 0 <= r < region.shape[0] and 0 <= c < region.shape[1]
              and (region[r, c] or edge[r, c]) and n not in taken]
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
    r0, c0 = (near if near is not None else (float(rr.mean()), float(cc.mean())))
    live = np.zeros(len(world.civs), dtype=bool)       # (never a city another living government holds - no "Barad-dur
    for o in world.civs:                               #  Clans" in Rhun while Mordor stands)
        live[o.id] = bool(o.id and not o.collapsed)
    O = world.O
    pool = [(n, r, c) for n, r, c, _ in cities if n not in taken and not (0 <= O[r, c] < len(live) and live[O[r, c]])]
    near_ = [x for x in pool if (x[1] - r0) ** 2 + (x[2] - c0) ** 2 <= NEAR_CITY ** 2]
    if near_:                                          # (a town nearby nobody holds: the countryside round it)
        return min(near_, key=lambda x: (x[1] - r0) ** 2 + (x[2] - c0) ** 2)[0]
    realm = realm_place(world, region)                 # no town anywhere near: "East Rhun", after the land it was in
    if realm is not None and realm not in taken:
        return realm
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
                "national": "State", "syndicate": "Syndicate", "theocracy": "Holy State"}[gov]
        return f"{base} {civ_id}"
    base = {"junta": f"{place} Junta", "democracy": f"Republic of {place}", "warlord": f"{place} Warlords",
            "tribal": f"{place} Clans", "national": f"Free {place}", "syndicate": f"Syndicate of {place}",
            "theocracy": f"Holy {place}"}[gov]
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
