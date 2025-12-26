#include "value.bac.hxx"
#include <sstream>
#include <iomanip>
#include <cctype>
#include "rubbish_can/colorful.hxx"

namespace bvr_sim {

std::optional<double> Value::as_double() const noexcept {
    if (type_ != DOUBLE) return std::nullopt;
    try {
        return std::any_cast<double>(data_);
    } catch (...) {
        colorful::printHONG("Error: Value::as_double: failed to cast data to double");
        return std::nullopt;
    }
}

std::optional<std::array<double, 3>> Value::as_vector() const noexcept {
    if (type_ != VECTOR) return std::nullopt;
    try {
        return std::any_cast<std::array<double, 3>>(data_);
    } catch (...) {
        colorful::printHONG("Error: Value::as_vector: failed to cast data to std::array<double, 3>");
        return std::nullopt;
    }
}

std::optional<std::map<std::string, std::string>> Value::as_map_ss() const noexcept {
    if (type_ != MAP_SS) return std::nullopt;
    try {
        return std::any_cast<std::map<std::string, std::string>>(data_);
    } catch (...) {
        colorful::printHONG("Error: Value::as_map_ss: failed to cast data to std::map<std::string, std::string>");
        return std::nullopt;
    }
}

std::optional<std::map<std::string, double>> Value::as_map_sd() const noexcept {
    if (type_ != MAP_SD) return std::nullopt;
    try {
        return std::any_cast<std::map<std::string, double>>(data_);
    } catch (...) {
        colorful::printHONG("Error: Value::as_map_sd: failed to cast data to std::map<std::string, double>");
        return std::nullopt;
    }
}

std::string Value::escape(const std::string& s) {
    std::string result;
    for (char c : s) {
        if (c == '=' || c == ',' || c == '\\') {
            result += '\\';
        }
        result += c;
    }
    return result;
}

std::string Value::unescape(const std::string& s) {
    std::string result;
    for (size_t i = 0; i < s.length(); ++i) {
        if (s[i] == '\\' && i + 1 < s.length()) {
            result += s[++i];
        } else {
            result += s[i];
        }
    }
    return result;
}

std::vector<std::string> Value::split(const std::string& s, char delimiter) {
    std::vector<std::string> tokens;
    std::string token;
    bool escaped = false;

    for (char c : s) {
        if (escaped) {
            token += c;
            escaped = false;
        } else if (c == '\\') {
            escaped = true;
        } else if (c == delimiter) {
            if (!token.empty()) {
                tokens.push_back(token);
                token.clear();
            }
        } else {
            token += c;
        }
    }

    if (!token.empty()) {
        tokens.push_back(token);
    }

    return tokens;
}

std::string Value::to_string() const {
    switch (type_) {
        case DOUBLE: {
            double d = std::any_cast<double>(data_);
            std::ostringstream oss;
            oss << std::fixed << std::setprecision(10) << d;
            std::string str = oss.str();
            str.erase(str.find_last_not_of('0') + 1, std::string::npos);
            if (str.back() == '.') str.pop_back();
            return "double(" + str + ")";
        }
        case VECTOR: {
            auto v = std::any_cast<std::array<double, 3>>(data_);
            std::ostringstream oss;
            oss << std::fixed << std::setprecision(10);
            oss << v[0] << "," << v[1] << "," << v[2];
            std::string str = oss.str();
            return "vector(" + str + ")";
        }
        case MAP_SS: {
            auto m = std::any_cast<std::map<std::string, std::string>>(data_);
            std::string result = "map_ss(";
            bool first = true;
            for (const auto& [k, v] : m) {
                if (!first) result += ",";
                result += escape(k) + "=" + escape(v);
                first = false;
            }
            result += ")";
            return result;
        }
        case MAP_SD: {
            auto m = std::any_cast<std::map<std::string, double>>(data_);
            std::string result = "map_sd(";
            bool first = true;
            for (const auto& [k, v] : m) {
                if (!first) result += ",";
                std::ostringstream oss;
                oss << std::fixed << std::setprecision(10) << v;
                std::string val_str = oss.str();
                val_str.erase(val_str.find_last_not_of('0') + 1, std::string::npos);
                if (val_str.back() == '.') val_str.pop_back();
                result += k + "=" + val_str;
                first = false;
            }
            result += ")";
            return result;
        }
        default:
            return "invalid";
    }
}

Value Value::from_string(const std::string& s) {
    size_t paren_start = s.find('(');
    size_t paren_end = s.rfind(')');

    if (paren_start == std::string::npos || paren_end == std::string::npos ||
        paren_start >= paren_end) {
        return Value();
    }

    std::string type_str = s.substr(0, paren_start);
    std::string content = s.substr(paren_start + 1, paren_end - paren_start - 1);

    if (type_str == "double") {
        try {
            return Value(std::stod(content));
        } catch (...) {
            return Value();
        }
    }
    else if (type_str == "vector") {
        auto parts = split(content, ',');
        if (parts.size() != 3) return Value();
        try {
            return Value(std::array<double, 3>{
                std::stod(parts[0]),
                std::stod(parts[1]),
                std::stod(parts[2])
            });
        } catch (...) {
            return Value();
        }
    }
    else if (type_str == "map_ss") {
        std::map<std::string, std::string> m;
        auto pairs = split(content, ',');
        for (const auto& pair : pairs) {
            size_t eq_pos = pair.find('=');
            if (eq_pos != std::string::npos) {
                std::string key = unescape(pair.substr(0, eq_pos));
                std::string val = unescape(pair.substr(eq_pos + 1));
                m[key] = val;
            }
        }
        return Value(m);
    }
    else if (type_str == "map_sd") {
        std::map<std::string, double> m;
        auto pairs = split(content, ',');
        for (const auto& pair : pairs) {
            size_t eq_pos = pair.find('=');
            if (eq_pos != std::string::npos) {
                std::string key = pair.substr(0, eq_pos);
                try {
                    double val = std::stod(pair.substr(eq_pos + 1));
                    m[key] = val;
                } catch (...) {
                    continue;
                }
            }
        }
        return Value(m);
    }

    return Value();
}

}
