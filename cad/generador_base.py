import numpy as np, trimesh
from trimesh.boolean import union, difference, intersection

# ---- Parámetros (mm) ----
W, H, D = 181.0, 158.5, 95.0      # D: altura de la base (cables hasta 80 mm sobre la protoboard)
T, FLOOR, LID_T = 2.5, 3.0, 3.0
FAN, FAN_T, FAN_HOLES = 80.0, 25.0, 71.5
FAN_C = (52.0, 110.0)
FAN_POST = D - FLOOR - FAN_T - 4.0  # 4 mm libres para las cabezas de los tornillos
PB_X0, PB_X1, PB_Y0, PB_Y1 = 7.0, 173.0, 5.0, 60.0
PB_H = 8.5

def box(x0, x1, y0, y1, z0, z1):
    b = trimesh.creation.box(extents=(x1 - x0, y1 - y0, z1 - z0))
    b.apply_translation(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)); return b
def cyl(cx, cy, r, z0, z1, sec=48):
    c = trimesh.creation.cylinder(radius=r, height=z1 - z0, sections=sec)
    c.apply_translation((cx, cy, (z0 + z1) / 2)); return c
def U(p): return union(p, engine='manifold')
def Dif(a, c): return a if not c else difference([a, U(c)], engine='manifold')
def cyl_y(cx, cz, r, y0, y1, sec=40):
    c = trimesh.creation.cylinder(radius=r, height=y1 - y0, sections=sec)
    c.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0])); c.apply_translation((cx, (y0 + y1) / 2, cz)); return c
def texto(txt, cx, z, h, prof=0.8):
    from matplotlib.textpath import TextPath
    from matplotlib.font_manager import FontProperties
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    tp = TextPath((0, 0), txt, size=h, prop=FontProperties(family="DejaVu Sans", weight="bold"))
    polys = [Polygon(p) for p in tp.to_polygons() if len(p) > 2]
    geo = None
    for p in polys:
        if not p.is_valid: p = p.buffer(0)
        geo = p if geo is None else geo.symmetric_difference(p)
    minx, miny, maxx, maxy = geo.bounds
    parts = geo.geoms if hasattr(geo, "geoms") else [geo]
    meshes = []
    for g in parts:
        m = trimesh.creation.extrude_polygon(g, prof + 1.0)
        v = m.vertices.copy()
        m.vertices = np.c_[v[:, 0] - (minx + maxx) / 2 + cx, v[:, 2] - 1.0, v[:, 1] - (miny + maxy) / 2 + z]
        m.invert(); meshes.append(m)
    return U(meshes)
def house(y0, y1, z0, z1, xa, xb):
    # ventana con techo en punta a 45° (sin soporte); prisma a lo largo de X
    zp = z1 + (y1 - y0) / 2; ym = (y0 + y1) / 2
    prof = [(y0, z0), (y1, z0), (y1, z1), (ym, zp), (y0, z1)]
    return trimesh.convex.convex_hull(np.array([(x, y, z) for x in (xa, xb) for (y, z) in prof], float))

screw = [(7, 66.5), (W - 7, 66.5), (7, H - 5.5), (W - 7, H - 5.5)]
fx, fy = FAN_C; s = FAN_HOLES / 2
fan_posts = [(fx - s, fy - s), (fx + s, fy - s), (fx - s, fy + s), (fx + s, fy + s)]

P = [box(0, W, 0, H, 0, FLOOR), box(0, W, 0, T, 0, D), box(0, W, H - T, H, 0, D),
     box(0, T, 0, H, 0, D), box(W - T, W, 0, H, 0, D)]
for cx, cy in screw: P.append(cyl(cx, cy, 3.5, 0, D))
for cx, cy in fan_posts:                       # postes altos: base ancha + columna
    P.append(cyl(cx, cy, 6.0, 0, FLOOR + 6))
    P.append(cyl(cx, cy, 4.5, 0, FLOOR + FAN_POST))
# esquineros de la protoboard
x0, x1, y0, y1 = PB_X0 - 0.5, PB_X1 + 0.5, PB_Y0 - 0.5, PB_Y1 + 0.5; w = 1.6; h = FLOOR + 7; L = 14
for (cx, cy, sx, sy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
    xa, xb = sorted((cx - sx * w, cx + sx * L)); ya, yb = sorted((cy - sy * w, cy + sy * L))
    P.append(box(xa, xb, cy - sy * w if sy > 0 else cy, cy if sy > 0 else cy + w, FLOOR - 0.5, h))
    P.append(box(cx - sx * w if sx > 0 else cx, cx if sx > 0 else cx + w, ya, yb, FLOOR - 0.5, h))
# bahía del adaptador jack-bornera
P.append(box(134, 172, 70.9, 72.5, FLOOR - 0.5, FLOOR + 8)); P.append(box(134, 172, 87.5, 89.1, FLOOR - 0.5, FLOOR + 8))
P.append(box(132.4, 134, 70.9, 89.1, FLOOR - 0.5, FLOOR + 8))

# ---- CUNA DEL VENTILADOR AUTOPORTANTE (se imprime sin soportes) ----
FZ = FLOOR + FAN_POST
for cx, cy in fan_posts:
    P.append(cyl(cx, cy, 9.0, 0, FLOOR + 4)); P.append(cyl(cx, cy, 6.0, 0, FZ))
fa0, fa1, fb0, fb1 = fx - 40, fx + 40, fy - 40, fy + 40
g, wt, Lw, Hw = 0.6, 2.4, 16, 12
X0, X1, Y0, Y1 = fa0 - g - wt, fa1 + g + wt, fb0 - g - wt, fb1 + g + wt
torre = Dif(box(X0, X1, Y0, Y1, 0, FZ), [box(X0 + wt, X1 - wt, Y0 + wt, Y1 - wt, -1, FZ + 1)])
ventanas = []
xm, ym = (X0 + X1) / 2, (Y0 + Y1) / 2
def arco_x(xc, y0, y1):   # ventana en pared paralela a X (corte a traves de Y)
    hw = 30; z0, z1 = FLOOR + 5, FZ - 4 - hw
    pr = [(xc - hw, z0), (xc + hw, z0), (xc + hw, z1), (xc, z1 + hw), (xc - hw, z1)]
    return trimesh.convex.convex_hull(np.array([(x, y, z) for y in (y0, y1) for (x, z) in pr], float))
def arco_y(yc, x0, x1):
    hw = 30; z0, z1 = FLOOR + 5, FZ - 4 - hw
    pr = [(yc - hw, z0), (yc + hw, z0), (yc + hw, z1), (yc, z1 + hw), (yc - hw, z1)]
    return trimesh.convex.convex_hull(np.array([(x, y, z) for x in (x0, x1) for (y, z) in pr], float))
ventanas += [arco_x(xm, Y0 - 1, Y0 + wt + 1), arco_x(xm, Y1 - wt - 1, Y1 + 1), arco_y(ym, X0 - 1, X0 + wt + 1), arco_y(ym, X1 - wt - 1, X1 + 1)]
P.append(Dif(torre, ventanas))
for (cx, cy, sx, sy) in ((fa0, fb0, 1, 1), (fa1, fb0, -1, 1), (fa0, fb1, 1, -1), (fa1, fb1, -1, -1)):   # esquineros sobre la torre
    ox, oy = cx - sx * g, cy - sy * g
    P.append(box(*sorted((ox, ox - sx * wt)), *sorted((oy - sy * wt, oy + sy * Lw)), FZ - 2, FZ + Hw))
    P.append(box(*sorted((ox - sx * wt, ox + sx * Lw)), *sorted((oy, oy - sy * wt)), FZ - 2, FZ + Hw))
for cx, cy in fan_posts:   # brazos poste-torre (verticales, desde el piso)
    P.append(box(min(cx, X0), max(cx, X0 + wt) if cx < xm else cx, cy - 1.6, cy + 1.6, FLOOR, FZ) if cx < xm else box(cx, X1, cy - 1.6, cy + 1.6, FLOOR, FZ))
P += [box(-12, 0, 100, 116, 0, 3), box(W, W + 12, 100, 116, 0, 3)]   # orejas
anclas = []
for ax_, ay_ in ((112, 72), (112, 100), (112, 128)):          # anclajes para precintos (ordenar cables)
    blk = box(ax_ - 6, ax_ + 6, ay_ - 3, ay_ + 3, FLOOR - 0.5, FLOOR + 9)
    tun = house(ay_ - 4, ay_ + 4, FLOOR, FLOOR + 3, ax_ - 2.2, ax_ + 2.2)
    tun2 = trimesh.convex.convex_hull(np.array([(x, y, z) for y in (ay_ - 4, ay_ + 4) for (x, z) in ((ax_ - 4, FLOOR), (ax_ + 4, FLOOR), (ax_ + 4, FLOOR + 2.5), (ax_, FLOOR + 6.5), (ax_ - 4, FLOOR + 2.5))]))
    anclas.append(Dif(blk, [tun2]))
P += anclas
base = U(P)

C = []
# ---- rejilla tipo panal (hexagonos con punta arriba: se imprimen sin soporte) ----
def hexa(cx, cz, r, a0, a1, axis):
    pts = []
    for k in range(6):
        ang = np.radians(90 + 60 * k)
        u, v = cx + r * np.cos(ang), cz + r * np.sin(ang)
        for t in (a0, a1):
            pts.append((u, t, v) if axis == 'y' else (t, u, v))
    return trimesh.convex.convex_hull(np.array(pts))
def panal(u0, u1, z0, z1, a0, a1, axis, r=4.6, wall=1.8, forma=None):
    hx = np.sqrt(3) * r + wall; hz = 1.5 * r + wall * np.sqrt(3) / 2
    out = []; row = 0; z = z0 + r
    while z + r <= z1:
        off = (hx / 2) if row % 2 else 0
        u = u0 + np.sqrt(3) / 2 * r + off
        while u + np.sqrt(3) / 2 * r <= u1:
            if forma is None or forma(u, z): out.append(hexa(u, z, r, a0, a1, axis))
            u += hx
        z += hz; row += 1
    return out
cxm, czm = W / 2, 47.0
elipse = lambda u, z: ((u - cxm) / 62) ** 2 + ((z - czm) / 29) ** 2 <= 1.0
C += panal(28, 153, 16, 80, -1, T + 1, 'y', forma=elipse)                     # frente: panal en ovalo
C += panal(96, 150, 30, 76, W - T - 1, W + 1, 'x', r=4.0)                     # costado derecho
C += panal(96, 150, 30, 76, -1, T + 1, 'x', r=4.0)                            # costado izquierdo
# ---- ojales en la pared trasera para colgarla (tornillo de cabeza <= 7 mm) ----
for kx in (112, 162):
    C.append(cyl_y(kx, 62, 4.0, H - T - 1, H + 1)); C.append(box(kx - 2, kx + 2, H - T - 1, H + 1, 62, 72)); C.append(cyl_y(kx, 72, 2.0, H - T - 1, H + 1))
# ---- cavidades para patitas de goma (10 mm) en la cara inferior ----
for px, py in ((16, 14), (W - 16, 14), (16, H - 14), (W - 16, H - 14)):
    C.append(cyl(px, py, 5.4, -1, 1.0))
# ---- texto grabado en el frente ----
C.append(texto("VENTILACIÓN INTELIGENTE  ·  PICO 2 W", cx=W / 2, z=9.0, h=5.5))
C.append(house(20, 45, 12, 20, -1, T + 1)); C.append(house(20, 45, 12, 20, W - T - 1, W + 1))   # USB
C.append(house(72.5, 87.5, 5, 16, W - T - 1, W + 1))     # enchufe 12 V
C.append(house(72, 88, 6, 12, -1, T + 1))                 # paso de cable izquierdo
C.append(cyl(-6, 108, 2.25, -1, 5)); C.append(cyl(W + 6, 108, 2.25, -1, 5))
for cx, cy in screw: C.append(cyl(cx, cy, 1.3, D - 14, D + 1))
base = Dif(base, C)

lid = box(0, W, 0, H, 0, LID_T)
cuts = [cyl(fx, fy, 37, -1, LID_T + 1, 72)] + [cyl(cx, cy, 1.7, -1, LID_T + 1) for cx, cy in screw]
cuts.append(box(42, 128, 9, 57, -1, LID_T + 1))
lid = Dif(lid, cuts)
g = U([cyl(fx, fy, 7, 0, LID_T), box(fx - 38, fx + 38, fy - 1.5, fy + 1.5, 0, LID_T), box(fx - 1.5, fx + 1.5, fy - 38, fy + 38, 0, LID_T)])
g = intersection([g, cyl(fx, fy, 37.5, -1, LID_T + 1, 72)], engine='manifold')
bars = U([box(xx, xx + 1.6, 9, 57, 0, LID_T) for xx in np.arange(46, 127, 5.0)])
lid = U([lid, g, bars])

ghost = {
    'protoboard': box(PB_X0, PB_X1, PB_Y0, PB_Y1, FLOOR, FLOOR + PB_H),
    'cables (80 mm)': box(PB_X0 + 2, PB_X1 - 2, PB_Y0 + 2, PB_Y1 - 2, FLOOR + PB_H, FLOOR + PB_H + 80),
    'ventilador': box(fx - 40, fx + 40, fy - 40, fy + 40, FLOOR + FAN_POST, FLOOR + FAN_POST + FAN_T),
    'adaptador12V': box(134, 172, 73.5, 86.5, FLOOR, FLOOR + 13),
}
for k, g_ in ghost.items():
    try: v = intersection([base, g_], engine='manifold').volume
    except Exception: v = 0
    print('choque', k, round(v, 2), 'mm3')
print('ventilador z:', FLOOR + FAN_POST, '->', FLOOR + FAN_POST + FAN_T, ' tapa en z =', D)
for n, m in (('base', base), ('tapa', lid)):
    print(n, m.is_watertight, round(m.volume / 1000, 1), 'cm3', np.round(m.bounds, 1).tolist())
base.export('Carcasa_BASE.stl')
