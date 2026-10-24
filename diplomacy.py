"""Diplomacy with memory: what each government thinks of each other one, and what it remembers.

opinion(a, b), -1..1: what government a thinks of b = its standing view (base: kin - the same old country or
alliance - BASE_KIN, old rivals BASE_RIVAL, creeds: ideology.affinity) + its mood (recent dealings, fading:
MOOD_FADE a day) - its grudges (wrongs it hasn't forgiven, fading only slowly: GRUDGE_FADE).  Not symmetric: the
attacked remember an attack longer than the attacker does.

What moves it (change()):
  a war declared        the attacked: mood ATTACKED, grudge ATTACKED_GRUDGE; the attacker cools too (WAR_MOOD); the
                        attacked's pact partners take it badly (PACT_ANGER)
  land lost in a war    grudge LOST_LAND per LOST_PER districts it lost (up to LOST_MAX) - revanchism
  peace                 both PEACE_MOOD (relief)
  tribute, puppetry     the vassal: grudge TRIBUTE_GRUDGE / PUPPET_GRUDGE; one that throws it off: the overlord's
                        mood THROWN_OFF
  help                  aid, reconstruction, an expedition's or a ship's help: mood HELP (and it forgives a little:
                        HELP_FORGIVE)
  trade                 a little every round (trade.py)
What it does:
  wars            war._consider: every kind of war (rivalry, scarcity, border disputes) is hostility() x as likely
                  between the two - a country goes to war with the neighbour it hates, not the one it trades with;
                  and a country with an old grudge against a weaker neighbour may go to war to take back what it
                  lost (REVANCHE_*)
  pacts           neighbours (or trading partners) that have liked each other a long time (PACT_OPINION both ways)
                  may sign a defensive pact (PACT_CHANCE); a pact between two that have fallen out lapses
                  (PACT_LAPSE)
  trade           only between those who can stand each other (trade.TRADE_OPINION)
  tribute         an overlord picks on the neighbour it likes least; a resentful vassal throws it off sooner
"""
import numpy as np

EVERY = 10
MOOD_FADE = 0.004          # (a day: half-life about 170 days)
GRUDGE_FADE = 0.0004       # (half-life about 5 years)
BASE_KIN = 0.25
BASE_RIVAL = -0.4
BASE_PACT = 0.2
ATTACKED = -0.6
ATTACKED_GRUDGE = 0.3
WAR_MOOD = -0.3
PACT_ANGER = -0.25
LOST_LAND = 0.1
LOST_PER = 10
LOST_MAX = 0.5
PEACE_MOOD = 0.15
TRIBUTE_GRUDGE = 0.2
PUPPET_GRUDGE = 0.3
THROWN_OFF = -0.5
HELP = 0.35
HELP_FORGIVE = 0.05
HOSTILE = (0.15, 3.0)      # hostility(): 1 - 2 x opinion, within these
REVANCHE_CHANCE = 0.02     # per war check (x grudge x calm), a country with REVANCHE_GRUDGE against a neighbour no
REVANCHE_GRUDGE = 0.35     # stronger than itself (REVANCHE_RATIO) goes to war to take back what it lost
REVANCHE_RATIO = 1.0
PACT_OPINION = 0.45
PACT_CHANCE = 0.05
PACT_LAPSE = -0.1


def _rel(world):
    return world.__dict__.setdefault("relations", {})


def base(world, a, b):
    ca, cb = world.civs[a], world.civs[b]
    v = 0.0
    if ca.root is not None and ca.root == cb.root:
        v += BASE_KIN
    else:
        import war
        x = war.alliance(world, a)
        if x is not None and x == war.alliance(world, b):
            v += BASE_KIN
    if frozenset((a, b)) in getattr(world, "rivals", ()):
        v += BASE_RIVAL
    import globalaffairs
    if globalaffairs.in_pact(world, a, b):
        v += BASE_PACT
    import ideology
    v += ideology.affinity(ca, cb)
    return v


def opinion(world, a, b):
    if a == b:
        return 1.0
    m, g = _rel(world).get((a, b), (0.0, 0.0))
    return float(np.clip(base(world, a, b) + m - g, -1, 1))


def grudge(world, a, b):
    return _rel(world).get((a, b), (0.0, 0.0))[1]


def change(world, a, b, mood=0.0, grudge=0.0):
    """Government a's view of b: mood += `mood`, grudge += `grudge` (each kept within -1..1 / 0..1)."""
    if a == b or a <= 0 or b <= 0:
        return
    rel = _rel(world)
    m, g = rel.get((a, b), (0.0, 0.0))
    rel[(a, b)] = (float(np.clip(m + mood, -1, 1)), float(np.clip(g + grudge, 0, 1)))


def hostility(world, a, b):
    """How much likelier than usual a war between a and b is (by the worse of their views of each other)."""
    op = min(opinion(world, a, b), opinion(world, b, a))
    return float(np.clip(1.0 - 2.0 * op, *HOSTILE))


# ------------------------------------------------------------------------------------------------ events
def on_war(world, a, b):
    change(world, b, a, mood=ATTACKED, grudge=ATTACKED_GRUDGE)
    change(world, a, b, mood=WAR_MOOD)
    import globalaffairs
    for k in globalaffairs.pacts(world):
        if b in k:
            p = next(iter(k - {b}))
            if p != a:
                change(world, p, a, mood=PACT_ANGER)


def on_peace(world, w):
    a, b = w["a"], w["b"]
    change(world, a, b, mood=PEACE_MOOD)
    change(world, b, a, mood=PEACE_MOOD)
    for win_id, n in w.get("captured", {}).items():
        lose_id = b if win_id == a else a
        g = min(LOST_MAX, LOST_LAND * n / LOST_PER)
        if g >= 0.05:
            change(world, lose_id, win_id, grudge=g)
            if g >= 0.2:
                world.war_note(f"{world.civs[lose_id].name} will not forget the land {world.civs[win_id].name} took",
                               log=False)


def on_vassal(world, lord, vassal, puppet=False):
    change(world, vassal, lord, grudge=PUPPET_GRUDGE if puppet else TRIBUTE_GRUDGE)


def on_thrown_off(world, lord, vassal):
    change(world, lord, vassal, mood=THROWN_OFF)


def on_help(world, donor, to):
    change(world, to, donor, mood=HELP, grudge=-HELP_FORGIVE)
    change(world, donor, to, mood=HELP / 3)


# ------------------------------------------------------------------------------------------------ step
def step(world):
    if world.ticks % EVERY:
        return
    rel = _rel(world)
    if rel:
        fm = (1.0 - MOOD_FADE) ** EVERY
        fg = (1.0 - GRUDGE_FADE) ** EVERY
        dead = {c.id for c in world.civs if c.collapsed}
        for k, (m, g) in list(rel.items()):
            if k[0] in dead or k[1] in dead:
                del rel[k]
                continue
            m, g = m * fm, g * fg
            if abs(m) < 0.005 and g < 0.005:
                del rel[k]
            else:
                rel[k] = (m, g)
    if world.ticks % (3 * EVERY) == 0:
        _pacts(world)


def _pacts(world):
    import war
    import globalaffairs
    import trade
    pacts = globalaffairs.pacts(world)
    for k in list(pacts):                                 # (pacts between two that have fallen out lapse)
        a, b = tuple(k)
        if a >= len(world.civs) or b >= len(world.civs):
            continue
        ca, cb = world.civs[a], world.civs[b]
        if getattr(ca, "overlord", None) in (b,) or getattr(cb, "overlord", None) in (a,):
            continue                                      # (a vassal's bond is to its overlord, liked or not)
        if min(opinion(world, a, b), opinion(world, b, a)) < PACT_LAPSE:
            del pacts[k]
            world.war_note(f"the pact between {ca.name} and {cb.name} lapses - they have fallen out")
    touching = war.contacts(world)
    near = set(touching) | {tuple(sorted(k)) for k in trade.routes(world)}
    import motives
    for a, b in sorted(near):
        if a >= len(world.civs) or b >= len(world.civs):
            continue
        ca, cb = world.civs[a], world.civs[b]
        if (not globalaffairs._live(ca) or not globalaffairs._live(cb) or globalaffairs.in_pact(world, a, b)
                or war.key(a, b) in world.wars or getattr(ca, "overlord", None) is not None
                or getattr(cb, "overlord", None) is not None):
            continue
        if min(opinion(world, a, b), opinion(world, b, a)) >= PACT_OPINION and world.pyrng.random() < PACT_CHANCE:
            globalaffairs._sign(world, ca, cb, "long friendship")


def friend_and_foe(world, a):
    """(best friend, worst enemy) of government a among the living - names, for the map's hover text."""
    best = worst = None
    for c in world.civs:
        if not c.id or c.id == a or c.collapsed or not c.ai:
            continue
        op = opinion(world, a, c.id)
        if abs(op) < 0.2:
            continue
        if best is None or op > best[0]:
            best = (op, c.name)
        if worst is None or op < worst[0]:
            worst = (op, c.name)
    return (best[1] if best and best[0] > 0.2 else None), (worst[1] if worst and worst[0] < -0.2 else None)
