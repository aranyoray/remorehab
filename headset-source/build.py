import sys, os, time, traceback, numpy as np, trimesh
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geom as g, headset as H

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'STL')
os.makedirs(OUT, exist_ok=True)
only = sys.argv[2:] if len(sys.argv) > 2 else None

meshes = {}
for name, fn, qty in H.PARTS:
    if only and not any(o in name for o in only): continue
    t0 = time.time()
    try:
        m = g.finalize(fn())
        meshes[name] = m
        bad = []
        if not m.is_watertight: bad.append('NOT-WATERTIGHT')
        if m.volume <= 0: bad.append('NEG-VOLUME')
        if m.body_count != 1: bad.append(f'{m.body_count}-BODIES')
        print(f"{name:18s} x{qty}  tris={len(m.faces):7d} vol={m.volume/1000:7.2f}cm3 "
              f"bbox={np.round(m.extents,1)}  {'  '.join(bad) or 'OK'}   [{time.time()-t0:.1f}s]")
        m.export(f"{OUT}/{name}.stl")
        r = trimesh.load(f"{OUT}/{name}.stl")        # what a slicer will actually see
        if not (r.is_watertight and r.body_count == 1 and r.volume > 0):
            print(f"{'':18s}   ^ STL round-trip: watertight={r.is_watertight} "
                  f"bodies={r.body_count}")
    except Exception as e:
        print(f"{name:18s} FAILED: {type(e).__name__}: {e}")
        traceback.print_exc(limit=3)
