#pragma once

#include "../data_obj.hxx"
#include <string>
#include <map>
#include <memory>

namespace bvr_sim {

class Aircraft;

class SensorBase {
protected:
    std::shared_ptr<Aircraft> parent;
    std::map<std::string, std::shared_ptr<DataObj>> data_dict;

public:
    SensorBase(const std::shared_ptr<Aircraft>& parent_) noexcept;

    virtual ~SensorBase() noexcept = default;

    virtual void update() = 0;

    virtual std::string log_suffix() const noexcept = 0;

    const std::map<std::string, std::shared_ptr<DataObj>>& get_data() const noexcept { return data_dict; }

    const std::shared_ptr<Aircraft>& get_parent() const noexcept { return parent; }

    virtual void clean_up() noexcept {
        parent = nullptr;
        data_dict.clear();
    }
};

}
