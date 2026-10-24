import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, FancyArrowPatch, Arc, Rectangle

plt.rcParams["axes.unicode_minus"] = False

# ---- Plate (Plaquette Ta avec rehausse), mm ----
W_PLATE, H_PLATE = 18.0, 15.5      # body
W_RISER = 11.0                     # rehausse width (centre)
T_BASE, T_TOTAL = 1.1, 5.0         # base plate thickness, total thickness
T_RISER = T_TOTAL - T_BASE         # 3.9
NECK_W, NECK_H = 1.8, 2.0
TAB_W, TAB_H = 4.0, 4.0
CH_H, CH_W = 2.0, 0.5              # bottom chamfer
# ---- Example sample (L along ST, W along Z, H along SN) ----
S_L, S_W, S_H = 3.0, 2.0, 0.5
S_OFF = (1.5, 2.0)                 # sample centre on plate (ST, Z) relative to plate centre
SRN_AXIS = (-1.0, -2.0)            # SRn axis piercing point on plate (ST, Z), adjustable
SRZ_AXIS_N = 2.0                   # SRz axis position along SN behind the sample surface, adjustable

u_t = np.array([1, -1]) / np.sqrt(2)   # +ST  (ST<0 -> upper-left)
u_n = np.array([1, 1]) / np.sqrt(2)    # +SN  (away from analyzer)


def arrow(ax, p0, p1, color="k", lw=1.6, ms=14, style="-|>", **kw):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle=style, mutation_scale=ms,
                                 color=color, lw=lw, **kw))


def box_top(s0, s1, n0, n1, rot=0.0):
    """Rectangle in (ST, SN) coordinates -> lab xy, rotated about z by rot (deg, math CCW)."""
    pts = [s * u_t + n * u_n for s, n in [(s0, n0), (s1, n0), (s1, n1), (s0, n1)]]
    c, s_ = np.cos(np.radians(rot)), np.sin(np.radians(rot))
    R = np.array([[c, -s_], [s_, c]])
    return [R @ p for p in pts]


fig = plt.figure(figsize=(20, 7.6))
gs = fig.add_gridspec(1, 3, width_ratios=[1.25, 1, 0.85])

# ================= 1. TOP VIEW =================
ax = fig.add_subplot(gs[0])
ax.set_title("(1) Top view (looking down -Z)  —  SRz=0, SN=0, ST=0", fontsize=13)

# analyzer focal plane
L = 26
ax.plot([-L / np.sqrt(2), L / np.sqrt(2)], [L / np.sqrt(2), -L / np.sqrt(2)], "--", color="tab:purple", lw=1.2)
ax.text(-17.5, 19.5, "Analyzer focal plane\n(upper-left → lower-right, 45°)", color="tab:purple", fontsize=10)

def draw_plate_top(rot, alpha=1.0, ls="-"):
    kw = dict(closed=True, alpha=alpha, ls=ls, lw=1.2)
    # base plate (full 18 mm), behind riser
    ax.add_patch(Polygon(box_top(-W_PLATE / 2, W_PLATE / 2, S_H + T_RISER, S_H + T_TOTAL, rot),
                         fc="#c9c9c9", ec="k", **kw))
    # riser (11 mm)
    ax.add_patch(Polygon(box_top(-W_RISER / 2, W_RISER / 2, S_H, S_H + T_RISER, rot),
                         fc="#e3e3e3", ec="k", **kw))
    # sample (on riser, front surface at SN focus)
    ax.add_patch(Polygon(box_top(S_OFF[0] - S_L / 2, S_OFF[0] + S_L / 2, 0, S_H, rot),
                         fc="tab:orange", ec="k", **kw))

draw_plate_top(0)
draw_plate_top(15, alpha=0.35, ls="--")
ax.text(12.5, 3.5, "SRz < 0\n(CCW from top)", color="gray", fontsize=10)
ax.add_patch(Arc((0, 0), 24, 24, theta1=-40, theta2=-22, color="gray", lw=1.5))
arrow(ax, (12 * np.cos(np.radians(-25)), 12 * np.sin(np.radians(-25))),
      (12 * np.cos(np.radians(-20)), 12 * np.sin(np.radians(-20))), color="gray")

# beam
arrow(ax, (0, -27), (0, -0.4), color="tab:red", lw=2.5, ms=20)
ax.text(0.7, -25, "Beam (+y)", color="tab:red", fontsize=12)

# analyzer lens (cone from lower-left)
d = -u_n
tip = d * 6
base_c = d * 22
perp = u_t
ax.add_patch(Polygon([tip + perp * 1.5, tip - perp * 1.5, base_c - perp * 5, base_c + perp * 5],
                     closed=True, fc="#b8d4f0", ec="tab:blue"))
ax.text(-24, -14, "Analyzer\n(lens axis ⊥ focal plane)", color="tab:blue", fontsize=10)
ax.plot(0, 0, "+", color="tab:blue", ms=16, mew=2)
ax.text(-3.5, 1.4, "Focus", color="tab:blue", fontsize=10)

# motor axes
o = np.array([16, -14])
arrow(ax, o, o + u_t * 7, color="tab:green")
arrow(ax, o, o + u_n * 7, color="tab:green")
ax.text(*(o + u_t * 7.6 + [0, -1]), "+ST", color="tab:green", fontsize=11)
ax.text(*(o + u_n * 7.6), "+SN", color="tab:green", fontsize=11)
ax.text(-25, 25.5, "ST<0 → sample moves upper-left\nSN↑ → away from analyzer (SN=65: transfer)", color="tab:green", fontsize=10, va="top")
arrow(ax, u_n * 8, u_n * 19, color="tab:green", ls=":", lw=1.4)
ax.text(*(u_n * 19 + [0.5, 0]), "SN→65 transfer", color="tab:green", fontsize=9)

# lab axes
lo = np.array([22, -27])
arrow(ax, lo, lo + [5, 0], ms=10, lw=1)
arrow(ax, lo, lo + [0, 5], ms=10, lw=1)
ax.text(lo[0] + 5.3, lo[1] - 0.4, "x", fontsize=10)
ax.text(lo[0] - 0.4, lo[1] + 5.6, "y", fontsize=10)
ax.plot(*lo, "o", mfc="w", mec="k", ms=7)
ax.plot(*lo, ".", color="k", ms=3)
ax.text(lo[0] - 3.2, lo[1] - 1.8, "z ⊙", fontsize=10)

ax.text(-26, -29.5, "grey: base plate 1.1 mm   light grey: riser 3.9 mm   orange: sample (height H)\ndashed: SRz rotation",
        fontsize=9, color="dimgray")
ax.set_xlim(-27, 30)
ax.set_ylim(-31, 27)
ax.set_aspect("equal")
ax.grid(alpha=0.2)
ax.set_xlabel("x / mm")
ax.set_ylabel("y / mm")

# ================= 2. FRONT VIEW (from analyzer) =================
ax = fig.add_subplot(gs[1])
ax.set_title("(2) View from analyzer to sample  —  SRn=120 (vertical)", fontsize=13)
w, h = W_PLATE / 2, H_PLATE / 2
body = [(-w, h), (-w, -h + CH_H), (-w + CH_W, -h), (w - CH_W, -h), (w, -h + CH_H), (w, h),
        (NECK_W / 2, h), (NECK_W / 2, h + NECK_H), (TAB_W / 2, h + NECK_H), (TAB_W / 2, h + NECK_H + TAB_H),
        (-TAB_W / 2, h + NECK_H + TAB_H), (-TAB_W / 2, h + NECK_H), (-NECK_W / 2, h + NECK_H), (-NECK_W / 2, h)]
ax.add_patch(Polygon(body, closed=True, fc="#c9c9c9", ec="k", lw=1.3))
ax.add_patch(Rectangle((-W_RISER / 2, -h), W_RISER, H_PLATE, fc="#e3e3e3", ec="k", lw=1.3))
ax.add_patch(Rectangle((S_OFF[0] - S_L / 2, S_OFF[1] - S_W / 2), S_L, S_W, fc="tab:orange", ec="k"))
ax.text(S_OFF[0] - S_L / 2 - 0.2, S_OFF[1] + S_W / 2 + 0.4, "Sample L×W", fontsize=10, color="tab:orange")
# beam spot at (ST0, SZ0)
ax.plot(0, 0, "+", color="tab:red", ms=18, mew=2.2)
ax.text(0.4, -1.3, "Beam spot / focus\n(ST0=0, SZ0=40)", color="tab:red", fontsize=9)
# dims
ax.annotate("", (-w, -h - 1.6), (w, -h - 1.6), arrowprops=dict(arrowstyle="<->"))
ax.text(0, -h - 2.6, "18", ha="center")
ax.annotate("", (-W_RISER / 2, -h - 0.7), (W_RISER / 2, -h - 0.7), arrowprops=dict(arrowstyle="<->", color="dimgray"))
ax.text(-3.8, -h - 0.55, "riser 11", fontsize=8, color="dimgray")
ax.annotate("", (-w - 1, -h), (-w - 1, h), arrowprops=dict(arrowstyle="<->"))
ax.text(-w - 2.3, 0, "15.5", rotation=90, va="center")
ax.text(TAB_W / 2 + 0.4, h + NECK_H + 1.5, "tab 4×4\nneck 1.8", fontsize=8, color="dimgray")
# axes
o = np.array([-13.0, -14.6])
arrow(ax, o, o + [4, 0], color="tab:green")
arrow(ax, o, o + [0, 4], color="tab:green")
ax.text(o[0] + 4.3, o[1] - 0.3, "+ST (towards lower-right)", color="tab:green", fontsize=10)
ax.text(o[0] - 0.6, o[1] + 4.5, "+Z (SZ↑)", color="tab:green", fontsize=10)
ax.text(-12.5, 13.8, "SZ: 40 = centre, 35 = stage 5 mm down", color="tab:green", fontsize=9)
# SRn rotation (axis offset from plate centre / beam spot)
ax.plot(*SRN_AXIS, "o", mfc="none", mec="tab:purple", ms=9, mew=2)
ax.plot(*SRN_AXIS, ".", color="tab:purple", ms=4)
ax.text(SRN_AXIS[0] - 6.6, SRN_AXIS[1] - 1.6, "SRn axis\n(offset a_t, a_z adjustable)", color="tab:purple", fontsize=9)
cx, cz = SRN_AXIS
ax.add_patch(Arc((cx, cz), 30, 30, theta1=65, theta2=105, color="tab:purple", lw=1.6))
arrow(ax, (cx + 15 * np.cos(np.radians(98)), cz + 15 * np.sin(np.radians(98))),
      (cx + 15 * np.cos(np.radians(110)), cz + 15 * np.sin(np.radians(110))), color="tab:purple")
# piezo stage (rides on SRn, sample frame)
po = np.array([S_OFF[0] + S_L / 2 + 0.6, S_OFF[1] - S_W / 2 - 0.2])
arrow(ax, po, po + [3, 0], color="tab:brown", ms=10, lw=1.3)
arrow(ax, po, po + [0, 3], color="tab:brown", ms=10, lw=1.3)
ax.text(po[0] + 3.1, po[1] - 0.4, "PIX", color="tab:brown", fontsize=9)
ax.text(po[0] - 0.3, po[1] + 3.2, "PIY", color="tab:brown", fontsize=9)
ax.text(-6.0, -12.9, "Piezo (rides on SRn/SRz, sample frame):\nPIX 0→300 µm = left→right, PIY 0→300 µm = down→up\ncentre 150,150",
        color="tab:brown", fontsize=8)
ax.text(-13.0, 11.0, "SRn 120→130\nCCW (about sample normal)", color="tab:purple", fontsize=10)
ax.set_xlim(-14.5, 15)
ax.set_ylim(-16, 15.5)
ax.set_aspect("equal")
ax.grid(alpha=0.2)
ax.set_xlabel("along ST / mm (viewing direction = +SN)")
ax.set_ylabel("Z / mm")

# ================= 3. SIDE VIEW =================
ax = fig.add_subplot(gs[2])
ax.set_title("(3) Side view (along ST)  —  SN & thickness", fontsize=13)
# n axis: 0 = sample surface = focus; + away from analyzer
ax.add_patch(Rectangle((S_H, -h), T_RISER, H_PLATE, fc="#e3e3e3", ec="k"))
ax.add_patch(Rectangle((S_H + T_RISER, -h), T_BASE, H_PLATE + NECK_H + TAB_H, fc="#c9c9c9", ec="k"))
ax.add_patch(Rectangle((0, S_OFF[1] - S_W / 2), S_H, S_W, fc="tab:orange", ec="k"))
ax.plot([0, 0], [-12, 14], "--", color="tab:blue")
ax.text(0.15, -12.4, "Analyzer focal plane", color="tab:blue", fontsize=9)
ax.plot([SRZ_AXIS_N, SRZ_AXIS_N], [-14, 14.5], "-.", color="tab:purple", lw=1.2)
ax.text(SRZ_AXIS_N + 0.2, 14.6, "SRz axis? (offset adjustable)", color="tab:purple", fontsize=8)
arrow(ax, (-9, 0), (-0.3, 0), color="tab:blue", lw=2)
ax.text(-9, 0.6, "from analyzer", color="tab:blue", fontsize=10)
ax.annotate("", (S_H, -h - 1), (S_H + T_TOTAL, -h - 1), arrowprops=dict(arrowstyle="<->"))
ax.text(S_H + 1.2, -h - 2.2, "5.0 (plate total)", fontsize=9)
ax.annotate("", (S_H + T_RISER, h + 1), (S_H + T_TOTAL, h + 1), arrowprops=dict(arrowstyle="<->"))
ax.text(S_H + T_TOTAL + 0.3, h + 0.6, "1.1", fontsize=9)
ax.text(S_H + 0.3, 6.0, "riser\n3.9", fontsize=8, color="dimgray")
ax.annotate("", (0, S_OFF[1] + S_W / 2 + 0.7), (S_H, S_OFF[1] + S_W / 2 + 0.7), arrowprops=dict(arrowstyle="<->", color="tab:orange"))
ax.text(-3.2, S_OFF[1] + S_W / 2 + 1.4, "H sample", fontsize=9, color="tab:orange")
arrow(ax, (S_H + T_TOTAL + 1.2, -4), (S_H + T_TOTAL + 5.5, -4), color="tab:green")
ax.text(S_H + T_TOTAL + 1.2, -5.2, "+SN (→65 transfer)", fontsize=9, color="tab:green")
ax.text(-9.5, -15.2, "SN = SN_f + H   (sample surface at focus)", fontsize=10, color="tab:green")
ax.set_xlim(-10, 12)
ax.set_ylim(-16, 15.5)
ax.set_aspect("equal")
ax.grid(alpha=0.2)
ax.set_xlabel("along SN / mm")
ax.set_ylabel("Z / mm")

fig.tight_layout()
fig.savefig("geometry_draft_v2.png", dpi=130)
