"""Governments merging.  Bigger organization is more stable, and everybody wants that - unless they're fighting.

Every MERGE_EVERY ticks, each pair of governments whose land touches (or comes within 2 tiles) and who are not at
war may merge.  The chance is high for fragments of the same former country (they share a `root`), lower for
unrelated colonies, and nil between the original nations.  The smaller one is absorbed: its land, garrisons, stores
and soldiers join the larger one, which gets a morale boost.  (civilization.py: big governments also lose
morale more slowly.)
"""
import numpy as np

import govern
import war

MERGE_EVERY = 10
REACH = 2                  # tiles apart that still count as neighbours
MIN_CONTACT = 3            # border / near-border tile pairs needed
KIN_CHANCE = 0.45          # per check, fragments of one former country
STRANGER_CHANCE = 0.12     # per check, unrelated colonies
MERGE_MORALE_BONUS = 1
MIN_MORALE = 4             # a collapsing government isn't a partner
SPLIT_COOLDOWN = 150       # a state that broke away doesn't rejoin anyone for this long
                           # (forms of government also matter: republics merge readily, warlords hardly ever)


def neighbours(world, reach=REACH):
    """{(a, b): number of tile pairs within `reach` tiles of each other} for governments a < b."""
    O = world.O
    rows, cols = O.shape
    counts = {}
    for dr in range(-reach, reach + 1):
        for dc in range(-reach, reach + 1):
            if (dr, dc) <= (0, 0):
                continue
            r0, r1 = max(0, dr), rows + min(0, dr)
            c0, c1 = max(0, dc), cols + min(0, dc)
            a = O[r0:r1, c0:c1]
            b = O[r0 - dr:r1 - dr, c0 - dc:c1 - dc]
            m = (a > 0) & (b > 0) & (a != b)
            if m.any():
                lo = np.minimum(a[m], b[m]).astype(np.int64)
                hi = np.maximum(a[m], b[m]).astype(np.int64)
                keys, n = np.unique(lo * 1000 + hi, return_counts=True)
                for k, v in zip(keys, n):
                    counts[(int(k // 1000), int(k % 1000))] = counts.get((int(k // 1000), int(k % 1000)), 0) + int(v)
    return counts


def merge(world, big, small, why=""):
    """Absorb `small` into `big`."""
    O = world.O
    mine = O == small.id
    O[mine] = big.id
    pop_b = max(1, big.m.get("pop", 1) if big.m else 1)
    pop_s = max(1, small.m.get("pop", 1) if small.m else 1)
    big.military = min(1.0, (big.military * pop_b + small.military * pop_s) / (pop_b + pop_s) + 0.05)
    big.materials += small.materials
    big.alert = max(big.alert, small.alert)
    if big.food is not None and small.food is not None:
        big.food += small.food
    big.sites.extend(small.sites)
    big.kills += small.kills
    big.morale = min(10, max(big.morale, small.morale) + MERGE_MORALE_BONUS)
    for civ in world.civs:                         # fragments pointing at the absorbed one now follow the survivor
        if civ.root == small.id:
            civ.root = big.root
    small.sites, small.bases, small.active = [], [], set()
    small.collapsed = True
    small.merged_into = big.id
    small.remnant = False
    world.note(f"{small.name} merges into {big.name}" + (f" ({why})" if why else ""))


def step(world):
    if world.ticks % MERGE_EVERY:
        return
    civs = world.civs
    for (a, b), contact in sorted(neighbours(world).items()):
        if contact < MIN_CONTACT:
            continue
        ca, cb = civs[a], civs[b]
        if not (ca.ai and cb.ai) or ca.collapsed or cb.collapsed or war.at_war(world, a) or war.at_war(world, b):
            continue
        if ca.morale < MIN_MORALE or cb.morale < MIN_MORALE:
            continue
        if any(c.split_from is not None and world.ticks - c.founded < SPLIT_COOLDOWN for c in (ca, cb)):
            continue
        kin = ca.root == cb.root
        if not kin and not (ca.successor and cb.successor):
            continue                               # separate nations stay separate
        p = (KIN_CHANCE if kin else STRANGER_CHANCE) * govern.mod(ca, "merge") * govern.mod(cb, "merge")
        if ca.gov != cb.gov:
            p *= 0.6
        if ca.famine != cb.famine:
            p *= 2                                 # one of them badly needs the other's stores
        if world.pyrng.random() >= p:
            continue
        pa = ca.m.get("pop", 0) if ca.m else 0
        pb = cb.m.get("pop", 0) if cb.m else 0
        big, small = (ca, cb) if (pa, ca.id) >= (pb, cb.id) else (cb, ca)
        merge(world, big, small, "same former country" if kin else "")
