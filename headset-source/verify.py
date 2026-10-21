import sys,os,itertools,numpy as np,trimesh
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import geom as g, headset as H

print("="*78); print("1. INTERFERENCE  (assembled parts should not overlap)"); print("="*78)
A=H.assembly(ipd=62.0)
bad=0
for (ka,ma),(kb,mb) in itertools.combinations(A.items(),2):
    if (ma.bounds[0]>mb.bounds[1]).any() or (mb.bounds[0]>ma.bounds[1]).any(): continue
    try: v=trimesh.boolean.intersection([ma,mb],engine='manifold').volume
    except Exception: v=float('nan')
    if v>5.0:
        print(f"  OVERLAP {ka:8s}/{kb:8s} = {v:9.1f} mm3"); bad+=1
print(f"  -> {bad} overlapping pair(s) above 5 mm3")

print(); print("="*78); print("2. IPD TRAVEL  (pods must clear the carrier slot and the septum)"); print("="*78)
car=H.build_carrier(); sep=H.build_septum(); pod=H.build_pod()
for ipd in (H.IPD_MIN, 62.0, H.IPD_MAX):
    row=[]
    for s in (-1,1):
        p=pod.copy(); p.apply_translation((s*ipd/2,0,0))
        row.append(trimesh.boolean.intersection([p,car],engine='manifold').volume)
    sp=[]
    for s in (-1,1):
        p=pod.copy(); p.apply_translation((s*ipd/2,0,0))
        sp.append(trimesh.boolean.intersection([p,sep],engine='manifold').volume)
    gap=ipd-2*(H.POD_W/2)
    print(f"  IPD {ipd:5.1f}  pod/carrier overlap {max(row):7.1f} mm3   pod/septum {max(sp):6.1f} mm3   "
          f"gap between pods {gap:5.1f} mm")

print(); print("="*78); print("3. CARRIER INSERTION  (must slide from the tray to its seat)"); print("="*78)
cw,ch=H.half(H.CARRIER)
print(f"  carrier outline            {2*cw:7.2f} x {2*ch:6.2f} mm")
for z in (0,10,20,30,36,38):
    iw,ih=H.half(H.inner(z))
    ok = "clears" if (iw>cw and ih>ch) else "BLOCKS"
    print(f"  cavity at z={z:4.0f}        {2*iw:7.2f} x {2*ih:6.2f}   {ok}")

print(); print("="*78); print("4. OPTICS"); print("="*78)
print(f"  lens centre to screen      {H.LENS_CENTRE_Z:6.1f} mm   (Cardboard class 38-45)")
print(f"  lens clear aperture        {H.LENS_CLEAR:6.1f} mm")
print(f"  face rim to screen         {H.Z_FACE:6.1f} mm")
print(f"  IPD range                  {H.IPD_MIN:.0f} - {H.IPD_MAX:.0f} mm")
print(f"  face rim: {H.RIM_MIN:.0f} mm at the centre -> {H.Z_FACE:.0f} mm at the temples")
for lab,r in (("between the eyes",0.),("at the pupils (x=31)",31.),("brow / chin (r=41)",41.),("temples (r=77)",77.)):
    print(f"    rim at {lab:22s} z = {H.rim_z(r):5.1f}")
# the gasket stands GSK_H proud of the rim; the cornea sits ~10 mm behind the contact
relief = H.rim_z(31.)+H.GSK_H+10.0-H.LENS_CENTRE_Z
print(f"  eye relief (pupil to lens)  {relief:5.1f} mm")
for d,lab in ((relief,'as designed'),):
    print(f"  FOV through the {H.LENS_CLEAR:.0f} mm aperture {lab}: "
          f"{2*np.degrees(np.arctan((H.LENS_CLEAR/2)/d)):.0f} deg")

print(); print("="*78); print("5. PRINTABILITY  (recommended orientation; overhang = face >45 deg from vertical)")
print("="*78)
ORI={'01_shell':('phone mouth down',[]),'02_screen_mask':('flat',[]),
     '03_lens_carrier':('plate down, hooks up',[('x',180)]),'04_lens_pod':('flange down',[]),'05_lens_ring':('flat',[]),
     '06_septum':('flat on its side',[('y',90)]),'07_door':('outside down',[]),
     '08_phone_spacer':('flat',[]),'09_face_gasket':('socket down',[]),
     '10_strap_buckle':('flat',[]),'11_focus_shim':('flat',[])}
for name,fn,qty in H.PARTS:
    m=g.prune(fn()).copy()
    note,rots=ORI[name]
    for ax,ang in rots:
        m.apply_transform(trimesh.transformations.rotation_matrix(np.radians(ang),
            {'x':[1,0,0],'y':[0,1,0],'z':[0,0,1]}[ax]))
    n=m.face_normals; a=m.area_faces
    down=n[:,2]<-1e-9
    bed = down & (np.abs(n[:,2])>0.999) & (m.triangles[:,:,2].max(1) < m.bounds[0][2]+0.05)
    sel = down & (np.abs(n[:,2])>np.cos(np.radians(45))) & ~bed
    over = 100*a[sel].sum()/a.sum()
    # "floating": a downward face with no material under it -> needs support.
    # A face with material below is a ledge the slicer bridges to.
    idx=np.where(sel)[0]; flo=0.0
    if len(idx):
        o=m.triangles_center[idx]+np.array([0,0,-0.05]); d=np.tile([0,0,-1.],(len(idx),1))
        hit=m.ray.intersects_any(ray_origins=o, ray_directions=d)
        flo=100*a[idx][~hit].sum()/a.sum()
    print(f"  {name:17s} x{qty}  h={m.extents[2]:5.1f}mm  overhang {over:5.1f}%  "
          f"needs support {flo:4.1f}%  bed {100*a[bed].sum()/a.sum():4.1f}%  ({note})")
