"""Turns a World into an RGB image (numpy only; main.py puts it on screen)."""
import numpy as np

from terrain import is_land, is_water

import mapio


def render_rgb(world, mode):
    """Returns a (rows, cols, 3) uint8 image, one pixel per tile."""
    h = np.clip(world.H, 0, 255)
    z = np.clip(world.Z, 0, 255)
    horde = None
    if mode in (1, 4):
        z = _steady_zombies(world, z)
        horde = _horde_shade(world, z)

    img = _base(world, mode, h, z, horde)
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


DISPLAY_FADE = 0.75         # (the map remembers zombies for a few days: a lone one wandering on and off a tile
                            #  doesn't make the border blink every tick)


def _steady_zombies(world, z):
    """Zombies as the map shows them: what's there now, or what was there lately, fading - whichever is more."""
    memo = getattr(world, "_zshow", None)
    t = getattr(world, "ticks", 0)
    if memo is None or memo[1].shape != z.shape or t < memo[0]:
        shown = z.astype(np.float32)
    elif t == memo[0]:
        return memo[2]
    else:
        shown = np.maximum(z.astype(np.float32), memo[1] * DISPLAY_FADE ** (t - memo[0]))
    out = np.rint(shown).astype(z.dtype)
    world._zshow = (t, shown, out)
    return out


HORDE_MIX = 0.6             # share of the 3x3 neighbourhood in a tile's horde shade (a horde reads as one body)
HORDE_TOP = 98              # percentile of the map's zombie tiles drawn at full brightness
HORDE_MIN_TOP = 12.0        # (but never brighter than this many zombies on a tile deserve)
HORDE_REF_FADE = 0.97       # the brightness scale follows the outbreak slowly (no flicker as the numbers move)


def _horde_shade(world, z):
    """0..255 per tile: how dense the zombies there are, as the eye should see it.  Log of the numbers against what is
    dense on this map at the moment - so a crowded world map shows its hordes, cores and thin fringes as well as a
    thinly peopled one does, instead of one flat red mass - with a little of the neighbourhood mixed in so a horde
    reads as one body.  Display only."""
    t = getattr(world, "ticks", 0)
    memo = getattr(world, "_hshow", None)
    if memo is not None and memo[0] == t and memo[2].shape == z.shape:
        return memo[2]
    zf = z.astype(np.float32)
    p = np.pad(zf, 1, mode="edge")
    near = (p[:-2, :-2] + p[:-2, 1:-1] + p[:-2, 2:] + p[1:-1, :-2] + p[1:-1, 2:]
            + p[2:, :-2] + p[2:, 1:-1] + p[2:, 2:] + zf) / 9.0
    v = np.log1p((1.0 - HORDE_MIX) * zf + HORDE_MIX * near)
    world._hnear = (t, near)
    some = zf > 0
    top = float(np.percentile(v[some], HORDE_TOP)) if some.sum() > 20 else 0.0
    top = max(top, float(np.log1p(HORDE_MIN_TOP)))
    if memo is not None and memo[2].shape == z.shape and 0 < t - memo[0] < 30:
        top = max(top, memo[1] * HORDE_REF_FADE ** (t - memo[0]))      # (falls slowly, rises at once)
    out = np.clip(v * (255.0 / top), 0, 255).astype(np.uint8)
    world._hshow = (t, top, out)
    return out


def _in_horde(world, z):
    """Tiles whose 3x3 neighbourhood holds a horde (more than 10 a tile on average)."""
    memo = getattr(world, "_hnear", None)
    if memo is None or memo[0] != getattr(world, "ticks", 0) or memo[1].shape != z.shape:
        _horde_shade(world, z)
        memo = world._hnear
    return memo[1] > 10


def _horde_ramp():
    """Colours for zombie-held ground, sparse to dense: dark blood red, red, and a hot light red for a horde's core."""
    x = np.arange(256, dtype=np.float32) / 255.0
    stops = np.array([0.0, 0.45, 0.8, 1.0])
    cols = np.array([(55, 0, 0), (150, 0, 0), (235, 20, 15), (255, 120, 95)], dtype=np.float32)
    return np.stack([np.interp(x, stops, cols[:, k]) for k in range(3)], axis=1).astype(np.uint8)


HORDE_RAMP = _horde_ramp()


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
    if hasattr(world, "shown"):
        from sim import fmt_people
        s = float(world.scale_map[i, j]) if getattr(world, "scale_map", None) is not None else world.pop_scale

        def ppl(n):
            return fmt_people(n * s)
    else:
        def ppl(n):
            return str(int(n))
    return (f"people {ppl(world.H[i, j])}  zombies {ppl(world.Z[i, j])}  defense {int(world.D[i, j])}  {name}  "
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


_SPECIAL = 1 + 11 + 256 + 2          # sea, thinly roamed (zombies 0..10), overrun (shade 0..255), shut border, war front


def _shade_table(n):
    """Colour table for the government view: entries civ * 121 + people (0..120) - the civilization's colour, dim
    (0.35) where nobody lives, full where crowded - then the special colours (see _ownership)."""
    cache = getattr(_shade_table, "cache", None)
    if cache is None or cache[0] < n:
        m = max(n, 64) * 2
        pal = np.array([civ_color(k) for k in range(m)], dtype=np.float32)
        f = 0.35 + 0.65 * np.arange(121, dtype=np.float32) / 120.0
        tab = (pal[:, None, :] * f[None, :, None]).astype(np.uint8).reshape(-1, 3)
        z = np.arange(256)
        special = np.zeros((_SPECIAL, 3), dtype=np.uint8)
        special[0] = (0, 0, 60)                                          # sea
        special[1:12] = np.stack([25 + 3 * z[:11], 12 + 0 * z[:11], 12 + 0 * z[:11]], axis=1)   # a few roaming
        special[12:268] = HORDE_RAMP                                  # overrun, by horde shade
        special[268] = (235, 235, 235)                                   # shut border
        special[269] = (255, 140, 0)                                     # war front
        cache = _shade_table.cache = (m, np.concatenate([tab, special]), m * 121)
    return cache[1], cache[2]


def _neighbour_pairs(a):
    """(x, y) view pairs of every pair of neighbouring tiles (side by side, one above the other, both diagonals)."""
    return ((a[:, 1:], a[:, :-1]), (a[1:], a[:-1]), (a[1:, 1:], a[:-1, :-1]), (a[1:, :-1], a[:-1, 1:]))


def _ownership(world, h, z, horde=None):
    """mode 4: land coloured by civilization (dim = few people), grey = anarchy, red = overrun, white = shut
    borders (quarantine), orange = active war fronts.  (Worked out as one index per tile into a colour table.)"""
    n = len(world.civs)
    O = world.O
    land = getattr(world, "land", None)
    if land is None or land.shape != O.shape:
        land = is_land(world.T)
    table, sp = _shade_table(n)
    code = O * 121 + np.minimum(h, 120)
    code[~land] = sp
    if horde is None:
        horde = _horde_shade(world, z)
    thin = land & (z > 0) & (z <= np.maximum(h, 10)) & (h <= 10)        # ground only a few zombies roam
    code[thin] = sp + 1 + z[thin]
    over = (z > np.maximum(h, 10)) | (thin & _in_horde(world, z))       # (a gap inside a horde is part of its body)
    code[over] = sp + 12 + horde[over].astype(code.dtype)
    if world.closed:
        shut_civ = np.zeros(max(n, int(O.max()) + 1), dtype=bool)
        shut_civ[[k for k in world.closed if k < len(shut_civ)]] = True
        shut = shut_civ[O]
        s8 = shut.astype(np.int8)
        open_sides = np.zeros(O.shape, dtype=np.int8)       # side neighbours not shut (the map's edge counts as shut)
        open_sides[:, 1:] += 1 - s8[:, :-1]
        open_sides[:, :-1] += 1 - s8[:, 1:]
        open_sides[1:] += 1 - s8[:-1]
        open_sides[:-1] += 1 - s8[1:]
        count = s8.copy()                                   # shut tiles in the 3x3 box
        count[:, 1:] += s8[:, :-1]
        count[:, :-1] += s8[:, 1:]
        c2 = count.copy()
        c2[1:] += count[:-1]
        c2[:-1] += count[1:]
        code[shut & ((open_sides >= 2) | ((open_sides >= 1) & (c2 <= 6)))] = sp + 268
    if world.wars:
        at_war = np.zeros((n, n), dtype=bool)
        for k in world.wars:
            a, b = tuple(k)
            if a < n and b < n:
                at_war[a, b] = at_war[b, a] = True
        warring = at_war.any(axis=1)
        front = np.zeros(O.shape, dtype=bool)
        for (x, y), (fx, fy) in zip(_neighbour_pairs(O), _neighbour_pairs(front)):
            d = (x != y) & warring[x] & warring[y]
            if d.any():
                hit = np.zeros(x.shape, dtype=bool)
                hit[d] = at_war[x[d], y[d]]
                fx |= hit
                fy |= hit
        code[front] = sp + 269
    return np.take(table, code.ravel(), axis=0).reshape(O.shape + (3,))


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


def _base(world, mode, h, z, horde=None):
    if mode == 4:
        return _ownership(world, h, z, horde)
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
    if horde is None:
        horde = _horde_shade(world, z)
    img[zombies_win] = HORDE_RAMP[horde[zombies_win]]
    img[both] = (255, 0, 255)
    thin = (h <= 10) & (z > 0) & (z <= 10)                            # a few zombies roaming
    img[thin] = np.stack([20 + 4 * z, 0 * z, 0 * z], axis=-1)[thin].astype(np.uint8)
    gap = thin & _in_horde(world, z)                                  # (a gap inside a horde is part of its body)
    img[gap] = HORDE_RAMP[horde[gap]]
    return img
