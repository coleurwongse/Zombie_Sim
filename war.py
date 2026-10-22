"""Wars between nations - and within them.

Declaration  every CHECK_EVERY ticks a nation that is short of food or materials may attack an
             adjacent nation that is better off (more likely the scarcer it is and the more aggressive
             its government).  Wars can also be there from the start (meta.json "wars", World(wars=...)).
             Old rivals (meta.json "rivals": India and Pakistan, the two Koreas ...) go to war more readily -
             RIVAL_CHANCE, more when either is short of things - border or no border.
             Nobody starts a war while zombies are at their gates.
Alliances    (meta.json "alliances": {"Free Peoples": [ids], ...}) members of one alliance never go to war with each
             other - breakaway states and free cities belong to their old country's alliance; a civil war within
             one country can still happen.
Civil war    (world.civil_wars, on by default) a region that breaks away may not be let go: when it secedes the old
             government may fight to take it back at once (CIVIL_AT_SPLIT, more likely for juntas and warlords),
             and a recovered government may later go to war to reunite the country (CIVIL_LATER).  Civil wars are
             fought harder (ground changes hands more easily), last longer, are rarely settled by armistice, and
             only give way to the zombies when things are truly desperate.  They end when one side is too weak to
             go on - it is absorbed (the country reunited by force) - or after a long stalemate (independence).
Fighting     every FIGHT_EVERY ticks: where the two touch, people die on both sides of the border (more for the
             weaker side, where defense is low, less on rough ground), materials are burned, armies shrink, and a
             clearly stronger side captures weakly defended border tiles (rough ground less easily).  Where they
             don't touch (the United States and Iran), it's a war of air and missile strikes on each other's cities
             every STRIKE_EVERY ticks - and strikes behind the front in a border war too.  Raids on towns, partisans
             in taken rough country and sea landings: warfare.py.  A long war wears morale down.
Peace        after PEACE_MIN ticks either side may sue for peace (more likely as the war drags on);
             a zombie emergency or a collapse ends it at once.  A peace holds: the two don't go to war again for
             PEACE_HOLDS days (TRUCE_HOLDS after a truce against the zombies) - wars don't flicker on and off.
"""
import numpy as np

from terrain import is_land

import govern
import warfare
from civilization import box_sum

CHECK_EVERY = 10
FIGHT_EVERY = 2
MIN_BORDER = 4            # border tiles needed for two nations to be in contact
MIN_POP = 300
SCARCE_FOOD_TICKS = 25    # food for fewer ticks than this counts as scarce
SCARCE_MATERIALS = 8.0
SCARCE_AT = 0.2
DECLARE_BASE = 0.25       # per check, times scarcity and aggression
CRISIS = 0.6              # danger at which the zombies are the only war that matters ...
CIVIL_CRISIS = 0.85       # ... (for a civil war: this desperate)
PEACE_MIN = 40
PEACE_CHANCE = 0.07       # per check once PEACE_MIN has passed (plus a bit more every tick of war)
WAR_MAX = 220
CIVIL_WAR_MAX = 600       # a civil war that drags on this long ends in independence
FIGHT_LOSS = 0.04         # share of border-tile people lost per round at an even match
FIGHT_COST = 0.03         # materials per person lost
FIGHT_ARMY = 0.00008      # army strength lost per person lost
CAPTURE_RATIO = 1.4       # strength ratio needed to take ground ...
CIVIL_CAPTURE_RATIO = 1.15   # ... in a civil war
CAPTURE_CHANCE = 0.25
WEARY_EVERY = 12          # ticks of war per point of morale lost ...
WEARY_FLOOR = 5           # ... down to this (losing battles, riots and the zombies can do the rest)
CIVIL_AT_SPLIT = 0.35     # chance the old government fights a region that breaks away (x its aggression)
CIVIL_LATER = 0.04        # per check: a recovered government goes to war to reunite the country
CIVIL_ABSORB = 0.15       # a side with less than this share of the other's people is absorbed
STRIKE_EVERY = 6          # distant wars: ticks between strikes
STRIKE_KILL = 0.06        # share of the people in a 3x3 city block killed by a strike
STRIKE_COST = 4.0         # materials per strike
STRIKE_MIN_ARMY = 0.25
STRIKE_RANGE = 70         # tiles between capitals a strike can reach ...
GLOBAL_REACH = 0.9        # ... unless the attacker's army is this strong (carriers, bombers, missiles)
RIVAL_CHANCE = 0.01       # per check: old rivals go to war (x (1 + 3 x scarcity) x aggression)
ROUGH_SAVES = 0.4          # defenders on rough ground (warfare.roughness) lose this much fewer ...
ROUGH_HOLDS = 0.6          # ... and their ground is this much harder to take
DISPUTE_CHANCE = 0.004     # per check, per pair of touching countries at peace with the zombies (x both aggressions):
                           # a border dispute comes to blows
DISTANT_WEARY_EVERY = 45
PEACE_HOLDS = 365          # days after a peace before the same two go to war again ...
TRUCE_HOLDS = 240          # ... after a truce against the zombies  # a war fought far away wears morale down much more slowly


def key(a, b):
    return frozenset((a, b))


def scarcity(civ):
    """0..1: how short of food and materials a nation is."""
    food = 0.0
    if civ.famine:
        food = 1.0
    elif civ.food is not None and civ.food_use > 0:
        food = float(np.clip(1.0 - civ.food / (SCARCE_FOOD_TICKS * civ.food_use), 0, 1))
    mats = float(np.clip(1.0 - civ.materials / SCARCE_MATERIALS, 0, 1))
    return 0.65 * food + 0.35 * mats


def _danger(civ):
    return civ.danger(civ.m)[0] if civ.m and civ.m.get("n") else 0.0


def alliance(world, civ_id):
    """The alliance a government belongs to (through the country it descends from), or None."""
    table = getattr(world, "alliance_of", None)
    if not table:
        return None
    c = world.civs[civ_id]
    return table.get(c.id, table.get(c.root))


def allied(world, a, b):
    """Members of the same alliance (different countries), or bound by a pact (globalaffairs.py) - they don't fight
    each other."""
    import globalaffairs
    if globalaffairs.in_pact(world, a, b):
        return True
    if world.civs[a].root == world.civs[b].root:
        return False
    x = alliance(world, a)
    return x is not None and x == alliance(world, b)


def at_peace_until(world, a, b):
    return world.__dict__.setdefault("truces", {}).get(key(a, b), -1)


def declare(world, a, b, reason="", quiet=False, civil=False, join=True, truce_ok=False):
    k = key(a, b)
    if k in world.wars or allied(world, a, b):
        return
    if not truce_ok and world.ticks < at_peace_until(world, a, b):
        return                                            # (a peace holds for a while: PEACE_HOLDS)
    crisis = CIVIL_CRISIS if civil else CRISIS
    if world.ticks > 0 and (_danger(world.civs[a]) > crisis or _danger(world.civs[b]) > crisis):
        return                                            # (it would only end in a truce against the zombies next day)
    world.wars[k] = dict(a=a, b=b, start=world.ticks, ticks=0, quiet=0, civil=civil)
    what = "CIVIL WAR" if civil else "WAR"
    verb = "fights" if civil else "attacks"
    world.war_note(f"{what}: {world.civs[a].name} {verb} {world.civs[b].name}" + (f" ({reason})" if reason else ""))
    if join and not civil:                                # (its pact partners stand by it)
        import globalaffairs
        for pk in list(globalaffairs.pacts(world)):
            if b in pk:
                p = world.civs[next(iter(pk - {b}))]
                if (p.ai and not p.collapsed and p.id != a and not at_war(world, p.id) and _danger(p) < 0.35
                        and not allied(world, p.id, a)):
                    world.war_note(f"{p.name} stands by its pact with {world.civs[b].name}")
                    declare(world, p.id, a, "its pact", join=False)


def end(world, k, why):
    w = world.wars.pop(k)
    world.__dict__.setdefault("truces", {})[k] = world.ticks + (TRUCE_HOLDS if "zombies" in why else PEACE_HOLDS)
    what = "civil war over" if w.get("civil") else "PEACE"
    world.war_note(f"{what}: {world.civs[w['a']].name} and {world.civs[w['b']].name} ({why}) after {w['ticks']} ticks")
    if not w.get("civil") and why in ("armistice", "exhaustion"):          # (a war won outright: a satellite)
        import globalaffairs
        for win_id, n in w.get("captured", {}).items():
            lose_id = w["b"] if win_id == w["a"] else w["a"]
            W, L = world.civs[win_id], world.civs[lose_id]
            if (n >= globalaffairs.SATELLITE_TAKEN and not L.collapsed and not W.collapsed and L.m and W.m
                    and L.m.get("pop", 0) < globalaffairs.SATELLITE_POP * W.m.get("pop", 1)
                    and getattr(L, "overlord", None) is None):
                globalaffairs.make_tributary(world, W, L, "wins the war")


def at_war(world, civ_id):
    return any(civ_id in k for k in world.wars)


def contacts(world):
    """{(a, b): border length} for every pair of governments whose land touches (a < b) - all pairs in one pass,
    cached for the tick."""
    cache = getattr(world, "_contacts", None)
    if cache is None or cache[0] != world.ticks:
        import union
        world._contacts = cache = (world.ticks, union.neighbours(world, reach=1))
    return cache[1]


def border(world, a, b):
    return contacts(world).get((min(a, b), max(a, b)), 0)


def maybe_civil_war(world, parent, rebel, why="it won't let the region go", chance=1.0):
    """Called when `rebel` breaks away from `parent`: maybe the old government fights to take it back (x `chance`:
    less over provinces it was overstretched to hold anyway)."""
    if not getattr(world, "civil_wars", True) or parent.collapsed or not parent.ai:
        return
    if _danger(parent) > CIVIL_CRISIS:
        return
    p = CIVIL_AT_SPLIT * chance * parent.traits.get("aggression", 1.0) * govern.mod(parent, "aggression")
    if world.pyrng.random() < p:
        declare(world, parent.id, rebel.id, why, civil=True)


def step(world):
    civs = world.civs
    for c in civs:
        c.war_hold = False
    if world.ticks % CHECK_EVERY == 0:
        _consider(world)
    for k, w in list(world.wars.items()):
        a, b = w["a"], w["b"]
        ca, cb = civs[a], civs[b]
        w["ticks"] += 1
        civil = w.get("civil", False)
        if ca.collapsed or cb.collapsed:
            end(world, k, "a government fell")
            continue
        crisis = CIVIL_CRISIS if civil else CRISIS
        if _danger(ca) > crisis or _danger(cb) > crisis:
            end(world, k, "truce against the zombies")
            continue
        close = border(world, a, b) >= MIN_BORDER
        if close:
            ca.war_hold = cb.war_hold = True              # morale doesn't recover with the enemy at the gates
        if world.ticks % FIGHT_EVERY == 0:
            if close:
                _fight(world, w)
            elif world.ticks % STRIKE_EVERY == 0:
                _strikes(world, w)
        if close and world.ticks % warfare.FRONT_STRIKE_EVERY == 0:
            _strikes(world, w, warfare.FRONT_STRIKE_ARMY)  # (artillery and air strikes behind the front too)
        warfare.step(world, w)                            # (raids, partisans, landings: warfare.py)
        if w["ticks"] % (WEARY_EVERY if close else DISTANT_WEARY_EVERY) == 0:
            for c in (ca, cb):                         # a long war wears a country down - it doesn't topple it alone
                if c.morale > WEARY_FLOOR:
                    c.riot_hit += 1
        if civil and world.ticks % CHECK_EVERY == 0 and _civil_outcome(world, k, w):
            continue
        if world.ticks % CHECK_EVERY == 0:
            limit = CIVIL_WAR_MAX if civil else WAR_MAX
            chance = (PEACE_CHANCE * (0.25 if civil else 1.0)) + 0.002 * (w["ticks"] - PEACE_MIN)
            if w["ticks"] >= limit:
                end(world, k, "independence" if civil else "exhaustion")
            elif w["ticks"] >= PEACE_MIN and world.pyrng.random() < chance:
                end(world, k, "armistice")


def _civil_outcome(world, k, w):
    """A side too small to go on is absorbed: the country is reunited (or taken over) by force."""
    import union
    ca, cb = world.civs[w["a"]], world.civs[w["b"]]
    pa = ca.m.get("pop", 0) if ca.m else 0
    pb = cb.m.get("pop", 0) if cb.m else 0
    if min(pa, pb) == 0 or border(world, ca.id, cb.id) < MIN_BORDER:
        return False
    if pb < CIVIL_ABSORB * pa or pa < CIVIL_ABSORB * pb:
        big, small = (ca, cb) if pa >= pb else (cb, ca)
        if union.too_big(world, big, small):           # (it can't hold more: the breakaway keeps its independence)
            end(world, k, "independence")
            return True
        world.wars.pop(k)
        union.merge(world, big, small, "won the civil war")
        return True
    return False


def _too_big(world, a, b):
    import union
    return union.too_big(world, a, b)


def _consider(world):
    civs = world.civs
    live = [c for c in civs if c.id and c.ai and not c.collapsed and c.m and c.m.get("pop", 0) >= MIN_POP]
    touching = contacts(world)
    for ca in live:
        if at_war(world, ca.id) or _danger(ca) > 0.35:
            continue
        # a recovered government may go to war to reunite the country
        if getattr(world, "civil_wars", True) and ca.morale >= 7 and ca.military >= 0.35:
            for cb in live:
                if (cb.split_from == ca.id and not at_war(world, cb.id) and _danger(cb) < CRISIS
                        and not _too_big(world, ca, cb)
                        and touching.get((min(ca.id, cb.id), max(ca.id, cb.id)), 0) >= MIN_BORDER
                        and world.pyrng.random() < CIVIL_LATER * govern.mod(ca, "aggression")):
                    declare(world, ca.id, cb.id, "to reunite the country", civil=True)
                    break
            if at_war(world, ca.id):
                continue
        sc = scarcity(ca)
        rival = None
        for k in getattr(world, "rivals", ()):
            if ca.id in k:
                other = world.civs[next(iter(k - {ca.id}))]
                if (other.ai and not other.collapsed and not at_war(world, other.id) and _danger(other) < 0.35
                        and other.m and other.m.get("pop", 0) >= MIN_POP
                        and world.ticks >= at_peace_until(world, ca.id, other.id)):
                    rival = other
        if rival is not None and world.pyrng.random() < (RIVAL_CHANCE * (1 + 3 * sc) * ca.traits["aggression"]
                                                         * govern.mod(ca, "aggression")):
            declare(world, ca.id, rival.id, "old rivals, and the crisis")
            continue
        if sc < SCARCE_AT:
            continue
        options = []
        for cb in live:
            if cb.id == ca.id or at_war(world, cb.id) or _danger(cb) > CRISIS:
                continue
            b = touching.get((min(ca.id, cb.id), max(ca.id, cb.id)), 0)
            if b < MIN_BORDER or scarcity(cb) >= sc or world.ticks < at_peace_until(world, ca.id, cb.id):
                continue                      # nothing to gain from someone just as poor
            options.append(cb)
        if options and world.pyrng.random() < DECLARE_BASE * sc * ca.traits["aggression"] * govern.mod(ca, "aggression"):
            cb = world.pyrng.choice(options)
            declare(world, ca.id, cb.id, "scarce " + ("food" if ca.famine or (ca.food or 0) < ca.food_use * SCARCE_FOOD_TICKS else "materials"))
    # border disputes: neighbours at peace with the zombies fall out now and then
    by_id = {c.id: c for c in live}
    for (a, b), length in touching.items():
        ca, cb = by_id.get(a), by_id.get(b)
        if (ca is None or cb is None or length < MIN_BORDER or at_war(world, a) or at_war(world, b)
                or _danger(ca) > 0.3 or _danger(cb) > 0.3 or allied(world, a, b)
                or world.ticks < at_peace_until(world, a, b)):
            continue
        p = (DISPUTE_CHANCE * ca.traits.get("aggression", 1.0) * cb.traits.get("aggression", 1.0)
             * govern.mod(ca, "aggression"))
        if world.pyrng.random() < p:
            att, dfn = (ca, cb) if world.pyrng.random() < 0.5 else (cb, ca)
            declare(world, att.id, dfn.id, "a border dispute")


def _pair_window(world, a, b, margin=2):
    ra, ca = world.bbox(a, margin)
    rb, cb = world.bbox(b, margin)
    rows = slice(min(ra.start, rb.start), max(ra.stop, rb.stop))
    cols = slice(min(ca.start, cb.start), max(ca.stop, cb.stop))
    return rows, cols


def _fight(world, w):
    a, b = w["a"], w["b"]
    win = _pair_window(world, a, b)
    H, D, O, T = world.H[win], world.D[win], world.O[win], world.T[win]     # views: losses go into the map
    ca, cb = world.civs[a], world.civs[b]
    ma, mb = O == a, O == b
    edge_a = ma & (box_sum(mb, 1) > 0) & (H > 0)
    edge_b = mb & (box_sum(ma, 1) > 0) & (H > 0)
    if int(edge_a.sum() + edge_b.sum()) < MIN_BORDER:
        w["quiet"] += 1
        return
    w["quiet"] = 0
    sa = 0.25 + ca.military * (0.6 + 0.8 * ca.strength)
    sb = 0.25 + cb.military * (0.6 + 0.8 * cb.strength)
    rough = warfare.roughness(T)                          # (rough ground: its defenders lose fewer ...)
    for civ, edge, own, other in ((ca, edge_a, sa, sb), (cb, edge_b, sb, sa)):
        frac = (FIGHT_LOSS * 2 * other / (own + other) * world.jitter(0.3) * (1 - np.minimum(D, 9) / 11.0)
                * (1.0 - ROUGH_SAVES * rough))
        deaths = np.where(edge, np.maximum(1, np.ceil(H * frac)), 0).astype(np.int32)
        deaths = np.minimum(deaths, np.maximum(H, 0))
        H -= deaths
        n = int(deaths.sum())
        civ.materials = max(0.0, civ.materials - n * FIGHT_COST)
        civ.military = max(0.0, civ.military - n * FIGHT_ARMY)
    ratio = CIVIL_CAPTURE_RATIO if w.get("civil") else CAPTURE_RATIO
    # the stronger side takes weakly held ground
    for win_c, lose, sw, sl, lm in ((ca, cb, sa, sb, mb), (cb, ca, sb, sa, ma)):
        if sw / sl < ratio:
            continue
        near_win = box_sum(O == win_c.id, 1) > 0
        prey = lm & near_win & (D <= (5 if w.get("civil") else 4)) & (H < (120 if w.get("civil") else 60)) & is_land(T)
        if not prey.any():
            continue
        take = prey & (world.rng.random(H.shape) < CAPTURE_CHANCE * min(2.0, sw / sl - (ratio - 0.4))
                       * (1.0 - ROUGH_HOLDS * rough))         # (... and it is harder to take)
        if take.any():
            O[take] = win_c.id
            ys, xs = np.nonzero(take)                         # (remembered: partisans fight on there - warfare.py)
            w.setdefault("taken", {}).setdefault(win_c.id, []).extend(
                ((ys + (win[0].start or 0)) * world.cols + xs + (win[1].start or 0)).tolist())
            D[take] = np.minimum(D[take], 2)
            w.setdefault("captured", {}).setdefault(win_c.id, 0)
            w["captured"][win_c.id] += int(take.sum())
            if world.ticks % (FIGHT_EVERY * 5) == 0:
                world.war_note(f"{win_c.name} takes ground from {lose.name}", log=world.ticks % (FIGHT_EVERY * 15) == 0)


def _strikes(world, w, min_army=STRIKE_MIN_ARMY):
    """Air and missile strikes on the enemy's cities (all a war is, between nations that don't touch)."""
    H, D = world.H, world.D
    for att, tgt in ((world.civs[w["a"]], world.civs[w["b"]]), (world.civs[w["b"]], world.civs[w["a"]])):
        if att.military < min_army or att.materials < STRIKE_COST * 2:
            continue
        if att.capital is not None and tgt.capital is not None and att.strength < GLOBAL_REACH:
            dr = abs(att.capital[0] - tgt.capital[0])
            dc = abs(att.capital[1] - tgt.capital[1])
            if world.wrap:
                dc = min(dc, world.cols - dc)
            if (dr * dr + dc * dc) ** 0.5 > STRIKE_RANGE * 0.5 / world.meta.get("res", 0.5):    # (range in degrees)
                continue                                  # out of reach
        win = world.bbox(tgt.id, 0)
        mine = (world.O[win] == tgt.id) & (H[win] > 50)
        if not mine.any():
            continue
        dense = np.where(mine, box_sum(np.maximum(H[win], 0), 1), -1)
        r, c = np.unravel_index(int(np.argmax(dense)), dense.shape)
        r += win[0].start or 0
        c += win[1].start or 0
        r0, r1, c0, c1 = max(r - 1, 0), r + 2, max(c - 1, 0), c + 2
        block = H[r0:r1, c0:c1]
        killed = (block * STRIKE_KILL * world.jitter(0.4) * (0.5 + att.strength)).astype(np.int32)
        block -= np.minimum(killed, np.maximum(block, 0))
        D[r0:r1, c0:c1] = np.maximum(D[r0:r1, c0:c1] - 1, 1)
        att.materials -= STRIKE_COST
        att.military = max(0.0, att.military - 0.002)
        import globalaffairs
        globalaffairs.mark(world, r, c, "strike")
        w["strikes"] = w.get("strikes", 0) + 1
        if w["strikes"] % 3 == 0:
            tgt.riot_hit += 1
        from fracture import _place
        world.war_note(f"{att.name} strikes {_place(world, (r, c))} ({tgt.name}): {world.people(killed.sum())} dead",
                       log=w["strikes"] % 10 == 1)
