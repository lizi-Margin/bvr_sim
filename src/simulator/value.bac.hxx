#pragma once

#include <string>
#include <array>
#include <map>
#include <optional>
#include <any>
#include <vector>

namespace bvr_sim {

class Value {
public:
    enum ValueType {
        DOUBLE,
        VECTOR,
        MAP_SS,
        MAP_SD,
        INVALID
    };

    Value() : type_(INVALID) {}
    Value(double d) : type_(DOUBLE), data_(d) {}
    Value(const std::array<double, 3>& v) : type_(VECTOR), data_(v) {}
    Value(const std::map<std::string, std::string>& m) : type_(MAP_SS), data_(m) {}
    Value(const std::map<std::string, double>& m) : type_(MAP_SD), data_(m) {}

    ValueType get_type() const noexcept { return type_; }
    bool is_valid() const noexcept { return type_ != INVALID; }

    std::optional<double> as_double() const noexcept;
    std::optional<std::array<double, 3>> as_vector() const noexcept;
    std::optional<std::map<std::string, std::string>> as_map_ss() const noexcept;
    std::optional<std::map<std::string, double>> as_map_sd() const noexcept;

    std::string to_string() const;
    static Value from_string(const std::string& s);

private:
    ValueType type_;
    std::any data_;

    static std::string escape(const std::string& s);
    static std::string unescape(const std::string& s);
    static std::vector<std::string> split(const std::string& s, char delimiter);
};

}
