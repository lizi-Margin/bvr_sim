#pragma once

#include <filesystem>
#include <string>

namespace bvr_sim::resource_paths {

std::filesystem::path get_resource_dir();
std::filesystem::path get_resource_path(const std::string& relative_path);
std::filesystem::path get_jsbsim_dir();

} // namespace bvr_sim::resource_paths
