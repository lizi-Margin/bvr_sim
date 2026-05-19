#include "set_env.hxx"
#include <iostream>
#include <string>

#ifdef _WIN32
    #include <cstdlib>
#else
    #include <stdlib.h>
#endif

bool set_env(const std::string& name, const std::string& value) {
#ifdef _WIN32
    errno_t err = _putenv_s(name.c_str(), value.c_str());
#endif
#ifndef _WIN32
    int err = setenv(name.c_str(), value.c_str(), 1);
#endif
    if (err != 0) {
        std::cerr << "Failed to set environment variable " << name << " to " << value << std::endl;
        return false;
    }
    return true;
}