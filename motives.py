"""Why governments do what they do: the state a country is in decides what it does abroad (globalaffairs.py,
warfare.py, war.py, crime.py), rather than the dice alone.

security     0..1  safe at home: no danger now, fed, in good heart, at peace - free to look outward.
instability  0..1  (smoothed over a couple of months, update()) how close it is to coming apart: morale breaking,
                   famine and shortages, unrest and riots in its towns, the people it has lost (a discredited
                   government), a war going badly, foreign rule (paying tribute), a new state not yet settled, the
                   kind of regime (warlords and juntas sit less securely than republics).
                   -> revolutions, paramilitaries and smugglers grow in unstable countries.
militarism   0..1  how readily it reaches for the gun: juntas and warlords most, then a strong army and an
                   aggressive temper.  -> raids (on enemies at war, on villages nobody governs), tribute demands.
need         0..1  short of food and materials (war.scarcity).  -> raids, wars for what the neighbours have.
ambition     0..1  secure, and inclined to expand: an aggressive temper or a militarist regime, with the means.
                   -> expeditions abroad (that end in colonies), wars of conquest, tributaries.
"""
import numpy as np

MILITARIST = {"junta": 1.0, "warlord": 0.9, "syndicate": 0.85, "national": 0.35, "tribal": 0.4, "democracy": 0.15}
REGIME_SHAKY = {"warlord": 0.15, "junta": 0.08, "syndicate": 0.12, "national": 0.0, "tribal": 0.0,
                "democracy": -0.05}
SMOOTH = 0.2               # (per update: the new reading's weight)


def _ok(c):
    return bool(c.id and c.ai and not c.collapsed and c.m and c.m.get("n"))


def security(world, c):
    if not _ok(c):
        return 0.0
    import war
    s = (1.0 - min(1.0, c.threat(c.m) / 0.3)) * min(1.0, c.morale / 8.0) * (0.0 if c.famine else 1.0)
    s *= 1.0 - 0.5 * war.scarcity(c)
    if war.at_war(world, c.id):
        s *= 0.6
    return float(max(0.0, s))


def instability(c):
    return float(getattr(c, "instability", 0.0))


def militarism(c):
    import govern
    m = 0.6 * MILITARIST.get(c.gov, 0.35) + 0.4 * min(1.0, c.military)
    return float(np.clip(m * c.traits.get("aggression", 1.0) * (0.7 + 0.3 * govern.mod(c, "aggression")), 0, 1))


def need(c):
    import war
    return war.scarcity(c)


def ambition(world, c):
    import govern
    temper = c.traits.get("aggression", 1.0) * govern.mod(c, "aggression")
    drive = float(np.clip(0.5 * temper + 0.5 * militarism(c), 0, 1.5))
    means = min(1.0, 0.4 + c.military) * min(1.0, c.materials / 80.0 + 0.3)
    return float(np.clip(security(world, c) * drive * means, 0, 1))


def update(world):
    """Instability for every living government (called every globalaffairs.EVERY days)."""
    import war
    n = len(world.civs)
    O = world.O
    land = world.statics.land & (O > 0) & (world.H > 10)
    tiles = np.bincount(O[land], minlength=n).astype(np.float64)
    U = getattr(world, "U", None)
    pop = np.bincount(O[land], weights=np.maximum(world.H[land], 0), minlength=n)
    unrest = (np.bincount(O[land], weights=np.clip(U[land], 0, 2) * np.maximum(world.H[land], 0), minlength=n)
              / np.maximum(pop, 1) if U is not None else np.zeros(n))         # (where the people are)
    riot = getattr(world, "riot", None)
    riots = (np.bincount(O[land & riot], minlength=n) / np.maximum(tiles, 1)
             if riot is not None and riot.shape == O.shape else np.zeros(n))
    losing = {}
    for w in world.wars.values():                      # (ground lost in a war)
        for win_id, k in w.get("captured", {}).items():
            lose = w["b"] if win_id == w["a"] else w["a"]
            losing[lose] = losing.get(lose, 0) + k
    for c in world.civs:
        if not _ok(c):
            continue
        morale = float(np.clip((8.0 - c.morale) / 8.0, 0, 1))
        hunger = 1.0 if c.famine else war.scarcity(c)
        lost = min(1.0, c.m.get("damage", 0.0))         # (a government that lost its people is discredited)
        young = 0.1 if c.successor and world.ticks - c.founded < 200 else 0.0
        raw = (0.3 * morale + 0.3 * hunger + 0.5 * min(1.0, unrest[c.id]) + min(0.3, 4.0 * riots[c.id])
               + 0.3 * lost + young
               + (0.1 if war.at_war(world, c.id) else 0.0) + min(0.2, losing.get(c.id, 0) / 100.0)
               + (0.12 if getattr(c, "overlord", None) is not None else 0.0)
               + REGIME_SHAKY.get(c.gov, 0.0))
        raw = float(np.clip(raw, 0, 1))
        c.instability = (1 - SMOOTH) * getattr(c, "instability", raw) + SMOOTH * raw
