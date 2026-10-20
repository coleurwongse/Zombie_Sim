"""How wars are fought, beyond the border battles of war.py.

Raids        a war party strikes an enemy town near the front (within RAID_REACH tiles of its own land): people are
             killed, food and materials carried off, its defenses battered (RAID_*).  The bolder the government, the
             more often.
Strikes      artillery and air strikes on enemy towns in range don't stop because the two share a border
             (FRONT_STRIKE_EVERY: war.py's strikes, which before only distant wars used).
Guerrillas   ground a country has taken in rough country - forest, hills, mountains, marsh, jungle - doesn't stay
             quiet: partisans kill the occupier's people and soldiers there, and now and then a district goes back to
             the side it was taken from (GUERRILLA_*).  Rough ground is also harder to take, and its defenders lose
             fewer (war._fight: ROUGH_*).
Sea landings a side with a strong army, ports and materials lands troops on a weakly held enemy coast within
             LANDING_REACH tiles of its ports - a beachhead of its own, and a new front (LANDING_*).
"""
import numpy as np

from civilization import box_sum
from terrain import PROTECTION, is_land

RAID_EVERY = 8
RAID_CHANCE = 0.35         # per check, per side able to (x aggression)
RAID_ARMY = 0.3
RAID_REACH = 18            # tiles from its own land
RAID_KILL = 0.12           # share of the people in the 3x3 block killed
RAID_LOOT = 0.08           # share of the enemy's food and materials carried off (at most RAID_LOOT_MAX materials)
RAID_LOOT_MAX = 12.0
RAID_COST = 0.004          # army strength lost per raid
FRONT_STRIKE_EVERY = 12
FRONT_STRIKE_ARMY = 0.45
GUERRILLA_EVERY = 4
GUERRILLA_KILL = 0.03      # share of the occupier's people on a rough, taken tile killed per round (x roughness)
GUERRILLA_ARMY = 0.00003   # army strength the occupier loses per person killed
GUERRILLA_RETAKE = 0.03    # chance per round a rough, taken district goes back (x roughness)
ROUGH = {2: 0.5, 3: 1.0, 9: 0.6, 11: 0.8, 12: 0.9}    # forest, mountain, highlands, wetlands, rainforest
LANDING_EVERY = 20
LANDING_CHANCE = 0.4
LANDING_ARMY = 0.5
LANDING_MATERIALS = 20.0
LANDING_REACH = 60         # water tiles from its ports
LANDING_TROOPS = 12        # people (soldiers) per beachhead tile
LANDING_RADIUS = 2
LANDING_KILL = 0.3         # share of the defenders on the beachhead killed


def roughness(T):
    """0..1 per tile: how good the ground is for partisans (and for defenders)."""
    out = np.zeros(T.shape, dtype=np.float32)
    for t, v in ROUGH.items():
        out[T == t] = v
    return out


def step(world, w):
    """Everything but the border battles, for war `w` (war.py calls this every tick of the war)."""
    t = world.ticks
    a, b = world.civs[w["a"]], world.civs[w["b"]]
    if t % RAID_EVERY == 0:
        for att, tgt in ((a, b), (b, a)):
            _raid(world, w, att, tgt)
    if t % GUERRILLA_EVERY == 0:
        _guerrillas(world, w)
    if t % LANDING_EVERY == 0 and world.ports:
        for att, tgt in ((a, b), (b, a)):
            _landing(world, w, att, tgt)


def _able(c, army):
    return c.ai and not c.collapsed and c.military >= army and c.m and c.m.get("pop", 0) > 0


def _raid(world, w, att, tgt):
    if not _able(att, RAID_ARMY) or world.pyrng.random() >= RAID_CHANCE * att.traits.get("aggression", 1.0):
        return
    import war
    win = war._pair_window(world, att.id, tgt.id, RAID_REACH + 1)
    H, O, D = world.H[win], world.O[win], world.D[win]
    near = box_sum(O == att.id, RAID_REACH) > 0
    prey = (O == tgt.id) & near & (H > 40) & (D < 7)
    if not prey.any():
        return
    dense = np.where(prey, box_sum(np.maximum(H, 0), 1), -1)
    r, c = np.unravel_index(int(np.argmax(dense)), dense.shape)
    r0, r1, c0, c1 = max(r - 1, 0), r + 2, max(c - 1, 0), c + 2
    block = H[r0:r1, c0:c1]
    killed = (np.maximum(block, 0) * RAID_KILL * world.jitter(0.4) * (0.5 + att.military)).astype(np.int32)
    block -= killed
    D[r0:r1, c0:c1] = np.maximum(D[r0:r1, c0:c1] - 1, 1)
    mats = min(RAID_LOOT_MAX, tgt.materials * RAID_LOOT)
    tgt.materials -= mats
    att.materials += mats
    if tgt.food is not None and att.food is not None:
        food = tgt.food * RAID_LOOT
        tgt.food -= food
        att.food += food
    att.military = max(0.0, att.military - RAID_COST)
    tgt.riot_hit += 1
    w["raids"] = w.get("raids", 0) + 1
    if w["raids"] % 4 == 1:
        from fracture import _place
        rr, cc = r + (win[0].start or 0), c + (win[1].start or 0)
        world.note(f"{att.name} raids {_place(world, (rr, cc))} ({tgt.name}): {world.people(killed.sum())} dead, "
                   f"stores carried off")


def _guerrillas(world, w):
    taken = w.get("taken")
    if not taken:
        return
    H, O, T = world.H.reshape(-1), world.O.reshape(-1), world.T.reshape(-1)
    for winner, idx in list(taken.items()):
        loser = w["b"] if winner == w["a"] else w["a"]
        idx = np.asarray(idx, dtype=np.int64)
        idx = idx[O[idx] == winner]                       # (still held by the occupier)
        taken[winner] = idx.tolist()
        if idx.size == 0:
            continue
        rough = roughness(T[idx])
        idx, rough = idx[rough > 0], rough[rough > 0]
        if idx.size == 0:
            continue
        occ, orig = world.civs[winner], world.civs[loser]
        killed = np.minimum(np.floor(np.maximum(H[idx], 0) * GUERRILLA_KILL * rough * world.jitter(0.3)
                                     + (world.rng.random(idx.size) if world.stochastic else 0.5)),
                            np.maximum(H[idx], 0)).astype(np.int32)
        H[idx] -= killed
        occ.military = max(0.0, occ.military - float(killed.sum()) * GUERRILLA_ARMY)
        if orig.collapsed or not orig.ai:
            continue
        back = (world.rng.random(idx.size) < GUERRILLA_RETAKE * rough * (0.5 + orig.military)) if world.stochastic \
            else np.zeros(idx.size, dtype=bool)
        if back.any():
            O[idx[back]] = loser
            w["guerrilla"] = w.get("guerrilla", 0) + int(back.sum())
            if w["guerrilla"] - int(back.sum()) < 5 <= w["guerrilla"] or world.pyrng.random() < 0.05:
                from fracture import _place
                r, c = divmod(int(idx[back][0]), world.cols)
                world.note(f"partisans drive {occ.name} out of {_place(world, (r, c))} ({orig.name} takes it back)")


def _landing(world, w, att, tgt):
    import expeditions
    if (not _able(att, LANDING_ARMY) or att.materials < LANDING_MATERIALS
            or world.pyrng.random() >= LANDING_CHANCE * att.traits.get("aggression", 1.0)):
        return
    if not any(world.O[r, k] == att.id and world.H[r, k] > 10 for r, k, s in world.ports):
        return
    sea = expeditions.sea_steps_cached(world, att, LANDING_REACH)
    S = world.statics
    coast = S.land & (sea <= LANDING_REACH) & (world.O == tgt.id) & (world.H > 10) & (world.D < 6)
    if not coast.any():
        return
    # the weakest held stretch of coast: few defenders, low defense, not right next to its own land (a new front)
    rr, cc = np.nonzero(coast)
    own_near = box_sum(world.O == att.id, 3)[rr, cc] > 0
    score = (world.D[rr, cc] * 30 + world.H[rr, cc] + 200 * own_near
             + (world.rng.random(rr.size) * 40 if world.stochastic else 0))
    j = int(np.argmin(score))
    r, c = int(rr[j]), int(cc[j])
    R = LANDING_RADIUS
    r0, r1, c0, c1 = max(r - R, 0), min(r + R + 1, world.rows), max(c - R, 0), min(c + R + 1, world.cols)
    head = (world.O[r0:r1, c0:c1] == tgt.id) & is_land(world.T[r0:r1, c0:c1]) & (world.D[r0:r1, c0:c1] < 7)
    n = int(head.sum())
    if n == 0 or not expeditions.draw_from_home(world, att, n * LANDING_TROOPS):
        return
    Hb = world.H[r0:r1, c0:c1]
    killed = np.where(head, (np.maximum(Hb, 0) * LANDING_KILL).astype(np.int32), 0)
    Hb -= killed
    Hb[head] += LANDING_TROOPS
    world.O[r0:r1, c0:c1][head] = att.id
    world.D[r0:r1, c0:c1][head] = 2
    att.materials -= LANDING_MATERIALS / 2
    att.military = max(0.0, att.military - 0.02)
    tgt.riot_hit += 1
    taken = w.setdefault("taken", {}).setdefault(att.id, [])
    ys, xs = np.nonzero(head)
    taken.extend(((ys + r0) * world.cols + xs + c0).tolist())
    from fracture import _place
    world.note(f"{att.name} lands troops at {_place(world, (r, c))} ({tgt.name}): a beachhead of {n} districts")
