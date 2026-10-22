"""The recovery era: once the outbreak has peaked and burned out, the world knows how to deal with zombies.

era(world)    0..1.  After ERA_START days, once the zombies on the map have fallen below ERA_SHARE of their peak, it
              rises to 1 over ERA_RAMP days (and falls back, slowly, only if they climb past ERA_RELAPSE of the peak).
In the recovery era everybody - governments, towns, villages - has lived through it:
  bites       zombies bite WARY_BITE x era less (people keep their distance, doors barred, nobody goes near the sick)
              and the people on a tile kill WARY_KILL x era more of them (engine._bites);
  militias    wherever people live within MILITIA_REACH of zombies, armed townsfolk and villagers go out after them
              (MILITIA_*): a stray pack or a fresh outbreak in a town is hunted down in days;
  alert       every government mobilizes like a veteran (front.py).
Small outbreaks still happen - a horde out of the wilds, a bitten traveller - but they stay local: the world doesn't
fall a second time.
"""
import numpy as np

from civilization import box_sum

ERA_START = 250
ERA_SHARE = 0.25
ERA_RELAPSE = 0.5
ERA_RAMP = 100
WARY_BITE = 0.6
WARY_KILL = 3.0
MILITIA_EVERY = 2
MILITIA_REACH = 3
MILITIA_RATE = 0.03        # zombies killed per tile per round, per person within reach (up to 4 x the zombies there)
MILITIA_MIN_H = 30         # people within reach it takes to raise a militia


def era(world):
    return float(getattr(world, "era", 0.0))


def step(world):
    z = float(world.Z.sum())
    peak = max(getattr(world, "_z_peak", 0.0), z)
    world._z_peak = peak
    e = era(world)
    if world.ticks >= ERA_START and peak > 0 and z < ERA_SHARE * peak:
        if e == 0.0:
            world.note("the outbreak has burned out: the world has learned how to live with the dead "
                       "(every town keeps watch - new outbreaks are hunted down)")
        e = min(1.0, e + 1.0 / ERA_RAMP)
    elif z > ERA_RELAPSE * peak:
        e = max(0.0, e - 1.0 / ERA_RAMP)
    world.era = e
    if e > 0 and world.ticks % MILITIA_EVERY == 0:
        world.last_militia = _militia(world, e)


def _militia(world, e):
    Z, H = world.Z, world.H
    zt = Z > 0
    if not zt.any():
        return 0
    from engine import active_windows
    total = 0
    for win, wrap in active_windows(world, zt, MILITIA_REACH + 1):
        Zw, Hw = Z[win], H[win]
        people = box_sum(np.where(world.land[win] & (Hw > 10), Hw, 0).astype(np.int32), MILITIA_REACH)
        hit = (Zw > 0) & (people >= MILITIA_MIN_H)
        if not hit.any():
            continue
        z = Zw[hit].astype(np.float64)
        kill = np.minimum(z, np.floor(e * MILITIA_RATE * np.minimum(people[hit], 4 * z)
                                      + (world.rng.random(z.size) if world.stochastic else 0.5)))
        Zw[hit] = (z - kill).astype(Zw.dtype)
        total += int(kill.sum())
    return total
