import numpy as np, trimesh
from trimesh.boolean import union, difference, intersection

# ---- Parametros (mm) ----
W, H, D = 181.0, 158.5, 95.0
T, FLOOR, LID_T = 2.5, 3.0, 3.0
R = 9.0                    # radio de las esquinas exteriores
CH = 2.0                   # bisel inferior de la base
FAN, FAN_T, FAN_HOLES = 80.0, 25.0, 71.5
FAN_C = (52.0, 110.0)
FAN_POST = D - FLOOR - FAN_T - 4.0
PB_X0, PB_X1, PB_Y0, PB_Y1 = 7.0, 173.0, 5.0, 60.0
GAP, SK_T, SK_H, LCH = 0.4, 2.0, 10.0, 1.5   # tapa: holgura, faldon, altura, bisel superior

def box(x0, x1, y0, y1, z0, z1):
    b = trimesh.creation.box(extents=(x1 - x0, y1 - y0, z1 - z0))
    b.apply_translation(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)); return b
def cyl(cx, cy, r, z0, z1, sec=48):
    c = trimesh.creation.cylinder(radius=r, height=z1 - z0, sections=sec)
    c.apply_translation((cx, cy, (z0 + z1) / 2)); return c
def U(p): return union(p, engine='manifold')
def Dif(a, c): return a if not c else difference([a, U(c)], engine='manifold')
def rr_pts(x0, x1, y0, y1, r, z, n=16):
    pts = []
    for cx, cy, a0 in ((x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180), (x1 - r, y0 + r, 270)):
        for a in np.linspace(a0, a0 + 90, n):
            pts.append((cx + r * np.cos(np.radians(a)), cy + r * np.sin(np.radians(a)), z))
    return pts
def rrect(x0, x1, y0, y1, r, z0, z1, ins0=0.0, ins1=0.0):
    p = rr_pts(x0 + ins0, x1 - ins0, y0 + ins0, y1 - ins0, max(r - ins0, 0.5), z0) + \
        rr_pts(x0 + ins1, x1 - ins1, y0 + ins1, y1 - ins1, max(r - ins1, 0.5), z1)
    return trimesh.convex.convex_hull(np.array(p))
def stadium_v(x, w, z0, z1, y0, y1):        # ranura vertical con extremos redondos (pared en Y)
    r = w / 2
    a = box(x - r, x + r, y0, y1, z0 + r, z1 - r)
    c1 = trimesh.creation.cylinder(radius=r, height=y1 - y0, sections=24); c1.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    c2 = c1.copy(); c1.apply_translation((x, (y0 + y1) / 2, z0 + r)); c2.apply_translation((x, (y0 + y1) / 2, z1 - r))
    return U([a, c1, c2])
def stadium_h(x0, x1, y, w, z0, z1):        # ranura horizontal redondeada (tapa)
    r = w / 2
    return U([box(x0 + r, x1 - r, y - r, y + r, z0, z1), cyl(x0 + r, y, r, z0, z1, 24), cyl(x1 - r, y, r, z0, z1, 24)])
def house(y0, y1, z0, z1, xa, xb):
    zp = z1 + (y1 - y0) / 2; ym = (y0 + y1) / 2
    prof = [(y0, z0), (y1, z0), (y1, z1), (ym, zp), (y0, z1)]
    return trimesh.convex.convex_hull(np.array([(x, y, z) for x in (xa, xb) for (y, z) in prof], float))

screw = [(7, 66.5), (W - 7, 66.5), (7, H - 5.5), (W - 7, H - 5.5)]
fx, fy = FAN_C; s = FAN_HOLES / 2
fan_posts = [(fx - s, fy - s), (fx + s, fy - s), (fx - s, fy + s), (fx + s, fy + s)]

# ================= BASE =================
outer = U([rrect(0, W, 0, H, R, 0, CH, ins0=CH, ins1=0), rrect(0, W, 0, H, R, CH, D)])
cavity = rrect(T, W - T, T, H - T, R - T, FLOOR, D + 1)
shell = Dif(outer, [cavity])
P = [shell]
for cx, cy in screw: P.append(cyl(cx, cy, 3.5, 0, D))
for cx, cy in fan_posts:
    P.append(cyl(cx, cy, 6.0, 0, FLOOR + 6)); P.append(cyl(cx, cy, 4.5, 0, FLOOR + FAN_POST))
x0, x1, y0, y1 = PB_X0 - 0.5, PB_X1 + 0.5, PB_Y0 - 0.5, PB_Y1 + 0.5; w = 1.6; h = FLOOR + 7; L = 14
for (cx, cy, sx, sy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
    xa, xb = sorted((cx - sx * w, cx + sx * L)); ya, yb = sorted((cy - sy * w, cy + sy * L))
    P.append(box(xa, xb, cy - sy * w if sy > 0 else cy, cy if sy > 0 else cy + w, FLOOR - 0.5, h))
    P.append(box(cx - sx * w if sx > 0 else cx, cx if sx > 0 else cx + w, ya, yb, FLOOR - 0.5, h))
P.append(box(134, 172, 70.9, 72.5, FLOOR - 0.5, FLOOR + 8)); P.append(box(134, 172, 87.5, 89.1, FLOOR - 0.5, FLOOR + 8))
P.append(box(132.4, 134, 70.9, 89.1, FLOOR - 0.5, FLOOR + 8))
for ex in (-7, W + 7):                         # orejas redondeadas para colgar en la pared
    P.append(cyl(ex, 108, 8, 0, 3)); P.append(box(min(ex, W / 2), max(ex, W / 2) if ex < 0 else ex, 100, 116, 0, 3) if False else box(ex if ex < 0 else W - 3, 3 if ex < 0 else ex, 100, 116, 0, 3))
base = U(P)
envelope = U([outer] + [cyl(ex, 108, 8, 0, 3) for ex in (-7, W + 7)] + [box(-7, 3, 100, 116, 0, 3), box(W - 3, W + 7, 100, 116, 0, 3)])
base = intersection([base, envelope], engine='manifold')

C = []
# rejilla frontal: ranuras verticales redondeadas, mas altas al centro
xs = np.arange(43, 139, 8.0); xm = (xs[0] + xs[-1]) / 2
for x in xs:
    hh = 50 - 22 * ((x - xm) / (xs[-1] - xm)) ** 2
    C.append(stadium_v(x, 4.0, 40 - hh / 2, 40 + hh / 2, -1, T + 1))
C.append(house(20, 45, 12, 20, -1, T + 1)); C.append(house(20, 45, 12, 20, W - T - 1, W + 1))   # USB
C.append(house(72.5, 87.5, 5, 16, W - T - 1, W + 1))                                         # 12 V
C.append(house(72, 88, 6, 12, -1, T + 1))                                                    # cable
C.append(cyl(-7, 108, 2.25, -1, 5)); C.append(cyl(W + 7, 108, 2.25, -1, 5))
for cx, cy in screw: C.append(cyl(cx, cy, 1.3, D - 14, D + 1))
for cx, cy in fan_posts: C.append(cyl(cx, cy, 1.6, FLOOR + FAN_POST - 12, FLOOR + FAN_POST + 1))
base = Dif(base, C)

# ================= TAPA (coordenadas de montaje: faldon z 0..10, placa z 10..13) =================
o = GAP + SK_T; Ro = 3.0; Z0 = SK_H
lo = U([rrect(-o, W + o, -o, H + o, Ro, 0, Z0 + LID_T - LCH), rrect(-o, W + o, -o, H + o, Ro, Z0 + LID_T - LCH, Z0 + LID_T, ins0=0, ins1=LCH)])
lin = box(-GAP, W + GAP, -GAP, H + GAP, -1, Z0)
lid = Dif(lo, [lin])
cuts = [cyl(fx, fy, 37.5, Z0 - 1, Z0 + LID_T + 1, 96)] + [cyl(cx, cy, 1.7, Z0 - 1, Z0 + LID_T + 1) for cx, cy in screw]
for i, yy in enumerate(np.arange(13, 56, 6.0)):     # rejilla sobre los sensores: ranuras redondeadas
    cuts.append(stadium_h(46, 124, yy, 3.4, Z0 - 1, Z0 + LID_T + 1))
cuts.append(box(-o - 1, W + o + 1, -o - 1, H + o + 1, Z0 + LID_T - 0.6, Z0 + LID_T + 1).difference(
    rrect(-o + 6, W + o - 6, -o + 6, H + o - 6, 4, Z0, Z0 + LID_T + 2), engine='manifold').intersection(
    rrect(-o + 4.8, W + o - 4.8, -o + 4.8, H + o - 4.8, 5.2, Z0, Z0 + LID_T + 2), engine='manifold'))   # ranura decorativa
lid = Dif(lid, cuts)
rings = [Dif(cyl(fx, fy, r + 0.8, Z0, Z0 + LID_T, 96), [cyl(fx, fy, r - 0.8, Z0 - 1, Z0 + LID_T + 1, 96)]) for r in (13, 25)]
spokes = [box(fx - 37.6, fx + 37.6, fy - 0.9, fy + 0.9, Z0, Z0 + LID_T), box(fx - 0.9, fx + 0.9, fy - 37.6, fy + 37.6, Z0, Z0 + LID_T)]
for a in (45, 135):
    b = box(-37.6, 37.6, -0.9, 0.9, Z0, Z0 + LID_T); b.apply_transform(trimesh.transformations.rotation_matrix(np.radians(a), [0, 0, 1])); b.apply_translation((fx, fy, 0)); spokes.append(b)
g = U(rings + spokes + [cyl(fx, fy, 5, Z0, Z0 + LID_T)])
g = intersection([g, cyl(fx, fy, 38, Z0 - 1, Z0 + LID_T + 1, 96)], engine='manifold')
lid = U([lid, g])

# ---- verificaciones ----
ghost = {'protoboard': box(PB_X0, PB_X1, PB_Y0, PB_Y1, FLOOR, FLOOR + 8.5),
         'cables': box(PB_X0 + 2, PB_X1 - 2, PB_Y0 + 2, PB_Y1 - 2, FLOOR + 8.5, FLOOR + 88.5),
         'ventilador': box(fx - 40, fx + 40, fy - 40, fy + 40, FLOOR + FAN_POST, FLOOR + FAN_POST + FAN_T),
         'adaptador': box(134, 172, 73.5, 86.5, FLOOR, FLOOR + 13)}
for k, g_ in ghost.items():
    print('choque', k, round(intersection([base, g_], engine='manifold').volume, 2))
m = lid.copy(); m.apply_translation((0, 0, D - SK_H))
for n, mm in (('base', base), ('tapa', lid)):
    print(n, mm.is_watertight, round(mm.volume / 1000, 1), 'cm3', np.round(mm.bounds, 1).tolist())

pr = lid.copy(); pr.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0])); pr.apply_translation(-pr.bounds[0])
pr.export('Carcasa_TAPA.stl')

