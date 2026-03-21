#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/functional.h>
#include <pybind11/eigen.h>

#include "core.hxx"
#include "simulator/simulator.hxx"
#include "rl/rl_manager.hxx"
#include "rubbish_can/json.hpp"

namespace py = pybind11;
using namespace bvr_sim;

namespace {

py::object json_to_python(json::JSON j) {
    switch (j.JSONType()) {
        case json::JSON::Class::Null:
            return py::none();
        case json::JSON::Class::Object: {
            py::dict d;
            for (auto& [key, val] : j.ObjectRange()) {
                d[py::str(key)] = json_to_python(val);
            }
            return d;
        }
        case json::JSON::Class::Array: {
            py::list lst;
            for (size_t i = 0; i < j.size(); ++i) {
                json::JSON elem = j[i];
                lst.append(json_to_python(elem));
            }
            return lst;
        }
        case json::JSON::Class::String:
            return py::str(j.ToString());
        case json::JSON::Class::Floating: {
            return py::float_(j.ToFloat());
        }
        case json::JSON::Class::Integral: {
            return py::int_(j.ToInt());
        }
        case json::JSON::Class::Boolean: {
            return py::bool_(j.ToBool());
        }
        default:
            return py::none();
    }
}

json::JSON python_to_json(const py::handle& obj) {
    if (obj.is_none()) {
        return json::JSON();
    }

    if (py::isinstance<py::bool_>(obj)) {
        return json::Boolean(py::cast<bool>(obj));
    }

    if (py::isinstance<py::int_>(obj)) {
        return json::Integral(py::cast<long>(obj));
    }

    if (py::isinstance<py::float_>(obj)) {
        return json::Float(py::cast<double>(obj));
    }

    if (py::isinstance<py::str>(obj)) {
        return json::String(py::cast<std::string>(obj));
    }

    if (py::isinstance<py::dict>(obj)) {
        json::JSON result = json::Object();
        for (auto& [key, val] : py::cast<py::dict>(obj)) {
            result[py::cast<std::string>(key)] = python_to_json(val);
        }
        return result;
    }

    if (py::isinstance<py::list>(obj)) {
        json::JSON result = json::Array();
        for (auto& item : py::cast<py::list>(obj)) {
            result.append(python_to_json(item));
        }
        return result;
    }

    return json::JSON();
}

}

PYBIND11_MODULE(bvr_sim_cpp, m) {
    m.doc() = "BVR Sim C++ bindings";

    py::enum_<TeamColor>(m, "TeamColor")
        .value("Red", TeamColor::Red)
        .value("Blue", TeamColor::Blue)
        .export_values();

    py::class_<SimCore, std::shared_ptr<SimCore>>(m, "SimCore")
        .def(py::init<double>(), py::arg("dt") = 0.4)
        .def("start", &SimCore::start)
        .def("stop", &SimCore::stop)
        .def("pause", &SimCore::pause)
        .def("resume", &SimCore::resume)
        .def("step", &SimCore::step)
        .def("step_sync", [](SimCore& self, int steps) {
            self.step(steps);
        }, py::arg("steps"))
        .def("handle", [](SimCore& self, const std::string& cmd) -> py::object {
            auto result = self.handle(cmd);
            return json_to_python(result);
        }, py::arg("cmd"))
        .def("set_acmi_file_path", &SimCore::set_acmi_file_path)
        .def("is_running", &SimCore::is_running)
        .def("is_paused", &SimCore::is_paused)
        .def("get_sim_time", &SimCore::get_sim_time)
        .def("get_dt", &SimCore::get_dt);

    py::class_<RLManager, std::shared_ptr<RLManager>>(m, "RLManager")
        .def(py::init<>())
        .def("get_observation", [](RLManager& self, const std::string& uid) -> py::object {
            auto obs = self.get_observation(uid);
            if (obs.empty()) return py::none();
            return py::array_t<double>(obs.size(), obs.data());
        }, py::arg("agent_uid"))
        .def("get_reward", [](RLManager& self, const std::string& uid, const py::object& info) -> double {
            return self.get_reward(uid, python_to_json(info));
        }, py::arg("agent_uid"), py::arg("info"))
        .def("get_done", &RLManager::get_done, py::arg("agent_uid"))
        .def("get_episode_done", &RLManager::get_episode_done)
        .def("get_reward_breakdown", &RLManager::get_reward_breakdown, py::arg("agent_uid"))
        .def("reset", &RLManager::reset)
        .def("load_reward_config", &RLManager::load_reward_config, py::arg("config_path"))
        .def("load_reward_config_str", &RLManager::load_reward_config_str, py::arg("config_str"))   
        .def("set_observation_space", &RLManager::set_observation_space, py::arg("obs_space_spec"))
        .def("get_baseline_action", [](RLManager& self, const std::string& uid) -> py::object {
            auto action = self.get_baseline_action(uid);
            if (!action.has_value()) return py::none();
            return json_to_python(action.value());
        }, py::arg("agent_uid"))
        .def("get_baseline_action_vec", [](RLManager& self, const std::string& uid) -> py::object {
            auto action = self.get_baseline_action_vec(uid);
            return py::array_t<double>(action.size(), action.data());
        }, py::arg("agent_uid"))
        .def("get_obs_dim", &RLManager::get_obs_dim);

}
