"""Rebuilding: how survivors start civilization again.

Growth      people in settled, safe, fed land have children (logistic) until a tile is back to what it held before
            the outbreak (or a little, by terrain, where nobody lived) - the world rebuilds, it doesn't boom.
Resettling  a government moves people from crowded places (refugees packed into safe cities) and from full ones into
            empty, safe land it holds or that borders land it holds: reclaimed and emptied districts fill up again,
            best land first.
Colonizing  dense tiles send small groups of settlers into empty safe land next door (also reclaimed land).
Expansion   a nation claims adjacent populated land nobody holds.
Hiding      once the hordes have left a stretch of country for good (no zombie within EMERGE_QUIET tiles for
            EMERGE_DAYS), people who hid out the outbreak there come out (EMERGE_*): a village here and there across
            the land the zombies took - the endgame isn't only the few countries that held out spreading back over
            empty land, it is villages everywhere growing into towns and banding together into new states.
Founding    a cluster of safe, unowned, populated tiles (refugee camps, hold-outs) - or a network of villages
            within VILLAGE_LINK tiles of each other - that stays put long enough and is big enough organizes itself
            into a new civilization (villages -> a local government -> merging with its neighbours into a regional
            state (union.py) -> a nation).  It takes over the
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
WILD_MAX = 30              # wilderness (land nobody lived on before: desert, steppe, tundra) a nation may annex per step
WILD_SAFE = 4              # ... when no zombie is within this many tiles of it
EXPAND_PACE = 0.5          # a tile next to a nation is taken this often per step (x its ground: slower into rough land),
EXPAND_JAG = 0.4           # more or less by the lie of the land (+- this): fronts advance raggedly - two countries
                           # growing into the same empty land meet along a winding border, not a straight line
EXPAND_EMPTY_MAX = 25      # empty, (nearly) zombie-free land next to a nation it can take over per step (its territory
                           # grows back over land the zombies have left)
RESETTLE_EVERY = 4
RESETTLE_SHARE = 0.04      # of a government's people that can be moved per step ...
SMALL_GROUP = 11           # (a small state sends a group out as soon as it has this many to spare)
RESETTLE_GROUP = 15        # ... in groups of this many per tile
RESETTLE_MAX_TILES = 160   # at most this many tiles settled per government per step
RESETTLE_KEEP = 15         # a tile never gives up people below this ...
RESETTLE_GIVE = 0.1       # ... and gives this share of what it has above that (more where it's crowded):
RESETTLE_CROWD = 0.25      #     this share of what it holds above RESETTLE_FULL of its pre-outbreak level (a place
RESETTLE_FULL = 0.6        #     filling up sends its young people out to the empty land around - that's how it spreads)
RESETTLE_MIN_MORALE = 4
TOWN_PULL = 1.0            # settlers shared out by (what a place is rebuilt to) ** this
RESETTLE_EMPTY_FIRST = 300   # emptied tiles are settled before half-empty ones are filled up
RESETTLE_DANGER = 0.25     # a government in more danger than this - or whose outbreak is growing - has other things
                           # to do than settling land (it fights, fortifies, holds on)
HOME_MIN = 30              # (maps that don't know the pre-outbreak population: tiles fill up to this)
PIONEER_RAGGED = 0.6       # (x 1 +- this from place to place: civilization.fine_jag) ...
PIONEER_ROUGH = 1.5        # ... and / (1 + this x how much rough ground slows the going: terrain.MOVE)
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
FOUND_MAX_LIVE = 150       # at most this many successor governments at once
FOUND_GARRISON = 0.25      # survivors around a fallen government's garrison organize with this share of the usual size
FOUND_MAX_TILES = 120      # a new government starts with at most this much land (the rest of the zone is
                           # annexed slowly, EXPAND_MAX tiles per step)
FOUND_MORALE = 7
FOUND_MATERIALS = 25.0
SALVAGE_PER_SITE = 10.0


RUSH = 3.0                 # a government with (almost) no zombies anywhere near it - an emptied continent - resettles
RUSH_CALM = 60             # (1 + RUSH) times as fast: fewer than RUSH_CALM zombies in its whole region ...
PIONEER_RUSH = 14          # ... its pioneers strike out this far beyond its border, and families are bigger
RUSH_BIRTH = 1.5           # (x this many children)
VILLAGE_EVERY = 5          # villages: people nobody governs (and a few from quiet countries) go off on their own -
VILLAGE_FROM = 25          # every VILLAGE_EVERY days a place with this many people may (VILLAGE_CHANCE; from a
VILLAGE_CHANCE = 0.15      # government's land: HOMESTEAD_CHANCE) send VILLAGE_GROUP of them to clean, empty land
HOMESTEAD_CHANCE = 0.02    # VILLAGE_NEAR..VILLAGE_FAR tiles away nobody holds: a village.  It farms and grows
VILLAGE_GROUP = 10         # (VILLAGE_BIRTH), but has no army and no walls: a horde wipes it out.  A cluster of
VILLAGE_NEAR, VILLAGE_FAR = 3, 10          # villages that holds out long enough organizes itself (found())
VILLAGE_MAX = 300          # groups per step (whole map)
VILLAGE_BIRTH = 0.7        # villagers' births, x a governed country's
GATHER = 2                 # stragglers nobody governs, scattered thin over safe land (no tile above 10), gather at the
GATHER_MIN = 15            # busiest spot within GATHER tiles once there are GATHER_MIN of them round it: a village
GATHER_MAX = 300           # (hubs per step)
VILLAGE_LINK = 4           # villages this close to each other count as one settled area when they organize (found)
EMERGE_EVERY = 10
EMERGE_START = 120         # (days into the outbreak: nobody comes out of hiding while it rages)
EMERGE_SHARE = 0.05        # share of once-lived-on tiles where people hid out the outbreak ...
EMERGE_QUIET = 10          # ... who come out once no zombie has been within this many tiles ...
EMERGE_DAYS = 60           # ... for this many days (to twice that: some wait longer)
EMERGE_GROUP = (8, 30)     # (people per hiding place: by what the place held, between these)
EMERGE_MAX = 400           # hiding places emptied per check (whole map)
SMALL_STATE = 600          # a state with fewer people than this ...
SMALL_STORE = 45           # ... has children while it has this many days of food in store, harvest or not,
SMALL_BIRTH = 3.0          # ... and SMALL_BIRTH times as many, and sends out all above SMALL_KEEP of what a place held
SMALL_KEEP = 0.5


def _healthy(world):
    """Per civilization id: can its people grow and settle?"""
    ok = np.zeros(len(world.civs), dtype=bool)
    for c in world.civs:
        if c.id and c.ai and not c.collapsed and not c.famine and (c.food is None or c.food > GROW_FOOD_TICKS * c.food_use):
            # people only have more children while the harvest feeds everyone (not on the stockpile alone)
            prod = c.food_prod if c.food_prod_avg is None else c.food_prod_avg
            ok[c.id] = c.food is None or prod >= c.food_use * 1.03
            if not ok[c.id] and c.m and c.m.get("pop", 0) < SMALL_STATE and c.food > SMALL_STORE * c.food_use:
                ok[c.id] = True                         # (a small new state lives off its stores while its fields grow)
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
    """How many people each tile is rebuilt to: what it held before the outbreak, or what its land holds now if that
    has changed (cleared, built on, ruined: landuse.py); maps without that: HOME_MIN, or what the terrain supports if
    that's less.  Wilderness stays wilderness."""
    h0 = getattr(world, "H0", None)
    if h0 is None:
        return np.minimum(CAP[world.T], HOME_MIN)
    import landuse                                       # (what it held before - until its land changes: landuse.py)
    return landuse.home(world)


def grow(world, healthy, scale=1.0):
    H, T, O = world.H, world.T, world.O
    cap = home(world)
    near2 = world.zombie_near(2)
    allow = healthy[O] & (H > 10) & (H < cap) & (near2 <= STRAY_OK)
    village = (O == 0) & (H > 10) & (H < cap) & (near2 == 0) & _farmable(T)      # (villages nobody governs)
    import nukes
    poisoned = nukes.poisoned(world)
    if poisoned is not None:
        allow &= ~poisoned
    births = H * BIRTH * scale * (1.0 - H / np.maximum(cap, 1))
    small = np.zeros(len(world.civs), dtype=bool)       # (a small young state - a colony, a garrison town - grows fast:
    for c in world.civs:                                 #  stragglers drift in, families are big)
        small[c.id] = bool(c.id and c.m and 0 < c.m.get("pop", 0) < SMALL_STATE)
    births = births * np.where(small[O], SMALL_BIRTH, 1.0) * np.where(_rush(world) > 1.0, RUSH_BIRTH, 1.0)[O]
    births = np.where(village, births * VILLAGE_BIRTH, births)
    H += _rounded(world, np.where(allow | village, births, 0.0)).astype(np.int32)


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


def _rush(world):
    """Per government id: how much faster it resettles (1 normally; 1 + RUSH with hardly a zombie in its region)."""
    memo = getattr(world, "_rush_memo", None)
    if memo is not None and memo[0] == world.ticks and memo[1].size == len(world.civs):
        return memo[1]
    out = np.ones(len(world.civs))
    for c in world.civs:
        if c.id and c.ai and not c.collapsed and c.m and c.m.get("n") and c.m.get("zone_z", 10 ** 9) < RUSH_CALM:
            out[c.id] = 1.0 + RUSH
    world._rush_memo = (world.ticks, out)
    return out


def _working(world):
    """Per government id: can it run a resettlement programme now?"""
    ok = np.zeros(len(world.civs), dtype=bool)
    for c in world.civs:
        if c.id and c.ai and not c.collapsed and c.morale >= RESETTLE_MIN_MORALE and c.m and c.m.get("n"):
            ok[c.id] = (c.threat(c.m) < RESETTLE_DANGER       # (not its past losses: that's why it rebuilds)
                        and c.m.get("growth", 0.0) <= 0.05 and c.m.get("pop_overrun", 0.0) < 0.05)
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
    rush = _rush(world)
    reach = np.where(rush > 1.0, PIONEER_RUSH, PIONEER_REACH)       # (an emptied continent: much further out)
    # how far out they go varies from place to place (fine_jag) and they go less far into rough ground: a ragged
    # spread along the lie of the land, not a disc round the border
    from civilization import fine_jag
    slow = 1.0 + PIONEER_ROUGH * (1.0 - world.statics.move.reshape(H.shape))
    lim = (1.0 + PIONEER_RAGGED * fine_jag(world)) / slow
    # (grown outward a step at a time from the advancing front only - side steps and diagonal ones alternating, so the
    #  spread is round-ish before the lie of the land makes it ragged)
    S = world.statics
    ef, lf, Of, landf = edge.ravel().copy(), lim.ravel(), O.ravel(), land.ravel()
    front = np.flatnonzero(ef > 0)
    for k in range(int(reach.max()) - 1):
        if front.size == 0:
            break
        owner = ef[front]
        keep = reach[owner] * lf[front] > k + 1
        front, owner = front[keep], owner[keep]
        new = []
        for dr, dc in (DIRECTIONS if k % 2 else ((-1, 0), (1, 0), (0, -1), (0, 1))):     # (round, not square)
            nb = S.nbr[(dr, dc)][front]
            on = nb >= 0
            nbo, own = nb[on], owner[on]
            on = (ef[nbo] == 0) & (Of[nbo] == 0) & landf[nbo] & (reach[own] * lf[nbo] > k + 1)
            nbo, own = nbo[on], own[on]
            if nbo.size:
                nbo, first = np.unique(nbo, return_index=True)
                new.append((nbo, own[first]))
        for nbo, own in new:                                # (this step's growth: from last step's front only)
            fresh = ef[nbo] == 0
            ef[nbo[fresh]] = own[fresh]
        front = np.concatenate([nbo for nbo, _ in new]) if new else np.zeros(0, dtype=np.int64)
    edge = ef.reshape(edge.shape)
    who = np.where(O > 0, claim, np.where(world.may_claim(edge), edge, 0))
    target = ((who > 0) & ok[who] & safe & (Z == 0) & habitable(T) & (hm >= SETTLE_HOME)
              & (H < 0.5 * hm) & (H >= 0))
    if not target.any():
        return 0
    # settlers walk there: only land joined to the government's own safe, lived-on land by safe ground (never through
    # a horde to the far side of it)
    reg, nreg = label_components(safe & land)
    keyed = np.unique(reg[(O > 0) & (H > 10) & safe].astype(np.int64) * n + O[(O > 0) & (H > 10) & safe])
    target &= np.isin(reg.astype(np.int64) * n + who, keyed) & (reg > 0)
    if not target.any():
        return 0
    # people to spare: crowded tiles give more
    donor = (O > 0) & ok[O] & safe & (H > RESETTLE_KEEP)
    give = np.where(donor, RESETTLE_GIVE * (H - RESETTLE_KEEP)
                    + RESETTLE_CROWD * np.maximum(H - RESETTLE_FULL * hm, 0), 0.0)
    small = np.zeros(n, dtype=bool)                     # (a small state sends out all it can spare above half of
    for c in world.civs:                                 #  what a place held - births fill it again: that's how a
        small[c.id] = bool(c.id and c.m and 0 < c.m.get("pop", 0) < SMALL_STATE)       # town becomes a country)
    give = np.where(donor & small[O], np.maximum(give, H - np.maximum(RESETTLE_KEEP, SMALL_KEEP * hm)), give)
    give = np.where(donor, give * rush[O], 0.0)          # (an emptied continent: everyone who can goes)
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
    budget = np.minimum(np.minimum(spare, RESETTLE_SHARE * people * rush), RESETTLE_MAX_TILES * RESETTLE_GROUP * rush)
    # (a small state - a colony, a garrison town - still sends out a group at a time when it has one to spare)
    budget = np.where((budget < RESETTLE_GROUP) & (spare >= SMALL_GROUP), np.minimum(spare, RESETTLE_GROUP), budget)
    slots = np.where(budget >= SMALL_GROUP, np.maximum(budget // RESETTLE_GROUP, 1), 0).astype(np.int64)
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
    # (shared out by what each place is rebuilt to: a town gets more of them than a farm - a country coming back has
    #  towns and countryside, not one even spread)
    wt = np.maximum(hm.ravel()[idx].astype(np.float64), 1.0) ** TOWN_PULL
    per = np.floor(got[owner] * wt / np.maximum(np.bincount(owner, weights=wt, minlength=n)[owner], 1e-9)).astype(np.int32)
    per = np.minimum(per, np.maximum(hm.ravel()[idx] - H.ravel()[idx], 0).astype(np.int32) + RESETTLE_GROUP)
    Hf, Of = H.reshape(-1), O.reshape(-1)
    Hf[idx] += per
    Of[idx] = np.where(per > 0, owner, Of[idx])
    leftover = (got - np.bincount(owner, weights=per, minlength=n)).astype(np.int32)   # (what's left over: spread
    count = np.bincount(owner, minlength=n)                                           #  evenly over the places ...)
    even = (leftover // np.maximum(count, 1)).astype(np.int32)
    Hf[idx] += even[owner]
    _, first = np.unique(owner, return_index=True)                                    # (... the rest with the first)
    Hf[idx[first]] += (leftover - even * count)[owner[first]]
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
    # wilderness nobody ever lived on (the Sahara) needs no settlers to be claimed: a neighbour takes it, if clean
    wild = (((O == 0) & world.wild & (H <= EXPAND_MIN_POP) & (H >= 0) & (Z == 0) & is_land(T) & (T != 5)
             & (world.zombie_near(WILD_SAFE) == 0)) if getattr(world, "H0", None) is not None
            else np.zeros(O.shape, dtype=bool))
    if not (free.any() or empty.any() or wild.any()):
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
    from civilization import jag
    pace = np.clip(EXPAND_PACE + EXPAND_JAG * jag(world) / 1.5, 0.05, 1.0) * np.sqrt(world.statics.move.reshape(O.shape))
    go = (world.rng.random(O.shape) < pace) if world.stochastic else (pace >= EXPAND_PACE * 0.6)
    for pool, cap, src in ((free, EXPAND_MAX, best), (empty, EXPAND_EMPTY_MAX, best_g), (wild, WILD_MAX, best)):
        best = src
        claim = pool & go & can[best] & world.may_claim(best)
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


def villages(world):
    """Unorganized settlement: small groups go off on their own and found villages on clean, empty land nobody holds
    (see VILLAGE_*).  Returns the number of groups."""
    H, Z, T, O = world.H, world.Z, world.T, world.O
    rows, cols = H.shape
    near = world.zombie_near(3)
    _gather(world, near)
    import landuse
    calm = np.zeros(len(world.civs), dtype=bool)          # (homesteaders: from a country rebuilding in peace)
    for c in world.civs:
        calm[c.id] = bool(landuse.recovering(c) and c.threat(c.m) < 0.1)
    chance = np.where(O == 0, VILLAGE_CHANCE, np.where(calm[O], HOMESTEAD_CHANCE, 0.0))
    src = (H >= VILLAGE_FROM) & (near == 0) & (chance > 0)
    rnd = world.rng.random(H.shape) if world.stochastic else np.full(H.shape, 0.99)
    rr, cc = np.nonzero(src & (rnd < chance))
    if rr.size == 0:
        return 0
    if rr.size > VILLAGE_MAX:
        pick = world.rng.choice(rr.size, VILLAGE_MAX, replace=False)
        rr, cc = rr[pick], cc[pick]
    rows, cols = H.shape
    hm = home(world)
    ready = np.zeros(H.shape, dtype=bool)
    ready[rr, cc] = True
    # where they can go: clean, empty land nobody holds, within VILLAGE_FAR of a group ready to leave, and not right
    # against other people (a village of its own, not the edge of a town)
    spot = ((O == 0) & (H <= 10) & (H >= 0) & (near == 0) & _farmable(T) & (hm >= SETTLE_HOME)
            & (box_sum(ready, VILLAGE_FAR) > 0) & (box_sum(H > 10, VILLAGE_NEAR - 1) == 0))
    ty, tx = np.nonzero(spot)
    if ty.size == 0:
        return 0
    k = min(rr.size, ty.size)
    pick = (world.rng.choice(ty.size, k, replace=False, p=hm[ty, tx] / hm[ty, tx].sum()) if world.stochastic
            else np.arange(k))
    used = np.zeros(rr.size, dtype=bool)
    mass = world.statics.landmass
    src, dst = [], []
    for j in pick:                                       # (each spot: the nearest group that hasn't left yet)
        y, x = int(ty[j]), int(tx[j])
        dr = np.abs(rr - y)
        dc = np.abs(cc - x)
        if world.wrap:
            dc = np.minimum(dc, cols - dc)
        d = np.maximum(dr, dc).astype(np.float64)
        d[used | (d > VILLAGE_FAR) | (mass[rr, cc] != mass[y, x])] = np.inf
        i = int(np.argmin(d))
        if not np.isfinite(d[i]):
            continue
        used[i] = True
        src.append(i)
        dst.append((y, x))
    if not src:
        return 0
    src = np.array(src)
    tr = np.array([d[0] for d in dst])
    tc = np.array([d[1] for d in dst])
    rr, cc = rr[src], cc[src]
    H[rr, cc] -= VILLAGE_GROUP
    H[tr, tc] = np.maximum(H[tr, tc], 0) + VILLAGE_GROUP
    world.villages_founded = getattr(world, "villages_founded", 0) + int(rr.size)
    return int(rr.size)


VILLAGE_LAND = 0.3         # villages only where the land can feed them (terrain.DENSITY: fields, woods, hills, towns)


def _farmable(T):
    from terrain import DENSITY
    return DENSITY[T] >= VILLAGE_LAND


def _gather(world, near):
    """Scattered stragglers nobody governs gather into villages (GATHER*)."""
    H, O, T = world.H, world.O, world.T
    thin = (O == 0) & (H > 0) & (H <= 10) & (near == 0) & _farmable(T)
    if not thin.any():
        return 0
    held = np.where(thin, H, 0)
    total = box_sum(held, GATHER)
    # hubs: the busiest thin tile round itself (ties broken by position), with enough people about
    from engine import shift
    best = held.astype(np.float64) + 1e-6 * np.arange(H.size).reshape(H.shape) / H.size
    peak = best.copy()
    for dr in range(-GATHER, GATHER + 1):
        for dc in range(-GATHER, GATHER + 1):
            if dr or dc:
                np.maximum(peak, shift(best, dr, dc, world.wrap, 0.0), out=peak)
    hubs = np.argwhere(thin & (best >= peak) & (total >= GATHER_MIN))
    if len(hubs) > GATHER_MAX:
        hubs = hubs[world.rng.choice(len(hubs), GATHER_MAX, replace=False)] if world.stochastic else hubs[:GATHER_MAX]
    rows, cols = H.shape
    n = 0
    for r, c in hubs:
        r0, r1, c0, c1 = max(r - GATHER, 0), min(r + GATHER + 1, rows), max(c - GATHER, 0), min(c + GATHER + 1, cols)
        win = thin[r0:r1, c0:c1]
        got = int(H[r0:r1, c0:c1][win].sum())
        H[r0:r1, c0:c1][win] = 0
        H[r, c] += got
        thin[r0:r1, c0:c1] = False
        n += 1
    return n


def _components(mask):
    return label_components(mask)


def emerge(world):
    """Survivors who hid out the outbreak come out once the hordes have long left (EMERGE_*): small villages on the
    land the zombies took.  Returns how many came out."""
    if world.ticks < EMERGE_START or getattr(world, "H0", None) is None:
        return 0
    H, O = world.H, world.O
    quiet = getattr(world, "_quiet_age", None)
    if quiet is None or quiet.shape != H.shape:
        quiet = world._quiet_age = np.zeros(H.shape, dtype=np.int32)
        world._hidden = (world.rng.random(H.shape) < EMERGE_SHARE) & world.statics.land & (world.H0 >= SETTLE_HOME)
        world._hidden_wait = (EMERGE_DAYS * (1.0 + world.rng.random(H.shape))).astype(np.int32)
    calm = world.zombie_near(EMERGE_QUIET) == 0
    quiet[:] = np.where(calm, np.minimum(quiet + EMERGE_EVERY, 30000), 0)
    out = world._hidden & (quiet >= world._hidden_wait) & (O == 0) & (H <= 10) & (H >= 0) & _farmable(world.T)
    idx = np.flatnonzero(out.ravel())
    if idx.size == 0:
        return 0
    if idx.size > EMERGE_MAX:
        idx = world.rng.choice(idx, EMERGE_MAX, replace=False)
    lo, hi = EMERGE_GROUP
    n = np.clip(world.H0.ravel()[idx].astype(np.int32) // 6, lo, hi)
    H.reshape(-1)[idx] += n
    world._hidden.reshape(-1)[idx] = False
    total = int(n.sum())
    world.emerged = getattr(world, "emerged", 0) + total
    if total >= 300 and world.ticks - getattr(world, "_emerge_noted", -10 ** 6) >= 90:
        world._emerge_noted = world.ticks
        from fracture import _place
        r, c = divmod(int(idx[int(np.argmax(n))]), world.cols)
        world.note(f"survivors come out of hiding across the emptied land ({world.people(total)}, around "
                   f"{_place(world, (r, c))} and elsewhere): villages again")
    return total


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
    garrison = np.zeros(H.shape, dtype=bool)          # (a fallen government's garrison still standing among them)
    for o in world.civs:
        if o.collapsed:
            for st in o.sites:
                garrison[st["center"]] = True
    if not stable.any():
        return
    # (villages a few tiles apart are one settled area: label the area round them, count the villages themselves)
    labels, n = _components(box_sum(stable, VILLAGE_LINK // 2) > 0)
    if n == 0:
        return
    labels = np.where(stable, labels, 0)
    flat = labels.reshape(-1)
    sizes = np.bincount(flat, minlength=n + 1)
    pops = np.bincount(flat, weights=H.reshape(-1), minlength=n + 1)
    rr, cc = np.indices(H.shape)
    held = np.bincount(flat, weights=garrison.reshape(-1), minlength=n + 1) > 0
    for k in np.argsort(-pops[1:]) + 1:
        small = FOUND_GARRISON if held[k] else 1.0       # (soldiers to organize around: a state even if small)
        if sizes[k] < max(2, FOUND_MIN_TILES * small) or pops[k] < FOUND_MIN_POP * small:
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
        spread = int(mask.sum()) < 0.5 * (np.ptp(np.nonzero(mask)[0]) + 1) * (np.ptp(np.nonzero(mask)[1]) + 1)
        world.note((f"the villages around {civ.place} band together: " if spread and getattr(civ, "place", None)
                    else "survivors found ") + civ.name
                   + (f" ({govern.LABEL[civ.gov]})" if world.cities else "")
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
    if t % VILLAGE_EVERY == 2:
        villages(world)
    if t % EXPAND_EVERY == 0:
        expand(world)
    if t % FOUND_EVERY == 0:
        found(world)
    if t % EMERGE_EVERY == 3:
        emerge(world)
