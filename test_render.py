"""render_rgb vs the original per-tile colour rules (copied from legacy draw())."""
import numpy as np, mapio, sim, render


def random_map(n, seed):
    """A random little map: people, zombies, defense, the original terrain types, two nations, a few airports."""
    rng = np.random.default_rng(seed)
    H = rng.integers(0, 256, (n, n)); Z = np.where(rng.random((n, n)) < 0.3, rng.integers(0, 256, (n, n)), 0)
    D = rng.integers(1, 10, (n, n)); T = rng.integers(1, 8, (n, n)); T[:, :3] = 0
    O = rng.integers(0, 3, (n, n))
    pts = [tuple(int(v) for v in rng.integers(3, n, 2)) for _ in range(6)]
    A = {p: [q for q in pts if q != p][:2] for p in pts}
    return H, Z, D, T, O, A


def legacy_color(mode, h, z, t):
    if mode == 3: return (z, 0, h)
    if mode == 2: return {0:(0,0,255),1:(0,150,0),2:(0,100,0),3:(75,75,75),4:(150,150,0),5:(255,255,255),6:(150,150,150),7:(100,100,100)}[t]
    if h > 10 >= z:
        return (0,0,255) if h > 200 else (0,0,150) if h > 80 else (0,0,75)
    elif h <= 10 < z:
        return (255,0,0) if z > 200 else (150,0,0) if z > 80 else (75,0,0)
    elif h <= 10 and z <= 10: return (20 + 4 * z, 0, 0) if z > 0 else (0,0,0)   # (new: a few roaming zombies, faint red)
    return (255,0,255)

w = sim.World(*random_map(60, 3))
w.H[0,:5] = [-5, 300, 11, 81, 201]; w.Z[0,:5] = [300, -3, 11, 81, 201]
for mode in (1,2,3):
    img = render.render_rgb(w, mode)
    for i in range(60):
        for j in range(60):
            if mode == 2 and (i, j) in w.airports:
                continue                          # (new: airports are marked in the terrain view)
            exp = legacy_color(mode, min(max(int(w.H[i,j]),0),255), min(max(int(w.Z[i,j]),0),255), int(w.T[i,j]))
            assert tuple(img[i,j]) == exp, (mode,i,j,img[i,j],exp)
print("render matches original colour rules in all 3 modes")

# PNG round trip + painted-terrain snapping
w.H[0,:5] = 7; w.Z[0,:5] = 9   # PNG holds 0..255 only
import tempfile, os
d = tempfile.mkdtemp(); w.save(d); w2 = sim.World.from_folder(d)
for a in "HZDTO":
    assert (getattr(w,a) == getattr(w2,a)).all(), a
assert w.airports == w2.airports
print("PNG save/load round trip exact")
