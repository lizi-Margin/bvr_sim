#include "base.hxx"
#include "../aircraft/base.hxx"

namespace bvr_sim {

SensorBase::SensorBase(const std::shared_ptr<Aircraft>& parent_) noexcept
    : parent(parent_) {
}

}
