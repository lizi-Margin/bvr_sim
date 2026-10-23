#include "yasim_support/Main/fg_props.hxx"
namespace { thread_local SGPropertyNode* active = nullptr; }
namespace bvr_sim::yasim_host {
Scope::Scope(SGPropertyNode* root) : previous(active) { active = root; }
Scope::~Scope() { active = previous; }
}
SGPropertyNode* fgGetNode(const char* path, bool create) {
    if (!active) throw std::logic_error("YASim property access outside FDM scope");
    return active->getNode(path, create);
}
SGPropertyNode* fgGetNode(const char* path, int index, bool create) {
    if (!active) throw std::logic_error("YASim property access outside FDM scope");
    return active->getNode(path, index, create);
}
float fgGetFloat(const char* p, float d) { auto n=fgGetNode(p); return n ? n->getFloatValue() : d; }
double fgGetDouble(const char* p, double d) { auto n=fgGetNode(p); return n ? n->getDoubleValue() : d; }
bool fgGetBool(const char* p, bool d) { auto n=fgGetNode(p); return n ? n->getBoolValue() : d; }
bool fgSetFloat(const char* p, float v) { return fgGetNode(p,true)->setFloatValue(v); }
bool fgSetDouble(const char* p, double v) { return fgGetNode(p,true)->setDoubleValue(v); }
bool fgSetBool(const char* p, bool v) { return fgGetNode(p,true)->setBoolValue(v); }
bool fgSetString(const char* p, const char* v) { return fgGetNode(p,true)->setStringValue(v); }
