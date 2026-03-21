#include "missile_aerodynamics.hxx"
#include <cmath>
#include <algorithm>

namespace bvr_sim {

using namespace c3utils;

double MissileAerodynamics::speed_of_sound(double alt_m) const noexcept {
    return get_mps(1.0, alt_m);
}

double MissileAerodynamics::air_density(double alt_m) const noexcept {
    // 指数近似：rho = 1.225 * exp(-z/9300)
    // BUG OverflowError: math range error
    alt_m = std::clamp(alt_m, 0.0, 10000.0);
    return 1.225 * std::exp(-alt_m / 9300.0);
}

double MissileAerodynamics::linear_interp(
    double x,
    const std::array<double, TABLE_SIZE>& x_table,
    const std::array<double, TABLE_SIZE>& y_table
) const noexcept {
    if (x <= x_table[0]) {
        return y_table[0];
    }
    if (x >= x_table[TABLE_SIZE - 1]) {
        return y_table[TABLE_SIZE - 1];
    }

    for (int i = 0; i < TABLE_SIZE - 1; ++i) {
        if (x >= x_table[i] && x <= x_table[i + 1]) {
            double t = (x - x_table[i]) / (x_table[i + 1] - x_table[i]);
            return y_table[i] + t * (y_table[i + 1] - y_table[i]);
        }
    }

    return y_table[TABLE_SIZE - 1];
}

std::pair<double, double> MissileAerodynamics::compute_drag(
    double v,
    double alpha_rad,
    double alt_m
) const noexcept {
    // 返回 drag_force (N) 以及用于诊断的 Cx_total.
    // v: 速度 magnitude (m/s)
    // alpha_rad: 迎角近似
    // alt_m: 高度，米
    if (v <= 1e-6) {
        return {0.0, 0.0};
    }

    double a = speed_of_sound(alt_m);
    double M = v / a;

    // 线性插值表值
    double Cx0 = linear_interp(M, MACH_TABLE, CX0_TABLE);
    double CxB = linear_interp(M, MACH_TABLE, CXB_TABLE);
    // printf(f"M={M:.2f} | Cx0={Cx0:.3f} | CxB={CxB:.3f} | Cx0+CxB={Cx0+CxB:.3f}")
    double K1 = linear_interp(M, MACH_TABLE, K1_TABLE);
    double K2 = linear_interp(M, MACH_TABLE, K2_TABLE);

    // 迎角影响（用 K1 * |alpha| + K2 * alpha^2 作为经验项）
    double alpha = alpha_rad;
    double Cx_alpha = K1 * std::abs(alpha) + K2 * (alpha * alpha);

    // =====================================================================
    // 波阻/跨音速峰值项 —— 经验函数：以 M=1 为中心，宽度由 Cx_k2 控制
    // =====================================================================
    double wave_peak = params.Cx_k1 * std::exp(-std::pow((M - 1.0) / params.Cx_k2, 2.0));

    // Cx_k3（超音速基线偏移），可加上
    double supersonic_decay = 0.0;
    if (M > 1.0) {
        // supersonic_decay = params.Cx_k3 * (1.0 - std::exp(-params.Cx_k4 * (M - 1.0)));
        // supersonic_decay = params.Cx_k3 + params.Cx_k4 * (M - 1.0);
        supersonic_decay = params.Cx_k3 * 2.0 * (1.0 - 1.0 / (1.0 + std::exp(-params.Cx_k4 * std::pow(M - 1.0, 2.0))));
        // supersonic_decay = params.Cx_k3 * 2.0 * (1.0 - 1.0 / (1.0 + 1.0));
        // supersonic_decay = params.Cx_k3;
    }

    // 超音速附加项（sqrt）
    double supersonic_term = 0.0;
    // if (M > 1.0) {
    //     // supersonic_term = params.supersonic_sqrt_coef * std::sqrt(std::max(0.0, M * M - 1.0));
    //     supersonic_term = params.supersonic_sqrt_coef * std::sqrt(std::max(0.0, M - 1.0));
    // }

    // 合成总阻力系数 (经验合成)
    double Cx_total = Cx0 + CxB + Cx_alpha + wave_peak + supersonic_decay + supersonic_term;

    double rho = air_density(alt_m);
    double D = 0.5 * rho * v * v * params.S_ref * Cx_total;

    return {D, Cx_total};
}

}
