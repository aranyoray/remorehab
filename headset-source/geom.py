"""Small parametric-solid toolkit: polygon helpers, lofts, booleans."""
import numpy as np, trimesh, mapbox_earcut as _ec

SQ2 = np.sqrt(2.0)

# ---------------------------------------------------------------- 2-D polygons
def fillet_poly(pts, r, nc=7):
    """Round every vertex of a CCW polygon. Always returns len(pts)*nc points."""
    pts = np.asarray(pts, float); n = len(pts); out = []
    for i in range(n):
        P, V, N = pts[(i - 1) % n], pts[i], pts[(i + 1) % n]
        d1, d2 = P - V, N - V
        l1, l2 = np.linalg.norm(d1), np.linalg.norm(d2)
        if l1 < 1e-9 or l2 < 1e-9:
            out.append(np.repeat(V[None], nc, 0)); continue
        u1, u2 = d1 / l1, d2 / l2
        ang = np.arccos(np.clip(u1 @ u2, -1, 1))
        if ang > np.pi - 1e-3 or ang < 1e-3 or r <= 1e-6:
            out.append(np.repeat(V[None], nc, 0)); continue
        t = min(r / np.tan(ang / 2), l1 * 0.499, l2 * 0.499)
        rr = t * np.tan(ang / 2)
        T1, T2 = V + u1 * t, V + u2 * t
        bis = u1 + u2
        nb = np.linalg.norm(bis)
        if nb < 1e-9:
            out.append(np.repeat(V[None], nc, 0)); continue
        bis /= nb
        C = V + bis * (rr / np.sin(ang / 2))
        a1 = np.arctan2(*(T1 - C)[::-1]); a2 = np.arctan2(*(T2 - C)[::-1])
        da = (a2 - a1 + np.pi) % (2 * np.pi) - np.pi
        th = a1 + da * np.linspace(0, 1, nc)
        out.append(C + rr * np.column_stack([np.cos(th), np.sin(th)]))
    return np.vstack(out)

def chamf_rect(w, h, c, r=3.0, nc=7):
    """Rectangle with 45-degree corner chamfers, then filleted. CCW, 8*nc pts."""
    W, H = w / 2, h / 2
    c = max(0.0, min(c, W * 0.95, H * 0.95))
    r = max(float(r), 0.30)
    p = [(W, H - c), (W - c, H), (-W + c, H), (-W, H - c),
         (-W, -H + c), (-W + c, -H), (W - c, -H), (W, -H + c)]
    return fillet_poly(p, r, nc)

def chamf_rect_inset(w, h, c, r, t, nc=7):
    """Exact parallel inward offset of chamf_rect by t."""
    return chamf_rect(w - 2 * t, h - 2 * t, c - t * (2 - SQ2), max(r - t, 0.3), nc)

def rrect(w, h, r, nc=9):
    W, H = w / 2, h / 2
    return fillet_poly([(W, H), (-W, H), (-W, -H), (W, -H)],
                       max(min(r, W * .99, H * .99), 0.30), nc)

def circle(d, n=72):
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.column_stack([np.cos(th), np.sin(th)]) * d / 2

# ---------------------------------------------------------------- solids
def _tri(poly):
    v = np.asarray(poly, np.float64)
    return np.asarray(_ec.triangulate_float64(v, np.array([len(v)]))).reshape(-1, 3)

def _sec3(s):
    """Accept (z, Nx2) or Nx3 and return Nx3."""
    if isinstance(s, tuple):
        p = np.asarray(s[1], float)
        return np.column_stack([p, np.full(len(p), float(s[0]))])
    a = np.asarray(s, float)
    return a if a.shape[1] == 3 else np.column_stack([a, np.zeros(len(a))])

def loft(sections, cap0=True, cap1=True):
    """sections: [(z, Nx2 CCW) | Nx3, ...] with identical N -> watertight Trimesh."""
    polys = [_sec3(s) for s in sections]
    N, M = len(polys[0]), len(polys)
    assert all(len(p) == N for p in polys), "loft sections must share point count"
    V = np.vstack(polys)
    j = np.arange(N); j2 = (j + 1) % N
    F = []
    for i in range(M - 1):
        a, b = i * N, (i + 1) * N
        F.append(np.column_stack([a + j, a + j2, b + j2]))
        F.append(np.column_stack([a + j, b + j2, b + j]))
    if cap0: F.append(_tri(polys[0][:, :2])[:, ::-1])
    if cap1: F.append(_tri(polys[-1][:, :2]) + (M - 1) * N)
    return clean(trimesh.Trimesh(V, np.vstack(F), process=False))

def prism(poly, z0, z1):
    return loft([(z0, poly), (z1, poly)])

def ring_profile(profile, n=96):
    """Revolve a 2-D (r,z) profile about the Z axis. profile CCW in (r,z)."""
    pr = np.asarray(profile, float)
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    V = np.concatenate([np.column_stack([pr[:, 0] * np.cos(t), pr[:, 0] * np.sin(t), pr[:, 1]])
                        for t in th])
    k = len(pr); F = []
    for i in range(n):
        a, b = i * k, ((i + 1) % n) * k
        for s in range(k):
            s2 = (s + 1) % k
            F.append([a + s, b + s, b + s2]); F.append([a + s, b + s2, a + s2])
    return clean(trimesh.Trimesh(V, np.array(F), process=False))

# ---------------------------------------------------------------- booleans
def clean(m):
    """Merge, drop degenerate faces, make winding consistent and outward."""
    m = trimesh.Trimesh(m.vertices.copy(), m.faces.copy(), process=False)
    m.merge_vertices()
    m.update_faces(m.nondegenerate_faces())
    m.update_faces(m.unique_faces())
    m.remove_unreferenced_vertices()
    m.fix_normals()
    if m.volume < 0:
        m.invert()
    return m

def _fix(m):
    m = m.copy(); m.merge_vertices(); m.remove_degenerate_faces()
    m.remove_duplicate_faces(); m.fix_normals()
    return m

def diff(a, *bs):
    r = a
    for b in bs: r = trimesh.boolean.difference([r, b], engine='manifold')
    return r

def union(*ms):
    r = ms[0]
    for b in ms[1:]: r = trimesh.boolean.union([r, b], engine='manifold')
    return r

def inter(a, *bs):
    r = a
    for b in bs: r = trimesh.boolean.intersection([r, b], engine='manifold')
    return r

def box(w, h, d, c=(0, 0, 0)):
    return trimesh.creation.box((w, h, d), trimesh.transformations.translation_matrix(c))

def cyl(d, h, c=(0, 0, 0), axis='z', n=64):
    m = trimesh.creation.cylinder(radius=d / 2, height=h, sections=n)
    if axis == 'x': m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    if axis == 'y': m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    m.apply_translation(c); return m

def smoothstep(t):
    t = np.clip(t, 0, 1); return t * t * (3 - 2 * t)

def weld(m):
    """Merge the duplicate vertices booleans leave along union seams.

    Without this the part is topologically watertight but split into dozens of
    face-adjacency islands, so splitting it apart discards real geometry and
    the STL round-trip opens holes."""
    m = trimesh.Trimesh(m.vertices.copy(), m.faces.copy(), process=False)
    m.merge_vertices()
    m.update_faces(m.nondegenerate_faces())
    m.update_faces(m.unique_faces())
    m.remove_unreferenced_vertices()
    return m

def prune(m, min_vol=1.0):
    """Weld, then drop stray slivers left by coincident-face booleans."""
    m = weld(m)
    if m.body_count <= 1:
        return m
    keep = [b for b in m.split(only_watertight=False) if b.volume > min_vol]
    return weld(trimesh.util.concatenate(keep)) if keep else m

def msimplify(m, tol=1e-4):
    """Collapse the sliver triangles booleans leave behind.

    They are harmless until something merges vertices - a slicer, or trimesh on
    load - at which point they go degenerate and tear holes in the surface.
    manifold3d removes them without moving any real surface."""
    import manifold3d as m3
    mm = m3.Manifold(m3.Mesh(np.asarray(m.vertices, dtype=np.float32),
                             np.asarray(m.faces, dtype=np.uint32)))
    msh = mm.simplify(tol).to_mesh()
    return trimesh.Trimesh(np.asarray(msh.vert_properties)[:, :3],
                           np.asarray(msh.tri_verts), process=False)

def patch_holes(m):
    """Fan-triangulate any open boundary loops left by a boolean."""
    m = weld(m)
    u, c = np.unique(m.edges_sorted, axis=0, return_counts=True)
    bnd = u[c == 1]
    if not len(bnd):
        return m
    adj = {}
    for a, b in bnd:
        adj.setdefault(int(a), []).append(int(b))
        adj.setdefault(int(b), []).append(int(a))
    seen, faces = set(), []
    for start in list(adj):
        if start in seen:
            continue
        loop, cur, prev = [start], start, None
        seen.add(start)
        while True:
            nxt = [v for v in adj[cur] if v != prev and v not in seen]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            seen.add(cur); loop.append(cur)
        for i in range(1, len(loop) - 1):
            faces.append([loop[0], loop[i], loop[i + 1]])
    if not faces:
        return m
    m = trimesh.Trimesh(m.vertices.copy(),
                        np.vstack([m.faces, np.array(faces, dtype=np.int64)]),
                        process=False)
    return weld(m)

def finalize(m, min_vol=1.0):
    """De-sliver, weld, drop stray shells, and patch any remaining holes."""
    try:
        m = msimplify(m)
    except Exception:
        pass
    m = prune(m, min_vol)
    for _ in range(3):
        if m.is_watertight:
            break
        trimesh.repair.fill_holes(m)
        m = patch_holes(weld(m))
    trimesh.repair.fix_normals(m)
    if m.volume < 0:
        m.invert()
    return m

def report(m, name=''):
    return (f"{name:26s} tris={len(m.faces):6d} watertight={str(m.is_watertight):5s} "
            f"vol={m.volume/1000:8.2f}cm3 bbox={np.round(m.extents,1)}")
