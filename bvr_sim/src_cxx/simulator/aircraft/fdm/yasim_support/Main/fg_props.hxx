#pragma once
// Standalone YASim host. Reuse JSBSim's SimGear property implementation to
// avoid two incompatible copies of SGPropertyNode in the same process.
#include <iostream>
#include <stdexcept>
#include <simgear/props/props.hxx>
#define SG_ALERT 0
#define SG_WARN 1
#define SG_GENERAL 0
#define SG_FLIGHT 0
#define SG_INPUT 0
#define SG_INFO 2
#define SG_DEV_ALERT 3
#define SG_DEV_WARN 3
#undef SG_LOG
#define SG_LOG(category, level, message) do { if ((level) == 0) { std::cerr << message << '\n'; } } while (false)
SGPropertyNode* fgGetNode(const char* path, bool create = false);
SGPropertyNode* fgGetNode(const char* path, int index, bool create = false);
float fgGetFloat(const char* path, float fallback = 0);
double fgGetDouble(const char* path, double fallback = 0);
bool fgGetBool(const char* path, bool fallback = false);
bool fgSetFloat(const char* path, float value);
bool fgSetDouble(const char* path, double value);
bool fgSetBool(const char* path, bool value);
bool fgSetString(const char* path, const char* value);

namespace bvr_sim::yasim_host {
// A scope is required during construction, parsing, solving and stepping.
// Each FDM owns a separate property tree; the scoped pointer is thread local.
class Scope {
    SGPropertyNode* previous;
public:
    explicit Scope(SGPropertyNode* root);
    ~Scope();
};
}

inline SGPropertyNode* fgGetNode(const std::string& p, bool c=false) { return fgGetNode(p.c_str(),c); }
inline bool fgSetFloat(const std::string& p,float v) { return fgSetFloat(p.c_str(),v); }

inline float fgGetFloat(const std::string& p,float d=0) { return fgGetFloat(p.c_str(),d); }
