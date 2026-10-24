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
Vigilance (the same, place by place): a district the dead have come near that has since lived in peace for
VIGIL_QUIET days (no zombie within VIGIL_REACH tiles; after VIGIL_ALL days, any district) keeps watch - and keeps it for VIGIL_FADE days after the dead come back.  On a
small map, where a reservoir of zombies (Mordor) can keep the world-wide count high for years, a late horde still
meets towns that know what to do, not a second fall of the whole continent.
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
VIGIL_START = 150          # (days into the outbreak)
VIGIL_QUIET = 90
VIGIL_REACH = 10
VIGIL_FADE = 200
VIGIL_ALL = 400            # (before this, only districts the dead have come near: a continent the outbreak hasn't
                           #  reached yet doesn't know what it is up against)


def era(world):
    return float(getattr(world, "era", 0.0))


def wary(world):
    """0..1 per tile: how ready its people are - the recovery era, or the district's own vigilance.  None: nowhere."""
    v = getattr(world, "vigil", None)
    e = era(world)
    if v is None or v.shape != world.H.shape:
        return None if e <= 0 else np.full(world.H.shape, e, dtype=np.float32)
    return np.maximum(v, np.float32(e)) if e > 0 else v


def _vigil(world):
    if world.ticks < VIGIL_START or getattr(world, "H0", None) is None:
        return
    calm = getattr(world, "_calm_days", None)
    if calm is None or calm.shape != world.H.shape:
        calm = world._calm_days = np.zeros(world.H.shape, dtype=np.int16)
        world.vigil = np.zeros(world.H.shape, dtype=np.float32)
        world._seen_dead = np.zeros(world.H.shape, dtype=bool)
    quiet = world.zombie_near(VIGIL_REACH) == 0
    world._seen_dead |= ~quiet
    calm[:] = np.where(quiet, np.minimum(calm + 1, 30000), 0)
    v = world.vigil
    v -= np.float32(1.0 / VIGIL_FADE)
    np.maximum(v, 0, out=v)
    v[(calm >= VIGIL_QUIET) & (world._seen_dead | (world.ticks >= VIGIL_ALL))] = 1.0


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
    _vigil(world)
    if world.ticks % MILITIA_EVERY == 0:
        w_ = wary(world)
        if w_ is not None:
            world.last_militia = _militia(world, w_)


def _militia(world, e):
    """`e`: readiness, one number for the whole map or per tile."""
    Z, H = world.Z, world.H
    zt = Z > 0
    if not zt.any():
        return 0
    e = np.broadcast_to(np.asarray(e, dtype=np.float32), Z.shape)
    from engine import active_windows
    total = 0
    for win, wrap in active_windows(world, zt, MILITIA_REACH + 1):
        Zw, Hw = Z[win], H[win]
        people = box_sum(np.where(world.land[win] & (Hw > 10), Hw, 0).astype(np.int32), MILITIA_REACH)
        hit = (Zw > 0) & (people >= MILITIA_MIN_H) & (e[win] > 0)
        if not hit.any():
            continue
        z = Zw[hit].astype(np.float64)
        kill = np.minimum(z, np.floor(e[win][hit] * MILITIA_RATE * np.minimum(people[hit], 4 * z)
                                      + (world.rng.random(z.size) if world.stochastic else 0.5)))
        Zw[hit] = (z - kill).astype(Zw.dtype)
        total += int(kill.sum())
    return total
