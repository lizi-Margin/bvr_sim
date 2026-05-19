#include <unordered_map>
#include <map>
#include <string>
#include <iostream>
#include <sstream>

template<typename T>
void print_unordered_map(const std::unordered_map<std::string, T> &map)
{
    std::cout << "{" << std::endl;
    for (const auto &pair : map)
    {
        std::cout << "\t" << pair.first << ": " << pair.second << std::endl;
    }
    std::cout << "}" << std::endl;
}

template<typename T>
void print_map(const std::map<std::string, T> &map)
{
    std::cout << "{" << std::endl;
    for (const auto &pair : map)
    {
        std::cout << "\t" << pair.first << ": " << pair.second << std::endl;
    }
    std::cout << "}" << std::endl;
}

template<typename T>
std::string print_map_s(const std::map<std::string, T> &map)
{
    std::stringstream ss;
    ss << "{" << std::endl;
    for (const auto &pair : map)
    {
        ss << "\t" << pair.first << ": " << pair.second << std::endl;
    }
    ss << "}" << std::endl;
    return ss.str();
}

// IWYU pragma: begin_exports
#include "check.hxx"
#include "colorful.hxx"
#include "SL.hxx"
#include "json_getter.hxx"
// IWYU pragma: end_exports
