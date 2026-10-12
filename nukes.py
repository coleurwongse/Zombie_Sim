"""Nuclear weapons: rare, desperate, devastating.  (world.nukes_allowed, on by default; --no-nukes turns them off.)

Who     governments with warheads (meta.json "nukes": United States, Russia, China, France, United Kingdom, India,
        Pakistan, Israel, North Korea).  A government that falls loses control of them.
When    checked every CHECK_EVERY ticks, and only in desperation:
          * against the horde: the government is in serious danger (danger >= DESPERATE) and a giant horde
            (>= HORDE zombies within 4 tiles of one spot) is within REACH tiles of its people - and it won't hit
            many of its own (the spot must have far more zombies than its people within the blast);
          * in a war, against the enemy's biggest city: when it is losing badly (morale at or below 4, or a good share
            of its land taken - WAR_CHANCE), or, between two nuclear powers, as the war escalates (ESCALATE);
          * in retaliation: a nuclear power that is hit - or whose people a neighbour's strike on a horde killed in
            numbers - may strike back at the one that fired, within a few days (RETALIATE).  One strike can start an
            exchange.  A country without warheads whose people were killed may go to war instead.
        Even then it's a gamble each time (CHANCE), cautious governments hesitate more, there is a long cooldown, and
        nobody fires more than MAX_STRIKES in a whole game.
What    everything within BLAST tiles of the target dies (BLAST_KILL), most of the ring around it too (RING_KILL);
        defenses are flattened; FALLOUT tiles around are poisoned for FALLOUT_TICKS: no harvests, no industry,
        no children, people slowly sicken.  The government that fired takes a morale hit, and so does its victim.
"""
import numpy as np

CHECK_EVERY = 10
DESPERATE = 0.7
HORDE = 2500
REACH = 15
CHANCE = 0.12
WAR_CHANCE = 0.05          # per check, losing a war badly
ESCALATE = 0.012           # per check, at war with another nuclear power (x2 when losing)
RETALIATE = 0.8            # chance a nuclear power strikes back when hit (/ caution)
RETALIATE_DECAY = 0.55     # ... times this for every warhead it has already used
COLLATERAL_RETALIATE = 0.3 # ... when a strike on a horde killed its people in numbers
COLLATERAL = 300           # people of another country killed that count as an attack on it
COLLATERAL_WAR = 0.4       # chance a country without warheads goes to war over it
COOLDOWN = 60
MAX_STRIKES = 4
BLAST = 2
BLAST_KILL = 0.95
RING_KILL = 0.6
FALLOUT = 4
FALLOUT_TICKS = 150
FALLOUT_SICK = 0.004       # share of the people on poisoned ground who die per tick


def step(world):
    if not getattr(world, "nukes_allowed", True):
        _fallout(world)
        return
    _retaliation(world)
    if world.ticks % CHECK_EVERY:
        _fallout(world)
        return
    _fallout(world)
    import war
    near4 = None
    for c in world.civs:
        if not c.ai or c.collapsed or c.nukes <= c.nukes_used or c.nukes_used >= MAX_STRIKES or not c.m:
            continue
        if world.ticks - getattr(c, "last_nuke", -10 ** 6) < COOLDOWN:
            continue
        caution = c.traits.get("caution", 1.0)
        d = c.danger(c.m)[0] if c.m.get("n") else 0.0
        if d >= DESPERATE:
            if near4 is None:
                near4 = world.zombie_near(4)
            target = _horde_target(world, c, near4)
            if target is not None and world.pyrng.random() < CHANCE / caution:
                detonate(world, c, target, "the horde")
                continue
        for k, w in world.wars.items():
            if c.id not in k:
                continue
            enemy = world.civs[w["b"] if w["a"] == c.id else w["a"]]
            lost = w.get("captured", {}).get(enemy.id, 0)
            losing = c.morale <= 4 or lost > 0.15 * max(c.m.get("n", 1), 1)
            chance = WAR_CHANCE if losing else 0.0
            if enemy.nukes > enemy.nukes_used and not enemy.collapsed:
                chance = max(chance, ESCALATE * (2 if losing else 1))
            if chance and world.pyrng.random() < chance / caution:
                target = _city_target(world, enemy)
                if target is not None:
                    detonate(world, c, target, enemy.name)
                    break


def _retaliation(world):
    """Strikes back that are due."""
    for c in world.civs:
        due = getattr(c, "strike_back", None)
        if not due or world.ticks < due[1]:
            continue
        c.strike_back = None
        enemy = world.civs[due[0]]
        if (c.collapsed or enemy.collapsed or c.nukes <= c.nukes_used or c.nukes_used >= MAX_STRIKES
                or not c.ai):
            continue
        target = _city_target(world, enemy)
        if target is not None:
            detonate(world, c, target, enemy.name, why="in retaliation")


def _provoked(world, attacker, victim, chance, why):
    """`victim` was hit by `attacker`: it may strike back (if it can), or go to war over it."""
    import war
    if victim.collapsed or not victim.ai or victim.id == attacker.id:
        return
    if why == "attack" and war.key(victim.id, attacker.id) not in world.wars:
        war.declare(world, victim.id, attacker.id, "nuclear attack")
    if victim.nukes > victim.nukes_used and victim.nukes_used < MAX_STRIKES:
        chance *= RETALIATE_DECAY ** victim.nukes_used                  # each exchange makes the next answer less likely
        if getattr(victim, "strike_back", None) is None and world.pyrng.random() < chance / victim.traits.get("caution", 1.0):
            victim.strike_back = (attacker.id, world.ticks + world.pyrng.randint(1, 4))
            world.note(f"{victim.name} vows to answer {attacker.name}'s nuclear strike")
    elif why == "collateral" and not war.at_war(world, victim.id) and world.pyrng.random() < COLLATERAL_WAR:
        war.declare(world, victim.id, attacker.id, "its people died in a nuclear strike")


def _horde_target(world, c, near4):
    win = world.bbox(c.id, REACH)
    mine = (world.O[win] == c.id) & (world.H[win] > 10)
    if not mine.any():
        return None
    from civilization import box_sum
    close = box_sum(mine, REACH) > 0
    z = np.where(close, near4[win], 0)
    if z.max() < HORDE:
        return None
    r, cc = np.unravel_index(int(np.argmax(z)), z.shape)
    r += win[0].start or 0
    cc += win[1].start or 0
    r0, r1, c0, c1 = max(r - BLAST, 0), r + BLAST + 1, max(cc - BLAST, 0), cc + BLAST + 1
    own = int(np.maximum(world.H[r0:r1, c0:c1], 0)[world.O[r0:r1, c0:c1] == c.id].sum())
    if own * 4 > int(world.Z[r0:r1, c0:c1].sum()):
        return None                                           # it would mostly kill its own people
    return int(r), int(cc)


def _city_target(world, enemy):
    win = world.bbox(enemy.id, 0)
    H = np.where(world.O[win] == enemy.id, np.maximum(world.H[win], 0), 0)
    if H.max() <= 50:
        return None
    from civilization import box_sum
    r, c = np.unravel_index(int(np.argmax(box_sum(H, 1))), H.shape)
    return int(r + (win[0].start or 0)), int(c + (win[1].start or 0))


def detonate(world, civ, rc, what, why=""):
    H, Z, D = world.H, world.Z, world.D
    r, c = rc
    rows, cols = H.shape
    rr, cc = np.ogrid[:rows, :cols]
    dc = np.abs(cc - c)
    if world.wrap:
        dc = np.minimum(dc, cols - dc)
    dist = np.hypot(rr - r, dc)
    blast, ring = dist <= BLAST + 0.5, (dist > BLAST + 0.5) & (dist <= BLAST + 1.5)
    dead_h = int(H[blast].sum() * BLAST_KILL + H[ring].sum() * RING_KILL)
    zone = blast | ring
    hit = np.bincount(world.O[zone], weights=(np.maximum(H[zone], 0) * np.where(blast[zone], BLAST_KILL, RING_KILL)),
                      minlength=len(world.civs))
    dead_z = int(Z[blast].sum() * BLAST_KILL + Z[ring].sum() * RING_KILL)
    for m, k in ((blast, BLAST_KILL), (ring, RING_KILL)):
        H[m] = (H[m] * (1 - k)).astype(np.int32)
        Z[m] = (Z[m] * (1 - k)).astype(np.int32)
    D[blast | ring] = 1
    fall = getattr(world, "fallout", None)
    if fall is None or fall.shape != H.shape:
        fall = world.fallout = np.zeros(H.shape, dtype=np.int32)
    fall[dist <= BLAST + FALLOUT] = FALLOUT_TICKS
    civ.nukes_used += 1
    civ.last_nuke = world.ticks
    civ.riot_hit += 2
    victim = world.O[r, c]
    if victim and victim != civ.id:
        world.civs[victim].riot_hit += 3
    world.nuclear_strikes = getattr(world, "nuclear_strikes", 0) + 1
    from fracture import _place
    world.note(f"NUCLEAR STRIKE{' ' + why.upper() if why else ''}: {civ.name} hits {what} at {_place(world, rc)} - "
               f"{dead_z} zombies and {dead_h} people killed")
    # the countries whose people died answer for it
    for k in np.flatnonzero(hit):
        if k == civ.id or k == 0:
            continue
        other = world.civs[int(k)]
        if what == other.name:
            _provoked(world, civ, other, RETALIATE, "attack")
        elif hit[k] >= COLLATERAL:
            other.riot_hit += 1
            _provoked(world, civ, other, COLLATERAL_RETALIATE, "collateral")


def _fallout(world):
    fall = getattr(world, "fallout", None)
    if fall is None or not fall.any():
        return
    hot = fall > 0
    H = world.H
    sick = hot & (H > 0)
    H[sick] -= np.maximum(1, (H[sick] * FALLOUT_SICK).astype(np.int32)) * (world.rng.random(int(sick.sum())) < 0.5)
    fall[hot] -= 1


def poisoned(world):
    """Tiles still under fallout (no harvests, no industry, no children)."""
    fall = getattr(world, "fallout", None)
    if fall is None:
        return None
    return fall > 0
