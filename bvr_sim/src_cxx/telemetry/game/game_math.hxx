#pragma once

#include "game_types.hxx"

#include <array>

namespace bvr_sim {

class GameMath {
public:
    static Float4x4 identity_matrix();
    static Float4x4 multiply(const Float4x4& a, const Float4x4& b);
    static Float4x4 translation_matrix(float x, float y, float z);
    static Float4x4 scale_matrix(float sx, float sy, float sz);
    static Float4x4 rotation_y_matrix(float angle);
    static Float4x4 shadow_projection_matrix(const std::array<float, 4>& plane, const std::array<float, 4>& light);

    static Float3x3 multiply(const Float3x3& a, const Float3x3& b);
    static Float3x3 rotation_x_matrix(float angle_rad);
    static Float3x3 rotation_y_matrix_3x3(float angle_rad);
    static Float3x3 rotation_z_matrix(float angle_rad);
    static Float3x3 build_sim_orientation_matrix(const std::array<double, 3>& orientation);
    static Float3x3 convert_nwu_matrix_to_viewer(const Float3x3& nwu_matrix);
    static Float4x4 row_vector_matrix_from_mat3(const Float3x3& column_vector_matrix);
};

} // namespace bvr_sim
