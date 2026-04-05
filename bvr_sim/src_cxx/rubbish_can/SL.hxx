#pragma once
#include <fstream>
#include <string>
#include <iostream>
#include <cstdarg>
#include <vector>
// #include <memory>
#include <mutex>
#include <chrono>
#include <ctime>
#include <iomanip>
#include <sstream>
#include "check.hxx"

// #define DISABLE 1

class SL {
private:
    inline static SL* instance_ = nullptr;

public:
    static SL& init_instance(const std::string& file_path, bool append)
    {
        instance_ = new SL(file_path, append);
        return *instance_;
    }

    static SL& get()
    {
        check(instance_, "SL::get() before init_instance()");
        return *instance_;
    }

    SL(const SL&) = delete;
    SL& operator=(const SL&) = delete;

    ~SL()
    {
        if (m_file.is_open()) {
            m_file.close();
        }
    }

    void print([[maybe_unused]] const std::string& msg)
    {
#ifndef DISABLE
        std::lock_guard<std::mutex> lock(m_mutex);
        m_file << timestamp() << " " << msg << std::endl;
        m_file.flush();
#endif
    }

    void printf([[maybe_unused]] const char* format, ...)
    {
#ifndef DISABLE
        std::lock_guard<std::mutex> lock(m_mutex);

        va_list args;
        va_start(args, format);

        va_list args_copy;
        va_copy(args_copy, args);
        int size = std::vsnprintf(nullptr, 0, format, args_copy);
        va_end(args_copy);

        if (size > 0) {
            std::vector<char> buf(size + 1);
            std::vsnprintf(buf.data(), buf.size(), format, args);
            m_file << timestamp() << " " << buf.data() << std::endl;
        }

        va_end(args);
        m_file.flush();
#endif
    }

    std::string timestamp()
    {
        auto now = std::chrono::system_clock::now();
        std::time_t t = std::chrono::system_clock::to_time_t(now);
        std::tm tm;
#if defined(_WIN32) || defined(_WIN64)
        localtime_s(&tm, &t);
#else
        localtime_r(&t, &tm);
#endif
        std::ostringstream oss;
        oss << "["
            << std::setfill('0')
            << std::setw(2) << tm.tm_mon + 1 << "-"
            << std::setw(2) << tm.tm_mday << "-"
            << std::setw(2) << tm.tm_hour << "-"
            << std::setw(2) << tm.tm_min << "-"
            << std::setw(2) << tm.tm_sec
            << "]";
        return oss.str();
    }

private:
    explicit SL(const std::string& file_path, bool append)
        : m_buffer(5 * 1024 * 1024)
    {
        std::ios_base::openmode mode = std::ios::out;
        if (append) {
            mode |= std::ios::app;
        }
        else {
            mode |= std::ios::trunc;
        }

        m_file.rdbuf()->pubsetbuf(m_buffer.data(), m_buffer.size());
        m_file.open(file_path, mode);
        if (!m_file.is_open()) {
            throw std::runtime_error("Failed to open log file: " + file_path);
        }
    }

    std::ofstream m_file;
    std::vector<char> m_buffer;
    std::mutex m_mutex;
};
