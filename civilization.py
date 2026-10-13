"""Civilizations: who owns what, their morale, and what they decide to do about zombies.

Id 0 is "nobody / anarchy".  It is a Civilization object too (so owner ids index
into world.civs directly) but it has constant morale and never decides anything.

A Civilization built with ai=False follows the ORIGINAL rules only (tile-count morale,
collapse below 2, no actions); that mode exists so the port can be checked against the old code.

With ai=True:
  Morale   drops when zombies are steadily expanding towards land that has no significant
           protection (military defense or terrain), recovers slowly when that is not the case,
           and is hit by riots.  Low morale also lowers tile defense (see sim.py).
           Morale < ANARCHY_AT  ->  the civilization collapses into anarchy.
  Actions  every DECISION_INTERVAL ticks: ignore / fortify / purge / evacuate (see score()).
  Fortify  plans a few specific SITES (cities, mountains, coastal chokepoints near the zombies),
           builds them up with materials (see economy.py).  A site that is overrun is lost for good:
           the materials are not refunded and the ground around it can't be re-fortified.
"""
from collections import deque

import numpy as np

from terrain import is_land, is_water

import govern

IGNORE, FORTIFY, PURGE, EVACUATE = "ignore", "fortify", "purge", "evacuate"
QUARANTINE, RECLAIM, OFFENSIVE, RETREAT = "quarantine", "reclaim", "offensive", "retreat"
ACTIONS = (IGNORE, FORTIFY, PURGE, EVACUATE, QUARANTINE, RECLAIM, OFFENSIVE, RETREAT)
ACTIVITIES = (QUARANTINE, RETREAT, FORTIFY, PURGE, EVACUATE, RECLAIM, OFFENSIVE)

# --- morale ---------------------------------------------------------------------------
ANARCHY_AT = 3             # morale below this: the civilization collapses ...
MORALE_HELD = 0.6          # ... but not while it still holds this share of its peak population: a government that
                           #     has most of its people doesn't dissolve over a bad month (it can still lose its capital)
NEAR_RADIUS = 4            # "close" = within this many tiles (square box)
MORALE_NEAR = 250          # zombies in that box for a tile to count as being on the front
SIGNIFICANT_DEFENSE = 4    # defense (or terrain protection) at/above this really holds zombies back
MORALE_MIN_TILES = 3       # an unprotected front must cover at least this many tiles ...
MORALE_MIN_SHARE = 0.01    # ... and this share of the civilization's populated land
MORALE_LOSS_EVERY = 2      # while the front keeps expanding, -1 morale every this many ticks (+ extra when severe)
TREND_WINDOW = 6           # ticks of history used to decide "steadily expanding"
TREND_GROWTH = 1.10        # ... and the unprotected front must have grown by this factor over the window
RECOVER_EVERY = 2          # when calm, +1 morale every this many ticks
from terrain import PROTECTION as TERRAIN_PROTECTION          # by terrain id (terrain.py)

# --- decisions ------------------------------------------------------------------------
# A civilization can run several activities at once (fortify + purge + evacuate); "ignore" just means none is on.
DECISION_INTERVAL = 5      # ticks between decisions (outbreaks here grow fast)
ACTIVATE = 0.35            # an activity switches on when its score reaches this ...
DEACTIVATE = 0.20          # ... and off again when it drops below this
NEAR_ZOMBIES = 300         # zombies inside that box for a tile to count as threatened
REGION_REACH = 6           # a civilization's region = land within this many tiles of its populated tiles
ZONE_WINDOW = 6            # ticks over which growth of the zombie population in its region is judged
GROWTH_MIN_ZOMBIES = 150   # ...but only once there are at least this many zombies in the region
CALM_ZOMBIES = 100         # fewer zombies than this in the whole region: nothing to worry about
STRONG_ARMOR = 0.6         # mean protection/10 on threatened land counted as "strong" ...
STRONG_GROWTH = 0.05       # ... if zombies in the region aren't growing faster than this over the window,
STRONG_OVERRUN_POP = 0.02  # ... under this share of people are in mostly-zombie tiles,
PEAK_FADE = 0.004          # the 'peak population' that damage is measured against fades by this much per tick
STRONG_DAMAGE = 0.02       # ... and less than this share of its peak population has been lost

# --- fortification --------------------------------------------------------------------
FORT_COST = 1.0            # materials per +1 defense on one tile
FORT_MIN_MATERIALS = 5     # below this it can't start anything
FORT_SITES = 6             # at most this many sites planned at once
FORT_TARGET = 7            # 7 = zombies can't enter and are exterminated inside (needs 50+ people to man it)
FORT_OUTPOST_TARGET = 5    # sparsely populated sites can only hold this much
FORT_LOOKAHEAD = 8         # zombies within this many tiles make a site more urgent
FORT_REGION = 20           # sites are only planned where there are zombies within this many tiles ...
FORT_MIN_NEAR = 60         # ... at least this many of them
FORT_MIN_POP = 50          # people needed to man a full-strength site (below 50 humans defense decays)
FORT_OUTPOST_POP = 12      # minimum people for any site
FORT_SPACING = 12          # sites are at least this far apart (and mildly discouraged within twice that)
CHOKE_MAX = 10             # land corridors up to this wide count as chokepoints
FORT_LOST_RADIUS = 3       # ground this close to a lost site can't be fortified again
FORTIFY_EVERY = 3          # ticks between build steps
REPLAN_COOLDOWN = 20       # ticks between planning new sites

# --- other actions --------------------------------------------------------------------
PURGE_EVERY = 5            # ticks between strikes
PURGE_MIN_ZOMBIES = 20     # a tile needs this many zombies to be targeted
PURGE_MAX_TILES = 60       # one strike hits at most this many tiles (the densest ones in reach)
PURGE_TARGETS_FULL = 8     # this many targets make a strike fully worthwhile
PURGE_KILL = 0.5           # share of zombies killed per strike
PURGE_COLLATERAL = 0.03    # share of humans killed on struck tiles
PURGE_COST = 0.005         # materials per zombie killed (ammunition)
PURGE_MIN_MATERIALS = 2    # can't launch a strike with less than this
EVAC_SHARE = 8             # a tile moves 1/EVAC_SHARE of its humans per tick
EVAC_IMPROVEMENT = 0.7     # ...only toward a neighbour with < this x the zombies nearby
EVAC_COST = 0.002          # materials per person moved (transport)
FAMINE_MORALE_EVERY = 3    # in famine, -1 morale every this many ticks ...
FAMINE_MORALE_FLOOR = 4    # ... but hunger alone never breaks a government (riots, deaths and unrest still hurt)

# --- quarantine -----------------------------------------------------------------------
QUAR_MIN_ZOMBIES = 150     # zombies in the region before closing borders is on the table
QUAR_FULL = 1000.0         # zombies outside the borders that make quarantine fully worthwhile

# --- military and reclamation ---------------------------------------------------------
MIL_START = 0.15           # founding nations begin with a small standing army (0..1)
MIL_MIN_POP = 150          # people needed before anyone can be drilled
MIL_MIN_MATERIALS = 15     # equipment needed to keep training
MIL_RATE = 0.006           # training per tick (scaled by population, up to 1500 people)
MIL_COST = 8.0             # materials per unit of training
MIL_ATTRITION = 0.002      # a destitute army melts away this fast
RECLAIM_READY = 0.3        # army strength needed to start a campaign
STABLE_TILES = 150         # governments at least this big lose morale more slowly (twice this: more so)
NOTE_GAP = 60             # ticks before the same government's same activity is announced again
QUAR_MIN_TICKS = 60        # borders stay shut at least this long once closed ...
QUAR_REOPEN_TICKS = 40     # ... and only reopen once the threat outside has stayed low this long
QUAR_SMOOTH = 0.35         # the quarantine case is judged on a running average (weight of the newest look)
RETREAT_DANGER = 0.45      # danger at which a government starts pulling back to defensible land
FORT_SITES_BASE = 3        # a government can keep up this many fortified sites / bases ...
FORT_SITES_PER_POP = 25000 # ... plus one per this many people
SITE_UPKEEP = 0.05         # materials per site per tick, plus ...
SITE_UPKEEP_LEVEL = 0.002  # ... this per tile per defense level
RECLAIM_MIN_ZOMBIES = 30   # zombies in the region before a campaign makes sense
RECLAIM_MIN_MATERIALS = 10
RECLAIM_EVERY = 2          # ticks between waves
RECLAIM_REACHES = (1, 2, 4, 6)    # the army fights the zombies in and near its land (deeper pushes are the offensive's job,
                                  # offensive.py) - sweeping far out only cleared an empty no-man's-land
RECLAIM_MIN_Z = 3
RECLAIM_TILES = 25         # tiles hit per wave at the weakest (+90 more at full army strength)
RECLAIM_KILL = 0.5         # base share of zombies killed on a hit tile (raised by army strength)
RECLAIM_COST = 0.004       # materials per zombie killed
RECLAIM_WAVE_COST = 0.003  # army strength lost per wave ...
RECLAIM_LOSS = 0.00005     # ... plus this per zombie killed

SIZE_MIN, SIZE_MAX = 0.15, 3.0    # how big a government's war effort is next to an average one's: sqrt(its people /
                                  # an average government's people), within these bounds.  Strikes, sweeps and
                                  # stockpiles scale with it (a big country fights with more than a small one).

# --- remnant garrisons ----------------------------------------------------------------
REMNANT_HOLD = 150         # ticks after the government falls before the garrisons start to wear down
REMNANT_DECAY_EVERY = 40   # then lose one level this often ...
REMNANT_FLOOR = 5          # ... down to this
REMNANT_PATROL = 0.10      # share of zombies next to a garrison killed per tick

DIRECTIONS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def box_sum(arr, r, rx=None):
    """Sum of arr over the (2r+1)x(2r+1) box around each tile (or (2r+1) rows x (2rx+1) columns), zero outside the
    map.  Running sums down the rows, then along them (integer counts in int32 - 255 x a million tiles fits - which
    is much faster)."""
    arr = np.asarray(arr)
    dt = np.int32 if arr.dtype == bool or (arr.dtype.kind in "iu" and arr.size * 256 < 2 ** 31) else np.int64
    rows, cols = arr.shape
    rx = r if rx is None else rx
    k, kx = 2 * r + 1, 2 * rx + 1
    c = np.zeros((rows + k, cols), dtype=dt)
    np.cumsum(arr, axis=0, dtype=dt, out=c[r + 1:r + 1 + rows])
    c[r + 1 + rows:] = c[r + rows]
    v = c[k:] - c[:-k]
    c2 = np.zeros((rows, cols + kx), dtype=dt)
    np.cumsum(v, axis=1, out=c2[:, rx + 1:rx + 1 + cols])
    c2[:, rx + 1 + cols:] = c2[:, rx + cols:rx + cols + 1]
    return c2[:, kx:] - c2[:, :-kx]


def round_sum(arr, r):
    """Like box_sum, but over a roundish patch (an octagon: two crossed rectangles) - so whatever is decided on these
    counts (who flees, what's given up, where the horde is 'near') has round edges, not square ones.  Scaled up to
    the box's area, so thresholds set for box counts still mean the same."""
    if r <= 1:
        return box_sum(arr, r)
    k = max(1, int(round(0.6 * r)))
    s = box_sum(arr, r, k) + box_sum(arr, k, r) - box_sum(arr, k)
    box, cross = (2 * r + 1) ** 2, 2 * (2 * r + 1) * (2 * k + 1) - (2 * k + 1) ** 2
    return (s * (box / cross)).astype(s.dtype)


SIDES = [(-1, 0), (1, 0), (0, -1), (0, 1)]


def steps(mask, n, through=None):
    """Steps from every tile to the nearest tile of `mask`, up to n (n + 1 beyond) - counted 'round': side steps and
    diagonal steps alternate, so the distance grows in octagons (close to circles), not in squares.  `through`, if
    given, is the ground the steps may cross."""
    rows, cols = mask.shape
    dist = np.where(mask, 0, n + 1).astype(np.int16)
    cur = mask.copy()
    for k in range(1, n + 1):
        grow = cur.copy()
        for dr, dc in (SIDES if k % 2 else DIRECTIONS):
            sr, tr = _slices(rows, dr)
            sc, tc = _slices(cols, dc)
            grow[tr, tc] |= cur[sr, sc]
        if through is not None:
            grow &= through | cur
        new = grow & ~cur
        if not new.any():
            break
        dist[new] = k
        cur = grow
    return dist


def jag(world, win=(slice(None), slice(None))):
    """A fixed field of -1.5..1.5 per tile: added to a reach, it makes the edge of what's in reach ragged."""
    f = getattr(world, "_jag", None)
    if f is None or f.shape != world.H.shape:
        from make_world import fbm
        seed = int(getattr(world, "seed", 0) or 0) if getattr(world, "stochastic", False) else 0
        g = fbm(np.random.default_rng(seed + 77), world.rows, world.cols,
                cells=(max(4, world.cols // 12), max(8, world.cols // 6), max(16, world.cols // 3)))
        f = world._jag = (np.clip((g - g.mean()) / (2.0 * g.std() + 1e-9), -1.0, 1.0) * 1.5).astype(np.float32)
    return f[win]


def within(world, mask, reach, win=(slice(None), slice(None)), through=None):
    """Tiles within about `reach` steps of `mask` (cut to window `win`): a ragged, roundish band - no boxes."""
    return steps(mask, reach + 2, through) <= reach + jag(world, win)


def protection(world):
    """How well each tile holds zombies back: military defense or terrain, whichever is better, plus a manned
    front line (front.py) in front of / at the tile.  Cached for the rest of the tick once asked for (defense only
    changes a little within a tick; front.step clears the cache when it re-mans the line)."""
    line = getattr(world, "line_prot", None)
    key = (getattr(world, "ticks", 0), id(line), id(world.D))
    cache = getattr(world, "_prot_cache", None)
    if cache is not None and cache[0] == key:
        return cache[1]
    p = np.maximum(world.D, TERRAIN_PROTECTION[world.T])
    if line is not None:
        p = p + line
    try:
        world._prot_cache = (key, p)
    except AttributeError:
        pass
    return p


def window(world, civ_id, margin):
    """Slices around a government's land (plus `margin` tiles): per-government work only needs to look there."""
    bb = getattr(world, "bbox", None)
    if bb is None:
        return slice(None), slice(None)
    return bb(civ_id, margin)


def _runs(passable):
    """Length of the unbroken passable run through every tile, along rows."""
    a = passable.astype(np.int32)
    rows, cols = a.shape
    fwd, bwd = np.zeros_like(a), np.zeros_like(a)
    fwd[:, 0], bwd[:, -1] = a[:, 0], a[:, -1]
    for j in range(1, cols):
        fwd[:, j] = (fwd[:, j - 1] + 1) * a[:, j]
        bwd[:, cols - 1 - j] = (bwd[:, cols - j] + 1) * a[:, cols - 1 - j]
    return np.where(passable, fwd + bwd - 1, 0)


def corridor_width(passable, cap=20):
    """How narrow the passable ground is at each tile: the shorter of the east-west and north-south
    runs through it (a gap in a mountain range is wide along the range and short across the gap...
    whichever way the range runs, the short run is the width of the pass)."""
    return np.minimum(np.minimum(_runs(passable), _runs(passable.T).T), cap)


def world_corridor(world):
    """corridor_width of the passable (not water, not mountain) ground - terrain never changes, so computed once."""
    cache = getattr(world, "_corridor", None)
    if cache is None or cache.shape != world.T.shape:
        cache = corridor_width(is_land(world.T) & (world.T != 3))
        try:
            world._corridor = cache
        except AttributeError:
            pass
    return cache


def _slices(n, dr):
    """(source, target) slices along one axis for a shift of dr."""
    if dr == 0:
        return slice(0, n), slice(0, n)
    if dr > 0:
        return slice(0, n - dr), slice(dr, n)
    return slice(-dr, n), slice(0, n + dr)


def flow_away(world, src, ok, share, cost, improvement, min_move=0, win=None):
    """Move 1/share of the humans on every `src` tile to its best neighbouring tile
    (lowest `cost`, must be `ok`, and must beat the tile's own cost by `improvement`).
    At least `min_move` people go (so tiny groups can leave too).  Humans are conserved and no tile
    goes above 255.  Returns the number of humans moved.
    Works on the source tiles only (a short list with their 8 neighbours), so it costs nothing where nothing moves.
    `win` (a pair of slices) says that src/ok/cost were cut to that window of the map (or limits the sources to it)."""
    H, O = world.H, world.O
    shape = H.shape
    if win is not None:
        full = []
        for a in (src, ok, cost):
            if a.shape == shape:
                b = np.zeros(shape, dtype=a.dtype)
                b[win] = a[win]
                full.append(b if a is src else a)
            else:
                b = np.zeros(shape, dtype=a.dtype) if a is not cost else np.full(shape, np.inf, dtype=np.float32)
                b[win] = a
                full.append(b)
        src, ok, cost = full
    idx = np.flatnonzero(src)
    if idx.size == 0:
        return 0
    nbr = world.statics.nbr
    Hf, Of = H.ravel(), O.ravel()
    okf = ok.ravel()
    costf = cost.ravel()
    closed = getattr(world, "closed", None)
    shut = None
    if closed:                                    # quarantined nations don't let outsiders in
        arr = np.zeros(len(world.civs), dtype=bool)
        arr[list(closed)] = True
        shut = arr
    cand = np.full((8, idx.size), np.inf, dtype=np.float32)
    tgts = np.zeros((8, idx.size), dtype=np.int64)
    for k, d in enumerate(DIRECTIONS):
        t = nbr[d][idx]
        valid = t >= 0
        tc = np.where(valid, t, 0)
        good = valid & okf[tc]
        if shut is not None:
            good &= ~(shut[Of[tc]] & (Of[tc] != Of[idx]))
        cand[k] = np.where(good, costf[tc].astype(np.float32), np.inf)
        tgts[k] = tc
    best = cand.argmin(axis=0)
    cols = np.arange(idx.size)
    go = cand[best, cols] < costf[idx].astype(np.float32) * improvement
    if not go.any():
        return 0
    s_i = idx[go]
    t_i = tgts[best[go], cols[go]]
    hs = Hf[s_i]
    amount = np.minimum(np.maximum(hs // share, min_move), np.maximum(hs, 0))
    moved = np.maximum(np.minimum(amount, 255 - Hf[t_i]), 0)
    Hf[s_i] -= moved
    np.add.at(Hf, t_i, moved)
    return int(moved.sum())


class Civilization:
    def __init__(self, civ_id, morale=8, name=None, ai=True, traits=None):
        self.id = civ_id
        self.name = name or ("Anarchy" if civ_id == 0 else f"Civ {civ_id}")
        self.morale = 10 if civ_id == 0 else morale
        self.tiles = 0
        self.ai = ai and civ_id != 0
        self.collapsed = False
        self.action = IGNORE
        self.next_decision = 0
        self.history = []            # (tick, action, scores) whenever the action changes
        self.m = {}                  # latest measurements, for display / debugging
        self.riot_hit = 0            # morale damage from riots, applied by update_morale
        self._unprotected = deque(maxlen=TREND_WINDOW)
        self._zone = deque(maxlen=ZONE_WINDOW + 1)
        self.peak_pop = 0
        self.active = set()          # activities currently switched on
        self._calm = 0
        self._pressure = 0
        self._famine_ticks = 0
        # fortification
        self.food = None             # set by economy.step on the first tick
        self.materials = 0.0
        self.food_use = self.food_prod = self.mat_income = 0.0
        self.famine = False
        self.sites = []              # dicts: center, tiles, level
        self.sites_lost = 0
        self.lost_mask = None
        self.next_plan = 0
        self.last_strike = 0
        # personality (1.0 = average): how readily it acts / how eager it is to fight
        self.traits = traits or {"caution": 1.0, "aggression": 1.0}
        # military, survivors, wars
        self.military = MIL_START if civ_id else 0.0
        self.successor = False       # founded by survivors after the world fell apart
        self.founded = 0
        self.remnant = False         # collapsed, but its fortified garrisons still stand
        self.collapsed_at = 0
        self.war_hold = False        # at war: morale doesn't recover
        self.blight_until = -1
        self.kills = 0
        self.quar_since = -10 ** 6
        self._noted = {}
        self.merged_into = None
        self.root = civ_id           # the original nation this government descends from (fragments share it)
        self.bases = []              # staged offensive: strongpoints in infested land (offensive.py)
        self.advances = 0
        self.next_base = 0
        self.base_check = (-1, False)
        self._world_ref = None
        self.tile_hist = deque(maxlen=8)   # tile count every 10 ticks, to notice when expansion has stalled
        self.long_hist = deque(maxlen=20)  # ... and over 200 ticks, to notice when it has grown fast (fracture.py)
        # government and breakup (govern.py, fracture.py)
        self.gov = "national"
        self.strength = 0.3          # how good its army is (0..1, meta "military"): training, the front line
        self.nukes = 0               # warheads (meta "nukes", nukes.py)
        self.nukes_used = 0
        self.ports = 0.0             # working port capacity (boats.py)
        self.capital = None          # (row, col) seat of government
        self.split_from = None       # the government it broke away from
        self.retreat_mask = None     # districts being given up (RETREAT)
        self.line_kills = 0
        self.front_len = 0           # front-line tiles it manned last tick (front.py)
        self.alert = 0.0             # mobilization of the front line (front.py)
        self.food_prod_avg = None    # harvests, smoothed (growth is judged on these, not on one good week)
        self._loss_acc = 0.0
        self._recover_acc = 0.0
        self.quar_avg = 0.0
        self.quar_low = 0
        self.upkeep = 0.0
        # peace (peace.py)
        self.peace = False
        self.calm_ticks = 0

    def size(self, world):
        """Its war effort next to an average government's (1.0): strikes, sweeps and the stockpile scale with it."""
        pop = self.m.get("pop", 0) if self.m else 0
        return float(np.clip(np.sqrt(pop / getattr(world, "pop_ref", max(pop, 1))), SIZE_MIN, SIZE_MAX))

    @property
    def is_anarchy(self):
        return self.id == 0

    # ------------------------------------------------------------------ measuring
    def measure(self, world):
        win = window(world, self.id, REGION_REACH + 1)          # its land and the ground around it
        H, Z = world.H[win], world.Z[win]
        owned = (world.O[win] == self.id) & (H > 10)
        n = int(owned.sum())
        m = dict(n=n, exposure=0.0, overrun=0.0, armor=1.0, unprotected=0, threatened=None, win=win,
                 pop=0, pop_exposure=0.0, pop_overrun=0.0, zone_z=0, strikes=0,
                 growth=0.0, damage=0.0, tick=world.ticks, inside_z=0, outside_z=0, hordes=0)
        if n and not world.Z[win].any():                       # no zombies anywhere near: nothing else to measure
            m["pop"] = int(H[owned].sum())
        elif n:
            near = world.zombie_near(NEAR_RADIUS)[win]
            prot = protection(world)[win]
            home = owned
            masses = getattr(self, "home_masses", None)
            if masses is not None:                         # (an expedition overseas doesn't count as the front at home)
                home = owned & np.isin(world.statics.landmass[win], masses)
            threatened = home & (near >= NEAR_ZOMBIES)
            front = home & (near >= MORALE_NEAR)
            pop = int(H[owned].sum())
            region = box_sum(owned, REGION_REACH) > 0         # its land and the ground around it
            m.update(
                threatened=threatened,
                exposure=float(threatened.sum()) / n,
                overrun=float((home & (Z > H)).sum()) / n,
                armor=float(prot[threatened].mean()) / 10 if threatened.any() else 1.0,
                unprotected=int((front & (prot < SIGNIFICANT_DEFENSE)).sum()),
                pop=pop,
                pop_exposure=float(H[threatened].sum()) / max(pop, 1),
                pop_overrun=float(H[home & (Z * 2 >= H)].sum()) / max(pop, 1),
                zone_z=int(Z[region].sum()),
                inside_z=int(Z[owned].sum()),
                strikes=int((region & (Z >= PURGE_MIN_ZOMBIES)).sum()),
                hordes=int((region & (Z >= RECLAIM_MIN_Z)).sum()),
            )
            m["outside_z"] = max(0, m["zone_z"] - m["inside_z"])
        return m

    assess = measure

    def observe(self, world):
        """measure() plus history-based quantities (zombie growth in the region, damage taken).
        Called once per tick."""
        m = self.measure(world)
        self._zone.append(m["zone_z"])
        if len(self._zone) > ZONE_WINDOW and m["zone_z"] >= GROWTH_MIN_ZOMBIES:
            m["growth"] = m["zone_z"] / max(self._zone[0], 50) - 1.0
        self.peak_pop = max(self.peak_pop * (1.0 - PEAK_FADE), m["pop"])     # old losses are gradually forgotten
        if self.peak_pop > 0:
            m["damage"] = max(0.0, 1.0 - m["pop"] / self.peak_pop)
        return m

    # ------------------------------------------------------------ morale / collapse
    def update_morale(self, world):
        if self.is_anarchy:
            return
        if not self.ai:                      # original rules
            if self.tiles < 2:
                self.morale -= 1
            elif self.morale < 10:
                self.morale += 1
            if self.morale < 2:
                world.O[world.O == self.id] = 0
            return
        if self.collapsed:
            return

        m = self.m = self.observe(world)
        n = m["n"]
        self._unprotected.append(m["unprotected"])
        loss, hold = 0, False
        m["significant"] = False
        if n == 0:                           # (a one-city state is still a state; nothing left is not)
            loss = 1
        else:
            share = m["unprotected"] / n
            significant = m["unprotected"] >= max(MORALE_MIN_TILES, MORALE_MIN_SHARE * n)
            hist = list(self._unprotected)
            rises = sum(b > a for a, b in zip(hist, hist[1:]))
            expanding = (len(hist) == TREND_WINDOW and hist[-1] >= hist[0] * TREND_GROWTH + 2
                         and rises >= TREND_WINDOW // 2)
            m["significant"] = significant
            m["growing_front"] = significant and expanding
            if significant and expanding:
                self._pressure += 1
                hold = True                  # no recovery while the front is still advancing
                loss = (1 if self._pressure % MORALE_LOSS_EVERY == 0 else 0)
                loss += (1 if share >= 0.1 else 0) + (1 if m["overrun"] >= 0.1 else 0)
            elif significant:
                hold = True
            else:
                self._pressure = 0
        if self.famine:
            hold = True
            self._famine_ticks += 1
            if self._famine_ticks % FAMINE_MORALE_EVERY == 0 and self.morale > FAMINE_MORALE_FLOOR:
                loss += 1
        else:
            self._famine_ticks = 0
        if self.war_hold:
            hold = True                      # morale doesn't recover while the war drags on
        loss += self.riot_hit
        self.riot_hit = 0
        if loss and n >= STABLE_TILES:                       # a big organization absorbs shocks
            if loss == 1 and world.ticks % 2 == 0:
                loss = 0
            elif loss >= 2 and n >= 2 * STABLE_TILES:
                loss -= 1
        res = getattr(self, "resolve", 0.0)
        if hold and not self.famine and getattr(self, "turned", False) and not m.get("growing_front"):
            hold = False                     # past the turning point a line that holds is enough to recover
        if loss:
            self._loss_acc += loss * govern.mod(self, "morale_loss") * (1.0 - 0.75 * res)   # (adapted: shrugs it off)
            loss = int(self._loss_acc)
            self._loss_acc -= loss
            self.morale = max(self.morale - loss, 0)
            self._calm = 0
        elif not hold:
            self._calm += 1
            if self._calm % RECOVER_EVERY == 0 and self.morale < 10:
                self._recover_acc += govern.mod(self, "recover") * (1.0 + res)
                if self._recover_acc >= 1.0:
                    self._recover_acc -= 1.0
                    self.morale += 1
        if self.morale < ANARCHY_AT and m.get("pop", 0) >= MORALE_HELD * max(getattr(self, "peak_pop", 0.0), 1.0):
            self.morale = ANARCHY_AT
        if self.morale < ANARCHY_AT:
            self.collapse(world)

    def collapse(self, world, why="morale broke", fracture=True):
        """The government falls.  With fracture (the normal case) its regions carry on as states of their own and
        only the hopeless places fall into anarchy (fracture.py).  Without it, all land becomes unowned at once
        (the old rule).  Either way the army doesn't dissolve: garrisons at fortified sites stay manned and keep
        holding their ground (see _maintain)."""
        if fracture and self.ai:
            import fracture as fr
            fr.fracture_all(world, self, why)
            return
        self.collapsed = True
        self.collapsed_at = world.ticks
        self.active = set()
        self.action = IGNORE
        self.bases = []
        self.remnant = bool(self.sites)
        self.military = min(self.military, 0.4)
        world.O[world.O == self.id] = 0
        world.note(f"{self.name} collapses into anarchy" +
                   (f" ({len(self.sites)} garrisons hold out)" if self.sites else ""))

    # ------------------------------------------------------------------- deciding
    def danger(self, m):
        """0..1: how bad things are for this civilization, judged by people at stake rather than land area."""
        s_exp = min(1.0, m["pop_exposure"] * 3)                 # people living near lots of zombies
        s_over = min(1.0, m["pop_overrun"] * 6)                 # people in tiles zombies mostly hold
        s_dmg = min(1.0, m["damage"] * 5)                       # share of the peak population already lost
        s_grow = min(1.0, max(0.0, m["growth"]) * 2)            # zombies multiplying in its region, anywhere
        d = max(s_exp, s_over, s_dmg, 0.8 * s_grow)
        if m["zone_z"] > 0:
            d = min(1.0, d + 0.3 * (10 - self.morale) / 10.0)   # falling morale makes everything feel urgent
        return d, s_over, s_dmg

    def threat(self, m):
        """0..1: the danger it is in right now - zombies at its people, overrun people, an outbreak growing - without
        what it has already lost (a country that lost a fifth of its people is not still in danger for that; it is
        rebuilding).  For rebuilding, settling and expeditions."""
        s_exp = min(1.0, m["pop_exposure"] * 3)
        s_over = min(1.0, m["pop_overrun"] * 6)
        s_grow = min(1.0, max(0.0, m["growth"]) * 2)
        return max(s_exp, s_over, 0.8 * s_grow)

    def score(self, m):
        d, s_over, s_dmg = self.danger(m)
        off = {FORTIFY: -1.0, PURGE: -1.0, EVACUATE: -1.0, QUARANTINE: -1.0, RECLAIM: -1.0, OFFENSIVE: -1.0}
        import offensive
        if offensive.ready(self, self._world_ref, d):
            off[OFFENSIVE] = 0.3 + 0.6 * self.military - d
        elif self.bases:
            off[OFFENSIVE] = DEACTIVATE + 0.05 - d if d < 0.35 else -1.0   # finish what it started
        # A strong, safe nation with an army takes the offensive.
        if (m["zone_z"] >= RECLAIM_MIN_ZOMBIES and m.get("hordes", m["strikes"]) > 0 and not self.famine
                and self.materials >= RECLAIM_MIN_MATERIALS and self.military >= RECLAIM_READY):
            off[RECLAIM] = 0.25 + 0.8 * self.military - 0.7 * d + 0.5 * getattr(self, "resolve", 0.0)
        off[RETREAT] = -1.0
        # Closing the borders pays off while the horde is still outside and the people inside are clean.
        # (Judged before the 'calm' shortcut: a quiet week at a shut border is no reason to open it.)
        if m["zone_z"] >= QUAR_MIN_ZOMBIES:
            clean = max(0.0, 1.0 - 2.5 * m["pop_overrun"] - m.get("inside_z", 0) / max(m["zone_z"], 1))
            off[QUARANTINE] = 1.2 * min(1.0, m.get("outside_z", 0) / QUAR_FULL) * clean
        calm = m["zone_z"] < CALM_ZOMBIES or d < 0.08           # few zombies, or none that matter
        if calm:
            return off
        strong = (m["armor"] >= STRONG_ARMOR and m["growth"] <= STRONG_GROWTH
                  and m["pop_overrun"] < STRONG_OVERRUN_POP and m["damage"] < STRONG_DAMAGE)
        if strong:                                               # ignoring the zombies is the right call
            return off
        can_purge = self.materials >= PURGE_MIN_MATERIALS and m["strikes"] > 0
        off.update({
            FORTIFY: (0.1 + 1.1 * d) if m.get("fort_ok") else -1.0,
            PURGE: (1.3 * d * min(1.0, m["strikes"] / PURGE_TARGETS_FULL)) if can_purge else -1.0,
            EVACUATE: 1.2 * s_over + 0.4 * s_dmg - 0.15,
        })
        if d >= RETREAT_DANGER and m.get("exposure", 0.0) >= 0.08:      # pull back to land that can be held
            off[RETREAT] = 0.9 * d + 0.6 * m.get("exposure", 0.0) - 0.35 - 0.6 * getattr(self, "resolve", 0.0)
        return off

    @property
    def label(self):
        return "+".join(a for a in ACTIVITIES if a in self.active) or IGNORE

    @property
    def closed(self):
        """Borders and airports are shut."""
        return QUARANTINE in self.active and not self.collapsed

    def decide(self, world):
        m = self.m if self.m.get("tick") == world.ticks else self.observe(world)
        self.m = m
        m["fort_ok"] = self.materials >= FORT_MIN_MATERIALS and bool(
            self._unfinished() or self._candidates(world).max() > 0)
        keys = (FORTIFY, PURGE, EVACUATE, QUARANTINE, RECLAIM, OFFENSIVE, RETREAT)
        self._world_ref = world
        scores = self.score(m) if m["n"] else {k: -1.0 for k in keys}
        caution, aggression = self.traits["caution"], self.traits["aggression"]
        active = set()
        for a, sc in scores.items():
            if a == QUARANTINE:
                continue
            sc += world.noise(0.04)                               # no two runs weigh things the same
            k = aggression if a in (RECLAIM, OFFENSIVE) else caution           # cautious governments act sooner
            if sc >= ACTIVATE / k or (a in self.active and sc >= DEACTIVATE / k):
                active.add(a)
        # Borders: shut on a sustained case, reopened only after the outside has been quiet for a good while.
        q = scores.get(QUARANTINE, -1.0)
        self.quar_avg = (1 - QUAR_SMOOTH) * self.quar_avg + QUAR_SMOOTH * max(q, 0.0)
        if QUARANTINE in self.active:
            self.quar_low = self.quar_low + DECISION_INTERVAL if self.quar_avg < DEACTIVATE / caution else 0
            if self.quar_low < QUAR_REOPEN_TICKS or world.ticks - self.quar_since < QUAR_MIN_TICKS:
                active.add(QUARANTINE)
        elif q >= ACTIVATE / caution and self.quar_avg >= DEACTIVATE / caution:
            active.add(QUARANTINE)
            self.quar_since, self.quar_low = world.ticks, 0
        if active != self.active or not self.history:
            best = max(active, key=scores.get) if active else IGNORE
            self.history.append((world.ticks, best, {k: round(v, 2) for k, v in scores.items()}))
            for a in ACTIVITIES:
                if a in active and a not in self.active and a != QUARANTINE:
                    if world.ticks - self._noted.get(a, -10 ** 6) >= NOTE_GAP:      # don't spam the log
                        world.note(f"{self.name} starts {a}")
                    self._noted[a] = world.ticks
        self.active = active
        self.action = max(active, key=scores.get) if active else IGNORE

    # --------------------------------------------------------------------- acting
    def act(self, world):
        """Called once per tick, before tiles are updated."""
        if not self.ai:
            return
        if world.ticks < self.traits.get("denial", 0):
            return                                          # a cover-up: officially, nothing is happening
        if self.collapsed:
            self._maintain(world)                # the garrisons of a fallen government still hold
            return
        if world.ticks >= self.next_decision:
            self.next_decision = world.ticks + DECISION_INTERVAL + (world.pyrng.randint(-1, 2) if world.stochastic else 0)
            self.decide(world)
        if FORTIFY in self.active and world.ticks % FORTIFY_EVERY == 0:
            if not self._unfinished() and world.ticks >= self.next_plan and self.materials >= FORT_MIN_MATERIALS:
                self._plan_sites(world)
                self.next_plan = world.ticks + REPLAN_COOLDOWN
            self._build(world)
        if PURGE in self.active and world.ticks % PURGE_EVERY == 0:
            self._purge(world)
        if EVACUATE in self.active:
            self._evacuate(world)
        if RETREAT in self.active:
            import fracture as fr
            fr.retreat(world, self)
        else:
            self.retreat_mask = None
        if RECLAIM in self.active and world.ticks % RECLAIM_EVERY == 0:
            self._reclaim(world)
        if OFFENSIVE in self.active or self.bases:
            import offensive
            offensive.step(self, world, active=OFFENSIVE in self.active)
        if world.ticks % 10 == 0:
            self.tile_hist.append(self.tiles)
            self.long_hist.append(self.tiles)
        self._train(world)
        self._maintain(world)        # standing fortifications hold whatever the civ is doing now

    def _train(self, world):
        """Draft and drill soldiers when the nation can afford it."""
        m = self.m
        if not m or not m.get("n"):
            return
        if m["pop"] < MIL_MIN_POP or self.famine or self.materials < MIL_MIN_MATERIALS:
            self.military = max(0.0, self.military - MIL_ATTRITION)
            return
        import peace
        if self.peace and self.military >= peace.army_floor(world):
            return                                              # peacetime: no more drafting (peace.py demobilizes)
        d = self.danger(m)[0]
        rate = (MIL_RATE * min(1.0, m["pop"] / 1500.0) * (1.0 if d < 0.6 else 0.5) * world.jitter(0.3)
                * govern.mod(self, "army") * (0.5 + self.strength)       # strong armies mobilize faster
                * (1.0 + getattr(self, "resolve", 0.0)))                  # (and a country at war with them, faster)
        rate = min(rate, 1.0 - self.military)
        self.military += rate
        self.materials -= MIL_COST * rate

    def _reclaim(self, world):
        """Organized counter-offensive: soldiers sweep the zombie concentrations closest to the borders."""
        if self.materials < RECLAIM_MIN_MATERIALS or self.military <= 0.02:
            return
        win = window(world, self.id, max(RECLAIM_REACHES) + 1)
        owned = (world.O[win] == self.id) & (world.H[win] > 10)
        Zw = world.Z[win]
        if not Zw.any():
            return
        # zombies among its own people first, then the nearest ones outside, then further out
        weight = np.zeros(Zw.shape, dtype=np.float32)
        dist = steps(owned, max(RECLAIM_REACHES) + 2)
        jg = jag(world, win)
        for k, reach in enumerate(sorted(RECLAIM_REACHES, reverse=True)):
            weight = np.where(dist <= reach + jg, k + 1.0, weight)                 # (round, ragged bands)
        weight = np.where(owned, len(RECLAIM_REACHES) + 2.0, weight)
        rr, cc = np.nonzero((weight > 0) & (Zw >= RECLAIM_MIN_Z))
        if rr.size == 0:
            return
        vals = Zw[rr, cc]
        res = getattr(self, "resolve", 0.0)
        width = max(4, int((RECLAIM_TILES + 70 * self.military) * self.size(world) * (1.0 + 0.9 * res)))
        if vals.size > width:
            keep = np.argpartition(-(vals * weight[rr, cc]), width)[:width]
            rr, cc, vals = rr[keep], cc[keep], vals[keep]
        quality = 0.6 + 0.8 * self.strength
        share = min(0.9, RECLAIM_KILL * (0.4 + self.military) * quality * world.jitter(0.25) * (1.0 + 0.9 * res))
        kills = np.minimum(np.maximum(1, np.ceil(vals * share)).astype(np.int32), vals)
        cost = float(kills.sum()) * RECLAIM_COST
        if cost > self.materials:
            kills = (kills * (self.materials / cost)).astype(np.int32)
            cost = float(kills.sum()) * RECLAIM_COST
        self.materials -= cost
        Zw[rr, cc] -= kills                                   # (a view: straight into the map)
        total = int(kills.sum())
        self.kills += total
        self.military = max(0.0, self.military - RECLAIM_WAVE_COST - total * RECLAIM_LOSS)

    # ---------------------------------------------------------------- fortification
    def _unfinished(self):
        return [s for s in self.sites if s["level"] < s["target"]]

    def fort_mask(self, shape):
        mask = np.zeros(shape, dtype=bool)
        for s in self.sites:
            for (r, c) in s["tiles"]:
                mask[r, c] = True
        return mask

    def _candidates(self, world):
        """Value of fortifying each tile as the centre of a new site (0 = not eligible).
        Valuable: places with many people nearby (cities) and narrow land corridors (passes, land
        bridges), where zombies are within reach.  Sites already planned push others away."""
        win = window(world, self.id, FORT_SPACING + 3)
        H, Z, T = world.H[win], world.Z[win], world.T[win]
        near8 = world.zombie_near(FORT_LOOKAHEAD)[win]
        near20 = world.zombie_near(FORT_REGION)[win]
        elig = ((world.O[win] == self.id) & (H >= FORT_OUTPOST_POP) & (Z < H) & is_land(T) & (near20 >= FORT_MIN_NEAR))
        out = np.zeros(world.H.shape)
        if not elig.any():
            return out
        if self.sites:
            centers = np.zeros(world.H.shape, dtype=bool)
            for s in self.sites:
                centers[s["center"]] = True
            elig &= box_sum(centers[win], FORT_SPACING - 1) == 0
        if self.lost_mask is not None:
            elig &= box_sum(self.lost_mask[win], FORT_LOST_RADIUS) == 0
        passable = is_land(T) & (T != 3)
        width = world_corridor(world)[win]
        choke = np.where(passable & (width <= CHOKE_MAX), (CHOKE_MAX + 1 - width) / float(CHOKE_MAX), 0.0)
        stake = np.clip(box_sum(np.maximum(H, 0), 3) / (49 * 150.0), 0, 1)       # people within 3 tiles
        city = stake * (H >= FORT_MIN_POP)
        threat = 0.3 + 0.7 * np.clip(near20 / 3000.0, 0, 1) + 0.5 * np.clip(near8 / 1500.0, 0, 1)
        value = (3.0 * city + 2.5 * choke + 0.3 + 0.4 * (T == 3) + 0.8 * (T == 6)) * threat   # (cities first)
        out[win] = np.where(elig, value, 0.0)
        return out

    def max_sites(self):
        """How many fortified sites / bases this government can keep manned and supplied."""
        pop = self.m.get("pop", 0) if self.m else 0
        return FORT_SITES_BASE + int(pop / FORT_SITES_PER_POP)

    def _plan_sites(self, world):
        val = self._candidates(world)
        rows, cols = val.shape
        while len(self.sites) < min(FORT_SITES, self.max_sites()):
            idx = int(val.argmax())
            r, c = divmod(idx, cols)
            if val[r, c] <= 0:
                break
            tiles = [(r, c)]
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                rr, cc = r + dr, c + dc
                if 0 <= rr < rows and 0 <= cc < cols and world.O[rr, cc] == self.id and is_land(world.T[rr, cc]):
                    tiles.append((rr, cc))
            target = FORT_TARGET if world.H[r, c] >= FORT_MIN_POP else FORT_OUTPOST_TARGET
            self.sites.append(dict(center=(r, c), tiles=tiles, level=int(world.D[r, c]), target=target))
            # spread out: nothing else within FORT_SPACING, and less appeal out to twice that
            val[max(0, r - 2 * FORT_SPACING):r + 2 * FORT_SPACING + 1, max(0, c - 2 * FORT_SPACING):c + 2 * FORT_SPACING + 1] *= 0.4
            val[max(0, r - FORT_SPACING + 1):r + FORT_SPACING, max(0, c - FORT_SPACING + 1):c + FORT_SPACING] = 0

    def _build(self, world):
        """One construction step: the unfinished site closest to the zombies gains a level if there
        are materials for it (so work goes where the front actually is).  Sites are finished one at a time."""
        unfinished = self._unfinished()
        if unfinished:
            near = world.zombie_near(FORT_LOOKAHEAD)
            s = max(unfinished, key=lambda site: near[site["center"]])
            cost = len(s["tiles"]) * FORT_COST
            if self.materials >= cost:
                self.materials -= cost
                s["level"] += 1

    def _maintain(self, world):
        """Standing sites keep their defense; a site whose centre is overrun is lost for good."""
        if not self.sites:
            return
        H, Z, D = world.H, world.Z, world.D
        riot = getattr(world, "riot", None)
        kept = []
        for s in self.sites:
            r, c = s["center"]
            if H[r, c] <= 10 or Z[r, c] > H[r, c] or (not self.collapsed and world.O[r, c] != self.id):
                if self.lost_mask is None:
                    self.lost_mask = np.zeros(H.shape, dtype=bool)
                self.lost_mask[r, c] = True
                self.sites_lost += 1
                continue
            s["tiles"] = [(rr, cc) for (rr, cc) in s["tiles"]
                          if (rr, cc) == (r, c) or (H[rr, cc] > 10 and Z[rr, cc] <= H[rr, cc])]
            if riot is not None and any(riot[rr, cc] for rr, cc in s["tiles"]):
                s["level"] = max(1, s["level"] - 1)          # unrest undermines the garrison
            if self.collapsed:                       # a leaderless garrison: holds a while, then wears down
                age = world.ticks - self.collapsed_at
                if age > REMNANT_HOLD and age % REMNANT_DECAY_EVERY == 0:
                    s["level"] = max(min(s["level"], REMNANT_FLOOR), s["level"] - 1)
                r0, r1, c0, c1 = max(r - 2, 0), r + 3, max(c - 2, 0), c + 3
                patch = Z[r0:r1, c0:c1]
                patch -= (patch * REMNANT_PATROL).astype(np.int32)
            for (rr, cc) in s["tiles"]:
                if D[rr, cc] < s["level"]:
                    D[rr, cc] = s["level"]
            kept.append(s)
        self.sites = kept

    # ----------------------------------------------------------------- other actions
    def _threatened(self, world):
        m = self.m if self.m and self.m.get("tick") == world.ticks else self.measure(world)
        full = np.zeros(world.H.shape, dtype=bool)
        if m.get("threatened") is not None:
            full[m["win"]] = m["threatened"]
        return full

    def _purge(self, world):
        """Hunting parties / air strikes on the densest zombie concentrations in the civilization's
        region - its own land and the ground around it, owned or not.  Costs materials (ammunition);
        with too little, the strike is smaller."""
        if self.materials < PURGE_MIN_MATERIALS:
            return
        Z, H = world.Z.reshape(-1), world.H.reshape(-1)
        owned = (world.O == self.id) & (world.H > 10)
        target = ((box_sum(owned, REGION_REACH) > 0) & (world.Z >= PURGE_MIN_ZOMBIES)).reshape(-1)
        idx = np.flatnonzero(target)
        if idx.size == 0:
            return
        most = max(4, int(PURGE_MAX_TILES * self.size(world)))
        if idx.size > most:
            idx = idx[np.argpartition(-Z[idx], most)[:most]]
        kills = (Z[idx] * min(0.9, PURGE_KILL * (0.2 + 0.8 * self.alert) * (1.0 + 0.9 * getattr(self, "resolve", 0.0)))
                 ).astype(np.int32)                                                      # (needs mobilizing too)
        cost = float(kills.sum()) * PURGE_COST
        scale = min(1.0, self.materials / cost) if cost > 0 else 1.0
        kills = (kills * scale).astype(np.int32)
        self.materials -= float(kills.sum()) * PURGE_COST
        Z[idx] -= kills
        H[idx] -= (np.maximum(H[idx], 0) * PURGE_COLLATERAL * scale).astype(np.int32)
        self.last_strike = int(idx.size)

    def _evacuate(self, world):
        """Threatened tiles send humans to the calmer neighbouring tile (same owner, not ocean)."""
        near = world.zombie_near(NEAR_RADIUS)
        ok = (world.O == self.id) & (is_land(world.T))
        if self.materials <= 0:
            return                                        # no transport
        moved = flow_away(world, self._threatened(world), ok, EVAC_SHARE, near, EVAC_IMPROVEMENT,
                          win=window(world, self.id, 1))
        self.materials = max(0.0, self.materials - moved * EVAC_COST)
