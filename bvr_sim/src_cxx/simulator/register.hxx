#pragma once

#include "rubbish_can/json.hpp"
#include <string>
#include <optional>
#include <vector>
#include <map>
#include <shared_mutex>

namespace bvr_sim {

class Register {
public:
    Register() = default;
    ~Register() = default;

    Register(const Register&) = delete;
    Register& operator=(const Register&) = delete;

    std::optional<json::JSON> get(const std::string& key) const noexcept;

    bool set(const std::string& key, const json::JSON& value) noexcept;

    std::optional<json::JSON> pop(const std::string& key) noexcept;

    bool has(const std::string& key) const noexcept;

    // void clear() noexcept;

    size_t size() const noexcept;

    std::map<std::string, json::JSON> get_all() const noexcept;

    std::optional<double> get_double(const std::string& key) const noexcept;

    std::optional<std::vector<double>> get_vector(const std::string& key) const noexcept;

    std::optional<std::map<std::string, std::string>> get_map_ss(const std::string& key) const noexcept;

    std::optional<std::map<std::string, double>> get_map_sd(const std::string& key) const noexcept;

private:
    std::map<std::string, json::JSON> data_;
    mutable std::shared_mutex mutex_;
};

}
