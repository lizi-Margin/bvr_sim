#include "yasim_support/Main/fg_props.hxx"
#include "yasim_fdm.hxx"
#include "extern/yasim/FGFDM.hpp"
#include "extern/yasim/Glue.hpp"
#include "extern/yasim/Ground.hpp"
#include "extern/yasim/Thruster.hpp"
#include "extern/yasim/PropEngine.hpp"
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <functional>
#include <filesystem>
#include <sstream>

namespace bvr_sim {
namespace {
constexpr double radius = 6378137.0;
// Only genuine command channels receive the host stick. Substring matching
// used to drive YF-23 speedbrake-aileron and Buccaneer autostab/droop with the
// same stick, summing unrelated source FCS branches into the physical surface.
int flight_channel(std::string key) {
    if(!key.empty()&&key.front()=='/')key.erase(0,1);
    static const std::map<std::string,int> channels={
        {"controls/flight/aileron",0},{"controls/flight/aileron-pos",0},
        {"autopilot/FCS/controls/flaperon-roll-norm",0},{"autopilot/FCS/controls/elevon-roll-norm",0},
        {"autopilot/FCS/controls/flight/aileron-norm",0},{"fcs/output/roll",0},
        {"fcs/aileron-hydraulic-cmd-norm",0},{"fcs/aileron-inner-cmd-norm",0},{"fcs/aileron-outer-cmd-norm",0},
        {"systems/hydraulic/outputs/aileron",0},{"systems/hydraulic/outputs/aileron[1]",0},
        {"controls/flight/elevator",1},{"controls/flight/elevator[1]",1},{"controls/flight/elevator-pos",1},
        {"sim/model/A-10/controls/flight/sas-elevator",1}, // sole source hstab primary command, not a duplicate SAS branch
        {"autopilot/FCS/controls/elevon-pitch-norm",1},{"autopilot/FCS/controls/flight/ruddervator-pitch-norm",1},
        {"fcs/output/pitch",1},{"fcs/elevator-cmd-norm",1},
        {"controls/flight/rudder",2},{"controls/flight/rudder-pos",2},
        {"autopilot/FCS/controls/rudder-norm",2},{"autopilot/FCS/controls/flight/ruddervator-yaw-norm",2},
        {"fcs/output/yaw",2},{"fcs/rudder-cmd-norm",2}
    };
    auto channel=channels.find(key);
    return channel==channels.end() ? -1 : channel->second;
}
// Sea-level tangent plane. Game terrain collision remains in the simulation
// caller; no renderer or session dependency enters the FDM.
class SeaGround : public yasim::Ground {
public:
    bool getBody(double, double* transform, double* linear, double* angular, unsigned int& id) override {
        // Gear stiction queries the supporting body's transform even while
        // retracted. The base Ground stub leaves these outputs untouched.
        for(int i=0;i<16;++i)transform[i]=(i%5==0)?1.:0.;
        for(int i=0;i<3;++i)linear[i]=angular[i]=0.;
        id=0;
        return true;
    }
    void getGroundPlane(const double*, double* plane, float* velocity, unsigned int& body) override {
        // Global plane points up; State::planeGlobalToLocal reverses it for gear.
        plane[0]=1; plane[1]=plane[2]=0; plane[3]=radius;
        velocity[0]=velocity[1]=velocity[2]=0; body=0;
    }
    void getGroundPlane(const double* p,double* plane,float* v,const simgear::BVHMaterial** material,unsigned int& b) override {
        *material=nullptr; getGroundPlane(p,plane,v,b);
    }
};
class Parser : public yasim::FGFDM {
    bool cruise = false;
public:
    std::map<std::string,double> controls;
    std::vector<std::string> inputs;
    void startElement(const char* name,const XMLAttributes& attrs) override {
        if (std::string(name)=="cruise") cruise=true;
        if (std::string(name)=="control-input" && attrs.hasAttribute("axis")) inputs.emplace_back(attrs.getValue("axis"));
        if (cruise && std::string(name)=="control-setting" && attrs.hasAttribute("axis") && attrs.hasAttribute("value"))
            controls[attrs.getValue("axis")]=std::stod(attrs.getValue("value"));
        yasim::FGFDM::startElement(name,attrs);
        if(std::string(name)=="airplane" && attrs.hasAttribute("bvr-solver-tweak"))
            getAirplane()->setSolverTweak(std::stof(attrs.getValue("bvr-solver-tweak")));
    }
    void endElement(const char* name) override {
        if(std::string(name)=="cruise")cruise=false;
        yasim::FGFDM::endElement(name);
    }
};
}
struct YASimFDM::Impl {
    std::string path;
    SGPropertyNode_ptr props;
    std::unique_ptr<Parser> host;
    yasim::State state;
    double target_speed=200;
    bool initialized=false;
    explicit Impl(std::string file):path(std::move(file)){}
};
YASimFDM::YASimFDM(double step,const std::string& path):AircraftFDM(step),impl(std::make_unique<Impl>(path)) {
    if(!std::isfinite(dt)||dt<=0||dt>.1)throw std::invalid_argument("YASim dt must be in (0,0.1]");
}
YASimFDM::~YASimFDM()=default;
void YASimFDM::reset(const std::map<std::string,std::any>& input) {
    impl->initialized=false;
    impl->host.reset();
    impl->props=new SGPropertyNode;
    yasim_host::Scope scope(impl->props);
    auto defaults=std::filesystem::path(impl->path).parent_path()/"host_properties.json";
    if(std::filesystem::is_regular_file(defaults)){
        std::ifstream file(defaults);std::stringstream buffer;buffer<<file.rdbuf();auto data=json::JSON::Load(buffer.str());
        if(data.hasKey("defaults"))for(const auto& [key,value]:data["defaults"].ObjectRange())
            fgSetDouble(key.c_str(),value.JSONType()==json::JSON::Class::Integral?double(value.ToInt()):value.ToFloat());
    }
    impl->host=std::make_unique<Parser>();
    std::ifstream stream(impl->path);
    if(!stream)throw std::runtime_error("Missing YASim XML: "+impl->path);
    readXML(stream,*impl->host,impl->path);
    auto a=impl->host->getAirplane();
    a->compile(std::getenv("BVR_YASIM_SOLVER_VERBOSE") != nullptr);
    if(a->getFailureMsg())throw std::runtime_error("YASim solve failed: "+std::string(a->getFailureMsg()));
    fgSetFloat("/sim/fuel-fraction",.5f);
    impl->host->init();
    for(const auto& [key,value]:impl->host->controls)fgSetDouble(key.c_str(),value);
    fgSetBool("/controls/gear/gear-down",false);
    fgSetFloat("/controls/gear/gear-down",0);
    fgSetFloat("/controls/flight/flaps",0);
    fgSetFloat("/controls/flight/speedbrake",0);
    position=std::any_cast<std::array<double,3>>(input.at("position"));
    velocity=std::any_cast<std::array<double,3>>(input.at("velocity"));
    for(double v:position)if(!std::isfinite(v))throw std::invalid_argument("Invalid YASim position");
    for(double v:velocity)if(!std::isfinite(v))throw std::invalid_argument("Invalid YASim velocity");
    auto scalar=[&](const char* key,double fallback) {auto it=input.find(key);return it==input.end()?fallback:std::any_cast<double>(it->second);};
    roll=scalar("roll",0);pitch=scalar("pitch",0);yaw=scalar("yaw",std::atan2(velocity[1],velocity[0]));
    auto& s=impl->state;s=yasim::State{};
    s.pos[0]=radius+position[2];s.pos[1]=-position[1];s.pos[2]=position[0];
    s.v[0]=float(velocity[2]);s.v[1]=float(-velocity[1]);s.v[2]=float(velocity[0]);
    float ned[9],orient[9];
    yasim::Glue::xyz2nedMat(0,0,ned);
    yasim::Glue::euler2orient(float(roll),float(-pitch),float(-yaw),orient);
    yasim::Math::mmul33(orient,ned,s.orient);
    a->getModel()->setState(&s);
    a->getModel()->setGroundCallback(new SeaGround());
    a->getModel()->setStandardAtmosphere(float(position[2]));
    impl->host->getExternalInput();
    a->initEngines();
    float initial_wind[3];s.globalToLocal(s.v,initial_wind);
    yasim::Math::mul3(-1,initial_wind,initial_wind);
    // This host resets in flight. Hybrid jet/prop aircraft need their piston
    // engines running; FlightGear normally supplies these startup properties.
    for(int e=0;e<a->numThrusters();++e){
        auto thruster=a->getModel()->getThruster(e);
        thruster->setWind(initial_wind);
        thruster->setStandardAtmosphere(float(position[2]));
        auto prop=thruster->getPropEngine();
        if(prop){
            fgGetNode("/controls/engines/engine",e,true)->getNode("magnetos",true)->setIntValue(3);
            prop->setMagnetos(3);
            prop->getEngine()->setRunning(true);
        }
    }
    a->stabilizeThrust();
    for(int e=0;e<a->numThrusters();++e){
        if(auto prop=a->getModel()->getThruster(e)->getPropEngine()){
            // FGFDM reads RPM back from its output property before every
            // integration pass. Publish the stabilized airborne RPM now,
            // otherwise a newly created zero-valued node stops the propeller.
            fgGetNode("/engines/engine",e,true)->getNode("rpm",true)->setFloatValue(prop->getOmega()*9.5492966f);
        }
    }
    impl->target_speed=get_speed();
    terminate=false;impl->initialized=true;
}
void YASimFDM::read_state() {
    auto s=impl->host->getAirplane()->getModel()->getState();
    position={s->pos[2],-s->pos[1],s->pos[0]-radius};
    velocity={s->v[2],-s->v[1],s->v[0]};
    float ned[9],inv[9],orientation[9],r,p,h;
    yasim::Glue::xyz2nedMat(0,0,ned);yasim::Math::trans33(ned,inv);
    yasim::Math::mmul33(s->orient,inv,orientation);
    yasim::Glue::orient2euler(orientation,&r,&p,&h);
    roll=r;pitch=-p;yaw=-h;
    for(double x:position)terminate|=!std::isfinite(x);
    for(double x:velocity)terminate|=!std::isfinite(x);
    terminate|=!std::isfinite(roll)||!std::isfinite(pitch)||!std::isfinite(yaw)||position[2]<0;
}
void YASimFDM::step(const ActionSpace& action) {
    if(!impl->initialized)throw std::logic_error("YASimFDM must be reset before stepping");
    if(auto rate=action.roll_rate_cmd();rate&&!std::isfinite(*rate))
        throw std::invalid_argument("YASim roll-rate command must be finite");
    if(terminate)return;
    yasim_host::Scope scope(impl->props);
    const int steps=int(std::ceil(dt/.005));
    const float inner=float(dt/steps);
    auto a=impl->host->getAirplane();
    a->getModel()->getIntegrator()->setInterval(inner);
    // Host heading/climb assist generates surface commands; YASim computes all
    // forces and integration. Direct normalized surfaces override the assist.
    for(int i=0;i<steps&&!terminate;++i){
        const double target_bank=std::clamp(-action.delta_heading()*.65,-.8,.8);
        const double target_pitch=std::clamp(-action.delta_altitude()*.3,-.35,.35);
        float rates[3];auto s=a->getModel()->getState();s->globalToLocal(s->rot,rates);
        // Centered/released heading input means stop rolling, not wings level.
        // The former unconditional -roll feedback erased a manually established
        // bank as soon as A/D was released, opposing a sustained banked turn.
        // Only an active heading request asks the assistant for a bank angle.
        const double bank_error=std::abs(action.delta_heading())>1e-4 ? target_bank-roll : 0.;
        double roll_assist=bank_error*1.8-rates[0]*.45;
        if(auto rate=action.roll_rate_cmd()){
            // Interactive rate mode is independent of heading error, including
            // a parked off-center mouse when A/D is released. Never erase bank
            // to chase a tiny heading error. Center means zero roll rate only.
            constexpr double pi=3.14159265358979323846;
            double requested=std::clamp(*rate,-pi/3,pi/3);
            // Slow outward mouse roll near 65 degrees; do not pull a larger
            // manually established bank back to this limit. Raw A/D bypasses it.
            if(requested*roll>0)
                requested*=std::clamp((65*pi/180-std::abs(roll))/(30*pi/180),0.,1.);
            roll_assist=(requested-rates[0])*.45;
        }
        double ail=action.aileron_cmd().value_or(std::clamp(roll_assist,-1.,1.));
        double ele=action.elevator_cmd().value_or(std::clamp((target_pitch-pitch)*1.8-rates[1]*.5,-1.,1.));
        double rud=action.rudder_cmd().value_or(0);
        double throttle=action.throttle_cmd().value_or(std::clamp(.6+(impl->target_speed+action.delta_speed()*100-get_speed())*.015,0.,1.));
        fgSetFloat("/controls/flight/aileron",float(std::clamp(ail,-1.,1.)));
        fgSetFloat("/controls/flight/elevator",float(std::clamp(ele,-1.,1.)));
        fgSetFloat("/controls/flight/rudder",float(std::clamp(rud,-1.,1.)));
        // Aircraft whose control inputs normally come from Nasal/JSBSim FCS
        // receive explicit host-assist aliases. This is a documented control
        // approximation, not execution of the source aircraft's systems.
        for(const auto& key:impl->host->inputs){
            if(key.find("trim")!=std::string::npos || key.find("fail")!=std::string::npos)continue;
            if(key.find("throttle")!=std::string::npos)fgSetDouble(key.c_str(),throttle);
            else if(key.find("reheat")!=std::string::npos || key.find("afterburner")!=std::string::npos)
                fgSetDouble(key.c_str(),std::clamp((throttle-.85)/.15,0.,1.));
            else {
                switch(flight_channel(key)){
                    case 0:fgSetDouble(key.c_str(),ail);break;
                    case 1:fgSetDouble(key.c_str(),ele);break;
                    case 2:fgSetDouble(key.c_str(),rud);break;
                    default:break;
                }
            }
        }
        for(int e=0;e<a->numThrusters();++e){
            auto n=fgGetNode("/controls/engines/engine",e,true);
            n->getNode("throttle",true)->setFloatValue(float(std::clamp(throttle,0.,1.)));
            n->getNode("mixture",true)->setFloatValue(1);
        }
        a->getModel()->setStandardAtmosphere(float(position[2]));
        a->getModel()->updateGround(s);
        impl->host->iterate(inner);
        read_state();
    }
}
double YASimFDM::property(const std::string& name) const {
    auto n=impl->props?impl->props->getNode(name,false):nullptr;
    return n?n->getDoubleValue():0;
}
void YASimFDM::set_property(const std::string& name,double value){
    if(!impl->initialized)throw std::logic_error("YASimFDM must be reset first");
    if(!std::isfinite(value))throw std::invalid_argument("Non-finite YASim property");
    impl->props->getNode(name,true)->setDoubleValue(value);
}
std::map<std::string,double> YASimFDM::visual_properties() const {
    std::map<std::string,double> result;
    if(!impl->props)return result;
    std::function<void(const SGPropertyNode*,std::string)> visit=[&](const SGPropertyNode* node,std::string path){
        if(path=="fdm" || path=="yasim")return; // omit diagnostic surface/mass trees
        if(node->nChildren()==0 && node->hasValue())result[path]=node->getDoubleValue();
        for(int i=0;i<node->nChildren();++i){
            auto c=node->getChild(i);auto name=std::string(c->getNameString());
            if(c->getIndex()!=0)name+="["+std::to_string(c->getIndex())+"]";
            visit(c,path.empty()?name:path+"/"+name);
        }
    };
    visit(impl->props,"");
    return result;
}
}
