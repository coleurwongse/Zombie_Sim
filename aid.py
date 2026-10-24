"""International aid: the United Nations (or, on a map with alliances, one's allies) helping countries in trouble.

Every AID_EVERY ticks the governments that are doing fine - safe (danger below DONOR_DANGER), fed, with a real army
and a stockpile, and big enough to matter - look at the ones in trouble (danger at least NEED_DANGER, or starving)
that they can reach: by land (a shared border), by sea (both have working ports), or by air (the strongest armies).
Never someone they are at war with; on a map with alliances (Middle-earth) only their allies.

  Food aid      a donor with a full granary ships some of its surplus to a hungry country.
  Peacekeepers  a donor sends troops (a MISSION, ~MISSION_TICKS long): every couple of ticks they sweep the zombies
                closest to the recipient's people - the bigger and better the donor's army, the wider the sweep.  It
                costs the donor ammunition and wears its army down; the mission is recalled when the donor gets into
                trouble at home or runs short.
On the world map this is "the UN": world.un counts the missions and the food sent.
"""
import numpy as np

from civilization import box_sum, window, within

AID_EVERY = 10
DONOR_DANGER = 0.2
DONOR_ARMY = 0.4
DONOR_SIZE = 0.8            # (Civilization.size: 1 = an average government)
DONOR_MATERIALS = 80.0
NEED_DANGER = 0.45
NEED_POP = 300
FOOD_SURPLUS_TICKS = 60     # granaries above this many ticks of food can give ...
FOOD_SHARE = 0.08           # ... this share of the surplus per round
MISSIONS_PER_DONOR = 4
MISSION_CHANCE = 0.6        # per round, a donor with room for another mission sends one (x its generosity)
MISSION_TICKS = 90
SWEEP_EVERY = 2
SWEEP_TILES = 28            # tiles swept per wave by an average-sized donor (x its size)
SWEEP_KILL = 0.35           # share of the zombies killed on a swept tile (x (0.5 + army strength))
SWEEP_REACH = 4             # how far out from the recipient's people the troops go
SWEEP_COST = 0.004          # materials per zombie killed
SWEEP_WEAR = 0.0004         # army strength the donor loses per wave
AIRLIFT = 0.85              # army strength that can reach anyone by air


def _ok_donor(world, c):
    if not c.ai or c.collapsed or c.is_anarchy or not c.m or c.famine:
        return False
    return (c.threat(c.m) < DONOR_DANGER and c.m.get("damage", 0.0) < 0.5 and c.military >= DONOR_ARMY and c.materials >= DONOR_MATERIALS
            and c.size(world) >= DONOR_SIZE)


def _needy(world, c):
    if not c.ai or c.collapsed or c.is_anarchy or not c.m or c.m.get("pop", 0) < NEED_POP:
        return 0.0
    d = c.danger(c.m)[0]
    if d < NEED_DANGER and not c.famine:
        return 0.0
    return max(d, 0.6 if c.famine else 0.0) * np.sqrt(c.m.get("pop", 0))


def _friends(world, a, b):
    import war
    if war.key(a.id, b.id) in world.wars:
        return False
    if getattr(world, "alliance_of", None):
        return war.allied(world, a.id, b.id) or a.root == b.root
    return True


def _reach(world, a, b):
    import war
    if war.border(world, a.id, b.id) > 0:
        return True
    if a.ports > 0 and b.ports > 0:
        return True
    return a.strength >= AIRLIFT and a.military >= 0.6


def step(world):
    missions = getattr(world, "missions", None)
    if missions is None:
        missions = world.missions = []
        world.un = dict(missions=0, food=0.0)
    if world.ticks % SWEEP_EVERY == 0:
        _run_missions(world)
        missions = world.missions
    if world.ticks % AID_EVERY:
        return
    donors = [c for c in world.civs if _ok_donor(world, c)]
    if not donors:
        return
    needy = sorted(((_needy(world, c), c) for c in world.civs), key=lambda x: -x[0])
    needy = [c for v, c in needy if v > 0]
    if not needy:
        return
    un = not getattr(world, "alliance_of", None)
    for d in donors:
        options = [c for c in needy if c.id != d.id and _friends(world, d, c) and _reach(world, d, c)]
        if not options:
            continue
        # food for the hungry
        if d.food is not None and d.food_use > 0 and d.food > FOOD_SURPLUS_TICKS * d.food_use:
            hungry = [c for c in options if c.famine or (c.food is not None and c.food < 15 * c.food_use)]
            if hungry:
                r = hungry[0]
                q = min((d.food - FOOD_SURPLUS_TICKS * d.food_use) * FOOD_SHARE, max(30 * r.food_use - r.food, 0))
                if q > 0:
                    d.food -= q
                    r.food += q
                    world.un["food"] += q
                    key = ("food", d.id, r.id)
                    if key not in getattr(world, "_aid_noted", set()):
                        world._aid_noted = getattr(world, "_aid_noted", set()) | {key}
                        world.note(f"{'UN food aid: ' if un else ''}{d.name} ships food to {r.name}")
        # troops
        mine = [m for m in missions if m["donor"] == d.id]
        if len(mine) >= MISSIONS_PER_DONOR:
            continue
        gen = d.traits.get("caution", 1.0) ** -0.5            # (the cautious keep their troops at home)
        if world.pyrng.random() >= MISSION_CHANCE * gen:
            continue
        taken = {m["to"] for m in mine}
        for r in options:
            if r.id in taken:
                continue
            missions.append(dict(donor=d.id, to=r.id, until=world.ticks + MISSION_TICKS))
            world.un["missions"] += 1
            import diplomacy
            diplomacy.on_help(world, d.id, r.id)
            world.note(f"UN peacekeepers from {d.name} arrive in {r.name}" if un
                       else f"{d.name} sends troops to help {r.name}")
            break


def _run_missions(world):
    keep = []
    for m in world.missions:
        d, r = world.civs[m["donor"]], world.civs[m["to"]]
        if (world.ticks >= m["until"] or d.collapsed or r.collapsed or not d.m
                or d.threat(d.m) >= 0.35 or d.military < 0.25 or d.materials < 10 or not _friends(world, d, r)):
            continue
        _sweep(world, d, r)
        keep.append(m)
    world.missions = keep


def _sweep(world, d, r):
    """The donor's troops hit the zombies closest to the recipient's people."""
    win = window(world, r.id, SWEEP_REACH + 1)
    owned = (world.O[win] == r.id) & (world.H[win] > 10)
    Zw = world.Z[win]
    if not owned.any() or not Zw.any():
        return 0
    weight = np.where(owned, 3.0, np.where(within(world, owned, SWEEP_REACH, win), 1.0, 0.0))
    import crossings
    hidden = crossings.surprise(world)                   # (a fresh landing: not found yet)
    if hidden is not None:
        weight = np.where(hidden[win], 0.0, weight)
    rr, cc = np.nonzero((weight > 0) & (Zw >= 3))
    if rr.size == 0:
        return 0
    vals = Zw[rr, cc]
    width = max(4, int(SWEEP_TILES * d.size(world)))
    if vals.size > width:
        keep = np.argpartition(-(vals * weight[rr, cc]), width)[:width]
        rr, cc, vals = rr[keep], cc[keep], vals[keep]
    share = min(0.9, SWEEP_KILL * (0.5 + d.strength) * world.jitter(0.25))
    kills = np.minimum(np.maximum(1, np.ceil(vals * share)).astype(np.int32), vals)
    cost = float(kills.sum()) * SWEEP_COST
    if cost > d.materials:
        kills = (kills * (d.materials / cost)).astype(np.int32)
        cost = float(kills.sum()) * SWEEP_COST
    d.materials -= cost
    Zw[rr, cc] -= kills
    d.military = max(0.0, d.military - SWEEP_WEAR)
    n = int(kills.sum())
    d.kills += n
    return n
