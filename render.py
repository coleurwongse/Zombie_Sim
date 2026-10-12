"""Turns a World into an RGB image (numpy only; main.py puts it on screen)."""
import numpy as np

from terrain import is_land, is_water

import mapio


def render_rgb(world, mode):
    """Returns a (rows, cols, 3) uint8 image, one pixel per tile."""
    h = np.clip(world.H, 0, 255)
    z = np.clip(world.Z, 0, 255)

    img = _base(world, mode, h, z)
    fall = getattr(world, "fallout", None)
    if fall is not None and mode in (1, 4) and fall.any():           # nuclear fallout: sickly green
        hot = fall > 0
        img[hot] = (img[hot] * 0.4 + np.array([150, 255, 60]) * 0.6).astype(np.uint8)
    for c in world.civs:
        if not c.sites:
            continue
        col = (255, 220, 0) if not c.collapsed else tuple(min(255, int(v * 1.2) + 40) for v in civ_color(c.id))
        for s in c.sites:                            # forts; a fallen government's garrisons in its own colour
            for rc in s["tiles"]:
                img[rc] = col
    if mode in (2, 4):
        for r, c, size in getattr(world, "ports", []):
            if world.O[r, c] > 0 and world.H[r, c] > 10:
                img[r, c] = (0, 230, 230)            # working ports
    if mode == 2:
        for (r, c) in world.airports:
            img[r, c] = (255, 120, 255)              # airports still flying
    if mode == 4:
        for c in world.civs:                         # seats of government
            if c.capital is not None and c.ai and not c.collapsed and world.O[c.capital] == c.id:
                img[c.capital] = (255, 255, 255)
    return img


def describe(world, i, j):
    """Hover text for tile (i, j)."""
    import terrain
    o = int(world.O[i, j])
    owner = world.civs[o].name if o < len(world.civs) else "?"
    if o == 0:
        owner = "nobody (anarchy)"
    for c in world.civs:
        for s in c.sites:
            if (i, j) in s["tiles"]:
                owner = (f"garrison of {c.name}" + (" (its government fell)" if c.collapsed else "")
                         + f" - defense {s['level']}")
    extra = []
    if (i, j) in world.airports:
        extra.append(f"airport ({len(world.airports[(i, j)])} routes)")
    for r, c, size in getattr(world, "ports", []):
        if (r, c) == (i, j):
            extra.append(f"port (size {size})")
    fall = getattr(world, "fallout", None)
    if fall is not None and fall[i, j] > 0:
        extra.append(f"fallout {fall[i, j]} days")
    t = int(world.T[i, j])
    name = terrain.NAMES[t] if 0 <= t < terrain.N else "?"
    return (f"people {int(world.H[i, j])}  zombies {int(world.Z[i, j])}  defense {int(world.D[i, j])}  {name}  "
            f"- {owner}" + ("  - " + ", ".join(extra) if extra else ""))


def civ_color(k):
    """A stable, well-spread colour per civilization id (anarchy = grey)."""
    if k == 0:
        return (90, 90, 90)
    hue = (k * 0.381966) % 1.0                       # golden-ratio hue steps never repeat close together
    i, f = int(hue * 6), hue * 6 - int(hue * 6)
    p, q, t = 0.35, 1 - 0.65 * f, 0.35 + 0.65 * f
    r, g, b = [(1, t, p), (q, 1, p), (p, 1, t), (p, q, 1), (t, p, 1), (1, p, q)][i % 6]
    return (int(r * 255), int(g * 255), int(b * 255))


def _ownership(world, h, z):
    """mode 4: land coloured by civilization (dim = few people), grey = anarchy, red = overrun, white = shut
    borders (quarantine), orange = active war fronts."""
    n = len(world.civs)
    palette = np.array([civ_color(k) for k in range(n)], dtype=np.float32)
    img = np.zeros(h.shape + (3,), dtype=np.float32)
    land = is_land(world.T)
    img[~land] = (0, 0, 60)
    img[land] = palette[world.O][land] * 0.35
    pop = np.clip(h / 120.0, 0, 1)[..., None]
    owned = land & (h > 0)
    img[owned] = (palette[world.O] * (0.35 + 0.65 * pop))[owned]
    thin = land & (z > 0) & (z <= np.maximum(h, 10)) & (h <= 10)        # ground only a few zombies roam
    img[thin] = np.stack([25 + 3 * z, 12 + 0 * z, 12 + 0 * z], axis=-1)[thin]
    over = z > np.maximum(h, 10)
    img[over] = np.stack([np.clip(z, 60, 255), np.zeros_like(z), np.zeros_like(z)], axis=-1)[over]
    if world.closed:
        shut = np.isin(world.O, list(world.closed))
        open_sides = ((~np.roll(shut, 1, 0)).astype(int) + ~np.roll(shut, -1, 0) + ~np.roll(shut, 1, 1)
                      + ~np.roll(shut, -1, 1))
        edge = shut & (open_sides >= 2) | shut & (open_sides >= 1) & (box_count(shut) <= 6)
        img[edge] = (235, 235, 235)
    for k in world.wars:
        a, b = tuple(k)
        ma, mb = world.O == a, world.O == b
        front = (ma & _touch(mb)) | (mb & _touch(ma))
        img[front] = (255, 140, 0)
    return img.astype(np.uint8)


def box_count(mask):
    """Tiles of mask in the 3x3 box around each tile."""
    out = np.zeros(mask.shape, dtype=int)
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            out += np.roll(np.roll(mask, dr, 0), dc, 1)
    return out


def _touch(mask):
    out = np.zeros_like(mask)
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            out |= np.roll(np.roll(mask, dr, 0), dc, 1)
    return out


def _base(world, mode, h, z):
    if mode == 4:
        return _ownership(world, h, z)
    if mode == 2:                                    # terrain
        img = np.zeros(h.shape + (3,), dtype=np.uint8)
        img[:] = (0, 0, 255)
        known = (world.T >= 0) & (world.T < len(mapio.TERRAIN))
        img[known] = mapio.terrain_to_rgb(world.T)[known]
        return img

    if mode == 3:                                    # population density: red = zombies, blue = humans
        img = np.zeros(h.shape + (3,), dtype=np.uint8)
        img[..., 0] = z
        img[..., 2] = h
        return img

    # mode 1: who controls the tile
    img = np.zeros(h.shape + (3,), dtype=np.uint8)
    humans_win = (h > 10) & (z <= 10)
    zombies_win = (h <= 10) & (z > 10)
    both = (h > 10) & (z > 10)
    img[humans_win & (h <= 80)] = (0, 0, 75)
    img[humans_win & (h > 80)] = (0, 0, 150)
    img[humans_win & (h > 200)] = (0, 0, 255)
    img[zombies_win & (z <= 80)] = (75, 0, 0)
    img[zombies_win & (z > 80)] = (150, 0, 0)
    img[zombies_win & (z > 200)] = (255, 0, 0)
    img[both] = (255, 0, 255)
    thin = (h <= 10) & (z > 0) & (z <= 10)                            # a few zombies roaming
    img[thin] = np.stack([20 + 4 * z, 0 * z, 0 * z], axis=-1)[thin].astype(np.uint8)
    return img
