#pragma once

#include "support/json.hpp"
#include "support/interp_table.hxx"
#include <map>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>

namespace bvr_sim {

// InterpTable is defined at global scope (no namespace)
using ::InterpTable;

/// Typed key-value parameter store.
/// Keys share a single namespace across all types — setting the same key
/// with a different type throws std::runtime_error.
/// JSON round-trip via to_string() / from_string().
class ParamStore {
public:
    enum class ValueType {
        None,
        Double,
        Bool,
        String,
        InterpTable,
    };

    ParamStore() = default;

    // ===== Getters =====
    // Do not use these getters that can cover up the absence of a key
    std::optional<double>                       get_double(const std::string& key) const noexcept;
    std::optional<bool>                         get_bool(const std::string& key) const noexcept;
    std::optional<std::string>                  get_string(const std::string& key) const noexcept;
    std::optional<std::shared_ptr<InterpTable>> get_interp_table(const std::string& key) const noexcept;

    // Use these getters that crash if the key is missing, to avoid silent bugs from typos or missing parameters
    double                                      get_double_(const std::string& key) const;
    bool                                        get_bool_(const std::string& key) const;
    const std::string&                          get_string_(const std::string& key) const;
    std::shared_ptr<InterpTable>                get_interp_table_(const std::string& key) const;

    // ===== Setters (throw if key already exists with different type) =====
    void set_double(const std::string& key, double value);
    void set_bool(const std::string& key, bool value);
    void set_string(const std::string& key, const std::string& value);
    void set_interp_table(const std::string& key, std::shared_ptr<InterpTable> table);

    // ===== Queries =====
    bool      has_key(const std::string& key) const noexcept;
    ValueType get_key_type(const std::string& key) const noexcept;

    // ===== Serialization (JSON internally) =====
    std::string         to_string() const;
    static ParamStore   from_string(const std::string& json_str);
    static ParamStore   from_file(const std::string& file_path);

private:
    std::map<std::string, double>                       doubles_;
    std::map<std::string, bool>                         bools_;
    std::map<std::string, std::string>                  strings_;
    std::map<std::string, std::shared_ptr<InterpTable>> tables_;
    std::map<std::string, ValueType>                    key_types_;

    void _register_key(const std::string& key, ValueType type);
};

} // namespace bvr_sim
