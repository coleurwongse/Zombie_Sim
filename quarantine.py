"""Quarantine: a nation that sees the horde outside its borders shuts them.

While a civilization has QUARANTINE active:
  * people can't walk into its land from outside (kernel `closed`, and flow_away in people/civilization);
  * its airports refuse flights from infected airports (kernel `closed`);
  * zombies leaving a heavily infested tile into its secure(ish) land - or the buffer strip just outside
    it - are slowed (kernel `qfac`);
  * border patrols kill a few zombies on and next to its land every other tick (costs materials);
  * the closed borders cost it trade (economy.py).
"""
import numpy as np

from civilization import box_sum

SLOW = 0.75            # share of the zombies that still get through into secure land (a fence slows a horde, it
BUFFER_SLOW = 0.9      # ... and into the strip just outside the border                  doesn't stop it)
SECURE_NEAR = 150      # 'secure(ish)': fewer zombies than this within 2 tiles
PATROL_EVERY = 2
PATROL_KILL = 0.06     # share of zombies killed on patrolled tiles
PATROL_MIN_Z = 3
PATROL_COST = 0.004    # materials per zombie killed


def update(world):
    closed = {c.id for c in world.civs if c.ai and c.closed}
    for k in sorted(closed - world.closed):
        world.note(f"{world.civs[k].name} closes its borders and airports")
    for k in sorted(world.closed - closed):
        world.note(f"{world.civs[k].name} reopens its borders")
    world.closed = closed
    if not closed:
        world.qfac = None
        return
    arr = np.zeros(len(world.civs), dtype=bool)
    arr[list(closed)] = True
    shut = arr[world.O]
    secure = shut & (world.zombie_near(2) < SECURE_NEAR)
    buffer_ = (box_sum(shut, 1) > 0) & ~shut
    world.qfac = np.where(secure, SLOW, np.where(buffer_, BUFFER_SLOW, 1.0))
    if world.ticks % PATROL_EVERY:
        return
    for k in closed:
        civ = world.civs[k]
        win = world.bbox(k, 2)
        Z = world.Z[win]                                      # a view: kills go straight into the map
        mine = world.O[win] == k
        patrolled = (box_sum(mine, 1) > 0) & (Z >= PATROL_MIN_Z)
        if not patrolled.any() or civ.materials <= 0:
            continue
        kills = np.where(patrolled, np.maximum(1, (Z * PATROL_KILL * world.jitter(0.3)).astype(np.int32)), 0)
        kills = np.minimum(kills, Z)
        cost = float(kills.sum()) * PATROL_COST
        if cost > civ.materials:
            kills = (kills * (civ.materials / cost)).astype(np.int32)
            cost = float(kills.sum()) * PATROL_COST
        civ.materials -= cost
        Z -= kills.astype(np.int32)
        civ.kills += int(kills.sum())
