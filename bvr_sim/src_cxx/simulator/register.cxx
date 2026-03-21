#include "register.hxx"
#include <mutex>

namespace bvr_sim {

std::optional<json::JSON> Register::get(const std::string& key) const noexcept {
    std::shared_lock lock(mutex_);
    auto it = data_.find(key);
    if (it != data_.end()) {
        return it->second;
    }
    return std::nullopt;
}

bool Register::set(const std::string& key, const json::JSON& value) noexcept {
    std::unique_lock lock(mutex_);
    data_[key] = value;
    return true;
}

std::optional<json::JSON> Register::pop(const std::string& key) noexcept {
    std::unique_lock lock(mutex_);
    auto it = data_.find(key);
    if (it != data_.end()) {
        json::JSON value = it->second;
        data_.erase(it);
        return value;
    }
    return std::nullopt;
}

bool Register::has(const std::string& key) const noexcept {
    std::shared_lock lock(mutex_);
    return data_.find(key) != data_.end();
}

// void Register::clear() noexcept {
//     std::unique_lock lock(mutex_);
//     data_.clear();
// }

size_t Register::size() const noexcept {
    std::shared_lock lock(mutex_);
    return data_.size();
}

std::map<std::string, json::JSON> Register::get_all() const noexcept {
    std::shared_lock lock(mutex_);
    return data_;
}

std::optional<double> Register::get_double(const std::string& key) const noexcept {
    auto val = get(key);
    if (!val) return std::nullopt;

    if (val->JSONType() == json::JSON::Class::Floating) {
        return val->ToFloat();
    } else if (val->JSONType() == json::JSON::Class::Integral) {
        return static_cast<double>(val->ToInt());
    }
    return std::nullopt;
}

std::optional<std::vector<double>> Register::get_vector(const std::string& key) const noexcept {
    auto val = get(key);
    if (!val) return std::nullopt;

    if (val->JSONType() != json::JSON::Class::Array) return std::nullopt;

    try {
        std::vector<double> result;
        for (size_t i = 0; i < val->size(); ++i) {
            auto elem = val->at(i);
            if (elem.JSONType() == json::JSON::Class::Floating) {
                result.push_back(elem.ToFloat());
            } else if (elem.JSONType() == json::JSON::Class::Integral) {
                result.push_back(static_cast<double>(elem.ToInt()));
            } else {
                return std::nullopt;
            }
        }
        return result;
    } catch (...) {
        return std::nullopt;
    }
}

std::optional<std::map<std::string, std::string>> Register::get_map_ss(const std::string& key) const noexcept {
    auto val = get(key);
    if (!val) return std::nullopt;

    if (val->JSONType() != json::JSON::Class::Object) return std::nullopt;

    try {
        std::map<std::string, std::string> result;
        for (auto& [k, v] : val->ObjectRange()) {
            if (v.JSONType() == json::JSON::Class::String) {
                result[k] = v.ToString();
            } else {
                return std::nullopt;
            }
        }
        return result;
    } catch (...) {
        return std::nullopt;
    }
}

std::optional<std::map<std::string, double>> Register::get_map_sd(const std::string& key) const noexcept {
    auto val = get(key);
    if (!val) return std::nullopt;

    if (val->JSONType() != json::JSON::Class::Object) return std::nullopt;

    try {
        std::map<std::string, double> result;
        for (auto& [k, v] : val->ObjectRange()) {
            if (v.JSONType() == json::JSON::Class::Floating) {
                result[k] = v.ToFloat();
            } else if (v.JSONType() == json::JSON::Class::Integral) {
                result[k] = static_cast<double>(v.ToInt());
            } else {
                return std::nullopt;
            }
        }
        return result;
    } catch (...) {
        return std::nullopt;
    }
}
}
