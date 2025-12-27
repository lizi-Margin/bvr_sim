#include "so_pool.hxx"
#include "rubbish_can/SL.hxx"
#include "rubbish_can/check.hxx"
#include <algorithm>

namespace bvr_sim {

SOPool& SOPool::instance() {
    static SOPool pool;
    return pool;
}

void SOPool::add(std::shared_ptr<SimulatedObject> obj) {
    if (!obj) {
        return;
    }
    std::unique_lock lock(mutex_);
    objects_[obj->uid] = obj;

    check_and_fix();
}

void SOPool::trash_out(const std::string& uid) {
    std::unique_lock lock(mutex_);
    auto it = objects_.find(uid);
    if (it == objects_.end()) {
        auto it_trash = trashed_objects_.find(uid);
        if (it_trash == trashed_objects_.end()) {
            colorful::printHUANG("[SOPool] Warning: can not trash out uid not existing");
            SL::get().print("[SOPool] Warning: can not trash out uid not existing");
            return;
        } else {
            colorful::printHUANG("[SOPool] Warning: can not re-trash a obj ", uid);
            SL::get().printf("[SOPool] Warning: can not re-trash a obj %s", uid.c_str());
            return;
        }
    }

    auto obj = it->second;
    objects_.erase(uid);

    auto it_trash = trashed_objects_.find(uid);
    if (it_trash == trashed_objects_.end()) {
        trashed_objects_[obj->uid] = obj;
    } else {
        colorful::printHONG("[SOPool::trash_out] WTF");
        std::abort();
    }
    check_and_fix();
}

void SOPool::clear() {
    std::unique_lock lock(mutex_);
    for (auto& [uid, obj] : objects_) {
        obj->clean_up();
    }
    objects_.clear();

    for (auto& [uid, obj] : trashed_objects_) {
        obj->clean_up();
    }
    trashed_objects_.clear();
}


void SOPool::check_and_fix() {
    if (objects_.size() == 0) {
        SL::get().printf("[SOPool::check_and_fix] SOPool is empty\n");
        return;
    }

    { // check size
        if (objects_.size() > 100) {
            SL::get().printf("[SOPool::check_and_fix] Warning SOPool size is %d, which is large, is there bugs?\n", objects_.size());
        }
    }


    { // check and fix the nullptr object
        for (auto it = objects_.begin(); it != objects_.end();) {
            if (!it->second) {
                SL::get().printf("[SOPool::check_and_fix] uid %s is nullptr!!!!\n", it->first.c_str());
                it = objects_.erase(it);
            } else {
                ++it;
            }
        }
    }

    { // check and fix the DataObj object
        for (auto it = objects_.begin(); it != objects_.end();) {
            if (it->second->Type == SOT::DataObj || it->second->Type <= SOT::Unknown || it->second->Type >= SOT::MAX_SOT_VALUE) {
                SL::get().printf("[SOPool::check_and_fix] uid %s is invalide Type %d, which is not allowed!!!!\n", it->first.c_str(), (int)it->second->Type);
                it = objects_.erase(it);
            } else {
                ++it;
            }
        }
    }

    { // detect the obj in both trashed_objects_ and objects_
        for (auto it = trashed_objects_.begin(); it != trashed_objects_.end();) {
            if (objects_.find(it->first) != objects_.end()) {
                SL::get().printf("[SOPool::check_and_fix] Error: uid %s is in both objects_ and trashed_objects_, which is not allowed!!!!\n", it->first.c_str());
                it = trashed_objects_.erase(it);
                colorful::printHONG("[SOPool::check_and_fix] Error: uid %s is in both objects_ and trashed_objects_, which is not allowed!!!!\n", it->first.c_str());
                std::abort();
            } else {
                ++it;
            }
        }
    }


    { // check the enemy and partner for each object
        // lamda to filter Type != SOT::Missile
        auto filter_not_type = [](std::vector<std::shared_ptr<SimulatedObject>>& objs, SOT tp) {
            return std::all_of(objs.begin(), objs.end(), [tp](const std::shared_ptr<SimulatedObject>& obj) {
                return obj->Type != tp;
            });
        };
        auto RedObjects = get_by_color(objects_, TeamColor::Red);
        auto BlueObjects = get_by_color(objects_, TeamColor::Blue);
        filter_not_type(RedObjects, SOT::Missile);
        filter_not_type(BlueObjects, SOT::Missile);


        for (auto it = objects_.begin(); it != objects_.end(); it++) {
            if (it->second) {
                std::shared_ptr<SimulatedObject> obj = it->second;
                // std::vector<std::shared_ptr<SimulatedObject>>* red_ones = nullptr;
                // std::vector<std::shared_ptr<SimulatedObject>>* blue_ones = nullptr;

                if (obj->color == TeamColor::Red) {
                    int ego_id = -1;
                    auto red_no_ego = RedObjects;
                    for (size_t i = 0; i < red_no_ego.size(); i ++) {
                        if (red_no_ego[i]->uid == obj->uid) {
                            ego_id = static_cast<int>(i);
                            break;
                        }
                    }
                    check(ego_id != -1, "ego_id is not found");
                    obj->partners = red_no_ego;
                    obj->enemies = BlueObjects;
                    // red_ones = &obj->partners;
                    // blue_ones = &obj->enemies;
                } else if (obj->color == TeamColor::Blue) {
                    int ego_id = -1;
                    auto blue_no_ego = BlueObjects;
                    for (size_t i = 0; i < blue_no_ego.size(); i ++) {
                        if (blue_no_ego[i]->uid == obj->uid) {
                            ego_id = static_cast<int>(i);
                            break;
                        }
                    }
                    check(ego_id != -1, "ego_id is not found");
                    obj->partners = blue_no_ego;
                    obj->enemies = RedObjects;
                    // red_ones = &obj->enemies;
                    // blue_ones = &obj->partners;
                } else {
                    SL::get().printf("[SOPool::check_and_fix] uid %s is not Red or Blue!!!!\n", it->first.c_str());
                    std::abort();
                }
                
                // if (red_ones) {
                //     if (red_ones->size() != RedObjects.size()) {
                //         *red_ones = RedObjects;
                //     }
                //     check(red_ones->size() == RedObjects.size(), "red_ones size is not equal to RedObjects size ???");
                //     for (size_t i = 0; i < red_ones->size(); i ++) {
                //         check(red_ones->at(i)->uid == RedObjects[i]->uid, "length eq but object is different");
                //     }
                // }

                // if (blue_ones) {
                //     if (blue_ones->size() != BlueObjects.size()) {
                //         *blue_ones = BlueObjects;
                //     }
                //     check(blue_ones->size() == BlueObjects.size(), "blue_ones size is not equal to BlueObjects size ???");
                //     for (size_t i = 0; i < blue_ones->size(); i ++) {
                //         check(blue_ones->at(i)->uid == BlueObjects[i]->uid, "length eq but object is different");
                //     }
                // }

            }

        }
    }
}

std::vector<std::shared_ptr<SimulatedObject>> SOPool::get_by_color(TeamColor color) const {
    std::vector<std::shared_ptr<SimulatedObject>> result;
    return get_by_color(objects_, color);
}

std::vector<std::shared_ptr<SimulatedObject>> SOPool::get_by_color(const std::map<std::string, std::shared_ptr<SimulatedObject>>& objects, TeamColor color) {
    std::vector<std::shared_ptr<SimulatedObject>> result;
    for (const auto& [uid, obj] : objects) {
        if (obj->color == color) {
            result.push_back(obj);
        }
    }
    return result;
}

std::shared_ptr<SimulatedObject> SOPool::get(const std::string& uid) const {
    std::shared_lock lock(mutex_);
    auto it = objects_.find(uid);
    if (it != objects_.end()) {
        return it->second;
    }
    return nullptr;
}

bool SOPool::has(const std::string& uid) const {
    std::shared_lock lock(mutex_);
    return objects_.find(uid) != objects_.end();
}

std::vector<std::shared_ptr<SimulatedObject>> SOPool::get_all() const {
    SL::get().print("[SOPool::get_all] called");
    std::shared_lock lock(mutex_);
    std::vector<std::shared_ptr<SimulatedObject>> result;
    result.reserve(objects_.size());
    for (const auto& [uid, obj] : objects_) {
        SL::get().printf("[SOPool::get_all] push_back ->      uid: %s, type: %s\n", uid.c_str(), SOT_to_string(obj->Type).c_str());
        result.push_back(obj);
    }
    SL::get().printf("[SOPool::get_all] return %d objects\n", result.size());
    return result;
}

std::vector<std::shared_ptr<SimulatedObject>> SOPool::get_by_type(SOT type) const {
    std::shared_lock lock(mutex_);
    return get_by_type(objects_, type);
}

std::vector<std::shared_ptr<SimulatedObject>> SOPool::get_by_type(const std::map<std::string, std::shared_ptr<SimulatedObject>>& objects, SOT type) {
    std::vector<std::shared_ptr<SimulatedObject>> result;
    for (const auto& [uid, obj] : objects) {
        if (obj->Type == type) {
            result.push_back(obj);
        }
    }
    return result;
}

std::vector<std::shared_ptr<SimulatedObject>> SOPool::get_by_type(const std::vector<std::shared_ptr<SimulatedObject>>& objects, SOT type) {
    std::vector<std::shared_ptr<SimulatedObject>> result;
    for (const auto& obj : objects) {
        if (obj->Type == type) {
            result.push_back(obj);
        }
    }
    return result;
}

size_t SOPool::size() const {
    std::shared_lock lock(mutex_);
    return objects_.size();
}


bool SOPool::in_trash_bin(const std::string& uid) const {
    std::shared_lock lock(mutex_);
    return trashed_objects_.find(uid) != trashed_objects_.end();
}

std::vector<std::shared_ptr<SimulatedObject>> SOPool::get_all_ever_existed() const {
    std::shared_lock lock(mutex_);
    std::vector<std::shared_ptr<SimulatedObject>> result;
    result.reserve(objects_.size() + trashed_objects_.size());
    for (const auto& [uid, obj] : objects_) {
        result.push_back(obj);
    }
    for (const auto& [uid, obj] : trashed_objects_) {
        result.push_back(obj);
    }
    return result;
}

// std::shared_ptr<SimulatedObject> SOPool::get_from_trash_bin(const std::string& uid) const {
//     std::shared_lock lock(mutex_);
//     auto it = trashed_objects_.find(uid);
//     if (it != trashed_objects_.end()) {
//         return it->second;
//     }
//     return nullptr;
// }

}