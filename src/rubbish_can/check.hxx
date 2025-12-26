#pragma once

#include <cstdio>
#include <cstdlib>
#include <string_view>
// #include <string>
#include <cstdarg>
#include <cpptrace/cpptrace.hpp>

#if __cplusplus >= 202002L
    #define CPP20_OR_LATER 1
    #include <source_location>
#endif

namespace check_func {
    [[noreturn]] inline void assert_fail(
        std::string_view expr,
        std::string_view msg
#ifdef CPP20_OR_LATER
        ,
        const std::source_location& loc = std::source_location::current()
#endif
    ) {
        // 输出到 stderr
        std::fprintf(stderr, 
            "Assertion failed: %s\n"
            "    Message: %s\n"
#ifdef CPP20_OR_LATER
            "    Location: %s:%d in function %s\n"
#endif
            ,expr.data(),
            msg.data()
#ifdef CPP20_OR_LATER
            ,loc.file_name(),
            loc.line(),
            loc.function_name()
#endif
        );
        
        cpptrace::generate_trace().print();
        std::abort();
    }
} // namespace check_func

#ifdef CPP20_OR_LATER
#define check(expr, msg) \
    do { \
        if (!(expr)) { \
            ::check_func::assert_fail(#expr, msg, std::source_location::current()); \
        } \
    } while (false)
#endif

#ifndef CPP20_OR_LATER
#define check(expr, msg) \
    do { \
        if (!(expr)) { \
            ::check_func::assert_fail(#expr, msg); \
        } \
    } while (false)
#endif


inline void format_check(bool condition, const char* fmt, ...)
{
    if (!condition) {
        va_list args;
        va_start(args, fmt);
        char buffer[1024];
        vsnprintf(buffer, sizeof(buffer), fmt, args);
        va_end(args);
        // colorful::printHONG(buffer);
        std::printf("Assertion failed: %s\n", buffer);
        cpptrace::generate_trace().print();
        std::abort();
    }
}