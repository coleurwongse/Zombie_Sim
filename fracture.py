"""How a country comes apart: gradually, region by region, not all at once.

Capital     every government has a seat (the biggest city at the start).  If the capital is overrun or lost, the
            government flees to the best city it still holds (big, safe, well protected, in its largest connected
            piece of land) and loses some morale.  Only if there is nowhere to go does the whole state break up.
Contact     land keeps in touch with the capital through land the government still controls (not overrun), or by
            sea along its own coasts.  A region cut off from the capital for CUTOFF_TICKS goes its own way: big enough
            and it becomes a new state (with its own form of government, see govern.py); too small and it is just
            lost (anarchy) - unless a fortified garrison holds out there, which stays loyal.
Retreat     a government in serious danger pulls back to land it can defend (fortified sites, mountains, ground far
            from the hordes): people in exposed districts are moved toward that core and the emptied land is
            given up.  (Activity RETREAT, see civilization.py.)
Breakdown   when morale finally breaks, the government loses its grip on the provinces but not on its heartland:
            it keeps the region around its capital (if that region can still be held) and rallies there, while the
            other regions go their own way - every region big enough becomes a successor state: a military junta
            where the army holds forts, a republic in safe and fed cities, warlords where it is desperate, clans in
            the countryside.  Only the hopeless places - big, crowded cities that can't be defended with hordes at
            the gates, and scraps too small to organize - fall into anarchy.  If even the heartland can't be held
            (or the capital falls with nowhere to go) the government is gone and every region is on its own.
"""
import numpy as np

from terrain import is_land, is_water

import economy
import govern
from civilization import box_sum, protection, flow_away
from labels import label

FRACTURE_EVERY = 10
CUTOFF_TICKS = 25          # out of contact this long -> the region goes its own way
SEA_REACH = 4              # sea within this many tiles of a government's own land carries its ships
SEA_MAX_Z = 20             # ... unless the water is thick with zombies
REGION_MIN_POP = 1500      # a region needs this many people ...
REGION_MIN_TILES = 15      # ... on at least this many populated tiles to organize into a state
REGION_SPACING = 24        # a collapsing country splits around major cities at least this far apart (tiles) ...
REGION_MAX = 6             # ... into at most this many regions per connected piece of land
REGION_CITY = 0.35         # ... and only around cities at least this big compared with its biggest one
CAPITAL_HELD = 0.3         # the capital counts as lost once less than this share of its city is under control
SAFE_NEAR = 60             # a region with fewer zombies than this within 8 tiles of all its land is "quiet" ...
SAFE_REGION_SHARE = 0.25   # ... and can organize as a state with this share of the usual size
REGION_DANGER = 0.6        # a region with this share of its people facing hordes falls into anarchy instead
CITY_POP = 150
ANARCHY_NEAR = 350         # zombies within 4 tiles that make a crowded city ungovernable ...
ANARCHY_PROT = 4           # ... unless it is protected at least this well
SUCCESSOR_MORALE = 8
RALLY_MORALE = 6           # a government that falls back on its heartland rallies to this morale
CAPITAL_MOVE_MORALE = 1    # morale lost when the government has to flee its capital
CAPITAL_SAFE = 0.7         # a new capital must have at least this share of its city under control
RETREAT_NEAR = 300         # zombies within 8 tiles that make a district 'exposed'
RETREAT_SHARE = 5          # an exposed district sends 1/RETREAT_SHARE of its people toward the core per tick
RETREAT_RANGE = 30
CAPITAL_GRACE = 15         # a new state's capital isn't judged lost in its first this many ticks ...
FRESH_TICKS = 60           # ... and a state that falls this young doesn't break up into more new states
OVEREXTEND_EVERY = 30      # overextension: how often a sprawling country is checked
OVEREXTEND_MIN = 150       # populated tiles a country needs before it can be overextended
OVEREXTEND_GAIN = 1.25     # it has grown past this x its size of ~200 ticks ago ...
OVEREXTEND_FOREIGN = 0.15  # ... or more than this share of its people live on land that was never its own
OVEREXTEND_SIZE = 600      # bigger countries are harder to hold together (x size / this, up to OVEREXTEND_SIZE_CAP)
OVEREXTEND_SIZE_CAP = 4.0
OVEREXTEND_CHANCE = 0.12   # per check, at instability 1
OVEREXTEND_COOLDOWN = 120
OVEREXTEND_GROWN = 1.5     # populated land beyond this x what its country held at the start makes it unstable ...
OVEREXTEND_GROWN_W = 0.8   # ... this much per unit (up to 2 units)
OVEREXTEND_SPRAWL = 15.0   # degrees: foreign land (never its country's) farther than this from the capital (90th
OVEREXTEND_WAR = 0.4       # x the usual chance of a civil war over provinces it was overstretched to hold
OVEREXTEND_FAR = 0.25      # populated land beyond about sim.HOME_REACH of the capital, more than this share of it ...
OVEREXTEND_FAR_W = 2.0     # ... makes a country unstable, this much per unit: its far provinces may go their own way
ABROAD_GROWN = 2.0         # past this x its country's old populated land (or ABROAD_FOREIGN of its people on others'
ABROAD_FOREIGN = 0.65      #   land) a country takes others' land only slowly (sim.ABROAD_SOFT) - and is likelier to split
OVEREXTEND_NEW_MAX = 600   # populated tiles a state founded after the outbreak may grow to on others' land
OVEREXTEND_SPRAWL_W = 0.6  #   percentile) makes it unstable, this much per extra OVEREXTEND_SPRAWL (up to 2)
OVEREXTEND_CONQUEST = 0.4  # land taken from other countries beyond this x its own original land makes it unstable ...
OVEREXTEND_CONQUEST_W = 1.2  # ... this much per unit (Mexico holding half the United States: likely to split)
INDEPENDENCE_EVERY = 30    # overseas land that was never the country's own (taken by an expedition, annexed ...)
INDEPENDENCE_CHANCE = 0.08 # ... declares independence with this chance per check (more when the country is shaky)
INDEPENDENCE_MIN_POP = 400


def controlled(world, civ_id):
    """Land a government still controls: its own, and not overrun (empty land counts).  Full-map mask, worked out
    only around the government's land."""
    win = world.bbox(civ_id, 1) if hasattr(world, "bbox") else (slice(None), slice(None))
    H, Z = world.H[win], world.Z[win]
    out = np.zeros(world.H.shape, dtype=bool)
    out[win] = (world.O[win] == civ_id) & ~((Z > 0) & (Z * economy.INFESTED >= H))
    return out


def _network(world, ctl):
    """Land under control plus the sea lanes along its coasts: what keeps a country in contact."""
    sea = is_water(world.T) & (world.Z < SEA_MAX_Z) & (box_sum(ctl, SEA_REACH) > 0)
    return ctl | sea


def _city_score(world, mask, sl=(slice(None), slice(None))):
    """How good each tile of `mask` is as a seat of government: a big city, safe, defensible.  (`mask` may be cut to
    the window `sl`.)"""
    H = np.maximum(world.H[sl], 0)
    size = box_sum(H, 2) / (25 * 255.0)
    safe = 1.0 - np.clip(world.zombie_near(8)[sl] / 2000.0, 0, 1)
    prot = np.clip(protection(world)[sl], 0, 10) / 10.0
    score = 2.0 * size + 1.5 * safe + 0.5 * prot + 0.3 * (world.T[sl] == 6)
    score = np.where(mask & (H >= 30), score, -np.inf)
    r0, c0 = sl[0].start or 0, sl[1].start or 0                # a famous big city beats a crowded suburb (the
    cities = []                                               # map's named cities count by their real size)
    for n, r, c, p in getattr(world, "cities", []):
        r, c = r - r0, c - c0
        if 0 <= r < score.shape[0] and 0 <= c < score.shape[1] and np.isfinite(score[r, c]):
            cities.append((p, r, c))
    if cities:
        top = max(p for p, _, _ in cities)
        for p, r, c in cities:
            score[r, c] += 1.0 + 1.5 * np.sqrt(p / max(top, 1e-9))
    return score


def pick_capital(world, civ, mask=None):
    """The seat of government: the best city - big (the map's named cities count by their real size), safe,
    defensible."""
    mask = (world.O == civ.id) if mask is None else mask
    score = _city_score(world, mask)
    if not np.isfinite(score).any():
        return None
    r, c = np.unravel_index(int(np.argmax(score)), score.shape)
    return int(r), int(c)


def _place(world, rc):
    """The named city nearest tile rc (one at the tile itself first) - for the log."""
    cities = getattr(world, "cities", None)
    if not cities:
        return f"({rc[0]},{rc[1]})"
    arr = getattr(world, "_city_rc", None)
    if arr is None or arr[0] is not cities:
        arr = world._city_rc = (cities, np.array([[r, c] for _, r, c, _ in cities], dtype=np.float64))
    d = (arr[1][:, 0] - rc[0]) ** 2 + (arr[1][:, 1] - rc[1]) ** 2
    return cities[int(np.argmin(d))][0]


def _point(world, rc):
    m = np.zeros(world.H.shape, dtype=bool)
    m[rc] = True
    return m


def _held_share(world, ctl, r, c, civ_id):
    """Share of the people in the government's part of the city around (r, c) (5x5 tiles; land that is or was its own -
    a capital by a border doesn't count the neighbours' suburbs) who live on land it still controls."""
    r0, r1, c0, c1 = max(r - 2, 0), r + 3, max(c - 2, 0), c + 3
    ours = (world.O[r0:r1, c0:c1] == civ_id) | (world.last_owner[r0:r1, c0:c1] == civ_id)
    H = np.where(ours, np.maximum(world.H[r0:r1, c0:c1], 0), 0)
    total = H.sum()
    return float(H[ctl[r0:r1, c0:c1]].sum()) / total if total > 0 else 0.0


def _capital_ok(world, civ, ctl):
    """The seat of government stands while the government still controls a fair part of the city around it."""
    if civ.capital is None:
        return False
    r, c = civ.capital
    return bool(ctl[r, c]) and world.H[r, c] > 10 and _held_share(world, ctl, r, c, civ.id) >= CAPITAL_HELD


def relocate(world, civ, ctl):
    """The capital is lost: move the government to the best city in its largest connected piece of land.  (Worked
    out in the window around its land: the sea lanes reach SEA_REACH tiles off its coasts at most.)"""
    sl = world.bbox(civ.id, SEA_REACH + 3)
    r0, c0 = sl[0].start or 0, sl[1].start or 0
    ctl_w = ctl[sl]
    net = ctl_w | (is_water(world.T[sl]) & (world.Z[sl] < SEA_MAX_Z) & (box_sum(ctl_w, SEA_REACH) > 0))
    lab, n = label(net)
    if n == 0:
        return False
    Hw = np.maximum(world.H[sl], 0)
    pops = np.bincount(lab.reshape(-1), weights=(Hw * ctl_w).reshape(-1), minlength=n + 1)
    pops[0] = 0
    best = int(np.argmax(pops))
    if pops[best] < REGION_MIN_POP / 2:
        return False
    old = civ.capital
    cand = ctl_w & (lab == best)
    if old is not None:
        cand[max(old[0] - 2 - r0, 0):max(old[0] + 3 - r0, 0), max(old[1] - 2 - c0, 0):max(old[1] + 3 - c0, 0)] = False
    score = _city_score(world, cand, sl)
    rc = None
    for _ in range(8):                                  # the best city that is really under control
        if not np.isfinite(score).any():
            break
        r, c = np.unravel_index(int(np.argmax(score)), score.shape)
        score[r, c] = -np.inf
        r, c = r + r0, c + c0
        if _held_share(world, ctl, r, c, civ.id) >= CAPITAL_SAFE:
            rc = (int(r), int(c))
            break
    if rc is None:
        return False
    civ.capital = rc
    civ.morale = max(0, civ.morale - CAPITAL_MOVE_MORALE)
    if old is not None and _place(world, old) != _place(world, rc):
        world.note(f"{civ.name} loses its capital {_place(world, old)}; the government moves to {_place(world, rc)}")
    return True


def _new_state(world, parent, region, gov=None, why=""):
    """Turn `region` (mask) of `parent`'s land into a new state.  Returns it (or None if no room for more)."""
    from civilization import Civilization       # noqa: F401  (world.add_civ builds it)
    pop = float(np.maximum(world.H[region], 0).sum())
    total = max(1.0, float(parent.m.get("pop", 0)) if parent.m else 1.0)
    share = min(1.0, pop / max(total, pop))
    sites_in = [s for s in parent.sites if region[s["center"]]]
    gov = gov or govern.choose(world, region, parent, sites=len(sites_in))
    civ = world.add_civ(morale=SUCCESSOR_MORALE)
    if civ is None:
        return None
    civ.gov = gov
    civ.successor, civ.founded, civ.split_from = True, world.ticks, parent.id
    civ.root = parent.root
    civ.capital = pick_capital(world, civ, region)
    civ.name = govern.state_name(world, gov, region, civ.id, parent, near=civ.capital)
    world.O[region] = civ.id
    world.last_owner[region] = civ.id
    civ.military = parent.military * (0.8 if gov == "junta" else 0.6)
    civ.alert = parent.alert
    civ.materials = max(20.0, parent.materials * share)
    parent.materials = max(0.0, parent.materials - civ.materials * 0.8)
    use = pop * economy.FOOD_PER_PERSON
    civ.food = max(use * 10, (parent.food or 0.0) * share)
    if parent.food is not None:
        parent.food = max(0.0, parent.food - civ.food * 0.8)
    civ.sites = sites_in
    parent.sites = [s for s in parent.sites if not region[s["center"]]]
    world.note(f"{civ.name} ({govern.LABEL[gov] or gov}) breaks away from {parent.name}" + (f": {why}" if why else ""))
    return civ


def _ungovernable(world, mask):
    """Crowded cities that can't be held: hordes at the gates and nothing to stop them."""
    H, T = world.H, world.T
    crowded = (T == 6) | (T == 7) | (H >= CITY_POP)
    return mask & crowded & (world.zombie_near(4) >= ANARCHY_NEAR) & (protection(world) < ANARCHY_PROT)


#                     deep grass forest mount desert ice  urban suburb shallow highl tundra wetl  rainf
BARRIER = np.array([  6.0, 1.0,  1.5,   9.0,  4.0,  5.0,  1.0,  1.0,  6.0,    2.5,  1.6,   3.5,  2.2], dtype=np.float32)
BARRIER_WATER = 1.5        # a tile on a river, lake or the coast costs this much more to cross (rivers make borders)
BARRIER_NOISE = 0.6        # and the ground's cost wobbles by up to exp(+-1.5 x this) over a large scale ...
BARRIER_FINE = 1.1         # ... and exp(+-this) tile to tile: ragged borders, never straight lines or arcs


def _ground_cost(world, win):
    """Cost of crossing each tile of window `win` when drawing a border: mountains, deserts, marsh and water are hard
    going, so the land falls apart along them - and some noise, so a border is never a straight line or an arc."""
    from civilization import jag
    from front import line_terrain
    T = np.clip(world.T[win], 0, len(BARRIER) - 1)
    cost = BARRIER[T]
    wet = line_terrain(world)[win] - 1.0 - 0.9 * (1.0 - world.statics.move.reshape(world.H.shape)[win])
    cost = cost + BARRIER_WATER * (wet > 0.15)
    fine = getattr(world, "_border_fine", None)
    if fine is None or fine.shape != world.H.shape:                 # (fine wiggles, fixed for the map)
        seed = int(getattr(world, "seed", 0) or 0) if getattr(world, "stochastic", False) else 0
        f = np.random.default_rng(seed + 99).random(world.H.shape).astype(np.float32)
        for _ in range(2):
            f = (f + np.roll(f, 1, 0) + np.roll(f, -1, 0) + np.roll(f, 1, 1) + np.roll(f, -1, 1)) / 5.0
        fine = world._border_fine = np.clip((f - f.mean()) / (2.5 * f.std() + 1e-9), -1.0, 1.0)
    return cost * np.exp(BARRIER_NOISE * jag(world, win) + BARRIER_FINE * fine[win])


def split_by_ground(world, part, seeds):
    """Share out the tiles of `part` (mask) between `seeds` [(r, c), ...]: each tile goes to the seed it is cheapest to
    reach over the ground (_ground_cost) - so regions meet along mountains, deserts and rivers, in ragged lines.
    Returns an int array, -1 outside `part`."""
    out = np.full(part.shape, -1, dtype=np.int32)
    rr, cc = np.nonzero(part)
    if rr.size == 0 or not seeds:
        return out
    r0, r1, c0, c1 = rr.min(), rr.max() + 1, cc.min(), cc.max() + 1
    win = (slice(r0, r1), slice(c0, c1))
    inside = part[win]
    cost = np.where(inside, _ground_cost(world, win), np.inf).astype(np.float64)
    dist = np.full(inside.shape, np.inf)
    lab = np.full(inside.shape, -1, dtype=np.int32)
    for i, (r, c) in enumerate(seeds):
        if r0 <= r < r1 and c0 <= c < c1 and inside[r - r0, c - c0]:
            dist[r - r0, c - c0], lab[r - r0, c - c0] = 0.0, i
    R, C = inside.shape
    for _ in range(4 * (R + C)):                        # relax until nothing improves (in place: converges fast)
        changed = False
        for dr, dc in ((0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            ts = (slice(max(dr, 0), R + min(dr, 0)), slice(max(dc, 0), C + min(dc, 0)))
            fs = (slice(max(-dr, 0), R + min(-dr, 0)), slice(max(-dc, 0), C + min(-dc, 0)))
            step = 1.4142 if dr and dc else 1.0
            cand = dist[fs] + 0.5 * (cost[fs] + cost[ts]) * step
            better = cand < dist[ts] - 1e-9
            if better.any():
                dist[ts][better] = cand[better]
                lab[ts][better] = lab[fs][better]
                changed = True
        if not changed:
            break
    lost = inside & (lab < 0)                           # (islands nothing reaches over land: the nearest seed)
    if lost.any():
        lr, lc = np.nonzero(lost)
        d = np.stack([(lr + r0 - r) ** 2 + (lc + c0 - c) ** 2 for r, c in seeds])
        lab[lr, lc] = d.argmin(axis=0)
    out[win] = np.where(inside, lab, -1)
    return out


def _centers(world, part):
    """The main cities of `part` a breaking country splits around: the densest places, at least REGION_SPACING apart
    and at least REGION_CITY of the biggest (at most REGION_MAX)."""
    cols = world.H.shape[1]
    dens = np.where(part, box_sum(np.maximum(world.H, 0), 3), -1).astype(np.float64)
    top = dens.max()
    centers = []
    while len(centers) < REGION_MAX:
        idx = int(np.argmax(dens))
        r, c = divmod(idx, cols)
        if dens[r, c] <= 0 or dens[r, c] < REGION_CITY * top:
            break
        centers.append((r, c))
        dens[max(0, r - REGION_SPACING):r + REGION_SPACING + 1, max(0, c - REGION_SPACING):c + REGION_SPACING + 1] = -1
    return centers


def _regions(world, mask):
    """Split `mask` into regions: connected pieces (by land or coastal sea), big pieces around their main cities."""
    net = _network(world, mask)
    lab, n = label(net)
    lab = np.where(mask, lab, 0)
    out = []
    for k in range(1, n + 1):
        part = lab == k
        tiles = int(part.sum())
        if tiles == 0:
            continue
        if tiles <= REGION_SPACING ** 2:
            out.append(part)
            continue
        centers = _centers(world, part)
        if len(centers) <= 1:
            out.append(part)
            continue
        near = split_by_ground(world, part, centers)    # (along mountains, deserts and rivers - not straight lines)
        for i in range(len(centers)):
            sub = part & (near == i)
            if sub.any():
                out.append(sub)
    return out


def _safe(world, region):
    """No horde anywhere near the region: a quiet province (Alaska when the lower 48 fall)."""
    return int(world.zombie_near(8)[region].max(initial=0)) < SAFE_NEAR


def _viable(world, region):
    """Can the region organize into a state?  A quiet one (no horde near it) can be much smaller - its people don't
    give up on government just because the capital far away fell."""
    H = world.H
    pop = int(np.maximum(H[region], 0).sum())
    near = world.zombie_near(4)
    danger = float(np.maximum(H, 0)[region & (near >= 300)].sum()) / max(pop, 1)
    small = SAFE_REGION_SHARE if _safe(world, region) else 1.0
    return (pop >= REGION_MIN_POP * small and int((region & (H > 10)).sum()) >= max(3, REGION_MIN_TILES * small)
            and danger < REGION_DANGER)


def fracture_all(world, civ, why, keep_core=True):
    """The government loses its grip.  It keeps the heartland around its capital if that can be held (keep_core) and
    rallies there; every other region becomes a state of its own where it can; the rest is anarchy.  Returns True if
    the government survives (on its heartland)."""
    from civilization import IGNORE
    H, O = world.H, world.O
    mine = O == civ.id
    ctl = controlled(world, civ.id)
    lost = _ungovernable(world, mine)
    O[mine & ~ctl] = 0                                   # overrun land is nobody's
    O[lost] = 0
    keep = ctl & ~lost
    regions = _regions(world, keep)
    core = None
    if keep_core and civ.capital is not None:
        r, c = civ.capital
        for region in regions:
            if region[r, c] and _viable(world, region):
                core = region
                break
    born = []
    fresh = civ.successor and world.ticks - civ.founded < FRESH_TICKS     # (a state just born that falls at once
    for region in regions:                                              #  doesn't break into more new states)
        if region is core:
            continue
        if _viable(world, region) and (not fresh or _safe(world, region)):
            new = _new_state(world, civ, region)
            if new is not None:
                born.append(new)
                continue
        O[region] = 0
    split = f"{', '.join(c.name for c in born)} break{'s' if len(born) == 1 else ''} away" if born else ""
    anarchy = f"{int(lost.sum())} city districts fall into anarchy" if lost.any() else ""
    if core is not None:
        civ.morale = max(civ.morale, RALLY_MORALE)
        civ.active = {a for a in civ.active if a == "quarantine"}         # shut borders stay shut through the crisis
        civ.bases = []
        civ._pressure = 0
        world.note(f"{civ.name} loses its grip on the provinces ({why}) and falls back on its heartland"
                   + "".join("; " + x for x in (split, anarchy) if x))
        import war
        for new in born:                                  # the heartland may not let them go
            war.maybe_civil_war(world, civ, new)
        return True
    civ.collapsed = True
    civ.collapsed_at = world.ticks
    O[O == civ.id] = 0                                   # (bits too small to be a region of their own: nobody's)
    civ.active = set()
    civ.action = IGNORE
    civ.bases = []
    civ.military = min(civ.military, 0.4)
    civ.remnant = bool(civ.sites)
    world.note(f"{civ.name}'s government falls ({why})" + (" - " + split if split else " - nothing is left to organize")
               + ("; " + anarchy if anarchy else ""))
    return False


def _secede(world, civ, ctl, lab, capital_label, age, sl):
    """Regions out of contact with the capital for too long go their own way.  (Everything here is cut to the
    window `sl` around the government's land.)"""
    H = world.H[sl]
    r0, c0 = sl[0].start or 0, sl[1].start or 0
    flat = lab.reshape(-1)
    n = int(lab.max())
    if n <= 1:
        return
    ages = np.bincount(flat, weights=age.reshape(-1), minlength=n + 1)
    sizes = np.bincount(flat, minlength=n + 1)
    for k in range(1, n + 1):
        if k == capital_label or sizes[k] == 0 or ages[k] / sizes[k] < CUTOFF_TICKS:
            continue
        part = (lab == k) & ctl
        if not part.any():
            continue

        def inside(rc):
            r, c = rc[0] - r0, rc[1] - c0
            return 0 <= r < part.shape[0] and 0 <= c < part.shape[1] and part[r, c]
        if any(inside(bs["center"]) for bs in civ.bases):
            continue                                    # an offensive base and its zone are supplied by the army
        forts = any(inside(s["center"]) for s in civ.sites)
        if forts and ages[k] / sizes[k] < 4 * CUTOFF_TICKS:
            continue                                    # garrisons hold out loyally for a long time
        pop = int(np.maximum(H[part], 0).sum())
        populated = int((part & (H > 10)).sum())
        region = np.zeros(world.H.shape, dtype=bool)
        region[sl] = part
        small = SAFE_REGION_SHARE if _safe(world, region) else 1.0     # (a quiet region manages on its own)
        if pop >= REGION_MIN_POP * small and populated >= max(3, REGION_MIN_TILES * small):
            new = _new_state(world, civ, region, why="cut off from the capital")
            if new is not None:
                import war
                war.maybe_civil_war(world, civ, new)
        elif forts:
            continue                                    # a besieged garrison holds out, loyal to the government
        else:
            world.O[sl][part] = 0
            if pop >= 100:
                r, c = np.argwhere(part)[0]
                world.note(f"{civ.name} loses contact with {world.people(pop)} people near "
                           f"{_place(world, (int(r) + r0, int(c) + c0))}")


def step(world):
    if world.ticks % FRACTURE_EVERY:
        return
    age = getattr(world, "cut_age", None)
    if age is None or age.shape != world.H.shape:
        age = world.cut_age = np.zeros(world.H.shape, dtype=np.int32)
    for civ in list(world.civs):
        if not civ.ai or civ.collapsed or civ.is_anarchy:
            continue
        near = world.bbox(civ.id, 2)
        if civ.capital is not None and not world.Z[near].any() and not getattr(civ, "_cut", False):
            continue                                    # no zombies anywhere near: nothing can have cut it apart
        ctl = controlled(world, civ.id)
        if not ctl.any():
            continue
        if civ.capital is None:
            civ.capital = pick_capital(world, civ)
            if civ.capital is None:
                continue                                # (nowhere to govern from yet)
        if civ.successor and world.ticks - civ.founded < CAPITAL_GRACE:
            pass                                        # (a new state gets a few days to set up its seat)
        elif not _capital_ok(world, civ, ctl) and not relocate(world, civ, ctl):
            fracture_all(world, civ, "its capital is lost", keep_core=False)
            continue
        sl = world.bbox(civ.id, 1)
        mine_c = world.O[sl] == civ.id
        ctl_c = ctl[sl]
        lab_c, n = label(ctl_c)
        age_c = age[sl]
        if n > 1:
            lab_c = _join_by_sea(world, sl, lab_c, n)
            n = len(np.unique(lab_c[lab_c > 0]))
        if n <= 1:
            age_c[mine_c] = 0
            civ._cut = False
            continue
        cr, cc = civ.capital[0] - (sl[0].start or 0), civ.capital[1] - (sl[1].start or 0)
        cap = int(lab_c[cr, cc]) if 0 <= cr < lab_c.shape[0] and 0 <= cc < lab_c.shape[1] else 0
        cut_c = ctl_c & (lab_c != cap)
        age_c[mine_c & ~cut_c] = 0
        age_c[cut_c] += FRACTURE_EVERY
        civ._cut = bool(cut_c.any())
        _secede(world, civ, ctl_c, lab_c, cap, np.where(ctl_c, age_c, 0), sl)


def _join_by_sea(world, sl, lab, n):
    """Pieces of a country with coasts on the same sea stay in touch (its ships reach them): relabel such pieces as
    one.  (Water thick with zombies doesn't break this - a navy can still sail through.)"""
    import boats
    body = boats.coasts(world).body[sl]
    on = (lab > 0) & (body > 0)
    if not on.any():
        return lab
    pairs = np.unique(np.stack([lab[on], body[on]], axis=1), axis=0)
    parent = list(range(n + 1))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    first = {}
    for comp, b in pairs:
        comp, b = int(comp), int(b)
        if b in first:
            ra, rb = find(first[b]), find(comp)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)
        else:
            first[b] = comp
    roots = np.array([find(i) for i in range(n + 1)], dtype=np.int32)
    return roots[lab]


def _bbox(mask, margin):
    rows = np.flatnonzero(mask.any(axis=1))
    cols = np.flatnonzero(mask.any(axis=0))
    if rows.size == 0:
        return slice(0, 0), slice(0, 0)
    return (slice(max(0, rows[0] - margin), rows[-1] + margin + 1),
            slice(max(0, cols[0] - margin), cols[-1] + margin + 1))


# ------------------------------------------------------------------------------------------------- retreat
def retreat(world, civ):
    """Pull back to defensible land: people in exposed districts move toward the core; emptied land is given up."""
    from people import _distance
    win = _bbox(world.O == civ.id, 1)
    H, O, T = world.H[win], world.O[win], world.T[win]
    mine = O == civ.id
    near8 = world.zombie_near(8)[win]
    prot = protection(world)[win]
    core = mine & (H > 10) & ((prot >= 5) | civ.fort_mask(world.H.shape)[win] | (near8 < 40))
    exposed = mine & (H > 10) & ~core & (near8 >= RETREAT_NEAR) & (prot < 4)
    full = np.zeros(world.H.shape, dtype=bool)
    full[win] = exposed
    civ.retreat_mask = full
    if not exposed.any() or not core.any():
        return 0
    land = mine & is_land(T)
    dist = _distance(world, land, core, RETREAT_RANGE)
    moved = flow_away(world, exposed & (dist < 10 ** 6), land & (dist < 10 ** 6), RETREAT_SHARE, dist, 1.0,
                      min_move=1, win=win)
    given_up = mine & (H <= 10) & (near8 >= RETREAT_NEAR) & ~core
    O[given_up] = 0
    return moved


def sim_home_reach():
    import sim
    return sim.HOME_REACH


def overextension(world):
    """A country that has grown fast - retaking a lot of land, or land that was never its own - may not hold together:
    the newly held provinces (or, failing that, the half furthest from the capital) break away as a state of their own.
    Bigger, more demoralized countries split more readily."""
    if world.ticks % OVEREXTEND_EVERY:
        return
    import war
    for civ in list(world.civs):
        if not civ.ai or civ.collapsed or civ.is_anarchy or not civ.m or civ.capital is None:
            continue
        n = int(civ.m.get("n", 0))
        hist = list(getattr(civ, "long_hist", ()))
        if n < OVEREXTEND_MIN or len(hist) < 10:
            civ._abroad_ok = True
            continue
        win = world.bbox(civ.id, 0)
        mine = (world.O[win] == civ.id) & (world.H[win] > 10)
        o0 = world.O0[win]
        foreign = mine & (o0 != civ.id) & (o0 != civ.root)
        pop = np.maximum(world.H[win], 0)
        f_share = float(pop[foreign].sum()) / max(1.0, float(pop[mine].sum()))
        gain = n / max(1.0, float(min(hist)))
        own0 = getattr(civ, "_own0", None)
        if own0 is None:                                # (its own original land: counted once)
            own0 = civ._own0 = max(1, int(((world.O0 == civ.id) | (world.O0 == civ.root)).sum()))
        conquest = (float((foreign & (o0 > 0)).sum()) / own0          # conquered land vs its own original land
                    if own0 >= 50 else 0.0)                         # (states founded later have none to compare)
        own0_pop = getattr(civ, "_own0_pop", None)
        if own0_pop is None:
            own0_pop = civ._own0_pop = int((((world.O0 == civ.id) | (world.O0 == civ.root)) & (world.H0 > 10)).sum())
        grown = n / own0_pop if own0_pop >= 50 else 0.0                # (Paris ruling half of Europe)
        sprawl = 0.0
        if foreign.any():                                               # (and ruling it from far away)
            rr, cc = np.nonzero(foreign)
            dc = np.abs(cc + win[1].start - civ.capital[1])
            if world.wrap:
                dc = np.minimum(dc, world.cols - dc)
            res = float(world.meta.get("res", 0.5))
            sprawl = float(np.percentile(np.hypot(rr + win[0].start - civ.capital[0], dc), 90)) * res
        # an overextended country takes no more of other countries' land (sim.may_claim) - a state founded later
        # (settlers, survivors: no country of its own to compare with) once it is as big as a merger may make one
        civ._abroad_ok = (grown <= ABROAD_GROWN and f_share <= ABROAD_FOREIGN if own0_pop >= 50
                          else n <= OVEREXTEND_NEW_MAX)
        if world.ticks - getattr(civ, "_overext", -10 ** 6) < OVEREXTEND_COOLDOWN:
            continue
        # (land far from the capital - past the reach it can claim at home: it has grown up to that edge)
        #  (a country's own land from the start doesn't count: Russia is big, not overstretched)
        mr, mc = np.nonzero(mine)
        dcap = np.abs(mc + win[1].start - civ.capital[1])
        if world.wrap:
            dcap = np.minimum(dcap, world.cols - dcap)
        res_ = float(world.meta.get("res", 0.5))
        far_ = (np.hypot(mr + win[0].start - civ.capital[0], dcap) * res_ > 0.8 * sim_home_reach()) & (o0[mr, mc] != civ.id)
        beyond = float(far_.mean()) if far_.size else 0.0
        instab_far = OVEREXTEND_FAR_W * max(0.0, beyond - OVEREXTEND_FAR)
        instab = (1.5 * max(0.0, gain - OVEREXTEND_GAIN) * min(1.0, f_share / 0.3)      # (regrowing at home is fine)
                  + instab_far
                  + 2.5 * max(0.0, f_share - OVEREXTEND_FOREIGN)
                  + OVEREXTEND_CONQUEST_W * min(2.0, max(0.0, conquest - OVEREXTEND_CONQUEST))
                  + OVEREXTEND_GROWN_W * min(2.0, max(0.0, grown - OVEREXTEND_GROWN))
                  + OVEREXTEND_SPRAWL_W * min(2.0, max(0.0, sprawl / OVEREXTEND_SPRAWL - 1.0)))
        if instab <= 0:
            continue
        size = min(OVEREXTEND_SIZE_CAP, max(0.3, n / OVEREXTEND_SIZE))
        mood = max(0.5, 1.0 + (8 - civ.morale) / 8.0)
        if world.pyrng.random() >= OVEREXTEND_CHANCE * instab * size * mood * govern.mod(civ, "morale_loss"):
            continue
        civ._overext = world.ticks
        # what breaks away: the land that was never its own, if that is a big part of it; else the far side
        full = np.zeros(world.H.shape, dtype=bool)
        full[win] = (world.O[win] == civ.id)
        conquered = foreign & (o0 > 0)
        if conquest >= OVEREXTEND_CONQUEST and conquered.any():
            # the biggest conquered country's old land rises up along its old borders
            ids, cnt = np.unique(o0[conquered], return_counts=True)
            old = int(ids[np.argmax(cnt)])
            part = np.zeros(world.H.shape, dtype=bool)
            part[win] = full[win] & (o0 == old)
            why = f"the conquered {world.civs[old].name.split(' (')[0]} won't be ruled from abroad"
        elif f_share >= 0.3:
            part = np.zeros(world.H.shape, dtype=bool)
            part[win] = full[win] & (o0 != civ.id) & (o0 != civ.root)
            why = "it never belonged to them, and the government can't hold it"
        else:
            # the far side: the country shared out between its capital and its other big cities along the lie of the
            # land (split_by_ground); the region of a big city far from the capital breaks away
            seeds = [tuple(civ.capital)] + [x for x in _centers(world, full) if
                                            abs(x[0] - civ.capital[0]) + abs(x[1] - civ.capital[1]) > REGION_SPACING]
            if len(seeds) < 2:
                continue
            share = split_by_ground(world, full, seeds)
            best, part = -1.0, None
            for i in range(1, len(seeds)):
                sub = share == i
                size = int(sub.sum())
                dc = abs(seeds[i][1] - civ.capital[1])
                if world.wrap:
                    dc = min(dc, world.cols - dc)
                far_ = np.hypot(seeds[i][0] - civ.capital[0], dc) * np.sqrt(size)
                if size and far_ > best:
                    best, part = far_, sub
            if part is None:
                continue
            why = "the realm has grown too big to govern from one capital"
        lab, k = label(part)
        if k == 0:
            continue
        sizes = np.bincount(lab.ravel(), minlength=k + 1)
        sizes[0] = 0
        if civ.capital is not None and lab[civ.capital]:
            sizes[lab[civ.capital]] = 0
        if sizes.max() == 0:
            continue                                    # (only the capital's own piece: nothing to break away)
        region = (lab == int(np.argmax(sizes))) & full
        if (int(np.maximum(world.H[region], 0).sum()) < REGION_MIN_POP / 2
                or int((region & (world.H > 10)).sum()) < REGION_MIN_TILES):
            continue
        new = _new_state(world, civ, region, why=why)
        if new is not None:
            war.maybe_civil_war(world, civ, new, "it won't let the provinces go", chance=OVEREXTEND_WAR)


def independence(world):
    """Overseas possessions that were never part of the country (land taken back by an expedition, or annexed across
    the sea) have a good chance of declaring independence - more so when the country at home is demoralized.  Land
    that was the country's own from the start (French Guiana, Alaska) doesn't."""
    if world.ticks % INDEPENDENCE_EVERY:
        return
    S = world.statics
    for civ in list(world.civs):
        if not civ.ai or civ.collapsed or civ.is_anarchy or civ.capital is None:
            continue
        win = world.bbox(civ.id, 0)
        mine = world.O[win] == civ.id
        o0 = world.O0[win]
        away = mine & (S.landmass[win] != S.landmass[civ.capital]) & (o0 != civ.id) & (o0 != civ.root)
        if not away.any():
            continue
        lab, k = label(away)
        bases = {b["center"] for b in civ.bases}
        for j in range(1, k + 1):
            part_w = lab == j
            pop = int(np.maximum(world.H[win][part_w], 0).sum())
            if pop < INDEPENDENCE_MIN_POP or int((part_w & (world.H[win] > 10)).sum()) < REGION_MIN_TILES // 2:
                continue
            region = np.zeros(world.H.shape, dtype=bool)
            region[win] = part_w
            if any(region[b] for b in bases):
                continue                                # (the army is still fighting there)
            mood = 1.0 + max(0.0, (7 - civ.morale) / 4.0)
            if world.pyrng.random() < INDEPENDENCE_CHANCE * mood:
                new = _new_state(world, civ, region, why="the overseas territory declares independence")
                if new is not None:
                    import war
                    war.maybe_civil_war(world, civ, new, "it won't give up its overseas territory",
                                        chance=OVEREXTEND_WAR)
