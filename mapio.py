"""Load / save a map stored as one PNG per layer.

A map is a folder:

    humans.png     grayscale   pixel value = human population (0-255)
    zombies.png    grayscale   pixel value = zombie population (0-255)
    defense.png    grayscale   pixel value = defense level * 25   (0..10 -> 0..250)
    owner.png      grayscale   pixel value = civilization id (0 = nobody / anarchy)
    terrain.png    RGB         painted with the terrain colours below
    airports.json  list of {"from": [row, col], "to": [[row, col], ...]}

One pixel = one tile.  Row = image y, column = image x.
"""
import json
import os

import numpy as np
from PIL import Image

DEFENSE_SCALE = 25

# id -> colour: the same colours display mode 2 uses, so the terrain layer looks like the terrain view and can be
# painted with those colours (terrain.py lists them).
import terrain as _terrain
TERRAIN = {i: (_terrain.NAMES[i], tuple(int(v) for v in _terrain.COLORS[i])) for i in range(_terrain.N)}
TERRAIN_COLORS = _terrain.COLORS


def terrain_to_rgb(terrain):
    """(rows, cols) terrain ids -> (rows, cols, 3) uint8 image."""
    ids = np.clip(terrain, 0, len(TERRAIN) - 1)
    return TERRAIN_COLORS[ids].astype(np.uint8)


def rgb_to_terrain(rgb):
    """(rows, cols, 3) image -> terrain ids.  Exact colours map exactly; anything
    else (anti-aliased brush edges, slightly-off colours) snaps to the nearest."""
    px = rgb.astype(np.int32)[..., None, :]                 # (r, c, 1, 3)
    dist = ((px - TERRAIN_COLORS[None, None]) ** 2).sum(axis=-1)   # (r, c, n terrain types)
    return dist.argmin(axis=-1).astype(np.int32)


def _read_gray(path):
    return np.array(Image.open(path).convert("L"), dtype=np.int32)


def load_map(folder):
    """Returns (humans, zombies, defense, terrain, owner, airports).
    All arrays are int32 with shape (rows, cols).
    airports is {(row, col): [(row, col), ...]}."""
    humans = _read_gray(os.path.join(folder, "humans.png"))
    zombies = _read_gray(os.path.join(folder, "zombies.png"))
    defense = np.rint(_read_gray(os.path.join(folder, "defense.png")) / DEFENSE_SCALE).astype(np.int32)
    owner = _read_gray(os.path.join(folder, "owner.png"))
    terrain = rgb_to_terrain(np.array(Image.open(os.path.join(folder, "terrain.png")).convert("RGB")))

    for name, arr in (("zombies", zombies), ("defense", defense), ("owner", owner), ("terrain", terrain)):
        if arr.shape != humans.shape:
            raise ValueError(f"{name}.png is {arr.shape[::-1]} but humans.png is {humans.shape[::-1]}")

    airports = {}
    path = os.path.join(folder, "airports.json")
    if os.path.exists(path):
        with open(path) as f:
            for entry in json.load(f):
                airports[tuple(entry["from"])] = [tuple(t) for t in entry["to"]]
    return humans, zombies, defense, terrain, owner, airports


def load_meta(folder):
    """Optional maps/<map>/meta.json: {"wrap": false, "sea_min": 8, "names": {"1": "China", ...},
    "capitals": {"1": [row, col]}, "cities": [{"name": "Wuhan", "row": r, "col": c, "pop": p}, ...]}"""
    path = os.path.join(folder, "meta.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_map(folder, humans, zombies, defense, terrain, owner, airports):
    os.makedirs(folder, exist_ok=True)

    def gray(name, arr):
        Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "L").save(os.path.join(folder, name))

    gray("humans.png", humans)
    gray("zombies.png", zombies)
    gray("defense.png", np.clip(defense, 0, 10) * DEFENSE_SCALE)
    gray("owner.png", owner)
    Image.fromarray(terrain_to_rgb(terrain), "RGB").save(os.path.join(folder, "terrain.png"))
    entries = [{"from": list(src), "to": [list(t) for t in dst]}
               for src, dst in sorted(airports.items()) if dst]
    with open(os.path.join(folder, "airports.json"), "w") as f:
        json.dump(entries, f)
