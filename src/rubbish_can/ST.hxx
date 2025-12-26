#include <chrono>
#include "SL.hxx"

struct ScopedStepTimer {
    const char* label;
    std::chrono::steady_clock::time_point t0;
    ScopedStepTimer(const char* lbl) : label(lbl), t0(std::chrono::steady_clock::now()) {}
    ~ScopedStepTimer() {
        using namespace std::chrono;
        const double ms = duration<double, std::milli>(steady_clock::now() - t0).count();
        SL::get().printf("[TIMER] %s : %.3f ms", label, ms);
    }
};

inline double ms_since(std::chrono::steady_clock::time_point t0) {
    using namespace std::chrono;
    return duration<double, std::milli>(steady_clock::now() - t0).count();
}
