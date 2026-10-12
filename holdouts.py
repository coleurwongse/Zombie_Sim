"""Holdouts: now and then a city the horde is about to overrun doesn't fall.

Every CHECK_EVERY ticks, each city (meta.json cities) that still has people, is about to be overrun (THREAT zombies
within 3 tiles) and isn't fortified yet gets ONE roll (HOLDOUT_CHANCE - so it happens, but not often): its people
barricade the streets (only the bigger half of the cities: small towns just fall).  If its government still stands, the city becomes one of its fortified sites (a garrison at
full strength); if nobody governs it any more, it becomes a free city of its own.  A barricaded city keeps the horde
out for as long as enough people man it (defense 7) - but it can still starve, riot or be worn down.
"""
import numpy as np

import economy
import govern

CHECK_EVERY = 5
HOLDOUT_CHANCE = 0.025
THREAT = 250              # zombies within 3 tiles: the horde is at the gates
MIN_PEOPLE = 100          # people in the city centre needed to man the barricades
BIG_CITY = 0.5            # only cities at least as big as this share of the map's cities (the median) get a roll
RADIUS = 1                # the barricaded block: (2 x RADIUS + 1) square around the centre
LEVEL = 7
FREE_RADIUS = 2           # a free city takes the populated land this close to its centre
FREE_FOOD_TICKS = 150     # ... with this much food put by
FREE_MATERIALS = 40.0


def step(world):
    if world.ticks % CHECK_EVERY or not world.cities:
        return
    checked = getattr(world, "_holdout_checked", None)
    if checked is None:
        checked = world._holdout_checked = set()
    big = getattr(world, "_holdout_big", None)
    if big is None:
        big = world._holdout_big = float(np.quantile([ct[3] for ct in world.cities], BIG_CITY))
    near3 = world.zombie_near(3)
    H, Z, O, D = world.H, world.Z, world.O, world.D
    forts = None
    for name, r, c, pop in world.cities:
        if pop < big or (r, c) in checked or H[r, c] < MIN_PEOPLE or near3[r, c] < THREAT or Z[r, c] > H[r, c]:
            continue
        if forts is None:
            forts = world.fort_mask()
        if forts[r, c]:
            continue
        checked.add((r, c))
        if world.pyrng.random() >= HOLDOUT_CHANCE:
            continue
        _barricade(world, name, r, c)
        forts = None


def _block(world, r, c, radius):
    r0, r1 = max(r - radius, 0), min(world.rows, r + radius + 1)
    c0, c1 = max(c - radius, 0), min(world.cols, c + radius + 1)
    return [(rr, cc) for rr in range(r0, r1) for cc in range(c0, c1)
            if world.statics.land[rr, cc] and world.H[rr, cc] > 10 and world.Z[rr, cc] <= world.H[rr, cc]]


def _barricade(world, name, r, c):
    owner = world.civs[int(world.O[r, c])]
    tiles = _block(world, r, c, RADIUS) or [(r, c)]
    if owner.id and owner.ai and not owner.collapsed:
        civ = owner
        world.note(f"{name} barricades itself - the city holds out for {owner.name}")
    else:
        civ = world.add_civ(morale=8)
        if civ is None:
            return
        region = np.zeros(world.H.shape, dtype=bool)
        for rc in _block(world, r, c, FREE_RADIUS) or [(r, c)]:
            region[rc] = True
        civ.gov = "junta" if world.pyrng.random() < 0.5 else "democracy"
        civ.successor, civ.founded = True, world.ticks
        prev = world.last_owner[r, c]
        civ.root = world.civs[int(prev)].root if prev else civ.id
        civ.name = f"Free City of {name}"
        world.O[region] = civ.id
        pop = float(np.maximum(world.H[region], 0).sum())
        civ.food = pop * economy.FOOD_PER_PERSON * FREE_FOOD_TICKS
        civ.materials = FREE_MATERIALS
        civ.military = 0.3
        civ.alert = 1.0
        civ.capital = (r, c)
        civ.peace = False
        alliance = getattr(world, "alliance_of", {}).get(civ.root)
        if alliance is not None:
            world.alliance_of[civ.id] = alliance
        world.note(f"{name} barricades itself and holds out on its own: the {civ.name}"
                   f"{' (' + govern.LABEL[civ.gov] + ')' if govern.LABEL.get(civ.gov) else ''}")
    for rc in tiles:
        world.D[rc] = max(world.D[rc], LEVEL)
        world.Z[rc] = 0
    civ.sites.append(dict(center=(r, c), tiles=tiles, level=LEVEL, target=LEVEL, holdout=True))
