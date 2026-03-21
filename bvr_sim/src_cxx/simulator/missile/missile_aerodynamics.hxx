#pragma once

#include "../../c3utils/c3utils.hxx"
#include <array>
#include <utility>

namespace bvr_sim {

using namespace c3utils;

class MissileAerodynamics {
public:
    static constexpr int TABLE_SIZE = 26;

    // --- Mach table and coefficient tables ---
    static constexpr std::array<double, TABLE_SIZE> MACH_TABLE = {
        0.0,  0.2,    0.4,     0.6,    0.8,     1.0,    1.2,    1.4,    1.6,    1.8,    2.0,
        2.2,  2.4,    2.6,     2.8,    3.0,     3.2,    3.4,    3.6,    3.8,    4.0,    4.2,
        4.4,  4.6,    4.8,     5.0
    };

    static constexpr std::array<double, TABLE_SIZE> CX0_TABLE = {
        0.468, 0.468,  0.468,   0.468,  0.479,  0.751,  0.88,   0.8572, 0.8132, 0.7645, 0.7205,
        0.6808, 0.6447, 0.6119, 0.582,  0.5545, 0.5292, 0.5057, 0.4838, 0.4633, 0.4439, 0.4256,
        0.4083, 0.3921, 0.377,  0.364
    };

    static constexpr std::array<double, TABLE_SIZE> CXB_TABLE = {
        0.021, 0.021,  0.021,   0.021,  0.021,  0.138,  0.153,  0.146,  0.1382, 0.1272, 0.1167,
        0.1073, 0.0987, 0.0909, 0.0837, 0.077,  0.0708, 0.065,  0.0595, 0.0544, 0.0495, 0.0449,
        0.0406, 0.0364, 0.0324, 0.0286
    };

    static constexpr std::array<double, TABLE_SIZE> K1_TABLE = {
        0.0025, 0.0025, 0.0025,  0.0025, 0.0025, 0.0024, 0.002,  0.00172, 0.00151, 0.00135, 0.00123,
        0.00114, 0.00106, 0.00099, 0.00094, 0.00088, 0.00084, 0.00079, 0.00074, 0.0007, 0.00066, 0.00062,
        0.00058, 0.00055, 0.00052, 0.0005
    };

    static constexpr std::array<double, TABLE_SIZE> K2_TABLE = {
        -0.0024, -0.0024, -0.0024, -0.0024, -0.0024, -0.0024, -0.00206, -0.00186, -0.00168, -0.0015, -0.00134,
        -0.00118, -0.00104, -0.0009, -0.00078, -0.00066, -0.00056, -0.00046, -0.00038, -0.0003, -0.00024, -0.00018,
        -0.00014, -0.0001, -0.00008, -0.00006
    };

    // --- ModelData wave / compressibility params (ModelData 中抽取) ---
    // 顺序参考 ModelData: [ ..., 0.029, 0.06, 0.01, -0.245, 0.08, 0.7, ... ]
    struct AerodynamicParams {
        double Cx_k0;                   // subsonic baseline (低速阈值)
        double Cx_k1;                   // 波峰高度
        double Cx_k2;                   // 峰陡度（越小越陡）
        double Cx_k3;                   // supersonic baseline offset（可用于修正）
        double Cx_k4;                   // 波峰后下降陡度
        double supersonic_sqrt_coef;
        double S_ref;                   // 参考面积 math.pi*(Diameter/2)**2
    };

    static constexpr AerodynamicParams DEFAULT_PARAMS = {
        0.029,      // Cx_k0
        0.06,       // Cx_k1
        0.01,       // Cx_k2
        -0.245,     // Cx_k3
        0.08,       // Cx_k4
        0.7,        // supersonic_sqrt_coef
        0.0248719   // S_ref
    };

public:
    AerodynamicParams params;

    MissileAerodynamics() noexcept : params(DEFAULT_PARAMS) {}

    explicit MissileAerodynamics(const AerodynamicParams& p) noexcept : params(p) {}

    double speed_of_sound(double alt_m) const noexcept;

    double air_density(double alt_m) const noexcept;

    double linear_interp(double x, const std::array<double, TABLE_SIZE>& x_table,
                        const std::array<double, TABLE_SIZE>& y_table) const noexcept;

    std::pair<double, double> compute_drag(double v, double alpha_rad, double alt_m) const noexcept;
};

}
