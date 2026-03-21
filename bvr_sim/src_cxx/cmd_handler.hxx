#pragma once


#include "rubbish_can/json.hpp"
#include <string>
#include <optional>


namespace bvr_sim {


class CmdHandler {
public:
    static CmdHandler& instance();


    CmdHandler(const CmdHandler&) = delete;
    CmdHandler& operator=(const CmdHandler&) = delete;


    // Handle a single-line command and return a JSON response
    json::JSON handle(const std::string& cmd) noexcept;


private:
    CmdHandler() = default;


    struct ParsedCommand {
        enum Type { GET, SET, INIT, CLEAR, INVALID } type = INVALID;
        std::string cmd; // "get" | "set" | "init"
        std::string uid;
        json::JSON value; // present for SET and INIT when JSON provided
    };


    json::JSON _handle(const std::string& cmd) noexcept;


    ParsedCommand parse_command(const std::string& cmd);
    void process_command_type(ParsedCommand& parsed);


    json::JSON handle_get(const ParsedCommand& parsed) noexcept;
    json::JSON handle_set(const ParsedCommand& parsed) noexcept;
    json::JSON handle_init(const ParsedCommand& parsed) noexcept;
    json::JSON handle_clear(const ParsedCommand& parsed) noexcept;
};


} // namespace bvr_sim