#include "cmd_handler.hxx"
#include "so_pool.hxx"
#include "bsl_pool.hxx"
#include "rubbish_can/SL.hxx"
#include "rubbish_can/check.hxx"
#include "unit_factory.hxx"
#include <regex>
#include <sstream>
#include <algorithm>

namespace bvr_sim {

CmdHandler& CmdHandler::instance() {
    static CmdHandler h;
    return h;
}

json::JSON CmdHandler::handle(const std::string& cmd) noexcept {
    SL::get().printf("[CmdHandler] Received command: %s\n", cmd.c_str());
    auto res = _handle(cmd);
    SL::get().printf("[CmdHandler] Command result: %s\n", res.dump(1, "", "").c_str());
    return res;
}

json::JSON CmdHandler::_handle(const std::string& cmd) noexcept {
    ParsedCommand parsed;
    try {
        parsed = parse_command(cmd);
    } catch (const std::runtime_error& e) {
        json::JSON err = json::JSON::Make( json::JSON::Class::Object );
        err["status"] = json::String("error");
        err["message"] = json::String("Parse failed: " + std::string(e.what()));
        return err;
    }
    process_command_type(parsed);
    if (parsed.type == ParsedCommand::INVALID) {
        json::JSON err = json::JSON::Make( json::JSON::Class::Object );
        err["status"] = json::String("error");
        err["message"] = json::String("invalid command");
        return err;
    }

    switch (parsed.type) {
        case ParsedCommand::GET:
            return handle_get(parsed);
        case ParsedCommand::SET:
            return handle_set(parsed);
        case ParsedCommand::INIT:
            return handle_init(parsed);
        case ParsedCommand::CLEAR:
            return handle_clear(parsed);
        default: {
            json::JSON err = json::JSON::Make( json::JSON::Class::Object );
            err["status"] = "error";
            err["message"] = "unknown command";
            return err;
        }
    }
}

json::JSON CmdHandler::handle_get(const ParsedCommand& parsed) noexcept {
    auto obj = SOPool::instance().get(parsed.uid);
    if (!obj) {
        json::JSON err = json::JSON::Make( json::JSON::Class::Object );
        err["status"] = json::String("error");
        err["message"] = json::String("uid not found");
        return err;
    }

    // return full object representation (assumes to_json exists)
    std::map<std::string, json::JSON> all_state;
    all_state = obj->get_register().get_all();
    json::JSON res = json::JSON::Make( json::JSON::Class::Object );
    for (auto &p : all_state) {
        res[p.first] = p.second;
    }
    res["empty"] = json::Boolean(obj->get_register().size() == 0);
    res["status"] = json::String("ok");
    return res;
}

json::JSON CmdHandler::handle_set(const ParsedCommand& parsed) noexcept {
    if (parsed.value.JSONType() == json::JSON::Class::Null) {
        json::JSON err = json::JSON::Make( json::JSON::Class::Object );
        err["status"] = json::String("error");
        err["message"] = json::String("missing json for set");
        return err;
    }

    auto obj = SOPool::instance().get(parsed.uid);
    if (!obj) {
        json::JSON err = json::JSON::Make( json::JSON::Class::Object );
        err["status"] = json::String("error");
        err["message"] = json::String("uid not found");
        return err;
    }

    json::JSON kv = parsed.value;
    if (kv.JSONType() != json::JSON::Class::Object) {
        json::JSON err = json::JSON::Make( json::JSON::Class::Object );
        err["status"] = json::String("error");
        err["message"] = json::String("set value must be a JSON object");
        return err;
    }

    bool all_ok = true;
    for (auto &p : kv.ObjectRange()) {
        if (!obj->set(p.first, p.second)) {
            all_ok = false;
        }
    }

    json::JSON res = json::JSON::Make( json::JSON::Class::Object );
    res["status"] = all_ok ? json::String("ok") : json::String("partial_failure");
    res["applied"] = json::Boolean(all_ok);
    return res;
}

json::JSON CmdHandler::handle_init(const ParsedCommand& parsed) noexcept {
    if (parsed.value.JSONType() == json::JSON::Class::Null) {
        json::JSON err = json::JSON::Make( json::JSON::Class::Object );
        err["status"] = json::String("error");
        err["message"] = json::String("missing json for init");
        return err;
    }

    json::JSON cfg = parsed.value;
    if (cfg.JSONType() != json::JSON::Class::Object) {
        json::JSON err = json::JSON::Make( json::JSON::Class::Object );
        err["status"] = "error";
        err["message"] = json::String("init json must be object");
        return err;
    }

    auto unit = UnitFactory::create_unit(parsed.uid, cfg);
    json::JSON res = json::JSON::Make( json::JSON::Class::Object );
    if (unit) {
        res["status"] = json::String("ok");
        res["uid"] = json::String(parsed.uid);
    } else {
        res["status"] = json::String("error");
        res["message"] = json::String("failed to create unit");
    }
    return res;
}

json::JSON CmdHandler::handle_clear(const ParsedCommand& parsed) noexcept {
    check(parsed.type == ParsedCommand::CLEAR, "clear command must be clear");
    // delete all existing obj
    size_t n = SOPool::instance().size();
    BaselinePool::instance().clear();
    SOPool::instance().clear();
    json::JSON res = json::JSON::Make( json::JSON::Class::Object );
    res["status"] = json::String("ok");
    res["message"] = json::String("all " + std::to_string(n) + " units cleared (deleted)");
    return res;
}

CmdHandler::ParsedCommand CmdHandler::parse_command(const std::string& input)
{
    // 强制三段格式：cmd uid json
    static const std::regex pattern(
        R"(^\s*([A-Za-z0-9]+)\s+([A-Za-z0-9]+)\s+(.+)\s*$)"
    );

    std::smatch match;
    if (!std::regex_match(input, match, pattern)) {
        throw std::runtime_error("Command format invalid: expected 'cmd uid json'");
    }

    std::string cmd  = match[1].str();
    std::string uid  = match[2].str();
    std::string json_str = match[3].str();  // 捕获剩余全部内容

    json::JSON value = json::JSON::Make( json::JSON::Class::Object );
    try {
        value = json::JSON::Load(json_str);
    } catch (...) {
        throw std::runtime_error("Invalid JSON payload");
    }

    ParsedCommand out;
    out.cmd = cmd;
    out.uid = uid;
    out.value = std::move(value);
    return out;
}

void CmdHandler::process_command_type(ParsedCommand& parsed) {
    if (parsed.cmd == "get") {
        parsed.type = ParsedCommand::GET;
    } else if (parsed.cmd == "set") {
        parsed.type = ParsedCommand::SET;
    } else if (parsed.cmd == "init") {
        parsed.type = ParsedCommand::INIT;
    } else if (parsed.cmd == "clear") {
        parsed.type = ParsedCommand::CLEAR;
    } else {
        parsed.type = ParsedCommand::INVALID;
    }
}

} // namespace bvr_sim
