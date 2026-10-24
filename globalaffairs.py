"""Global affairs: countries that aren't fighting for their lives take part in what happens elsewhere.

What a country does abroad follows from the state it is in (motives.py): secure countries with the urge to expand
send expeditions and make conquests, unstable ones have revolutions, militarist and hungry ones raid.

Expeditions   a strong country that is secure at home and wants to expand (motives.ambition) sends an expeditionary
              force to a fallen city anywhere it can reach (a shared border, ports at both ends, or an army strong
              enough to fly in): for CORPS_DAYS its troops sweep the hordes within CORPS_RADIUS of it (CORPS_*) -
              clearing the way for survivors to come back.  It costs the sender materials, soldiers (people) and army
              strength.  An ambitious sender that clears the city plants a colony there (COLONY_AMBITION).
Reconstruction a rich, safe country sends materials and food to a friend rebuilding after the outbreak (RECON_*).
Pacts         countries that have fought the zombies side by side (an expedition or peacekeepers), or that share an
              enemy, sign a defensive pact: they never fight each other, and when one is attacked the other joins
              the war (world.pacts; war.allied counts them).
Proxy wars    a power with a stake in a war - an old rival of one side, or a pact with the other - arms the side it
              favours: materials and army strength (PROXY_*).
Tributaries   the strongest militarist states (juntas, warlords, strong armies - motives.militarism) make weak
              neighbours they far outmatch (power x TRIBUTE_RATIO) pay tribute (TRIBUTE_*): a share of their food and
              materials, and the two are bound by a pact.  A tributary resents it (RESENT_*): it stops paying when its
              overlord falters (at war, in trouble) or when it has grown strong enough - and the overlord answers with
              a punitive war if it can, or the two are rivals from then on.
Puppets       a satellite state governed in its overlord's interest (PUPPET_*): a war won decisively ends with the
              loser a puppet; a strong neighbour may back a coup and put its own men in power in a country in revolt;
              an overlord tightens its grip on a tributary that has paid long and is far weaker.  A puppet pays less
              tribute, but follows its overlord into its wars and starts none of its own.
              (The map: a line with arrows from each tributary (gold) or puppet (purple) to its overlord.)
Revolutions   an unstable government (motives.instability: morale breaking, famine, riots, a war going badly, foreign
              rule, a shaky regime) may be overthrown (REVOLT_*): a new form of government (junta, republic,
              warlords...), a new name, a shaken army.
Conquest      a secure, ambitious country goes to war with a weaker neighbour for its land (CONQUEST_*).
Village raids an organized state - militarist (juntas, warlords) or short of food and materials - raids the villages
              nobody governs within reach over land: some killed, some carried off to work its land, their stores
              taken (VRAID_*).
Map marks     raids, strikes, landings, partisan actions, expeditions and revolutions are marked on the map for a few
              weeks (mark(); main.py draws them) - not once the zombies hold the place (nobody left to tell of it).
"""
import numpy as np

import motives
from civilization import box_sum

EVERY = 10
MARK_DAYS = 30
# expeditions
CORPS_ARMY = 0.5
CORPS_SIZE = 0.6
CORPS_MATERIALS = 60.0
CORPS_SAFE = 0.15           # the sender's danger at home must be below this
CORPS_CHANCE = 0.12         # per check, per able country (x its ambition / caution)
CORPS_SECURE = 0.6          # (motives.security: only a country this secure at home sends troops abroad)
COLONY_AMBITION = 0.3       # a sender this ambitious that clears the city founds a colony there (settlers.found)
CORPS_MAX = 1               # forces abroad per country at once
CORPS_DAYS = 120
CORPS_RADIUS = 10
CORPS_TILES = 20            # tiles swept per wave (x the sender's size)
CORPS_KILL = 0.25           # share of the zombies on a swept tile killed (x (0.5 + army strength))
CORPS_MIN_Z = 300           # a city with this many zombies within CORPS_RADIUS is worth an expedition ...
CORPS_MAX_Z = 3000          # ... and one with more than this (x the sender's size and army) is beyond it: it
                            #     goes where it can win, and sets up where the hordes are thinnest (the staging point)
CORPS_EASY = 1500           # (of the cities it can take on, it prefers survivors near a small horde)
CORPS_COST = 0.004          # materials per zombie killed
CORPS_WEAR = 0.0005         # army strength lost per wave
CORPS_SOLDIERS = 60         # people the sender ships out (and loses: they don't come back as settlers)
AIRLIFT = 0.8
# reconstruction
RECON_RICH = 160.0          # materials a donor must have ...
RECON_SHARE = 0.12          # ... and the share of what it has above that it gives
RECON_DAMAGE = 0.25         # a recipient that has lost at least this share of its people
# pacts, proxies, tributaries, revolutions, conquest
PACT_CHANCE = 0.15
PROXY_EVERY = 20
PROXY_MATERIALS = 15.0
PROXY_ARMY = 0.03
TRIBUTE_EVERY = 30
TRIBUTE_CHANCE = 0.08
TRIBUTE_POP = 0.25          # the weaker one has under this share of the stronger one's people ...
TRIBUTE_SHARE = 0.04        # ... and pays this share of its materials and food every EVERY days
TRIBUTE_RATIO = 2.0         # (military power - army x training x size: the overlord has at least this x the other's)
TRIBUTE_MILITARIST = 0.4    # (motives.militarism - or ambition - an overlord needs at least this)
SATELLITE_TAKEN = 25        # a war in which the winner took this many districts and the loser is this much weaker
SATELLITE_POP = 0.5         # (people) ends with the loser a puppet
PUPPET_SHARE = 0.02         # a puppet pays this share (instead of TRIBUTE_SHARE)
PUPPET_COUP = 0.35          # chance a revolution next to a militarist power TRIBUTE_RATIO x stronger installs its puppet
PUPPET_TIGHTEN = 0.05       # per tribute check: an overlord makes a tributary of PUPPET_AFTER days, power ratio 3+,
PUPPET_AFTER = 300          #  its puppet
RESENT_EVERY = 0.03         # a tributary's resentment grows this much per check (x its own militarism) ...
RESENT_STRONG = 0.75        # ... and it stops paying once resentful enough and this strong next to its overlord
REVOLT_CHANCE = 0.15        # per check, for a government at the very edge (x ((instability - REVOLT_AT) / (1 - ..)) ** 1.5,
                            #  x (1 - 0.7 x threat): a coup in the middle of the emergency happens too, less often)
REVOLT_AT = 0.35            # (motives.instability below this: no revolution)
REVOLT_THREAT = 1.01        # (no gate: under the zombies it is just less likely, below)
REVOLT_COOLDOWN = 300
CONQUEST_CHANCE = 0.06      # per check, x the country's ambition (motives.ambition)
CONQUEST_AMBITION = 0.35
CONQUEST_RATIO = 1.6
VRAID_CHANCE = 0.3          # per check, x (militarism + need) - 0.3
VRAID_REACH = 10
VRAID_KILL = 0.15
VRAID_TAKE = 0.3


def mark(world, r, c, kind):
    """Remember an event at (r, c) for the map (kinds: raid, strike, landing, partisan, expedition, revolution,
    tribute, conquest, village)."""
    marks = world.__dict__.setdefault("marks", [])
    marks.append((world.ticks, int(r), int(c), kind))
    if len(marks) > 400:
        del marks[:len(marks) - 400]


def recent_marks(world):
    """The marks of the last MARK_DAYS - dropping those where the zombies now hold the place."""
    marks = getattr(world, "marks", [])
    if not marks:
        return []
    H, Z = world.H, world.Z
    keep, gone = [], set()
    for i, m in enumerate(marks):
        if world.ticks - m[0] > MARK_DAYS:
            continue
        r, c = m[1], m[2]
        r0, r1, c0, c1 = max(r - 2, 0), r + 3, max(c - 2, 0), c + 3
        z, h = int(Z[r0:r1, c0:c1].sum()), int(np.maximum(H[r0:r1, c0:c1], 0).sum())
        if z > 20 and z > h:                               # (overrun: nobody left there to tell of it)
            gone.add(i)
            continue
        keep.append(m)
    if gone:
        world.marks = [m for i, m in enumerate(marks) if i not in gone]
    return keep


def pacts(world):
    return world.__dict__.setdefault("pacts", {})


def in_pact(world, a, b):
    return frozenset((a, b)) in pacts(world)


def _live(c):
    return bool(c.id and c.ai and not c.collapsed and not c.is_anarchy and c.m and c.m.get("n"))


def _sign(world, a, b, why):
    if a.id == b.id or in_pact(world, a.id, b.id):
        return
    pacts(world)[frozenset((a.id, b.id))] = world.ticks
    world.war_note(f"PACT: {a.name} and {b.name} sign a defensive pact ({why})")


def step(world):
    corps = world.__dict__.setdefault("corps", [])
    if world.ticks % 2 == 0 and corps:
        _run_corps(world, corps)
    for k in [k for k in pacts(world) if any(world.civs[i].collapsed for i in k)]:
        del pacts(world)[k]                              # (a fallen government's pacts die with it ...)
    for c in world.civs:                                 # (... and its tributaries are free)
        lord = getattr(c, "overlord", None)
        if lord is not None and (lord >= len(world.civs) or world.civs[lord].collapsed):
            c.overlord = None
            c.vassal_kind = None
    if world.ticks % EVERY:
        return
    motives.update(world)
    live = [c for c in world.civs if _live(c)]
    _expeditions(world, live, corps)
    _reconstruction(world, live)
    _tribute(world, live)
    _revolutions(world, live)
    _conquest(world, live)
    _village_raids(world, live)
    if world.ticks % PROXY_EVERY == 0:
        _proxies(world, live)


# ------------------------------------------------------------------------------------------------ expeditions
def _able(world, c):
    import war
    return (c.military >= CORPS_ARMY and c.size(world) >= CORPS_SIZE and c.materials >= CORPS_MATERIALS
            and c.threat(c.m) < CORPS_SAFE and not c.famine and not war.at_war(world, c.id)
            and motives.security(world, c) >= CORPS_SECURE
            and sum(1 for x in getattr(world, "corps", []) if x["donor"] == c.id) < CORPS_MAX)


def _can_reach(world, c, r, k):
    """By land (its own landmass), by sea (it has a working port; the city is on a coast), or by air."""
    S = world.statics
    if c.capital is not None and S.landmass[c.capital] == S.landmass[r, k]:
        return True
    if c.ports > 0 and (world.statics.sea_dist[max(r - 2, 0):r + 3, max(k - 2, 0):k + 3] == 1).any():
        return True
    return c.strength >= AIRLIFT and c.military >= 0.7


def _targets(world):
    """Fallen cities worth an expedition: nobody governs them (or a fallen government did), hordes about them, and
    survivors or a living government not far off (somebody to clear the way for).  Cached for the check."""
    memo = getattr(world, "_corps_targets", None)
    if memo is not None and memo[0] == world.ticks:
        return memo[1]
    zr = world.zombie_near(CORPS_RADIUS)
    people = box_sum(world.H > 10, CORPS_RADIUS * 2) > 0
    out = []
    for name, r, k, pop in world.cities:
        o = int(world.O[r, k])
        if (o == 0 or world.civs[o].collapsed) and zr[r, k] >= CORPS_MIN_Z and people[r, k]:
            out.append(((1.0 + pop) / (1.0 + float(zr[r, k]) / CORPS_EASY), name, r, k, int(zr[r, k])))
    out.sort(reverse=True)
    world._corps_targets = (world.ticks, out[:60])
    return out[:60]


def _expeditions(world, live, corps):
    if not world.cities:
        return
    busy = {(x["r"], x["c"]) for x in corps}
    for c in live:
        if (not _able(world, c) or world.pyrng.random() >= CORPS_CHANCE * (0.15 + 1.5 * motives.ambition(world, c))
                / max(c.traits.get("caution", 1.0), 0.5)):
            continue
        import expeditions
        draw = getattr(expeditions, "draw_from_home", None)
        able_z = CORPS_MAX_Z * c.size(world) * (0.5 + c.military)
        for _, name, r, k, z in _targets(world):
            if (r, k) in busy or z > able_z or not _can_reach(world, c, r, k):
                continue
            if draw is not None and not draw(world, c, CORPS_SOLDIERS):
                break
            corps.append(dict(donor=c.id, r=r, c=k, name=name, until=world.ticks + CORPS_DAYS, killed=0,
                              claim=motives.ambition(world, c) >= COLONY_AMBITION))
            busy.add((r, k))
            c.materials -= CORPS_MATERIALS * 0.25
            mark(world, *_staging(world, r, k), "expedition")
            far = c.capital is not None and world.statics.landmass[c.capital] != world.statics.landmass[r, k]
            world.war_note(f"{c.name} sends an expeditionary force {'overseas ' if far else ''}to {name}"
                           + (" - to claim it" if corps[-1]["claim"] else ""))
            break


def _staging(world, r, k):
    """Where an expeditionary force sets up near a city: the land tile within 1.5 x CORPS_RADIUS with the fewest
    zombies about (ties: the nearest) - not in the middle of the horde."""
    R = int(CORPS_RADIUS * 1.5)
    r0, r1, c0, c1 = max(r - R, 0), min(r + R + 1, world.rows), max(k - R, 0), min(k + R + 1, world.cols)
    near = world.zombie_near(4)[r0:r1, c0:c1].astype(np.float64)
    yy, xx = np.mgrid[r0:r1, c0:c1]
    score = np.where(world.land[r0:r1, c0:c1], near + 0.5 * np.hypot(yy - r, xx - k), np.inf)
    j = np.unravel_index(int(np.argmin(score)), score.shape)
    return int(yy[j]), int(xx[j])


def _run_corps(world, corps):
    keep = []
    for x in corps:
        d = world.civs[x["donor"]]
        if (world.ticks >= x["until"] or d.collapsed or not d.m or d.threat(d.m) >= 0.35 or d.military < 0.2
                or d.materials < 5):
            _end_corps(world, x, d)
            continue
        r, k, R = x["r"], x["c"], CORPS_RADIUS
        r0, r1, c0, c1 = max(r - R, 0), min(r + R + 1, world.rows), max(k - R, 0), min(k + R + 1, world.cols)
        Zw = world.Z[r0:r1, c0:c1]
        rr, cc = np.nonzero(Zw >= 3)
        if rr.size == 0:
            _end_corps(world, x, d, cleared=True)
            continue
        vals = Zw[rr, cc]
        width = max(6, int(CORPS_TILES * d.size(world)))
        if vals.size > width:
            pick = np.argpartition(-vals, width)[:width]
            rr, cc, vals = rr[pick], cc[pick], vals[pick]
        share = min(0.9, CORPS_KILL * (0.5 + d.military) * world.jitter(0.25))
        kills = np.minimum(np.maximum(1, np.ceil(vals * share)).astype(np.int32), vals)
        cost = float(kills.sum()) * CORPS_COST
        if cost > d.materials:
            kills = (kills * (d.materials / cost)).astype(np.int32)
            cost = float(kills.sum()) * CORPS_COST
        Zw[rr, cc] -= kills
        d.materials -= cost
        d.military = max(0.0, d.military - CORPS_WEAR)
        d.kills += int(kills.sum())
        x["killed"] += int(kills.sum())
        if int(Zw.sum()) < 40:
            _end_corps(world, x, d, cleared=True)
            continue
        keep.append(x)
    corps[:] = keep


def _end_corps(world, x, d, cleared=False):
    if cleared:
        mark(world, x["r"], x["c"], "expedition")
        world.war_note(f"{d.name}'s expeditionary force clears {x['name']} ({world.people(x['killed'])} zombies destroyed)")
    # (fighting side by side: the sender and whoever lives near there may sign a pact)
    o = int(world.O[x["r"], x["c"]])
    near = [c for c in world.civs if _live(c) and c.id != d.id and c.capital is not None
            and abs(c.capital[0] - x["r"]) + abs(c.capital[1] - x["c"]) < 40]
    if cleared and near and world.pyrng.random() < PACT_CHANCE * 2:
        _sign(world, d, near[0], f"the expedition to {x['name']}")
    if cleared and x.get("claim") and not d.collapsed and o == 0:        # (it came to expand: a colony of its own)
        import settlers
        r, k = _staging(world, x["r"], x["c"])
        if world.land[r, k] and world.O[r, k] == 0 and d.m and d.m.get("pop", 0) >= settlers.SETTLE_MIN_POP:
            col = settlers.found(world, d, r, k)
            if col is not None:
                world.war_note(f"{d.name} plants a colony at {x['name']}: {col.name}")


# ------------------------------------------------------------------------------------------------ reconstruction
def _reconstruction(world, live):
    import aid
    rebuilding = [c for c in live if c.m.get("damage", 0.0) >= RECON_DAMAGE and c.threat(c.m) < 0.3
                  and getattr(c, "_worst_damage", c.m.get("damage", 0.0)) >= RECON_DAMAGE]
    if not rebuilding:
        return
    for d in live:
        if d.materials < RECON_RICH or d.threat(d.m) >= 0.15 or d.m.get("damage", 0.0) >= 0.3:
            continue
        options = [r for r in rebuilding if r.id != d.id and aid._friends(world, d, r) and aid._reach(world, d, r)]
        if not options:
            continue
        r = min(options, key=lambda c: c.materials)
        q = (d.materials - RECON_RICH) * RECON_SHARE
        d.materials -= q
        r.materials += q
        if d.food is not None and r.food is not None and d.food_use > 0 and d.food > 90 * d.food_use:
            f = (d.food - 90 * d.food_use) * RECON_SHARE
            d.food -= f
            r.food += f
        key = ("recon", d.id, r.id)
        noted = world.__dict__.setdefault("_recon_noted", set())
        if key not in noted:
            noted.add(key)
            world.war_note(f"{d.name} helps rebuild {r.name}: materials and food")
            import diplomacy
            diplomacy.on_help(world, d.id, r.id)
            if world.pyrng.random() < PACT_CHANCE:
                _sign(world, d, r, "reconstruction")


# ------------------------------------------------------------------------------------------------ tributaries
def _tribute(world, live):
    import war
    for c in live:                                      # tribute paid - and thrown off when the overlord falters
        lord = getattr(c, "overlord", None)
        if lord is None:
            continue
        L = world.civs[lord]
        puppet = getattr(c, "vassal_kind", "tributary") == "puppet"
        import diplomacy                                # (the more it hates its overlord, the faster)
        c.resent = getattr(c, "resent", 0.0) + (RESENT_EVERY * (0.5 + motives.militarism(c)) * (0.5 if puppet else 1.0)
                                                * (1.0 + diplomacy.grudge(world, c.id, L.id)))
        sa = 0.25 + c.military * (0.6 + 0.8 * c.strength)
        sl = 0.25 + L.military * (0.6 + 0.8 * L.strength)
        if (L.collapsed or not L.m or L.threat(L.m) > 0.5 or (war.at_war(world, L.id) and world.pyrng.random() < 0.05)
                or (c.resent >= 1.0 and sa >= RESENT_STRONG * sl and world.pyrng.random() < 0.2)):
            _throw_off(world, c, L)
            continue
        share = PUPPET_SHARE if puppet else TRIBUTE_SHARE
        m = c.materials * share
        c.materials -= m
        L.materials += m
        if c.food is not None and L.food is not None:
            f = c.food * share
            c.food -= f
            L.food += f
    if world.ticks % TRIBUTE_EVERY:
        return
    touching = war.contacts(world)
    # an overlord tightens its grip: a tributary that has paid long and is far weaker becomes its puppet
    for c in live:
        lord = getattr(c, "overlord", None)
        if (lord is None or getattr(c, "vassal_kind", "tributary") == "puppet"
                or world.ticks - getattr(c, "vassal_since", world.ticks) < PUPPET_AFTER):
            continue
        L = world.civs[lord]
        if power(world, L) >= 3 * power(world, c) and world.pyrng.random() < PUPPET_TIGHTEN * (0.5 + motives.militarism(L)):
            make_tributary(world, L, c, "tightens its grip", puppet=True)
    # the strongest militarist states first: each demands tribute of the weakest neighbour it far outmatches
    lords = [s for s in live if s.military >= 0.5 and s.threat(s.m) <= 0.15 and not war.at_war(world, s.id)
             and getattr(s, "overlord", None) is None
             and max(motives.militarism(s), motives.ambition(world, s)) >= TRIBUTE_MILITARIST]
    lords.sort(key=lambda s: -power(world, s))
    for s in lords:
        if (war.at_war(world, s.id)
                or world.pyrng.random() >= TRIBUTE_CHANCE * 2.5 * motives.militarism(s) * motives.settled(world)):
            continue
        ps = power(world, s)
        prey = []
        for w_ in live:
            k = (min(s.id, w_.id), max(s.id, w_.id))
            if (w_.id == s.id or touching.get(k, 0) < war.MIN_BORDER or getattr(w_, "overlord", None) is not None
                    or war.allied(world, s.id, w_.id) or w_.m.get("pop", 0) > TRIBUTE_POP * s.m.get("pop", 1)
                    or war.at_war(world, w_.id) or ps < TRIBUTE_RATIO * power(world, w_)
                    or any(getattr(v, "overlord", None) == w_.id for v in live)):
                continue
            prey.append((ps / max(power(world, w_), 1e-9), w_))
        if not prey:
            continue
        import diplomacy                                # (the weakest - and, of those, the one it likes least)
        ratio, w_ = max(prey, key=lambda x: x[0] * (1.0 - 0.5 * diplomacy.opinion(world, s.id, x[1].id)))
        # (a proud or warlike one may refuse - if it isn't hopelessly outmatched)
        if ratio < 3.0 and world.pyrng.random() < 0.5 * motives.militarism(w_) + 0.2:
            war.declare(world, s.id, w_.id, "it refused to pay tribute")
            if w_.capital is not None:
                mark(world, *w_.capital, "conquest")
        else:
            make_tributary(world, s, w_, "demands tribute")


def power(world, c):
    """Military power: army strength x training, x the country's size."""
    return (0.25 + c.military * (0.6 + 0.8 * c.strength)) * c.size(world)


def _throw_off(world, c, L):
    """`c` stops paying `L`: if the overlord can, it makes war to bring it back in line; if not, they're rivals."""
    import war
    c.overlord = None
    c.vassal_kind = None
    c.resent = 0.0
    pacts(world).pop(frozenset((c.id, L.id)), None)
    import diplomacy
    diplomacy.on_thrown_off(world, L.id, c.id)
    if c.capital is not None:
        mark(world, *c.capital, "revolution")
    able = (not L.collapsed and L.m and L.m.get("n") and L.threat(L.m) < 0.3 and L.military >= 0.35
            and not war.at_war(world, L.id))
    if able:
        world.war_note(f"{c.name} stops paying tribute to {L.name}")
        war.declare(world, L.id, c.id, "it stopped paying tribute", truce_ok=True)
    else:
        world.war_note(f"{c.name} throws off {L.name}'s rule")
        if not L.collapsed:
            world.__dict__.setdefault("rivals", set()).add(frozenset((c.id, L.id)))


def make_tributary(world, lord, vassal, how="demands tribute", puppet=False):
    """`vassal` pays tribute to `lord` - or, `puppet`, is its puppet state."""
    if getattr(vassal, "overlord", None) != lord.id:
        vassal.vassal_since = world.ticks
    vassal.overlord = lord.id
    vassal.vassal_kind = "puppet" if puppet else "tributary"
    vassal.resent = 0.0
    for k in [k for k in pacts(world) if vassal.id in k and lord.id not in k]:
        del pacts(world)[k]                              # (its foreign policy is its overlord's now)
    pacts(world)[frozenset((lord.id, vassal.id))] = world.ticks
    import diplomacy
    diplomacy.on_vassal(world, lord.id, vassal.id, puppet)
    what = (f"a puppet state of {lord.name}" if puppet else f"its tributary (paying tribute to {lord.name})")
    world.war_note(f"{lord.name} {how}: {vassal.name} becomes {what}")
    if vassal.capital is not None:
        mark(world, *vassal.capital, "puppet" if puppet else "tribute")


# ------------------------------------------------------------------------------------------------ revolutions
def _revolutions(world, live):
    import govern
    for c in live:
        inst = motives.instability(c)
        if (inst < REVOLT_AT or c.threat(c.m) >= REVOLT_THREAT
                or world.ticks - max(getattr(c, "_revolution", -10 ** 6), getattr(c, "founded", 0)) < REVOLT_COOLDOWN
                or world.pyrng.random() >= (REVOLT_CHANCE * motives.settled(world) * ((inst - REVOLT_AT) / (1 - REVOLT_AT)) ** 1.5
                                            * (1.0 - 0.7 * c.threat(c.m)))):
            continue
        c._revolution = world.ticks
        region = world.O == c.id
        if not region.any():
            continue
        old = c.gov
        options = {"junta", "democracy", "warlord", "tribal"} - {old}
        new = govern.choose(world, region, c, sites=len(c.sites))
        if new not in options:
            new = world.pyrng.choice(sorted(options))
        old_name = c.name
        c.gov = new
        c.place = None                                    # (its own city is still its own to be named after)
        c.name = govern.state_name(world, new, region, c.id, near=c.capital)
        c.morale = max(c.morale, 6)
        c.military *= 0.8
        c.materials *= 0.8
        c.instability = 0.25                              # (a new regime gets its honeymoon)
        what = {"junta": "the army takes power", "democracy": "the people rise and declare a republic",
                "warlord": "the country falls to its warlords", "tribal": "power passes to the clans"}[new]
        world.war_note(f"REVOLUTION in {old_name} ({'famine' if c.famine else 'unrest'}): {what} - now {c.name}")
        if c.capital is not None:
            mark(world, *c.capital, "revolution")
        import ideology                                   # (maybe a creed comes to power with it: ideology.py)
        ideology.on_revolution(world, c)
        backer = _backer(world, c, live)                  # (a strong neighbour puts its own men in power)
        if backer is not None and world.pyrng.random() < PUPPET_COUP:
            make_tributary(world, backer, c, "backs the coup", puppet=True)


def _backer(world, c, live):
    """The strongest militarist neighbour far stronger than `c` (or None)."""
    import war
    if getattr(c, "overlord", None) is not None:
        return None
    touching = war.contacts(world)
    best = None
    for b in live:
        k = (min(b.id, c.id), max(b.id, c.id))
        if (b.id == c.id or touching.get(k, 0) < war.MIN_BORDER or getattr(b, "overlord", None) is not None
                or motives.militarism(b) < TRIBUTE_MILITARIST or power(world, b) < TRIBUTE_RATIO * power(world, c)
                or war.key(b.id, c.id) in world.wars):
            continue
        if best is None or power(world, b) > power(world, best):
            best = b
    return best


# ------------------------------------------------------------------------------------------------ conquest
def _conquest(world, live):
    import war
    touching = war.contacts(world)
    for a in live:
        amb = motives.ambition(world, a)
        if (amb < CONQUEST_AMBITION or getattr(a, "vassal_kind", None) == "puppet" or a.military < 0.6 or a.threat(a.m) > 0.15 or war.at_war(world, a.id)
                or world.pyrng.random() >= CONQUEST_CHANCE * amb * motives.settled(world)):
            continue
        sa = 0.25 + a.military * (0.6 + 0.8 * a.strength)
        prey = []
        for b in live:
            k = (min(a.id, b.id), max(a.id, b.id))
            if b.id == a.id or touching.get(k, 0) < war.MIN_BORDER or war.allied(world, a.id, b.id):
                continue
            sb = 0.25 + b.military * (0.6 + 0.8 * b.strength)
            if sa >= CONQUEST_RATIO * sb and b.threat(b.m) < 0.5:
                prey.append(b)
        if prey:
            b = world.pyrng.choice(prey)
            war.declare(world, a.id, b.id, "to take its land")
            if b.capital is not None:
                mark(world, *b.capital, "conquest")


# ------------------------------------------------------------------------------------------------ proxies
def _proxies(world, live):
    import war
    for k, w in list(world.wars.items()):
        sides = (world.civs[w["a"]], world.civs[w["b"]])
        for p in live:
            if p.id in k or war.at_war(world, p.id) or p.materials < 2 * PROXY_MATERIALS or p.threat(p.m) > 0.2:
                continue
            for side, enemy in (sides, sides[::-1]):
                rival = frozenset((p.id, enemy.id)) in getattr(world, "rivals", set())
                friend = in_pact(world, p.id, side.id)
                if (rival or friend) and not side.collapsed and world.pyrng.random() < 0.5:
                    p.materials -= PROXY_MATERIALS
                    side.materials += PROXY_MATERIALS
                    side.military = min(1.0, side.military + PROXY_ARMY)
                    noted = world.__dict__.setdefault("_proxy_noted", set())
                    if (p.id, side.id, enemy.id) not in noted:
                        noted.add((p.id, side.id, enemy.id))
                        world.war_note(f"{p.name} arms {side.name} against {enemy.name}")
                    break


# ------------------------------------------------------------------------------------------------ village raids
def _village_raids(world, live):
    H, O = world.H, world.O
    villages = (O == 0) & (H > 10) & (world.zombie_near(6) == 0)      # (settled villages - not people in flight)
    if not villages.any():
        return
    from civilization import steps
    for c in live:
        drive = motives.militarism(c) + motives.need(c) - 0.3
        if (c.military < 0.3 or c.threat(c.m) > 0.2 or not c.capital or drive <= 0
                or world.pyrng.random() >= VRAID_CHANCE * drive * motives.settled(world)):
            continue
        win = c.m.get("win") or (slice(None), slice(None))
        mine = (O[win] == c.id) & (H[win] > 10)
        if not mine.any():
            continue
        near = villages[win] & (box_sum(mine, VRAID_REACH) > 0)
        if near.any():                                    # (over land: no raiding across the sea)
            near &= steps(mine, VRAID_REACH, through=world.statics.land[win]) <= VRAID_REACH
        if not near.any():
            continue
        ys, xs = np.nonzero(near)
        j = int(np.argmax(H[win][ys, xs]))
        r, k = int(ys[j] + (win[0].start or 0)), int(xs[j] + (win[1].start or 0))
        h = int(H[r, k])
        dead, taken = int(h * VRAID_KILL), int(h * VRAID_TAKE)
        H[r, k] -= dead + taken
        # (the captives are put to work on its own land, at the place nearest the village)
        ys2, xs2 = np.nonzero(mine)
        d = np.abs(ys2 + (win[0].start or 0) - r) + np.abs(xs2 + (win[1].start or 0) - k)
        i = int(np.argmin(d))
        tr, tc = int(ys2[i] + (win[0].start or 0)), int(xs2[i] + (win[1].start or 0))
        H[tr, tc] = min(255, int(H[tr, tc]) + taken)
        c.materials += 1.0
        mark(world, r, k, "village")
        n = world.__dict__.get("_vraid_n", 0) + 1
        world._vraid_n = n
        from fracture import _place
        why = "for food" if motives.need(c) > motives.militarism(c) else "for captives and loot"
        world.war_note(f"{c.name} raids the villages near {_place(world, (r, k))} {why}: "
                       f"{world.people(dead)} killed, {world.people(taken)} carried off", log=n % 5 == 1)
