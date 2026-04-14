#include "param_store.hxx"
#include "rubbish_can/check.hxx"
#include <fstream>
#include <sstream>
#include <stdexcept>

namespace bvr_sim {

namespace {

const char* value_type_name(ParamStore::ValueType type) noexcept {
    switch (type) {
    case ParamStore::ValueType::None:
        return "none";
    case ParamStore::ValueType::Double:
        return "double";
    case ParamStore::ValueType::Bool:
        return "bool";
    case ParamStore::ValueType::String:
        return "string";
    case ParamStore::ValueType::InterpTable:
        return "interp_table";
    }
    return "unknown";
}

} // namespace

void ParamStore::_register_key(const std::string& key, ValueType type) {
    auto it = key_types_.find(key);
    if (it != key_types_.end() && it->second != type) {
        throw std::runtime_error(
            "ParamStore: key '" + key + "' already registered as '" +
            value_type_name(it->second) + "', cannot re-register as '" + value_type_name(type) + "'"
        );
    }
    key_types_[key] = type;
}

std::optional<double> ParamStore::get_double(const std::string& key) const noexcept {
    auto it = doubles_.find(key);
    if (it == doubles_.end()) return std::nullopt;
    return it->second;
}

std::optional<bool> ParamStore::get_bool(const std::string& key) const noexcept {
    auto it = bools_.find(key);
    if (it == bools_.end()) return std::nullopt;
    return it->second;
}

std::optional<std::string> ParamStore::get_string(const std::string& key) const noexcept {
    auto it = strings_.find(key);
    if (it == strings_.end()) return std::nullopt;
    return it->second;
}

std::optional<std::shared_ptr<InterpTable>> ParamStore::get_interp_table(const std::string& key) const noexcept {
    auto it = tables_.find(key);
    if (it == tables_.end()) return std::nullopt;
    return it->second;
}

double ParamStore::get_double_(const std::string& key) const {
    const auto value = get_double(key);
    check(value.has_value(), "ParamStore::get_double_: missing or type-mismatched key '" + key + "'");
    return *value;
}

bool ParamStore::get_bool_(const std::string& key) const {
    const auto value = get_bool(key);
    check(value.has_value(), "ParamStore::get_bool_: missing or type-mismatched key '" + key + "'");
    return *value;
}

const std::string& ParamStore::get_string_(const std::string& key) const {
    auto it = strings_.find(key);
    check(it != strings_.end(), "ParamStore::get_string_: missing or type-mismatched key '" + key + "'");
    return it->second;
}

std::shared_ptr<InterpTable> ParamStore::get_interp_table_(const std::string& key) const {
    const auto value = get_interp_table(key);
    check(value.has_value(), "ParamStore::get_interp_table_: missing or type-mismatched key '" + key + "'");
    check(*value != nullptr, "ParamStore::get_interp_table_: null table for key '" + key + "'");
    return *value;
}

void ParamStore::set_double(const std::string& key, double value) {
    _register_key(key, ValueType::Double);
    doubles_[key] = value;
}

void ParamStore::set_bool(const std::string& key, bool value) {
    _register_key(key, ValueType::Bool);
    bools_[key] = value;
}

void ParamStore::set_string(const std::string& key, const std::string& value) {
    _register_key(key, ValueType::String);
    strings_[key] = value;
}

void ParamStore::set_interp_table(const std::string& key, std::shared_ptr<InterpTable> table) {
    check(table != nullptr, "ParamStore::set_interp_table: table must not be null");
    _register_key(key, ValueType::InterpTable);
    tables_[key] = std::move(table);
}

bool ParamStore::has_key(const std::string& key) const noexcept {
    return key_types_.find(key) != key_types_.end();
}

ParamStore::ValueType ParamStore::get_key_type(const std::string& key) const noexcept {
    auto it = key_types_.find(key);
    if (it == key_types_.end()) return ValueType::None;
    return it->second;
}

std::string ParamStore::to_string() const {
    json::JSON root    = json::JSON::Make(json::JSON::Class::Object);
    json::JSON doubles_j = json::JSON::Make(json::JSON::Class::Object);
    json::JSON bools_j   = json::JSON::Make(json::JSON::Class::Object);
    json::JSON strings_j = json::JSON::Make(json::JSON::Class::Object);
    json::JSON tables_j  = json::JSON::Make(json::JSON::Class::Object);

    for (const auto& [k, v] : doubles_)
        doubles_j[k] = json::JSON(v);
    for (const auto& [k, v] : bools_)
        bools_j[k] = json::JSON(v);
    for (const auto& [k, v] : strings_)
        strings_j[k] = json::JSON(v);
    for (const auto& [k, v] : tables_)
        tables_j[k] = v->to_json();

    root["doubles"] = doubles_j;
    root["bools"]   = bools_j;
    root["strings"] = strings_j;
    root["tables"]  = tables_j;
    return root.dump();
}

ParamStore ParamStore::from_string(const std::string& json_str) {
    auto root = json::JSON::Load(json_str);
    ParamStore store;

    if (root.hasKey("doubles")) {
        for (auto& [k, v] : root["doubles"].ObjectRange()) {
            // Guard against integer-valued JSON numbers (Class::Integral vs Class::Floating)
            double val = v.IsFloating() ? v.ToFloat() : static_cast<double>(v.ToInt());
            store.set_double(k, val);
        }
    }
    if (root.hasKey("bools")) {
        for (auto& [k, v] : root["bools"].ObjectRange())
            store.set_bool(k, v.ToBool());
    }
    if (root.hasKey("strings")) {
        for (auto& [k, v] : root["strings"].ObjectRange())
            // Note: SimpleJSON's ToString() returns the escaped form of strings.
            // Strings containing backslashes, quotes, or control chars may not round-trip cleanly.
            // This is acceptable for the intended use case (missile model names, parameter names).
            store.set_string(k, v.ToString());
    }
    if (root.hasKey("tables")) {
        for (auto& [k, v] : root["tables"].ObjectRange())
            store.set_interp_table(k, std::make_shared<InterpTable>(InterpTable::from_json(v)));
    }
    return store;
}

ParamStore ParamStore::from_file(const std::string& file_path) {
    std::ifstream file(file_path, std::ios::in | std::ios::binary);
    check(file.is_open(), "ParamStore::from_file: failed to open '" + file_path + "'");

    std::ostringstream buffer;
    buffer << file.rdbuf();
    return from_string(buffer.str());
}

} // namespace bvr_sim
