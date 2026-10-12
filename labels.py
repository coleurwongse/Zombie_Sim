"""Connected-component labelling (8-connected) without scipy.

Works on horizontal runs instead of single tiles: every row is cut into runs of True with numpy, runs that touch
a run in the previous row (diagonals included) are joined with a small union-find.  A map has far fewer runs
than tiles, so this is fast enough to call every few ticks on a whole continent.
"""
import numpy as np

try:
    from scipy.ndimage import label as _scipy_label
except Exception:                                      # pragma: no cover
    _scipy_label = None


def label(mask):
    """Returns (labels, n): labels is int32 with 0 outside the mask and 1..n for each 8-connected component."""
    mask = np.asarray(mask, dtype=bool)
    if _scipy_label is not None:
        lab, n = _scipy_label(mask, structure=np.ones((3, 3), dtype=int))
        return lab.astype(np.int32), int(n)
    rows, cols = mask.shape
    m = mask.astype(np.int8)
    pad = np.zeros((rows, cols + 2), dtype=np.int8)
    pad[:, 1:-1] = m
    d = np.diff(pad, axis=1)
    sr, sc = np.nonzero(d == 1)                         # run starts (row, col)
    er, ec = np.nonzero(d == -1)                        # run ends (exclusive col)
    nruns = len(sr)
    labels = np.zeros((rows, cols), dtype=np.int32)
    if nruns == 0:
        return labels, 0
    parent = list(range(nruns))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    # runs are ordered row by row, start column ascending
    row_first = np.searchsorted(sr, np.arange(rows + 1))
    sc_l, ec_l = sc.tolist(), ec.tolist()
    for r in range(1, rows):
        a0, a1 = row_first[r - 1], row_first[r]         # previous row's runs
        b0, b1 = row_first[r], row_first[r + 1]
        if a0 == a1 or b0 == b1:
            continue
        i = a0
        for j in range(b0, b1):
            s, e = sc_l[j] - 1, ec_l[j] + 1             # 8-connectivity: diagonal neighbours touch too
            while i < a1 and ec_l[i] <= s:
                i += 1
            k = i
            while k < a1 and sc_l[k] < e:
                ra, rb = find(k), find(j)
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
                k += 1
    roots = np.array([find(k) for k in range(nruns)])
    _, comp = np.unique(roots, return_inverse=True)
    comp = comp.astype(np.int32) + 1
    lengths = ec - sc
    starts = sr * cols + sc
    offsets = np.arange(int(lengths.sum())) - np.repeat(np.cumsum(lengths) - lengths, lengths)
    labels.reshape(-1)[np.repeat(starts, lengths) + offsets] = np.repeat(comp, lengths)
    return labels, int(comp.max())
