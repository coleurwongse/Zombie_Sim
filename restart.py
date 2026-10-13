"""Rebuilding: how survivors start civilization again.

Growth      people in settled, safe, fed land have children (logistic) until a tile is back to what it held before
            the outbreak (or a little, by terrain, where nobody lived) - the world rebuilds, it doesn't boom.
Resettling  a government moves people from crowded places (refugees packed into safe cities) and from full ones into
            empty, safe land it holds or that borders land it holds: reclaimed and emptied districts fill up again,
            best land first.
Colonizing  dense tiles send small groups of settlers into empty safe land next door (also reclaimed land).
Expansion   a nation claims adjacent populated land nobody holds.
Founding    a cluster of safe, unowned, populated tiles (refugee camps, hold-outs) that stays put long
            enough and is big enough organizes itself into a new civilization.  It takes over the
            garrisons of fallen governments inside its land, gets a little salvage, and from then on
            fortifies, drills an army and eventually goes after the zombies (RECLAIM, civilization.py).
"""
import numpy as np

from terrain import is_land, is_water, habitable

import economy
import govern
from civilization import box_sum, DIRECTIONS, NEAR_RADIUS, _slices, MIL_START

from labels import label as label_components

#                 ocean grass forest mountain desert ice urban suburban
from terrain import CAP                    # people a tile supports, by terrain id (terrain.py)
BIRTH = 0.012
GROW_FOOD_TICKS = 15       # a nation only grows while it has this many ticks of food in store
COLONIZE_EVERY = 4
COLONIZE_FROM = 70
SETTLERS = 12
COLONIZE_CHANCE = 0.25
EXPAND_EVERY = 4
EXPAND_MAX = 14            # tiles a nation can claim per step
EXPAND_MIN_POP = 10
EXPAND_MIN_MORALE = 5
EMPTY_MAX_NEAR = 6         # (a few stray zombies around don't stop it)
EXPAND_EMPTY_MAX = 25      # empty, (nearly) zombie-free land next to a nation it can take over per step (its territory
                           # grows back over land the zombies have left)
RESETTLE_EVERY = 4
RESETTLE_SHARE = 0.04      # of a government's people that can be moved per step ...
RESETTLE_GROUP = 15        # ... in groups of this many per tile
RESETTLE_MAX_TILES = 160   # at most this many tiles settled per government per step
RESETTLE_KEEP = 20         # a tile never gives up people below this ...
RESETTLE_GIVE = 0.1       # ... and gives this share of what it has above that (more where it's crowded):
RESETTLE_CROWD = 0.25      #     this share of what it holds above its pre-outbreak level
RESETTLE_MIN_MORALE = 4
RESETTLE_EMPTY_FIRST = 300   # emptied tiles are settled before half-empty ones are filled up
RESETTLE_DANGER = 0.7      # a government in more danger than this has other things to do
HOME_MIN = 30              # (maps that don't know the pre-outbreak population: tiles fill up to this)
PIONEER_REACH = 6          # settlers also strike out this many tiles (over land) beyond the border into clean, empty land
SETTLE_HOME = 11           # only land that held at least this many people before is worth resettling
STRAY_OK = 2               # zombies within 2 tiles that still let people have children and resettle
FOUND_EVERY = 8
FOUND_MIN_TILE_POP = 12
FOUND_MIN_POP = 400
FOUND_MIN_TILES = 8
FOUND_SAFE_NEAR = 40       # zombies within NEAR_RADIUS must be fewer than this
FOUND_SETTLED = 32         # ticks a place must have been unowned, populated and safe before it can organize
FOUND_APART = 12           # ... and at least this far from any standing government (those annex nearby land)
FOUND_MAX_LIVE = 30        # at most this many successor governments at once
FOUND_MAX_TILES = 120      # a new government starts with at most this much land (the rest of the zone is
                           # annexed slowly, EXPAND_MAX tiles per step)
FOUND_MORALE = 7
FOUND_MATERIALS = 25.0
SALVAGE_PER_SITE = 10.0


def _healthy(world):
    """Per civilization id: can its people grow and settle?"""
    ok = np.zeros(len(world.civs), dtype=bool)
    for c in world.civs:
        if c.id and c.ai and not c.collapsed and not c.famine and (c.food is None or c.food > GROW_FOOD_TICKS * c.food_use):
            # people only have more children while the harvest feeds everyone (not on the stockpile alone)
            prod = c.food_prod if c.food_prod_avg is None else c.food_prod_avg
            ok[c.id] = c.food is None or prod >= c.food_use * 1.03
    return ok


def _rounded(world, x):
    if world.stochastic:
        return np.floor(x + world.rng.random(x.shape))
    acc = getattr(world, "_birth_acc", None)             # deterministic: carry the fractions over
    acc = (np.zeros(x.shape) if acc is None else acc) + x
    whole = np.floor(acc)
    world._birth_acc = acc - whole
    return whole


def home(world):
    """How many people each tile is rebuilt to: what it held before the outbreak (maps without that: HOME_MIN, or what
    the terrain supports if that's less).  Wilderness stays wilderness."""
    h0 = getattr(world, "H0", None)
    if h0 is None:
        return np.minimum(CAP[world.T], HOME_MIN)
    return h0


def grow(world, healthy, scale=1.0):
    H, T, O = world.H, world.T, world.O
    cap = home(world)
    allow = healthy[O] & (H > 10) & (H < cap) & (world.zombie_near(2) <= STRAY_OK)
    import nukes
    poisoned = nukes.poisoned(world)
    if poisoned is not None:
        allow &= ~poisoned
    births = H * BIRTH * scale * (1.0 - H / np.maximum(cap, 1))
    H += _rounded(world, np.where(allow, births, 0.0)).astype(np.int32)


def colonize(world, healthy):
    H, Z, T, O = world.H, world.Z, world.T, world.O
    rows, cols = H.shape
    safe = world.zombie_near(2) <= STRAY_OK
    order = list(range(8))
    world.pyrng.shuffle(order)
    moved = 0
    for k in order:
        dr, dc = DIRECTIONS[k]
        sr, tr = _slices(rows, dr)
        sc, tc = _slices(cols, dc)
        empty = (H[tr, tc] <= 10) & (Z[tr, tc] == 0) & is_land(T[tr, tc]) & (T[tr, tc] != 5)
        mine = (O[tr, tc] == 0) | (O[tr, tc] == O[sr, sc])
        src = healthy[O[sr, sc]] & (H[sr, sc] >= COLONIZE_FROM) & safe[sr, sc]
        go = src & empty & mine & (world.rng.random(src.shape) < COLONIZE_CHANCE)
        amount = np.where(go, SETTLERS, 0).astype(np.int32)
        H[sr, sc] -= amount
        H[tr, tc] += amount
        view = O[tr, tc]
        view[go & (view == 0)] = O[sr, sc][go & (view == 0)]
        moved += int(amount.sum())
    return moved


def _working(world):
    """Per government id: can it run a resettlement programme now?"""
    ok = np.zeros(len(world.civs), dtype=bool)
    for c in world.civs:
        if c.id and c.ai and not c.collapsed and c.morale >= RESETTLE_MIN_MORALE and c.m and c.m.get("n"):
            ok[c.id] = c.threat(c.m) < RESETTLE_DANGER        # (not its past losses: that's why it rebuilds)
    return ok


def resettle(world):
    """Governments move people into empty, safe land: their own emptied districts and unclaimed land on their edge."""
    H, Z, T, O = world.H, world.Z, world.T, world.O
    n = len(world.civs)
    ok = _working(world)
    if not ok.any():
        return 0
    hm = home(world)
    safe = world.zombie_near(2) <= STRAY_OK          # (a straggler or two around doesn't stop the work)
    import nukes
    poisoned = nukes.poisoned(world)
    if poisoned is not None:
        safe = safe & ~poisoned
    guarded = world.guarded()
    # who could settle each tile: its owner, or for unclaimed land a neighbouring government whose land there is guarded
    claim = np.where((O > 0) & guarded, O, 0)
    edge = np.zeros_like(O)
    for dr, dc in DIRECTIONS:
        sr, tr = _slices(H.shape[0], dr)
        sc, tc = _slices(H.shape[1], dc)
        view = edge[tr, tc]
        np.copyto(view, claim[sr, sc], where=(view == 0) & (claim[sr, sc] > 0))
    # pioneers: clean, unclaimed land a few tiles further out can be settled too (it's guarded once people live there)
    land = world.statics.land
    for k in range(PIONEER_REACH - 1):
        grow = edge.copy()
        for dr, dc in (DIRECTIONS if k % 2 else ((-1, 0), (1, 0), (0, -1), (0, 1))):     # (round, not square)
            sr, tr = _slices(H.shape[0], dr)
            sc, tc = _slices(H.shape[1], dc)
            view = grow[tr, tc]
            np.copyto(view, edge[sr, sc], where=(view == 0) & (edge[sr, sc] > 0) & (O[tr, tc] == 0) & land[tr, tc])
        edge = grow
    who = np.where(O > 0, claim, np.where(world.may_claim(edge), edge, 0))
    target = ((who > 0) & ok[who] & safe & (Z == 0) & habitable(T) & (hm >= SETTLE_HOME)
              & (H < 0.5 * hm) & (H >= 0))
    if not target.any():
        return 0
    # people to spare: crowded tiles give more
    donor = (O > 0) & ok[O] & safe & (H > RESETTLE_KEEP)
    give = np.where(donor, RESETTLE_GIVE * (H - RESETTLE_KEEP) + RESETTLE_CROWD * np.maximum(H - hm, 0), 0.0)
    give = np.minimum(give, np.maximum(H - RESETTLE_KEEP, 0))
    spare = np.bincount(O.ravel(), weights=give.ravel(), minlength=n)
    people = np.bincount(O.ravel(), weights=np.maximum(H, 0).ravel(), minlength=n)
    # which tiles each government settles this step: the best land first (with some randomness), up to its budget
    idx = np.flatnonzero(target.ravel())
    owner = who.ravel()[idx]
    value = (hm.ravel()[idx].astype(np.float64) + (world.rng.random(idx.size) * 40 if world.stochastic else 0)
             + RESETTLE_EMPTY_FIRST * (H.ravel()[idx] <= 10))         # (emptied land first: the country spreads out)
    order = np.lexsort((-value, owner))
    idx, owner = idx[order], owner[order]
    start = np.searchsorted(owner, owner, side="left")
    rank = np.arange(owner.size) - start
    budget = np.minimum(np.minimum(spare, RESETTLE_SHARE * people), RESETTLE_MAX_TILES * RESETTLE_GROUP)
    slots = (budget // RESETTLE_GROUP).astype(np.int64)
    pick = rank < slots[owner]
    idx, owner = idx[pick], owner[pick]
    if idx.size == 0:
        return 0
    need = np.bincount(owner, minlength=n) * RESETTLE_GROUP
    frac = np.where(spare > 0, np.minimum(1.0, need / np.maximum(spare, 1e-9)), 0.0)
    u = world.rng.random(H.shape) if world.stochastic else 0.5          # (fair rounding: many tiles give a little)
    taken = np.minimum(np.floor(give * frac[O] + u), np.maximum(H - RESETTLE_KEEP, 0)).astype(np.int32)
    taken[give <= 0] = 0
    H -= taken
    got = np.bincount(O.ravel(), weights=taken.ravel(), minlength=n)
    per = np.floor(got[owner] / np.maximum(np.bincount(owner, minlength=n)[owner], 1)).astype(np.int32)
    Hf, Of = H.reshape(-1), O.reshape(-1)
    Hf[idx] += per
    Of[idx] = np.where(per > 0, owner, Of[idx])
    leftover = (got - np.bincount(owner, weights=per, minlength=n)).astype(np.int32)   # (what rounding left over goes
    _, first = np.unique(owner, return_index=True)                                    #  with the first group)
    Hf[idx[first]] += leftover[owner[first]]
    return int(got.sum())


def expand(world):
    H, Z, T, O, U, R = world.H, world.Z, world.T, world.O, world.U, world.R
    rows, cols = H.shape
    can = np.zeros(len(world.civs), dtype=bool)
    for c in world.civs:
        can[c.id] = bool(c.id and c.ai and not c.collapsed and c.morale >= EXPAND_MIN_MORALE)
    free = (O == 0) & (H > EXPAND_MIN_POP) & (Z * economy.INFESTED < H) & is_land(T) & (U < 0.5) & (R < 1.0)
    empty = ((O == 0) & (H <= EXPAND_MIN_POP) & (H >= 0) & (Z == 0) & is_land(T) & (T != 5)
             & (world.zombie_near(2) <= EMPTY_MAX_NEAR))
    if not (free.any() or empty.any()):
        return
    world.guarded()
    core = getattr(world, "_guard_core", None)
    guarded = np.where(core if core is not None else world.guarded(), O, 0)   # empty land is only taken where its
                                                                              # people can keep guarding it
    best = np.zeros_like(O)
    best_g = np.zeros_like(O)
    order = list(range(8))
    world.pyrng.shuffle(order)
    for k in order:
        dr, dc = DIRECTIONS[k]
        sr, tr = _slices(rows, dr)
        sc, tc = _slices(cols, dc)
        nb = np.zeros_like(O)
        nb[tr, tc] = O[sr, sc]
        best = np.where((best == 0) & (nb > 0), nb, best)
        nb[tr, tc] = guarded[sr, sc]
        best_g = np.where((best_g == 0) & (nb > 0), nb, best_g)
    for pool, cap, src in ((free, EXPAND_MAX, best), (empty, EXPAND_EMPTY_MAX, best_g)):
        best = src
        claim = pool & can[best] & world.may_claim(best)
        for cid in np.unique(best[claim]):
            sel = np.flatnonzero((claim & (best == cid)).reshape(-1))
            if sel.size > cap:
                sel = world.rng.choice(sel, cap, replace=False)
            O.reshape(-1)[sel] = cid
    _adopt_garrisons(world)


def _adopt_garrisons(world):
    """A government that now holds ground where a fallen one left a garrison takes the garrison over."""
    for old in world.civs:
        if not (old.collapsed and old.sites):
            continue
        keep = []
        for s in old.sites:
            new = world.O[s["center"]]
            if new > 0 and world.civs[new].ai and not world.civs[new].collapsed:
                world.civs[new].sites.append(s)
                world.civs[new].materials += SALVAGE_PER_SITE
                world.civs[new].military = max(world.civs[new].military, 0.5 * old.military)
                world.note(f"{world.civs[new].name} takes over a garrison of {old.name}")
            else:
                keep.append(s)
        old.sites = keep
        old.remnant = bool(keep)


def _components(mask):
    return label_components(mask)


def found(world):
    H, Z, T, O = world.H, world.Z, world.T, world.O
    cand = ((O == 0) & (H >= FOUND_MIN_TILE_POP) & is_land(T) & (Z * economy.INFESTED < H)
            & (world.zombie_near(NEAR_RADIUS) < FOUND_SAFE_NEAR))
    age = getattr(world, "_found_age", None)
    if age is None:
        age = np.zeros(H.shape, dtype=np.int32)
    age = np.where(cand, age + FOUND_EVERY, 0)           # how long each tile has been settled and safe
    world._found_age = age
    live = np.zeros(len(world.civs), dtype=bool)
    for c in world.civs:
        live[c.id] = bool(c.id and c.ai and not c.collapsed)
    if sum(1 for c in world.civs if c.successor and live[c.id]) >= FOUND_MAX_LIVE:
        return
    stable = (age >= FOUND_SETTLED) & (box_sum(live[O], FOUND_APART) == 0)
    if not stable.any():
        return
    labels, n = _components(stable)
    if n == 0:
        return
    flat = labels.reshape(-1)
    sizes = np.bincount(flat, minlength=n + 1)
    pops = np.bincount(flat, weights=H.reshape(-1), minlength=n + 1)
    rr, cc = np.indices(H.shape)
    for k in np.argsort(-pops[1:]) + 1:
        if sizes[k] < FOUND_MIN_TILES or pops[k] < FOUND_MIN_POP:
            continue
        mask = labels == k
        if sizes[k] > FOUND_MAX_TILES:                     # organize around the biggest settlement
            hr, hc = np.unravel_index(np.argmax(np.where(mask, H, -1)), H.shape)
            dist = np.maximum(abs(rr - hr), abs(cc - hc)) + 0.001 * (rr + cc)
            keep = np.argsort(np.where(mask, dist, np.inf).reshape(-1))[:FOUND_MAX_TILES]
            mask = np.zeros(H.shape, dtype=bool)
            mask.reshape(-1)[keep] = True
        civ = world.add_civ(morale=FOUND_MORALE, name=None)
        if civ is None:
            return
        civ.successor, civ.founded = True, world.ticks
        prev = world.last_owner[mask]                   # which former government's land is this?
        prev = prev[prev > 0]
        if prev.size:
            civ.root = world.civs[int(np.bincount(prev).argmax())].root
        civ.military = MIL_START / 3
        civ.gov = govern.choose(world, mask, None, sites=sum(1 for o in world.civs if o.collapsed for s in o.sites if mask[s["center"]]))
        O[mask] = civ.id
        age[mask] = 0
        pop = int(H[mask].sum())
        civ.food = pop * economy.FOOD_PER_PERSON * economy.FOOD_START_TICKS * 0.5
        civ.materials = FOUND_MATERIALS
        civ.name = govern.state_name(world, civ.gov, mask, civ.id) if world.cities else f"Colony {civ.id}"
        civ.capital = None
        world.note(f"survivors found {civ.name}" + (f" ({govern.LABEL[civ.gov]})" if world.cities else "")
                   + f": {world.people(pop)} people on {int(mask.sum())} tiles")
        _adopt_garrisons(world)


def step(world):
    t = world.ticks
    healthy = _healthy(world)
    if t % 2 == 0:
        grow(world, healthy, 2.0)                       # (every other tick, twice the births)
    if t % RESETTLE_EVERY == 1:
        world.last_resettled = resettle(world)
    if t % COLONIZE_EVERY == 0:
        colonize(world, healthy)
    if t % EXPAND_EVERY == 0:
        expand(world)
    if t % FOUND_EVERY == 0:
        found(world)
