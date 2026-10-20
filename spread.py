"""Introductions: the outbreak keeps knocking on the doors of the continents it hasn't reached yet.

On the world map a continent can be lucky at first - the few infected travellers who arrive are caught, the first
cluster is stamped out - but as long as the outbreak rages elsewhere, more keep coming: infected refugees on boats,
travellers who slipped through before the flights stopped, smuggled cargo.  Every INTRO_EVERY days, each continent
without an outbreak going on there now may get a new introduction at one of its big cities or ports - the bigger the
outbreak in the world, the likelier (half as likely once it has been hit: TOUCHED) - up to INTRO_MAX times.  Some of those are stamped out again too, so runs stay different; but a continent sitting the
whole disaster out untouched becomes rare.  On the hand-drawn maps there are no continent boxes: every landmass
but the main one (the Counterweight Continent, Fourecks, Krull, the Isle of Balar) counts on its own - infected
sailors bring it to their towns - a big one (ISLAND_MAX settled tiles or more) like a continent.
"""
import numpy as np

INTRO_EVERY = 10
INTRO_WANE = 0.4           # none once the world's zombies have fallen below this share of their peak
INTRO_FROM = 25            # days into the outbreak before the first one (the source has to get going first)
INTRO_UNTIL = 250          # ... and none after this (by then the world has shut its doors)
INTRO_CHANCE = 0.25        # per check per continent, at a full-size outbreak elsewhere
INTRO_FULL = 0.01          # "full size": this share of the world's people are zombies
INTRO_MAX = 5              # times a continent is reached (introductions and hordes crossing the sea: crossings.py)
INTRO_FAR = 3              # ... a separate continent on a hand-drawn map (the Counterweight Continent) this often
INTRO_ISLAND = 1           # ... and a big island (ISLAND_MIN once-settled tiles or more) at least once
ISLAND_MIN = 40
INTRO_COUNTRY = 3          # ... and a sizeable country (SPARED_MIN settled tiles) still untouched SPARED_FROM days in
SPARED_MIN = 100
SPARED_FROM = 60
SPARED_LOST = 0.15
SCATTER = 12               # an introduction into such a country or an island is spread over this many towns ...
SCATTER_BOOST = 1.5        # ... and this much bigger
ISLAND_MAX = 3000           # (bigger than this is a continent)
INTRO_Z = 450              # zombies arriving (spread over the 3x3 around the city) ...
INTRO_GROW = 1.6           # ... x this for every one before it on that continent
INTRO_NEAR = 8             # they turn up in the most crowded undefended place this close to the city
INTRO_MAX_DEFENSE = 4      # (a mobilized country's ordinary defense: forts and garrisons are 6+)
TOUCHED = 0.15             # a continent counts as hit once this share of its once-settled land has been lost
ACTIVE_TILES = 25          # no new one while hordes hold this many of its tiles (an outbreak going on there now) ...
ACTIVE_SHARE = 0.03        # ... or this share of its once-settled land, if more

# continents as (lon0, lon1, lat0, lat1) boxes, minus (lon0, lon1, lat0, lat1) cut-outs
CONTINENTS = {
    "North America": ((-170, -52, 7, 75), [(-75, -52, 58, 75)]),
    "South America": ((-92, -30, -57, 7), []),
    "Europe": ((-12, 42, 35, 72), []),
    "Africa": ((-20, 52, -36, 35), [(36, 52, 11, 35)]),
    "Asia": ((42, 150, -11, 75), []),
    "Oceania": ((110, 180, -50, -10), []),
}


def _masks(world):
    cache = getattr(world, "_continents", None)
    if cache is not None:
        return cache
    settled = (world.H0 > 10) & world.land
    out = {}
    if not world.meta.get("real_pops"):                 # (a hand-drawn map: every landmass but the main one)
        mass = world.statics.landmass
        lived = world.land & (world.H0 > 0)              # (thinly lived-on land counts too: the Fourecks outback)
        counts = np.bincount(mass[lived], minlength=int(mass.max()) + 1)
        biggest = int(np.argmax(counts))
        for k in np.flatnonzero(counts >= ISLAND_MIN):
            if k and k != biggest:
                out[f"{'continent' if counts[k] >= ISLAND_MAX else 'island'} {k}"] = lived & (mass == k)
        world._continents = out
        return out
    lon0, lon1, lat0, lat1 = world.meta["bounds"]
    lat = np.linspace(lat1, lat0, world.rows)[:, None] * np.ones((1, world.cols))
    lon = np.linspace(lon0, lon1, world.cols)[None, :] * np.ones((world.rows, 1))
    for name, ((a0, a1, b0, b1), cuts) in CONTINENTS.items():
        m = (lon > a0) & (lon < a1) & (lat > b0) & (lat < b1)
        for c0, c1, d0, d1 in cuts:
            m &= ~((lon > c0) & (lon < c1) & (lat > d0) & (lat < d1))
        if name == "Asia":
            m &= ~out["Europe"]
        out[name] = m & settled
    # the big islands (Japan, Britain, Madagascar ...) each count on their own as well
    mass = world.statics.landmass
    counts = np.bincount(mass[settled], minlength=int(mass.max()) + 1)
    biggest = int(np.argmax(counts))
    for k in np.flatnonzero((counts >= ISLAND_MIN) & (counts < ISLAND_MAX)):
        if k == biggest or k == 0:
            continue
        m = settled & (mass == k)
        if any((m & out[n]).sum() > 0.8 * m.sum() and out[n].sum() < 1.25 * m.sum() for n in CONTINENTS):
            continue                                    # (that's a continent - the Americas, Australia)
        out[f"island {k}"] = m
    world._continents = out
    return out


def _spared(world):
    """Sizeable countries the outbreak has passed by so far (SPARED_FROM days in, never more than SPARED_LOST of their
    settled land lost): each gets its own introductions too (INTRO_COUNTRY) - nobody is safe just for sitting behind
    a narrow land bridge or a strait (Britain, Japan, Indonesia)."""
    if world.ticks < SPARED_FROM or not world.meta.get("real_pops"):
        return []
    settled = (world.H0 > 10) & world.land
    o0 = world.O0[settled]
    n = len(world.civs)
    size = np.bincount(o0, minlength=n)
    lost = np.bincount(o0, weights=(world.H[settled] <= 10), minlength=n) / np.maximum(size, 1)
    worst = getattr(world, "_worst_lost", None)          # (the worst it has been hit so far, not just now: a country
    if worst is None or worst.size != n:                 #  that stamped out a small outbreak and recovered still
        worst = np.zeros(n)                              #  hasn't really been hit)
    worst = world._worst_lost = np.maximum(worst, lost)
    out = []
    for k in np.flatnonzero((size >= SPARED_MIN) & (worst < SPARED_LOST)):
        if k == 0:
            continue
        out.append((f"country {k}", settled & (world.O0 == k)))
    return out


def reached(world, name, m):
    """How often the outbreak has been brought to region `name`: introductions plus hordes that swam ashore there."""
    n = world.__dict__.setdefault("_intro_count", {}).get(name, 0)
    for t, r, c in getattr(world, "_cross_log", []):
        if m[r, c] or (0 <= r < m.shape[0] and m[max(r - 1, 0):r + 2, max(c - 1, 0):c + 2].any()):
            n += 1
    return n


def step(world):
    if world.ticks % INTRO_EVERY or not (INTRO_FROM <= world.ticks <= INTRO_UNTIL):
        return
    meta = getattr(world, "meta", None) or {}
    if not getattr(world, "cities", None) or getattr(world, "H0", None) is None:
        return
    masks = _masks(world)
    hit = world.__dict__.setdefault("_intro_hit", {})
    count = world.__dict__.setdefault("_intro_count", {})
    z_share = float(world.Z.sum()) / max(1.0, float(np.maximum(world.H0, 0).sum()))
    peak = world._intro_peak = max(getattr(world, "_intro_peak", 0.0), z_share)
    if z_share < INTRO_WANE * peak:
        return                                          # (past the worst: the world is recovering - no more of them)
    pull = min(1.0, z_share / INTRO_FULL)
    for name, m in list(masks.items()) + _spared(world):
        n = int(m.sum())
        if n == 0:
            continue
        lost = float((m & (world.H <= 10)).sum()) / n
        hit[name] = max(hit.get(name, 0.0), lost)
        cap = (INTRO_ISLAND if name.startswith("island") else INTRO_COUNTRY if name.startswith("country")
               else INTRO_FAR if name.startswith("continent") else INTRO_MAX)
        if reached(world, name, m) >= cap:
            continue
        if int((m & (world.Z > 10)).sum()) >= max(ACTIVE_TILES, ACTIVE_SHARE * n):
            continue                                    # (it's there already: let it play out)
        if world.pyrng.random() >= INTRO_CHANCE * pull:
            continue
        cand = [(p, r, c, nm) for nm, r, c, p in world.cities if m[r, c] and world.H[r, c] > 10]
        if not cand:                                    # (an island without a named city: its biggest town)
            rr, cc = np.nonzero(m & (world.H > 10))
            if rr.size == 0:
                continue
            j = int(np.argmax(world.H[rr, cc]))
            from fracture import _place
            cand = [(1.0, int(rr[j]), int(cc[j]), _place(world, (int(rr[j]), int(cc[j]))))]
        def unready(rc):                                # (a mobilized army sweeps a fresh cluster away within a day:
            o = world.civs[int(world.O[rc])]            #  they get a foothold where nobody is ready for them)
            if not o.id or o.collapsed:
                return 1.0
            return max(0.05, 1.1 - o.alert) ** 2 * max(0.1, 1.1 - min(1.0, o.military))
        w = np.array([p ** 0.7 * unready((r, c)) for p, r, c, _ in cand], dtype=np.float64)
        p, r, c, nm = cand[int(world.rng.choice(len(cand), p=w / w.sum()))]
        # (they turn in the crowded, undefended streets near it - not inside a garrisoned fortress)
        R = INTRO_NEAR
        win = (slice(max(r - R, 0), r + R + 1), slice(max(c - R, 0), c + R + 1))
        open_ = (world.H[win] > 10) & (world.D[win] <= INTRO_MAX_DEFENSE) & m[win]
        if not open_.any():
            continue
        score = np.where(open_, world.H[win], -1)
        j = np.unravel_index(int(np.argmax(score)), score.shape)
        r, c = int(win[0].start + j[0]), int(win[1].start + j[1])
        n = INTRO_Z * INTRO_GROW ** count.get(name, 0) * pull   # (each bigger than the last that was stamped
        #                                                                 out - but only as big as the outbreak still is)
        if name.startswith(("country", "island")) and meta.get("real_pops"):     # (hand-drawn maps: at one city -
            #                                                                          an army may stamp it out)
            # a country or island the outbreak has passed by: the infected turn up in many towns at once - an army
            # can sweep one cluster in a day, not a dozen (Britain, Indonesia, Japan don't get off just for being
            # compact and quick to mobilize)
            towns = np.flatnonzero((m & (world.H > 10) & (world.D <= INTRO_MAX_DEFENSE)).ravel())
            if towns.size == 0:
                continue
            wts = world.H.ravel()[towns].astype(np.float64)
            k_ = min(SCATTER, towns.size)
            pick = world.rng.choice(towns, k_, replace=False, p=wts / wts.sum()) if world.stochastic else towns[:k_]
            flat = world.Z.reshape(-1)
            flat[pick] = np.minimum(flat[pick] + int(n * SCATTER_BOOST) // k_, 255)
            count[name] = count.get(name, 0) + 1
            world.note(f"infected travellers bring the outbreak to {nm} and {k_ - 1} other towns")
            world.__dict__.setdefault("_intro_log", []).append((world.ticks, name))
            continue
        k = 1 if n <= 9 * 120 else 2
        r0, r1, c0, c1 = max(r - k, 0), r + k + 1, max(c - k, 0), c + k + 1
        patch = world.Z[r0:r1, c0:c1]
        patch += np.minimum(int(n) // patch.size, 255 - patch)
        count[name] = count.get(name, 0) + 1
        world.note(f"infected travellers bring the outbreak to {nm}")
        world.__dict__.setdefault("_intro_log", []).append((world.ticks, name))
