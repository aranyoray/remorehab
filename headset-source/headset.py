"""
FACET VR  —  a Google-Cardboard-class smartphone VR headset.

Completely original geometry: faceted (chamfered-octagon) shroud, hexagonal
vent fields, three-point strap, sliding-IPD lens pods.  No logos, wordmarks or
decorative brand graphics on any part.

Coordinate system (millimetres)
  X   left(-) / right(+),  0 = centre line
  Y   down(-) / up(+),     0 = optical axis
  Z   0 = phone screen plane,  +Z toward the user's face
"""
import numpy as np, trimesh
import geom as g
from geom import chamf_rect, rrect, loft, prism, diff, union, inter, box, cyl, \
                 smoothstep, report

# ════════════════════════════════════════════════════════ PARAMETERS
# -- optics (sized for the Ø47 biconvex lenses the donor design uses) --------
LENS_D        = 47.4     # lens outside diameter + fit clearance
LENS_T        = 21.4     # lens axial thickness + clearance
LENS_CLEAR    = 42.0     # clear aperture
LENS_CENTRE_Z = 42.0     # lens centre to screen (Cardboard-class ≈ 40 mm)
IPD_MIN, IPD_MAX = 56.0, 68.0

# -- phone envelope ---------------------------------------------------------
PHONE_W, PHONE_H, PHONE_T = 168.0, 82.0, 11.0

# -- shroud -----------------------------------------------------------------
Z_DOOR   = -18.5         # outer face of the door
Z_MOUTH  = -14.0         # front rim of the shell (the phone drops in here)
Z_SCREEN =   0.0         # phone screen plane
Z_MASK   =   2.6         # back face of the screen mask
Z_CARR   =  30.0         # screen-side face of the lens carrier
CARR_T   =   6.0         # carrier plate thickness
Z_FACE   =  88.0         # deepest point of the face rim (at the temples)
RIM_MIN  =  58.0         # shallowest point of the rim (centre, between the eyes)
R_FACE   = 113.8         # radius of the face-form surface that shapes the rim
ZC_FACE  = RIM_MIN + R_FACE

W0, H0, C0 = 178.0, 94.0, 26.0    # outer section at the phone end
W1, H1, C1 = 150.0, 80.0, 15.0    # outer section at the face end
FILLET, WALL = 3.5, 2.4
TRAY_W, TRAY_H, TRAY_C = 170.0, 84.0, 22.0
NC   = 9                 # points per octagon corner -> 72 per section
FIT  = 0.35              # sliding-fit clearance

# ════════════════════════════════════════════════════════ SECTION PROFILES
def _t(z):
    return smoothstep((z - Z_SCREEN) / (Z_FACE - Z_SCREEN)) if z > Z_SCREEN else 0.0

def outer_dims(z):
    t = _t(z)
    return W0 + (W1 - W0) * t, H0 + (H1 - H0) * t, C0 + (C1 - C0) * t

def outer(z, grow=0.0):
    w, h, c = outer_dims(z)
    return chamf_rect(w + 2 * grow, h + 2 * grow, c + grow * (2 - g.SQ2),
                      max(FILLET + grow, 0.3), NC)

def inner(z, grow=0.0):
    """Cavity profile: constant phone tray up to the mask, tapered beyond."""
    if z <= Z_MASK:
        return chamf_rect(TRAY_W + 2 * grow, TRAY_H + 2 * grow,
                          TRAY_C + grow * (2 - g.SQ2), max(2.5 + grow, 0.3), NC)
    w, h, c = outer_dims(z)
    return chamf_rect(w - 2 * WALL + 2 * grow, h - 2 * WALL + 2 * grow,
                      c - WALL * (2 - g.SQ2) + grow * (2 - g.SQ2),
                      max(FILLET - WALL + grow, 0.3), NC)

def half(poly):  return poly[:, 0].max(), poly[:, 1].max()

Z_CARR1 = Z_CARR + CARR_T                       # face-side face of the carrier
CARRIER = inner(Z_CARR1, grow=-FIT)             # sized to pass the taper
CARR_HW, CARR_HH = half(CARRIER)

# ════════════════════════════════════════════════════════ SHARED FEATURES
def nose_arch(grow=0.0, z_end=50.0, z_top=92.0, z_ref=72.0, fmax=1.45):
    """Tapered arch cut at the bottom centre, clearing the bridge of the nose.

    Sized to stay clear of the lens pods (whose underside is at y = -28.25)
    everywhere they exist, then opening out quickly towards the rim."""
    YB, secs = -54.0, []
    for z in np.linspace(z_end, z_top, 18):
        f = np.clip((z - z_end) / (z_ref - z_end), 0, fmax)
        aw = max(50.0 * f ** 0.55, 0.8)
        ah = 16.0 + 30.0 * f
        p = rrect(aw + 2 * grow, 2 * (ah + grow), aw / 2 + grow, 9)
        p[:, 1] += YB
        secs.append((z, p))
    return loft(secs)

def face_form(dz=0.0, subd=5):
    """Solid filling everything beyond the face-contact surface.

    Subtracting it sculpts the concave rim that lets the headset sit on the
    brow, cheeks and temples instead of standing the face off on a flat ring.
    At the centre the rim lands at RIM_MIN; at the temples it reaches Z_FACE."""
    s = trimesh.creation.icosphere(subdivisions=subd, radius=R_FACE)
    s.apply_translation((0, 0, ZC_FACE + dz))
    return s

def collar(gi, go, z0=36.0, z1=114.0, n=18):
    """Open ring hugging the shell's outer surface, from offset gi to go."""
    zs = np.linspace(z0, z1, n)
    inner_s = ([(z0 - 3, outer(z0, grow=gi))] + [(z, outer(z, grow=gi)) for z in zs]
               + [(z1 + 3, outer(z1, grow=gi))])
    return diff(loft([(z, outer(z, grow=go)) for z in zs]), loft(inner_s))

def rim_z(r):
    return ZC_FACE - np.sqrt(max(R_FACE ** 2 - r ** 2, 0.0))

def hex_field(u0, u1, v0, v1, lo, hi, axis='y', pitch=9.2, rad=4.3):
    """Hexagonal perforation lattice. axis = direction the holes run."""
    th = np.pi / 6 + np.linspace(0, 2 * np.pi, 6, endpoint=False)
    hexp = np.column_stack([np.cos(th), np.sin(th)]) * rad
    dv, parts, row, v = pitch * np.sqrt(3) / 2, [], 0, v0
    while v <= v1 + 1e-9:
        us = np.arange(u0, u1 + 1e-9, pitch) + (pitch / 2 if row % 2 else 0.0)
        for u in us:
            if u > u1: continue
            parts.append(prism(hexp + np.array([u, v]), lo, hi))
        row += 1; v += dv
    m = trimesh.util.concatenate(parts)
    if axis == 'y':   # rotate so the extrusion runs along Y and v maps to Z
        m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    return m

def xz_prism(pts, y0, y1):
    """Extrude a CCW polygon given in the XZ plane along Y."""
    m = prism(np.asarray(pts, float), -y1, -y0)
    m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    return m

def xz_panel(w, h, cx, cz, r=10.0, span=240.0):
    """Rounded region in the XZ plane, swept along Y - used to bound vent fields."""
    p = rrect(w, h, r, 13); p[:, 0] += cx; p[:, 1] += cz
    m = prism(p, -span / 2, span / 2)
    m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    return m

def wall_pocket(sx, z0, z1, hy, depth):
    """Blind pocket in the cavity wall that follows the shell's taper."""
    ring = diff(loft([(z0, inner(z0, grow=depth)), (z1, inner(z1, grow=depth))]),
                loft([(z0 - 1, inner(z0, grow=0.0)), (z1 + 1, inner(z1, grow=0.0))]))
    return inter(ring, box(70, hy, (z1 - z0) + 2, (sx * 60, 0, (z0 + z1) / 2)))

def slot(wz, hy, depth, centre, axis='x'):
    """Rounded slot cutter: wz along Z, hy along Y, `depth` along `axis`."""
    p = rrect(wz, hy, min(wz, hy) / 2 - 0.01, 9)
    m = prism(p, -depth / 2, depth / 2)
    if axis == 'x':
        m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0]))
    elif axis == 'y':
        m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    m.apply_translation(centre)
    return m

# ════════════════════════════════════════════════════════ 01 SHELL
def build_shell():
    zs = [Z_MOUTH] + list(np.linspace(Z_SCREEN, Z_FACE + 16, 32))
    m = diff(loft([(z, outer(z)) for z in zs]),
             loft([(Z_MOUTH - 6, inner(Z_MOUTH)), (Z_MASK, inner(Z_MASK))] +
                  [(z, inner(z)) for z in np.linspace(Z_MASK + .001, Z_FACE + 22, 28)]))

    def ringed(z0, z1, bore):
        """Inward frame from the cavity wall to `bore`, between z0 and z1."""
        return diff(loft([(z0, inner(z0, grow=0.5)), (z1, inner(z1, grow=0.5))]),
                    prism(bore, z0 - 1, z1 + 1))

    # mask seat, lens-carrier stop, face-port flange
    m = union(m, ringed(Z_MASK, Z_MASK + 4.0, chamf_rect(163, 77, 20, 2, NC)))
    m = union(m, ringed(Z_CARR1, Z_CARR1 + 3.0, inner(Z_CARR1, grow=-FIT - 2.2)))
    # sculpt the face rim, then groove it for the gasket bead
    m = diff(m, face_form(0.0))
    m = diff(m, inter(collar(-1.2, 1.2), diff(face_form(-9.4), face_form(-5.6))))

    m = diff(m, nose_arch())

    # three-point strap slots
    w, _, _ = outer_dims(62.0)
    _, h, _ = outer_dims(50.0)
    m = diff(m, slot(4.8, 26, 40, (w / 2, 0, 62.0), 'x'),
                slot(4.8, 26, 40, (-w / 2, 0, 62.0), 'x'),
                slot(26, 4.8, 40, (0, h / 2, 50.0), 'y'))

    # Hexagonal cooling grille over the PHONE BAY only.  The lens cavity is
    # deliberately left unperforated: holes there would let daylight onto the
    # lenses and wash out the image.
    m = diff(m, inter(hex_field(-64, 64, -14.0, 3.0, -120, 120),
                      xz_panel(124, 15.6, 0.0, -5.6, r=6.5)))

    # Six slim anti-fog slots low down, where warm breath first reaches the
    # lenses.  Bottom-only, so stray light from above cannot enter.
    for sx in (-1, 1):
        for x in (30.0, 42.0, 54.0):
            m = diff(m, slot(3.2, 14.0, 30.0, (sx * x, -48.0, 50.0), 'y'))

    # shallow groove that retains the face gasket
    m = diff(m, diff(loft([(83.0, outer(83.0, grow=1.0)), (85.6, outer(85.6, grow=1.0))]),
                     loft([(82.4, outer(83.0, grow=-1.0)), (86.2, outer(85.6, grow=-1.0))])))

    # blind pockets: door latches (tray wall) and lens-carrier snaps
    for sx in (-1, 1):
        m = diff(m, slot(4.4, 20, 1.5, (sx * (W0 / 2 - 0.45), 0, -1.4), 'x'))
        m = diff(m, wall_pocket(sx, Z_CARR - 3.4, Z_CARR + 0.8, 15.0, 1.25))
    return m

# ════════════════════════════════════════════════════════ 02 SCREEN MASK
def build_mask():
    m = prism(chamf_rect(TRAY_W - 0.6, TRAY_H - 0.6, TRAY_C, 2.5, NC), Z_SCREEN, Z_MASK)
    for sx in (-1, 1):
        p = chamf_rect(76, 72, 18, 4, NC); p[:, 0] += sx * 41.5
        m = diff(m, prism(p, Z_SCREEN - 1, Z_MASK + 1))
    m = diff(m, box(2.4, 22, 2.2, (0, 0, Z_MASK - 0.9)))     # septum socket
    return m

# ════════════════════════════════════════════════════════ 03 LENS CARRIER
SLOT_W, SLOT_H = 121.0, 57.0
SEPT_Y = SLOT_H / 2 + 6.0

def build_carrier():
    m = loft([(Z_CARR, CARRIER), (Z_CARR1, CARRIER)])
    m = diff(m, prism(rrect(SLOT_W, SLOT_H, 10, 11), Z_CARR - 1, Z_CARR1 + 1))
    xw = half(inner(Z_CARR - 0.5))[0]          # cavity wall beside the hook
    for sx in (-1, 1):                         # ramped snap hooks
        x0, x1 = CARR_HW - 1.0, xw + 0.85
        pts = [(x0, Z_CARR - 2.6), (x1, Z_CARR - 1.2), (x1, Z_CARR + 0.5), (x0, Z_CARR + 0.5)]
        hook = xz_prism([(sx * px, pz) for px, pz in (pts if sx > 0 else pts[::-1])], -6, 6)
        m = union(m, hook)
        m = diff(m, box(1.4, 18, 9.0, (sx * (CARR_HW - 4.2), 0, Z_CARR + CARR_T / 2)))
    for sy in (-1, 1):                                        # septum sockets
        m = diff(m, box(2.4, 13, 4.0, (0, sy * SEPT_Y, Z_CARR + 1.6)))
    return m

# ════════════════════════════════════════════════════════ 04 LENS POD
POD_W, POD_H = 51.0, SLOT_H - 0.5
# The flange seals the slot above and below only.  Making it wider than the
# barrel would make the two pods foul each other (and the septum) at low IPD.
FLG_W, FLG_H = POD_W, 65.0
Z_POD0, Z_POD1 = 28.6, 55.6
ZL0, ZL1 = LENS_CENTRE_Z - LENS_T / 2, LENS_CENTRE_Z + LENS_T / 2
RING_OD = LENS_D + 4.0

def build_pod():
    m = union(prism(rrect(FLG_W, FLG_H, 11, 11), Z_POD0, Z_CARR),      # rear flange
              prism(rrect(POD_W, POD_H, 9, 11), Z_CARR, Z_CARR1),      # waist in slot
              prism(rrect(POD_W, POD_H, 9, 11), Z_CARR1, Z_POD1))      # barrel
    m = diff(m,
             cyl(LENS_D, LENS_T + 0.02, (0, 0, LENS_CENTRE_Z)),        # lens pocket
             cyl(LENS_CLEAR, 40, (0, 0, ZL0 - 20 + 0.005)),            # clear aperture
             cyl(RING_OD + 0.3, (Z_POD1 - ZL1) + 0.02,
                 (0, 0, (ZL1 + Z_POD1) / 2)))                          # ring seat
    m = diff(m, g.ring_profile(np.array([                              # snap groove
             [RING_OD / 2 + 0.15, ZL1 + 1.50], [RING_OD / 2 + 1.25, ZL1 + 1.50],
             [RING_OD / 2 + 1.25, ZL1 + 2.45], [RING_OD / 2 + 0.15, ZL1 + 2.45]])))
    for sy in (-1, 1):                                                 # capture barbs
        y = POD_H / 2 * sy
        m = union(m, box(17, 3.2, 2.2, (0, y + sy * 1.2, Z_CARR1 + 1.1)))
        m = diff(m, box(20, 2.0, 12, (0, y - sy * 1.7, Z_CARR1 - 2.6)))
    # Finger grooves for setting IPD by hand, scalloped into the top and bottom
    # faces only - deep enough to grip, nowhere near the lens bore.
    for k in range(4):
        zk = Z_POD1 - 2.4 - 3.2 * k
        for sy in (-1, 1):
            m = diff(m, cyl(2.6, 70, (0, sy * POD_H / 2, zk), 'x', 20))
    return m

def build_ring():
    r = g.ring_profile(np.array([[LENS_CLEAR / 2, ZL1 + 0.15], [RING_OD / 2, ZL1 + 0.15],
                                 [RING_OD / 2, ZL1 + 2.75], [LENS_CLEAR / 2, ZL1 + 2.75]]))
    r = union(r, g.ring_profile(np.array([   # snap bead with a lead-in ramp
             [RING_OD / 2, ZL1 + 1.55], [RING_OD / 2 + 1.05, ZL1 + 2.05],
             [RING_OD / 2 + 1.05, ZL1 + 2.35], [RING_OD / 2, ZL1 + 2.35]])))
    return diff(r, box(1.8, 70, 8, (0, 32, ZL1 + 1.5)))      # compression split

def build_shim():
    return g.ring_profile(np.array([[LENS_CLEAR / 2 + 0.4, ZL0 - 1.0],
                                    [LENS_D / 2 - 0.4, ZL0 - 1.0],
                                    [LENS_D / 2 - 0.4, ZL0], [LENS_CLEAR / 2 + 0.4, ZL0]]))

# ════════════════════════════════════════════════════════ 05 SEPTUM
def build_septum():
    def hh(z):
        h = half(inner(max(z, Z_MASK + 1e-3)))[1] - 1.2
        return min(h, 37.8 + 1.6 * max(0.0, z - 7.4))      # clear the mask-seat frame
    secs = [(z, rrect(2.0, 2 * hh(z), 1.0, 9)) for z in np.linspace(Z_MASK, Z_CARR, 14)]
    m = loft(secs)
    m = union(m, box(2.0, 20, 2.0, (0, 0, Z_MASK - 1.0)))              # tab -> mask
    for sy in (-1, 1):
        m = union(m, box(2.0, 12, 3.6, (0, sy * SEPT_Y, Z_CARR + 1.8)))  # tabs -> carrier
    return m

# ════════════════════════════════════════════════════════ 06 DOOR
LEAF_Y, LEAF_T, PAD_TOP = 29.0, 1.8, -6.5

def build_door():
    out = outer(Z_MOUTH)
    m = union(loft([(Z_DOOR, out), (Z_MOUTH, out)]),
              diff(prism(chamf_rect(TRAY_W - 0.8, TRAY_H - 0.8, TRAY_C, 2.5, NC),
                         Z_MOUTH, Z_MOUTH + 2.5),
                   prism(chamf_rect(TRAY_W - 8.8, TRAY_H - 8.8, TRAY_C - 4, 2.5, NC),
                         Z_MOUTH - 1, Z_MOUTH + 4)))
    m = diff(m, hex_field(-70, 70, -17, 17, Z_DOOR - 1, Z_MOUTH + 1, axis='z'))

    # Leaf-spring clamps.  Thinned from the INSIDE face so that, printed
    # outside-down, every cut faces up and the pads grow upward: no support.
    zl = Z_DOOR + LEAF_T
    for sy in (-1, 1):
        y = sy * LEAF_Y
        m = diff(m, box(104, 15.0, 9.0, (0, y, zl + 4.5)))                # thin to LEAF_T
        m = diff(m, box(104, 2.2, 9.0, (0, y + sy * 8.6, Z_DOOR + 2.25)))  # free the edges
        m = union(m, box(30, 13, PAD_TOP - zl, (0, y, (zl + PAD_TOP) / 2)))

    # Snap arms that reach along the OUTSIDE of the shell.  Latching inside the
    # tray would foul a full-width phone, and from outside they are easy to
    # pinch open.
    xi = W0 / 2 + 0.3
    for sx in (-1, 1):
        m = union(m, box(4.8, 18, 4.5, (sx * (xi - 0.1), 0, Z_DOOR + 2.25)))   # root
        m = union(m, box(2.2, 18, 19.0, (sx * (xi + 1.1), 0, (Z_DOOR + 0.5) / 2)))
        hook = [(xi - 1.2, -3.4), (xi + 0.8, -3.4), (xi + 0.8, 0.6), (xi - 1.2, -0.4)]
        m = union(m, xz_prism([(sx * px, pz) for px, pz in
                               (hook if sx > 0 else hook[::-1])], -8, 8))
        m = union(m, box(3.4, 18, 2.4, (sx * (xi + 1.7), 0, Z_DOOR + 2.0)))   # finger pad
    m = diff(m, cyl(28, 14, (0, -H0 / 2, Z_DOOR - 2), 'z'))   # thumb notch
    return m

# ════════════════════════════════════════════════════════ 07 PHONE SPACER
SPACER_W, SPACER_X = 10.0, 80.0

def build_stop():
    """End spacer that centres a shorter phone in the tray.  Print 2-4; use
    0-2 per side.  Clipped to the tray's chamfered corner so it always drops in."""
    m = prism(rrect(SPACER_W, TRAY_H + 2, 3, 11), Z_MOUTH + 3.4, Z_SCREEN - 0.8)
    m.apply_translation((SPACER_X, 0, 0))
    m = inter(m, prism(inner(0.0, grow=-0.4), Z_MOUTH - 2, Z_SCREEN + 2))
    m = diff(m, box(6.0, 20.0, 9.0, (SPACER_X + 2.9, 0, Z_MOUTH + 6.0)))  # latch-arm relief
    m.apply_translation((-SPACER_X, 0, 0))
    return m

# ════════════════════════════════════════════════════════ 08 FACE GASKET
GSK_T, GSK_LIP, GSK_H, GSK_SOCK = 2.8, 5.0, 6.5, 10.0   # wall, lip, stand-off, socket

def build_gasket():
    """Slip-on face interface.  Print in TPU (or PLA at a pinch).

    Its socket and its contact face are cut by the same face-form surface that
    sculpts the shell's rim, so the two match exactly however the rim curves."""
    # Every band overlaps its neighbour generously.  Butting them on a shared
    # surface - or on a razor-thin one - leaves cracks and non-manifold edges.
    EPS = 0.5
    m = inter(collar(0.35, 0.35 + GSK_T), diff(face_form(-GSK_SOCK), face_form(0.0)))
    # The contact pad reaches inboard of the socket.  Stepping it in over five
    # bands keeps every face under 45 deg, so the pad needs no support.
    # The first band sits level with the socket, so the staircase never bites
    # into the shell where the two still overlap below the rim.
    n = 7
    for k in range(n):
        gi = 0.35 - (GSK_LIP + 0.35) * k / (n - 1)
        m = union(m, inter(collar(gi, 0.35 + GSK_T),
                           diff(face_form(GSK_H * k / n - EPS),
                                face_form(GSK_H * (k + 1) / n))))
    # bead that drops into the shell's retaining groove
    m = union(m, inter(collar(-0.95, 1.15), diff(face_form(-9.0), face_form(-6.0))))
    return diff(m, nose_arch(grow=2.0, z_top=96.0))

# ════════════════════════════════════════════════════════ 09 STRAP BUCKLE
def build_buckle():
    m = prism(rrect(34, 24, 3.5, 11), 0, 4.0)
    for dy in (7.0, -7.0):
        p = rrect(27, 5.2, 2.2, 9); p[:, 1] += dy
        m = diff(m, prism(p, -1, 5))
    return m

# ════════════════════════════════════════════════════════ PART TABLE
PARTS = [
    ("01_shell",        build_shell,   1),
    ("02_screen_mask",  build_mask,    1),
    ("03_lens_carrier", build_carrier, 1),
    ("04_lens_pod",     build_pod,     2),
    ("05_lens_ring",    build_ring,    2),
    ("06_septum",       build_septum,  1),
    ("07_door",         build_door,    1),
    ("08_phone_spacer", build_stop,    4),
    ("09_face_gasket",  build_gasket,  1),
    ("10_strap_buckle", build_buckle,  2),
    ("11_focus_shim",   build_shim,    4),
]

def assembly(ipd=62.0):
    """All parts placed as assembled, for visual checking."""
    out = {}
    out['shell'] = build_shell()
    out['mask'] = build_mask()
    out['carrier'] = build_carrier()
    out['septum'] = build_septum()
    out['door'] = build_door()
    out['gasket'] = build_gasket()
    pod, ring = build_pod(), build_ring()
    for s, nm in ((-1, 'L'), (1, 'R')):
        p = pod.copy(); p.apply_translation((s * ipd / 2, 0, 0)); out['pod' + nm] = p
        r = ring.copy(); r.apply_translation((s * ipd / 2, 0, 0)); out['ring' + nm] = r
    st = build_stop()
    for s, nm in ((-1, 'L'), (1, 'R')):
        q = st.copy()
        if s < 0:
            q.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [0, 0, 1]))
        q.apply_translation((s * SPACER_X, 0, 0)); out['stop' + nm] = q
    return out
