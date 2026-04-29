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
