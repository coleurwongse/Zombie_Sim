"""Global affairs: countries that aren't fighting for their lives take part in what happens elsewhere.

Expeditions   a strong country that is safe at home sends an expeditionary force to a fallen city anywhere it can
              reach (a shared border, ports at both ends, or an army strong enough to fly in): for CORPS_DAYS its
              troops sweep the hordes within CORPS_RADIUS of it (CORPS_*) - clearing the way for survivors to come back.
              It costs the sender materials, soldiers (people) and army strength.
Reconstruction a rich, safe country sends materials and food to a friend rebuilding after the outbreak (RECON_*).
Pacts         countries that have fought the zombies side by side (an expedition or peacekeepers), or that share an
              enemy, sign a defensive pact: they never fight each other, and when one is attacked the other joins
              the war (world.pacts; war.allied counts them).
Proxy wars    a power with a stake in a war - an old rival of one side, or a pact with the other - arms the side it
              favours: materials and army strength (PROXY_*).
Tributaries   a strong country makes a much weaker neighbour pay tribute (TRIBUTE_*): it pays a share of its food and
              materials, and the two are bound by a pact; a war won decisively ends with the loser a satellite.  A
              tributary throws its overlord off when the overlord falters (at war, in trouble, fallen).
Revolutions   a government in deep trouble - famine, morale breaking, a long war - may be overthrown (REVOLT_*): a new
              form of government (junta, republic, warlords...), a new name, a shaken army.
Conquest      a strong, aggressive country at peace with the zombies goes to war with a weaker neighbour for its land
              (CONQUEST_*).
Village raids an organized state raids the villages nobody governs near it: some killed, some carried off to work its
              land, their stores taken (VRAID_*).
Map marks     raids, strikes, landings, partisan actions, expeditions and revolutions are marked on the map for a few
              weeks (mark(); main.py draws them).
"""
import numpy as np

from civilization import box_sum

EVERY = 10
MARK_DAYS = 30
# expeditions
CORPS_ARMY = 0.5
CORPS_SIZE = 0.6
CORPS_MATERIALS = 60.0
CORPS_SAFE = 0.15           # the sender's danger at home must be below this
CORPS_CHANCE = 0.1          # per check, per able country (x 1 / caution)
CORPS_MAX = 1               # forces abroad per country at once
CORPS_DAYS = 120
CORPS_RADIUS = 10
CORPS_TILES = 20            # tiles swept per wave (x the sender's size)
CORPS_KILL = 0.25           # share of the zombies on a swept tile killed (x (0.5 + army strength))
CORPS_MIN_Z = 300           # a city with this many zombies within CORPS_RADIUS is worth an expedition
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
SATELLITE_TAKEN = 25        # a war in which the winner took this many districts and the loser is this much weaker
SATELLITE_POP = 0.5         # (people) ends with the loser a satellite
REVOLT_CHANCE = 0.03        # per check, for a government in deep trouble that isn't fighting for its life
REVOLT_THREAT = 0.3         # (with the zombies at the gates, nobody has time for a revolution)
REVOLT_COOLDOWN = 300
CONQUEST_CHANCE = 0.012     # per check, for a strong aggressive country with a weaker neighbour
CONQUEST_RATIO = 1.6
VRAID_CHANCE = 0.25
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
    return [m for m in getattr(world, "marks", []) if world.ticks - m[0] <= MARK_DAYS]


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
    world.note(f"PACT: {a.name} and {b.name} sign a defensive pact ({why})")


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
    if world.ticks % EVERY:
        return
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
            out.append((float(zr[r, k]) * (1.0 + pop), name, r, k))
    out.sort(reverse=True)
    world._corps_targets = (world.ticks, out[:60])
    return out[:60]


def _expeditions(world, live, corps):
    if not world.cities:
        return
    busy = {(x["r"], x["c"]) for x in corps}
    for c in live:
        if not _able(world, c) or world.pyrng.random() >= CORPS_CHANCE / max(c.traits.get("caution", 1.0), 0.5):
            continue
        import expeditions
        draw = getattr(expeditions, "draw_from_home", None)
        for _, name, r, k in _targets(world):
            if (r, k) in busy or not _can_reach(world, c, r, k):
                continue
            if draw is not None and not draw(world, c, CORPS_SOLDIERS):
                break
            corps.append(dict(donor=c.id, r=r, c=k, name=name, until=world.ticks + CORPS_DAYS, killed=0))
            busy.add((r, k))
            c.materials -= CORPS_MATERIALS * 0.25
            mark(world, r, k, "expedition")
            far = c.capital is not None and world.statics.landmass[c.capital] != world.statics.landmass[r, k]
            world.note(f"{c.name} sends an expeditionary force {'overseas ' if far else ''}to {name}")
            break


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
        world.note(f"{d.name}'s expeditionary force clears {x['name']} ({world.people(x['killed'])} zombies destroyed)")
    # (fighting side by side: the sender and whoever lives near there may sign a pact)
    o = int(world.O[x["r"], x["c"]])
    near = [c for c in world.civs if _live(c) and c.id != d.id and c.capital is not None
            and abs(c.capital[0] - x["r"]) + abs(c.capital[1] - x["c"]) < 40]
    if cleared and near and world.pyrng.random() < PACT_CHANCE * 2:
        _sign(world, d, near[0], f"the expedition to {x['name']}")


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
            world.note(f"{d.name} helps rebuild {r.name}: materials and food")
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
        if L.collapsed or not L.m or L.threat(L.m) > 0.5 or (war.at_war(world, L.id) and world.pyrng.random() < 0.05):
            c.overlord = None
            pacts(world).pop(frozenset((c.id, L.id)), None)
            world.note(f"{c.name} throws off {L.name}'s rule")
            if c.capital is not None:
                mark(world, *c.capital, "revolution")
            continue
        m = c.materials * TRIBUTE_SHARE
        c.materials -= m
        L.materials += m
        if c.food is not None and L.food is not None:
            f = c.food * TRIBUTE_SHARE
            c.food -= f
            L.food += f
    if world.ticks % TRIBUTE_EVERY:
        return
    touching = war.contacts(world)
    for s in live:
        if (s.military < 0.5 or s.threat(s.m) > 0.15 or war.at_war(world, s.id) or getattr(s, "overlord", None)
                or world.pyrng.random() >= TRIBUTE_CHANCE * s.traits.get("aggression", 1.0)):
            continue
        for w_ in live:
            k = (min(s.id, w_.id), max(s.id, w_.id))
            if (w_.id == s.id or touching.get(k, 0) < war.MIN_BORDER or getattr(w_, "overlord", None) is not None
                    or war.allied(world, s.id, w_.id) or w_.m.get("pop", 0) > TRIBUTE_POP * s.m.get("pop", 1)
                    or war.at_war(world, w_.id)):
                continue
            if w_.military < 0.6 * s.military or world.pyrng.random() < 0.6:
                make_tributary(world, s, w_, "demands tribute")
            else:
                war.declare(world, s.id, w_.id, f"it refused to pay tribute")
                if w_.capital is not None:
                    mark(world, *w_.capital, "conquest")
            break


def make_tributary(world, lord, vassal, how="demands tribute"):
    vassal.overlord = lord.id
    pacts(world)[frozenset((lord.id, vassal.id))] = world.ticks
    world.note(f"{lord.name} {how}: {vassal.name} becomes its {'satellite' if 'war' in how else 'tributary'}")
    if vassal.capital is not None:
        mark(world, *vassal.capital, "tribute")


# ------------------------------------------------------------------------------------------------ revolutions
def _revolutions(world, live):
    import govern
    for c in live:
        weary = getattr(c, "riot_hit", 0) >= 6
        trouble = c.famine or c.morale <= 3 or weary
        if (not trouble or c.threat(c.m) >= REVOLT_THREAT
                or world.ticks - getattr(c, "_revolution", -10 ** 6) < REVOLT_COOLDOWN
                or world.pyrng.random() >= REVOLT_CHANCE * (0.5 if c.gov == "national" else 1.0)):
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
        what = {"junta": "the army takes power", "democracy": "the people rise and declare a republic",
                "warlord": "the country falls to its warlords", "tribal": "power passes to the clans"}[new]
        world.note(f"REVOLUTION in {old_name}: {what} - now {c.name}")
        if c.capital is not None:
            mark(world, *c.capital, "revolution")


# ------------------------------------------------------------------------------------------------ conquest
def _conquest(world, live):
    import war
    touching = war.contacts(world)
    for a in live:
        aggressive = a.traits.get("aggression", 1.0) >= 1.15 or a.gov in ("junta", "warlord")
        if (not aggressive or a.military < 0.6 or a.threat(a.m) > 0.15 or war.at_war(world, a.id)
                or world.pyrng.random() >= CONQUEST_CHANCE * a.traits.get("aggression", 1.0)):
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
                        world.note(f"{p.name} arms {side.name} against {enemy.name}")
                    break


# ------------------------------------------------------------------------------------------------ village raids
def _village_raids(world, live):
    H, O = world.H, world.O
    villages = (O == 0) & (H > 10)
    if not villages.any():
        return
    for c in live:
        if (c.military < 0.3 or c.threat(c.m) > 0.2 or not c.capital
                or world.pyrng.random() >= VRAID_CHANCE * c.traits.get("aggression", 1.0) * 0.5):
            continue
        win = c.m.get("win") or (slice(None), slice(None))
        mine = (O[win] == c.id) & (H[win] > 10)
        if not mine.any():
            continue
        near = villages[win] & (box_sum(mine, VRAID_REACH) > 0)
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
        if n % 5 == 1:
            from fracture import _place
            world.note(f"{c.name} raids the villages near {_place(world, (r, k))}: "
                       f"{world.people(dead)} killed, {world.people(taken)} carried off")
