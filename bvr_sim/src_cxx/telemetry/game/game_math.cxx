#include "game_types.hxx"

#include <cmath>

namespace bvr_sim {

Float4x4 Float4x4::identity() {
    Float4x4 out{};
    out.m[0][0] = 1.0f;
    out.m[1][1] = 1.0f;
    out.m[2][2] = 1.0f;
    out.m[3][3] = 1.0f;
    return out;
}

Float4x4 Float4x4::multiply(const Float4x4& a, const Float4x4& b) {
    Float4x4 out{};
    for (int r = 0; r < 4; ++r) {
        for (int c = 0; c < 4; ++c) {
            out.m[r][c] = a.m[r][0] * b.m[0][c]
                        + a.m[r][1] * b.m[1][c]
                        + a.m[r][2] * b.m[2][c]
                        + a.m[r][3] * b.m[3][c];
        }
    }
    return out;
}

Float4x4 Float4x4::translation(float x, float y, float z) {
    Float4x4 out = identity();
    out.m[3][0] = x;
    out.m[3][1] = y;
    out.m[3][2] = z;
    return out;
}

Float4x4 Float4x4::scale(float sx, float sy, float sz) {
    Float4x4 out{};
    out.m[0][0] = sx;
    out.m[1][1] = sy;
    out.m[2][2] = sz;
    out.m[3][3] = 1.0f;
    return out;
}

Float4x4 Float4x4::rotation_y(float angle) {
    Float4x4 out = identity();
    const float c = std::cos(angle);
    const float s = std::sin(angle);
    out.m[0][0] = c;
    out.m[0][2] = -s;
    out.m[2][0] = s;
    out.m[2][2] = c;
    return out;
}

Float4x4 Float4x4::shadow_projection(const std::array<float, 4>& plane, const std::array<float, 4>& light) {
    Float4x4 out{};
    const float dot_value = plane[0] * light[0] + plane[1] * light[1] + plane[2] * light[2] + plane[3] * light[3];
    for (int row = 0; row < 4; ++row) {
        for (int col = 0; col < 4; ++col) {
            out.m[row][col] = (row == col ? dot_value : 0.0f) - light[col] * plane[row];
        }
    }
    return out;
}

Float3x3 Float3x3::multiply(const Float3x3& a, const Float3x3& b) {
    Float3x3 result{};
    for (int row = 0; row < 3; ++row) {
        for (int col = 0; col < 3; ++col) {
            float value = 0.0f;
            for (int k = 0; k < 3; ++k) {
                value += a.m[row][k] * b.m[k][col];
            }
            result.m[row][col] = value;
        }
    }
    return result;
}

Float3x3 Float3x3::rotation_x(float angle_rad) {
    const float c = std::cos(angle_rad);
    const float s = std::sin(angle_rad);
    return {{{1.0f, 0.0f, 0.0f}, {0.0f, c, -s}, {0.0f, s, c}}};
}

Float3x3 Float3x3::rotation_y(float angle_rad) {
    const float c = std::cos(angle_rad);
    const float s = std::sin(angle_rad);
    return {{{c, 0.0f, s}, {0.0f, 1.0f, 0.0f}, {-s, 0.0f, c}}};
}

Float3x3 Float3x3::rotation_z(float angle_rad) {
    const float c = std::cos(angle_rad);
    const float s = std::sin(angle_rad);
    return {{{c, -s, 0.0f}, {s, c, 0.0f}, {0.0f, 0.0f, 1.0f}}};
}

Float3x3 Float3x3::from_sim_orientation(const std::array<double, 3>& orientation) {
    const Float3x3 rx = rotation_x(static_cast<float>(orientation[0]));
    const Float3x3 ry = rotation_y(static_cast<float>(orientation[1]));
    const Float3x3 rz = rotation_z(static_cast<float>(orientation[2]));
    return multiply(rz, multiply(ry, rx));
}

Float3x3 Float3x3::convert_nwu_to_viewer(const Float3x3& nwu_matrix) {
    static const Float3x3 basis_change = {{{1.0f, 0.0f, 0.0f}, {0.0f, 0.0f, 1.0f}, {0.0f, 1.0f, 0.0f}}};
    return multiply(basis_change, multiply(nwu_matrix, basis_change));
}

Float4x4 Float4x4::from_row_vector_mat3(const Float3x3& column_vector_matrix) {
    Float4x4 out = identity();
    for (int row = 0; row < 3; ++row) {
        for (int col = 0; col < 3; ++col) {
            out.m[row][col] = column_vector_matrix.m[col][row];
        }
    }
    return out;
}

} // namespace bvr_sim
