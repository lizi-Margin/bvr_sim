#include "resource_paths.hxx"
#include <cstdlib>
#include <stdexcept>

namespace bvr_sim::resource_paths {

namespace {

constexpr const char* kResourceDirEnv = "BVR_SIM_RESOURCE_DIR";
constexpr const char* kJsbsimDirEnv = "JSBSIM_DIR";

std::filesystem::path source_tree_resource_dir() {
    std::filesystem::path source_file(__FILE__);
    return source_file.parent_path().parent_path() / "resources";
}

std::filesystem::path require_existing_dir(
    const std::filesystem::path& candidate,
    const std::string& description
) {
    if (std::filesystem::exists(candidate) && std::filesystem::is_directory(candidate)) {
        return candidate;
    }
    throw std::runtime_error("BVR Sim " + description + " directory not found: " + candidate.string());
}

} // namespace

std::filesystem::path get_resource_dir() {
    if (const char* env_value = std::getenv(kResourceDirEnv)) {
        return require_existing_dir(std::filesystem::path(env_value), "resource");
    }

    const auto packaged_resources = source_tree_resource_dir();
    if (std::filesystem::exists(packaged_resources) && std::filesystem::is_directory(packaged_resources)) {
        return packaged_resources;
    }

    throw std::runtime_error(
        "BVR Sim resource directory is unavailable. Set BVR_SIM_RESOURCE_DIR or install packaged resources."
    );
}

std::filesystem::path get_resource_path(const std::string& relative_path) {
    return get_resource_dir() / relative_path;
}

std::filesystem::path get_jsbsim_dir() {
    if (const char* env_value = std::getenv(kJsbsimDirEnv)) {
        return require_existing_dir(std::filesystem::path(env_value), "JSBSim");
    }

    const auto packaged_jsbsim = get_resource_dir() / "jsbsim";
    if (std::filesystem::exists(packaged_jsbsim) && std::filesystem::is_directory(packaged_jsbsim)) {
        return packaged_jsbsim;
    }

    throw std::runtime_error(
        "BVR Sim JSBSim directory is unavailable. Set JSBSIM_DIR or install packaged resources."
    );
}

} // namespace bvr_sim::resource_paths
