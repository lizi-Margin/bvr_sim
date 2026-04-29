#pragma once

#include <array>
#include <string>
#include <unordered_map>
#include <vector>

namespace bvr_sim {

struct Float3 {
    float x = 0.0f;
    float y = 0.0f;
    float z = 0.0f;
};

struct Float4x4 {
    float m[4][4]{};

    static Float4x4 identity();
    static Float4x4 translation(float x, float y, float z);
    static Float4x4 scale(float sx, float sy, float sz);
    static Float4x4 rotation_y(float angle);
    static Float4x4 shadow_projection(const std::array<float, 4>& plane, const std::array<float, 4>& light);
    static Float4x4 from_row_vector_mat3(const struct Float3x3& column_vector_matrix);
    static Float4x4 multiply(const Float4x4& a, const Float4x4& b);
};

struct Float3x3 {
    float m[3][3]{};

    static Float3x3 multiply(const Float3x3& a, const Float3x3& b);
    static Float3x3 rotation_x(float angle_rad);
    static Float3x3 rotation_y(float angle_rad);
    static Float3x3 rotation_z(float angle_rad);
    static Float3x3 from_sim_orientation(const std::array<double, 3>& orientation);
    static Float3x3 convert_nwu_to_viewer(const Float3x3& nwu_matrix);
};

struct Vertex {
    float position[3];
    float color[3];
    float normal[3];
    float uv[2];
};

struct MeshData {
    struct MeshVertex {
        std::array<float, 3> position{0.0f, 0.0f, 0.0f};
        std::array<float, 3> normal{0.0f, 1.0f, 0.0f};
        std::array<float, 2> uv{0.0f, 0.0f};
        bool has_normal = false;
    };

    std::vector<MeshVertex> vertices;
    std::array<float, 3> center{0.0f, 0.0f, 0.0f};
    float radius = 1.0f;
    bool loaded = false;
};

struct MeshLibrary {
    std::unordered_map<std::string, MeshData> meshes;
};

} // namespace bvr_sim
