import numpy as np
from uhtk.c3utils.i3utils import get_mps
import math

# --- Mach table and coefficient tables ---
_mach_table = np.array([0.0,  0.2,    0.4,     0.6,    0.8,     1.0,    1.2,    1.4,    1.6,    1.8,    2.0,2.2,2.4,2.6,2.8,3.0,3.2,3.4,3.6,3.8,4.0,4.2,4.4,4.6,4.8,5.0])
_Cx0_table = np.array([0.468, 0.468,  0.468,   0.468,  0.479,	0.751,	0.88,	0.8572,	0.8132,	0.7645,	0.7205,	0.6808,	0.6447,	0.6119,	0.582,	0.5545,	0.5292,	0.5057,	0.4838,	0.4633,	0.4439,	0.4256,	0.4083,	0.3921,	0.377,	0.364 ])
_CxB_table = np.array([0.021, 0.021,  0.021,   0.021,  0.021,	0.138,	0.153,	0.146,	0.1382,	0.1272,	0.1167,	0.1073,	0.0987,	0.0909,	0.0837,	0.077,	0.0708,	0.065,	0.0595,	0.0544,	0.0495,	0.0449,	0.0406,	0.0364,	0.0324,	0.0286 ])
_K1_table = np.array([ 0.0025,0.0025, 0.0025,  0.0025, 0.0025,	0.0024,	0.002,	 0.00172, 0.00151, 0.00135,0.00123, 0.00114, 0.00106, 0.00099,0.00094, 0.00088, 0.00084, 0.00079, 0.00074, 0.0007, 0.00066, 0.00062, 0.00058, 0.00055,0.00052, 0.0005 ])
_K2_table = np.array([-0.0024,-0.0024,-0.0024, -0.0024,-0.0024,-0.0024,-0.00206,-0.00186,-0.00168,-0.0015,-0.00134,-0.00118,-0.00104,-0.0009,-0.00078,-0.00066,-0.00056,-0.00046,-0.00038,-0.0003,-0.00024,-0.00018,-0.00014,-0.0001,-0.00008,-0.00006 ])

# --- ModelData wave / compressibility params (ModelData 中抽取) ---
# 顺序参考 ModelData: [ ..., 0.029, 0.06, 0.01, -0.245, 0.08, 0.7, ... ]
Cx_k0 = 0.029  # subsonic baseline (低速阈值)
Cx_k1 = 0.06   # 波峰高度
Cx_k2 = 0.01   # 峰陡度（越小越陡）
Cx_k3 = -0.245 # supersonic baseline offset（可用于修正）
Cx_k4 = 0.08   # 波峰后下降陡度
supersonic_sqrt_coef = 0.7

# 参考面积
S_ref = 0.0248719  # math.pi*(Diameter/2)**2

def speed_of_sound(alt_m):
    return get_mps(1.0, alt_m)


def air_density(alt_m):
    # 指数近似：rho = 1.225 * exp(-z/9300)
    # BUG OverflowError: math range error
    alt_m = min(max(0.0, alt_m), 10_000)
    return 1.225 * math.exp(-alt_m / 9300.0)

def compute_drag(v: float, alpha_rad: float, alt_m: float):
    """
    返回 drag_force (N) 以及用于诊断的 Cx_total.
    v: 速度 magnitude (m/s)
    alpha_rad: 迎角近似
    alt_m: 高度，米
    """
    if v <= 1e-6:
        return 0.0, 0.0

    a = speed_of_sound(alt_m)
    M = v / a

    # 线性插值表值
    Cx0 = float(np.interp(M, _mach_table, _Cx0_table))
    CxB = float(np.interp(M, _mach_table, _CxB_table))
    # print(f"M={M:.2f} | Cx0={Cx0:.3f} | CxB={CxB:.3f} | Cx0+CxB={Cx0+CxB:.3f}")
    K1 = float(np.interp(M, _mach_table, _K1_table))
    K2 = float(np.interp(M, _mach_table, _K2_table))

    # 迎角影响（用 K1 * |alpha| + K2 * alpha^2 作为经验项）
    alpha = alpha_rad
    Cx_alpha = K1 * abs(alpha) + K2 * (alpha ** 2)

    #####################################################################
    # 波阻/跨音速峰值项 —— 经验函数：以 M=1 为中心，宽度由 Cx_k2 控制
    wave_peak = Cx_k1 * math.exp(-((M - 1.0) / Cx_k2) ** 2)
    #####################################################################

    # Cx_k3（超音速基线偏移），可加上
    if M > 1.0:
        # supersonic_decay = Cx_k3 * (1.0 - math.exp(-Cx_k4 * (M - 1.0)))
        # supersonic_decay = Cx_k3 + Cx_k4 * (M - 1.0)
        supersonic_decay = Cx_k3 * 2 * (1.0 - 1.0 / (1.0 + math.exp(-Cx_k4 * (M - 1.0)**2)))
        # supersonic_decay = Cx_k3 * 2 * (1.0 - 1.0 / (1.0 + 1.0))
        # supersonic_decay = Cx_k3
    else:
        supersonic_decay = 0.0

    # 超音速附加项（sqrt）
    supersonic_term = 0.0
    # if M > 1.0:
    # #     # supersonic_term = supersonic_sqrt_coef * math.sqrt(max(0.0, M * M - 1.0))
    #     supersonic_term = supersonic_sqrt_coef * math.sqrt(max(0.0, M - 1.0))

    # 合成总阻力系数 (经验合成)
    Cx_total = Cx0 + CxB + Cx_alpha + wave_peak + supersonic_decay + supersonic_term



    rho = air_density(alt_m)
    D = 0.5 * rho * v * v * S_ref * Cx_total

    return D, Cx_total

def unit_test_v2():
    import os
    import numpy as np
    from matplotlib import pyplot as plt

    # Mach grid
    mach_grid = np.linspace(0.1, 5.0, 300)
    mps_grid = np.linspace(50, 500, 300)

    # Altitudes to compare (m)
    altitudes = [0.0, 5000.0, 10000.0]

    # Small alpha (0 rad) for baseline
    alpha_rad = 0.0

    # Output directory
    out_dir = "./"
    os.makedirs(out_dir, exist_ok=True)
    saved_files = []

    # -------- Plot 1: Cx vs Mach (all altitudes) --------
    plt.figure(figsize=(8, 4))
    for alt in altitudes:
        Cx_vals = []
        for M in mach_grid:
            a = speed_of_sound(alt)
            v = M * a
            _, cx = compute_drag(v, alpha_rad, alt)
            Cx_vals.append(cx)
        plt.plot(mach_grid, Cx_vals, label=f"{int(alt)} m")
    plt.xlabel("Mach")
    plt.ylabel("Cx_total")
    plt.title("Cx vs Mach (alpha=0 rad)")
    plt.legend(title="Altitude")
    plt.tight_layout()
    filename = os.path.join(out_dir, "cx_vs_mach_all_alt.png")
    plt.savefig(filename, dpi=150)
    plt.close()
    saved_files.append(filename)

    # -------- Plot 2: Cx vs mps (all altitudes) --------
    plt.figure(figsize=(8, 4))
    for alt in altitudes:
        Cx_vals = []
        for v in mps_grid:
            _, cx = compute_drag(v, alpha_rad, alt)
            Cx_vals.append(cx)
        plt.plot(mps_grid, Cx_vals, label=f"{int(alt)} m")
    plt.xlabel("Speed (m/s)")
    plt.ylabel("Cx_total")
    plt.title("Cx vs Speed (alpha=0 rad)")
    plt.legend(title="Altitude")
    plt.tight_layout()
    filename = os.path.join(out_dir, "cx_vs_mps_all_alt.png")
    plt.savefig(filename, dpi=150)
    plt.close()
    saved_files.append(filename)

    # -------- Plot 3: Drag vs Mach (all altitudes) --------
    plt.figure(figsize=(8, 4))
    for alt in altitudes:
        drag_vals = []
        for M in mach_grid:
            a = speed_of_sound(alt)
            v = M * a
            drag, _ = compute_drag(v, alpha_rad, alt)
            drag_vals.append(drag)
        plt.plot(mach_grid, drag_vals, label=f"{int(alt)} m")
    plt.xlabel("Mach")
    plt.ylabel("Drag (N)")
    plt.title("Drag vs Mach (alpha=0 rad)")
    plt.legend(title="Altitude")
    plt.tight_layout()
    filename = os.path.join(out_dir, "drag_vs_mach_all_alt.png")
    plt.savefig(filename, dpi=150)
    plt.close()
    saved_files.append(filename)

    # -------- Plot 4: Drag vs mps (all altitudes) --------
    plt.figure(figsize=(8, 4))
    for alt in altitudes:
        drag_vals = []
        for v in mps_grid:
            drag, _ = compute_drag(v, alpha_rad, alt)
            drag_vals.append(drag)
        plt.plot(mps_grid, drag_vals, label=f"{int(alt)} m")
    plt.xlabel("Speed (m/s)")
    plt.ylabel("Drag (N)")
    plt.title("Drag vs Speed (alpha=0 rad)")
    plt.legend(title="Altitude")
    plt.tight_layout()
    filename = os.path.join(out_dir, "drag_vs_mps_all_alt.png")
    plt.savefig(filename, dpi=150)
    plt.close()
    saved_files.append(filename)

    # -------- Print samples for verification --------
    for alt in [0, 5000, 10000]:
        v = 340
        D, Cx = compute_drag(v, 0, alt)
        print(f"v={v:.2f} m/s | alt={alt:5.0f} m | rho={air_density(alt):.3f} | Cx={Cx:.3f} | D={D:.2f} N")

    for alt in [0, 5000, 10000]:
        v = speed_of_sound(alt)
        D, Cx = compute_drag(v, 0, alt)
        print(f"v={v:.2f} m/s | alt={alt:5.0f} m | rho={air_density(alt):.3f} | Cx={Cx:.3f} | D={D:.2f} N")
    for mach in [0.9, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2, 1.25, 1.3, 1.35, 1.4]:
        v = get_mps(mach, alt)
        D, Cx = compute_drag(v, 0, alt)
        print(f"v={v:.2f} m/s | alt={alt:5.0f} m | Mach={mach:.2f} | rho={air_density(alt):.3f} | Cx={Cx:.3f} | D={D:.2f} N")

    print(f"\nSaved plots: {saved_files}")