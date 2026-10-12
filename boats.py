"""The sea: refugees in boats, and shipping (trade and food) between ports.

Refugee boats
  Every BOAT_EVERY ticks, people on coasts the zombies are reaching (a horde close by, or zombies already among them)
  put to sea: the most frightened coastal districts each send a boatload to the nearest safe coast across the same
  water (no zombies near it, room for more people; up to BOAT_RANGE tiles away; never into a country that has shut
  its borders, unless it's their own).  A port nearby means big ships: much bigger loads.  Some of those on board
  were bitten before they left: they arrive as zombies (more of them the more zombies there were where they boarded) -
  that's how the outbreak jumps across straits and seas.
Ocean ships
  From a frightened district with a port, now and then (SHIP_CHANCE) a big ship takes refugees much further: to a
  safe port anywhere on the same ocean (bigger ports likelier), across the Pacific or the Atlantic.  A long voyage
  lets an infection spread on board: besides those bitten before leaving, a few more turn on the way (SHIP_TURN).
Shipping
  A port works while its government holds it (people there, not overrun).  Every working port earns materials from
  trade, scaled by how much of the world's shipping is still running (trade collapses as the world does) and halved
  for a nation with shut borders.  Nations with ports and full granaries ship food to nations with ports that are
  running out (importers pay materials), up to what their ports can handle.
"""
import numpy as np

from labels import label
from terrain import is_water

BOAT_EVERY = 2
BOAT_FEAR = 90             # zombies within 4 tiles that make a coastal district take to the boats ...
BOAT_MIN_POP = 30          # ... if it has at least this many people
BOATS_PER_TICK = 90        # at most this many boatloads leave per round (the most frightened districts first)
BOAT_SHARE = 0.2           # a district sends at most this share of its people per round ...
BOAT_LOAD = 25             # ... and a boatload holds this many (x PORT_LOAD per port size nearby)
PORT_LOAD = 1.0
BOAT_RANGE = 60            # tiles
SAFE_NEAR = 15             # a safe coast has fewer zombies than this within 8 tiles
SAFE_ROOM = 200            # ... and fewer people than this
INFECTED = 0.45            # share of the zombie:people ratio where they boarded that arrives as zombies
SHIP_CHANCE = 0.12         # a frightened district with a port sends an ocean ship this often per round ...
SHIP_MIN_PORT = 2          # ... if its port is at least this big
SHIP_LOAD = 120            # people aboard an ocean ship
SHIP_TURN = 0.025          # share of those aboard who turn on the way (on top of the ones bitten before leaving)
SHIP_MIN_RANGE = 60        # (shorter trips are ordinary boats)
PORT_REACH = 2             # a port serves the coast within this many tiles
TRADE = 0.012              # materials per tick per unit of port size (x the world's shipping still running)
FOOD_EXPORT_TICKS = 60     # granaries above this many ticks of food can export ...
FOOD_IMPORT_TICKS = 20     # ... to nations below this many
FOOD_PER_PORT = 0.03       # food a unit of port size can unload per tick
FOOD_PRICE = 0.5           # materials paid per unit of food


class Coasts:
    """Water bodies and coastal tiles - terrain only, worked out once."""

    def __init__(self, world):
        S = world.statics
        water = ~S.land
        lab, n = label(water)
        if world.wrap and n:                              # the same sea on both sides of the date line
            left, right = lab[:, 0], lab[:, -1]
            pairs = {(int(a), int(b)) for a, b in zip(left, right) if a and b and a != b}
            parent = list(range(n + 1))

            def find(x):
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x
            for a, b in pairs:
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
            roots = np.array([find(i) for i in range(n + 1)])
            lab = roots[lab]
        self.water_label = lab
        body = np.zeros(lab.shape, dtype=np.int32)
        flat = lab.ravel()
        for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            t = S.nbr[d]
            nb = np.where(t >= 0, flat[np.where(t >= 0, t, 0)], 0).reshape(lab.shape)
            body = np.where(S.land & (body == 0) & (nb > 0), nb, body)
        self.body = body                                   # for coastal land: which water body it's on (0 = inland)
        self.coast = body > 0
        idx = np.flatnonzero(self.coast)
        self.coast_idx = idx
        self.coast_r, self.coast_c = np.divmod(idx, lab.shape[1])
        self.coast_body = body.ravel()[idx]
        # ports: the coast each one serves, and its size
        self.port_size = np.zeros(lab.shape, dtype=np.int32)      # the coast each port serves (boat loads)
        self.port_tile = np.zeros(lab.shape, dtype=np.int32)      # the ports themselves (trade capacity)
        for r, c, s in getattr(world, "ports", []):
            self.port_tile[r, c] = max(self.port_tile[r, c], s)
            r0, r1 = max(0, r - PORT_REACH), min(lab.shape[0], r + PORT_REACH + 1)
            c0, c1 = max(0, c - PORT_REACH), min(lab.shape[1], c + PORT_REACH + 1)
            self.port_size[r0:r1, c0:c1] = np.maximum(self.port_size[r0:r1, c0:c1], s)
        self.port_size[~self.coast] = 0


def coasts(world):
    c = getattr(world, "_coasts", None)
    if c is None:
        c = world._coasts = Coasts(world)
    return c


def step(world):
    shipping(world)
    if world.ticks % BOAT_EVERY == 0:
        world.last_boats = refugee_boats(world)


def refugee_boats(world):
    C = coasts(world)
    if C.coast_idx.size == 0:
        return 0
    H, Z, O = world.H, world.Z, world.O
    Hf, Zf, Of = H.ravel(), Z.ravel(), O.ravel()
    near4 = world.zombie_near(4).ravel()[C.coast_idx]
    hs = Hf[C.coast_idx]
    zs = Zf[C.coast_idx]
    scared = (hs >= BOAT_MIN_POP) & ((near4 >= BOAT_FEAR) | ((zs > 0) & (zs * 2 >= hs)))
    if not scared.any():
        return 0
    cand = np.flatnonzero(scared)
    fear = near4[cand] / np.maximum(hs[cand], 1)
    if cand.size > BOATS_PER_TICK:
        cand = cand[np.argpartition(-fear, BOATS_PER_TICK)[:BOATS_PER_TICK]]
    near8 = world.zombie_near(8).ravel()[C.coast_idx]
    safe = (near8 < SAFE_NEAR) & (hs < SAFE_ROOM) & world.statics.land.ravel()[C.coast_idx]
    if not safe.any():
        return 0
    closed = getattr(world, "closed", set()) or set()
    rows, cols = H.shape
    sr, sc = C.coast_r[safe], C.coast_c[safe]
    sb, si = C.coast_body[safe], C.coast_idx[safe]
    so = Of[si]
    shut = np.isin(so, list(closed)) if closed else np.zeros(so.shape, dtype=bool)
    moved = 0
    rnd = world.rng
    for k in cand:
        src = C.coast_idx[k]
        r, c, body, owner = C.coast_r[k], C.coast_c[k], C.coast_body[k], Of[src]
        ok = (sb == body) & ~(shut & (so != owner))
        if not ok.any():
            continue
        dc = np.abs(sc - c)
        if world.wrap:
            dc = np.minimum(dc, cols - dc)
        dist = np.hypot(sr - r, dc)
        dist = np.where(ok & (dist <= BOAT_RANGE) & (dist >= 2), dist, np.inf)
        j = int(np.argmin(dist))
        if not np.isfinite(dist[j]):
            continue
        dst = si[j]
        port = C.port_size.ravel()[src]
        load = BOAT_LOAD * (1 + PORT_LOAD * port)
        n = int(min(Hf[src] * BOAT_SHARE, load, 255 - Hf[dst]))
        if n <= 0:
            continue
        ratio = min(1.0, Zf[src] / max(Hf[src], 1))
        bitten = int(rnd.binomial(n, min(1.0, ratio * INFECTED))) if world.stochastic else int(n * ratio * INFECTED)
        Hf[src] -= n
        Hf[dst] += n - bitten
        Zf[dst] += bitten
        moved += n
        if port >= SHIP_MIN_PORT and rnd.random() < SHIP_CHANCE:
            moved += _ocean_ship(world, C, src, body, owner, ratio)
        if n >= 40 and world.pyrng.random() < 0.2:
            from fracture import _place
            world.note(f"boats carry {n} refugees from {_place(world, (int(r), int(c)))} to "
                       f"{_place(world, (int(sr[j]), int(sc[j])))}" + (f" ({bitten} infected)" if bitten else ""))
    return moved


def _ports_by_body(world, C):
    cache = getattr(world, "_ship_ports", None)
    if cache is None:
        idx = np.array([r * world.cols + c for r, c, s in world.ports if C.body[r, c] > 0], dtype=np.int64)
        size = np.array([s for r, c, s in world.ports if C.body[r, c] > 0], dtype=np.float64)
        cache = world._ship_ports = (idx, size, C.body.ravel()[idx] if idx.size else idx)
    return cache


def _ocean_ship(world, C, src, body, owner, ratio):
    """A big ship from a frightened port to a safe port far away on the same ocean."""
    idx, size, pbody = _ports_by_body(world, C)
    if idx.size == 0:
        return 0
    Hf, Zf, Of = world.H.ravel(), world.Z.ravel(), world.O.ravel()
    r, c = divmod(int(src), world.cols)
    pr, pc = np.divmod(idx, world.cols)
    dc = np.abs(pc - c)
    if world.wrap:
        dc = np.minimum(dc, world.cols - dc)
    dist = np.hypot(pr - r, dc)
    closed = getattr(world, "closed", set()) or set()
    near8 = world.zombie_near(8).ravel()[idx]
    ok = ((pbody == body) & (dist >= SHIP_MIN_RANGE) & (Of[idx] > 0) & (Hf[idx] > 10) & (Hf[idx] < 240)
          & (near8 < SAFE_NEAR))
    if closed:
        ok &= ~(np.isin(Of[idx], list(closed)) & (Of[idx] != owner))
    if not ok.any():
        return 0
    w = np.where(ok, size, 0.0)
    j = int(world.rng.choice(idx.size, p=w / w.sum())) if world.stochastic else int(np.argmax(w))
    dst = idx[j]
    n = int(min(Hf[src] * BOAT_SHARE, SHIP_LOAD, 255 - Hf[dst]))
    if n <= 0:
        return 0
    p = min(1.0, ratio * INFECTED + SHIP_TURN)
    bitten = int(world.rng.binomial(n, p)) if world.stochastic else int(n * p)
    Hf[src] -= n
    Hf[dst] += n - bitten
    Zf[dst] += bitten
    world.ships = getattr(world, "ships", 0) + 1
    if bitten or world.pyrng.random() < 0.3:
        from fracture import _place
        world.note(f"a ship carries {n} refugees from {_place(world, (r, c))} across the ocean to "
                   f"{_place(world, divmod(int(dst), world.cols))}" + (f" - {bitten} turn on arrival" if bitten else ""))
    return n


def shipping(world):
    C = coasts(world)
    if not world.ports:
        return
    H, Z, O = world.H, world.Z, world.O
    working = (C.port_tile > 0) & (O > 0) & (H > 10) & (Z * 3 < H)
    cap = np.bincount(O[working], weights=C.port_tile[working], minlength=len(world.civs))
    total = getattr(world, "_port_total", None)
    if total is None:
        total = world._port_total = max(1.0, float(cap.sum()))
    running = min(1.0, float(cap.sum()) / total)            # how much of the world's shipping still runs
    world.trade_index = running
    exporters, importers = [], []
    for c in world.civs:
        if c.is_anarchy or not c.ai or c.collapsed:
            continue
        c.ports = float(cap[c.id])
        if not c.ports:
            continue
        c.materials += TRADE * c.ports * running * (0.5 if c.closed else 1.0)
        if c.food is None or c.food_use <= 0 or c.closed:
            continue
        if c.food > FOOD_EXPORT_TICKS * c.food_use:
            exporters.append(c)
        elif c.food < FOOD_IMPORT_TICKS * c.food_use:
            importers.append(c)
    if not exporters or not importers:
        return
    supply = sum(min((c.food - FOOD_EXPORT_TICKS * c.food_use) * 0.05, c.ports * FOOD_PER_PORT) for c in exporters)
    need = {c.id: min((FOOD_IMPORT_TICKS * c.food_use - c.food), c.ports * FOOD_PER_PORT, c.materials / FOOD_PRICE)
            for c in importers}
    want = sum(v for v in need.values() if v > 0)
    if supply <= 0 or want <= 0:
        return
    f = min(1.0, supply / want) * running
    shipped = 0.0
    for c in importers:
        q = max(0.0, need[c.id]) * f
        c.food += q
        c.materials -= q * FOOD_PRICE
        shipped += q
    for c in exporters:
        part = min((c.food - FOOD_EXPORT_TICKS * c.food_use) * 0.05, c.ports * FOOD_PER_PORT) / supply
        c.food -= shipped * part
        c.materials += shipped * part * FOOD_PRICE
    world.food_shipped = shipped
