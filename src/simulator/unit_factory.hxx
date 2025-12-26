#pragma once

#include "simulator.hxx"
#include <string>
#include <memory>
#include <map>

namespace bvr_sim {

class UnitFactory {
public:
    enum class UnitType {
        Unknown,
        Fighter,
        SLAMRAM,
        GroundStaticTarget
    };

    static UnitType parse_unit_type(const std::string& unit_spec) noexcept;

    static std::shared_ptr<SimulatedObject> create_unit(
        const std::string& uid,
        json::JSON spec_json
    ) noexcept;

private:
    static const std::map<std::string, UnitType> UNIT_MAP;
};

}
