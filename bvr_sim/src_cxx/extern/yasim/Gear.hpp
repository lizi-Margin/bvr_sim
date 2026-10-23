#ifndef _GEAR_HPP
#define _GEAR_HPP
#include "Math.hpp"

#include <functional>


namespace simgear {
class BVHMaterial;
}

namespace yasim {

class Ground;
class RigidBody;
struct State;


/* Contains a vector and pre-generates unit and magnitude values. */
struct GearVector
{
    GearVector( float v0=0, float v1=0, float v2=0);
    void set( float v0, float v1, float v2);
    float v[3];
    float unit[3];
    float magnitude;
};

// A landing gear has the following parameters:
//
// position: a point in the aircraft's local coordinate system where the
//     fully-extended wheel will be found.
// compression: a vector from position where a fully-compressed wheel
//     will be, also in aircraft-local coordinates.
// spring coefficient: force coefficient along the compression axis, in
//     Newtons per meter.
// damping coefficient: force per compression speed, in Ns/m
// static coefficient of friction: force along the ground plane exerted
//     by a motionless wheel.  A unitless scalar.
// dynamic coefficient of friction: force along the ground plane exerted
//     by a sliding/skidding wheel.
// braking fraction: fraction of the dynamic friction that will be
//     actually exerted by a rolling wheel
// rotation: the angle from "forward" by which the wheel is rotated
//     around its compression axis.  In radians.
//
class Gear {
public:
    Gear();

    // Externally set values
    void setPosition(float* position) { Math::set3(position, _pos); }
    void getPosition(float* out) { Math::set3(_pos, out); }
    void setCompression(float* compression);
    void getCompression(float* out) { Math::set3(_cmpr.v, out); }
    
    void setWheelAxle(float* wheelAxle);
    void getWheelAxle(float* out) { Math::set3(_wheelAxle.v, out); }
    
    void setWheelRadius(float wheelRadius) { _wheelRadius = wheelRadius; }
    float getWheelRadius() { return _wheelRadius; }
    
    void setTyreRadius(float tyreRadius) { _tyreRadius = tyreRadius; }
    float getTyreRadius() { return _tyreRadius; }
    
    void getContact(float* contact) { Math::set3( _contact, contact); }
    
    void setSpring(float spring) { _spring = spring; }
    float getSpring() { return _spring; }
    void setSpring2(float spring2) { _spring2 = spring2; }
    void setDamping(float damping) { _damp = damping; }
    float getDamping() {return _damp; }
    void setStaticFriction(float sfric) { _sfric = sfric; }
    float getStaticFriction() { return _sfric; }
    void setDynamicFriction(float dfric) { _dfric = dfric; }
    float getDynamicFriction() { return _dfric; }
    void setBrake(float brake) { _brake = Math::clamp(brake, 0, 1); }
    float getBrake() { return _brake; }
    void setRotation(float rotation) { _rot = rotation; }
    float getRotation() { return _rot; }
    void setExtension(float extension) { _extension = Math::clamp(extension, 0, 1); }  
    float getExtension() { return _extension; }
    void setCastering(bool c) { _castering = c; }
    bool getCastering() { return _castering; }
    void setOnWater(bool c) { _onWater = c; }
    void setOnSolid(bool c) { _onSolid = c; }
    void setSpringFactorNotPlaning(float f) { _spring_factor_not_planing = f; }
    void setSpeedPlaning(float s) { _speed_planing = s; }
    void setReduceFrictionByExtension(float s) { _reduceFrictionByExtension = s; }
    void setInitialLoad(float l) { _initialLoad = l; }
    float getInitialLoad() {return _initialLoad; }
    void setIgnoreWhileSolving(bool c) { _ignoreWhileSolving = c; }
    void setStiction(bool s) { _stiction = s; }
    bool getStiction() { return _stiction; }
    void setStictionABS(bool a) { _stiction_abs = a; }
    bool getStictionABS() { return _stiction_abs; }

    void setGlobalGround(double* global_ground, float* global_vel,
        double globalX, double globalY,
                         const simgear::BVHMaterial *material, unsigned int body);
    void getGlobalGround(double* global_ground);
    float getCasterAngle() { return _casterAngle; }
    float getRollSpeed() { return _rollSpeed; }
    float getBumpAltitude();
    bool getGroundIsSolid() { return _ground_isSolid; }
    float getGroundFrictionFactor() { return (float)_ground_frictionFactor; }
    void integrate(float dt);

    // Takes a velocity of the aircraft relative to ground, a rotation
    // vector, and a ground plane (all specified in local coordinates)
    // and make a force and point of application (i.e. ground contact)
    // available via getForce().
    void calcForce(Ground *g_cb, RigidBody* body, State* s, float* v, float* rot);
    void calcForceWithoutStiction(float wgt, float steer[3], float skid[3], float *cv, float *force);
    void calcForceWithStiction(Ground *g_cb, State *s, float wgt, float steer[3], float skid[3], float *cv, float *force);

    // Computed values: total force, weight-on-wheels (force normal to
    // ground) and compression fraction.
    void getForce(float* force, float* contact);
    float getWoW() { return _wow; }
    float getCompressFraction() { return _frac; }
    float getCompressDist() { return _compressDist; }
    bool getSubmergable() {return (!_ground_isSolid)&&(!_isContactPoint); }
    bool getIgnoreWhileSolving() {return _ignoreWhileSolving; }
    void setContactPoint(bool c) { _isContactPoint=c; }

    // Update the stuck point after all integrator's iterations
    void updateStuckPoint(State* s);
    void getStuckPoint(double *out);
    void setStuckPoint(double *in);

private:
    float calcFriction(float wgt, float v);
    float calcFrictionFluid(float wgt, float v);
    void calcFriction(float *gpos, float *cv, float *steer, float *skid, float wgt, float *force);
    void calcFrictionFluid(float *cv, float *steer, float *skid, float wgt, float *force);

    float _fric_spring = 0;
    bool _castering = false;
    bool _rolling = false;
    bool _slipping = false;
    float _pos[3] = {0};
    double _stuck[3] = {0};
    GearVector _cmpr;
    float _spring = 0;
    float _spring2 = 0;
    float _damp = 0;
    float _sfric = 0;
    float _dfric = 0;
    float _brake = 0;
    float _rot = 0;
    float _extension = 0;
    float _force[3] = {0};
    float _contact[3] = {0};
    float _wow = 0;
    float _frac = 0;    /* Compression as fraction of maximum. */
    float _initialLoad = 0;
    float _compressDist = 0;    /* Vertical compression distance. */
    double _global_ground[4] = {0};
    float _global_vel[3] = {0};
    float _casterAngle = 0;
    float _rollSpeed = 0;
    bool _isContactPoint = false;
    bool _onWater = false;
    bool _onSolid = false;
    float _spring_factor_not_planing = 0;
    float _speed_planing = 0;
    float _reduceFrictionByExtension = 0;
    bool _ignoreWhileSolving = false;
    bool _stiction = false;
    bool _stiction_abs = false;

    double _ground_frictionFactor = 0;
    double _ground_rollingFriction = 0;
    double _ground_loadCapacity = 0;
    double _ground_loadResistance = 0;
    double _ground_bumpiness = 0;
    bool _ground_isSolid = false;
    double _global_x = 0;
    double _global_y = 0;
    unsigned int _body_id = 0;
    double _ground_rot[9] = {0};
    double _ground_trans[3] = {0};

    GearVector _wheelAxle;
    float _wheelRadius = 0;
    float _tyreRadius = 0;
};


/* [This is internal implementation for Gear(), exposed here to allow unit
testing.]

Finds compression of gear needed to make outside of tyre rest on ground.

    ground
        Definition of ground plane; points on ground satisfy p.ground[:3] ==
        ground[4]. Is assumed that for points below ground, p.ground[:3] is
        positive.
    compression
        Movement of wheel centre at maximum compression.
    wheel_pos
        Centre of wheel at full extension.
    wheel_axle
        Direction of wheel axle; defines orientation of wheel.
    wheel_radius
        Distance from <wheel_pos> to centre of tubular tyre.
    tyre_radius
        Radius of tubular tyre.
    bump_fn
        Callable that returns bump value.
    o_contact
        Out-param for position of tyre contact after compression has been
        applied.
    o_compression_distance_vertical
        Out-param vertical compression distance in metres.
    o_compression_norm
        Out-param compression as a fraction of maximum compression.

If on ground, sets out-params for ground contact and returns true. Otherwise
sets out-params for maximum extension of the gear and returns false.
*/
bool gearCompression(
        const float (&ground)[4],
        const GearVector& compression,
        const float (&wheel_pos)[3],
        const GearVector& wheel_axle,
        float wheel_radius,
        float tyre_radius,
        std::function< float ()> bump_fn,
        float (&o_contact)[3],
        float& o_compression_distance_vertical,
        float& o_compression_norm
        );

/* Old calculation for simple contact point.

    ground
        Definition of ground plane; points on ground satisfy p.ground[:3] ==
        ground[4]. Is assumed that for points below ground, p.ground[:3] is
        positive.
    pos
        Position of contact point.
    compression
        Movement of contact point at maximum compression.
    bump_fn
        Callable that returns bump value.
    o_contact
        Position of tyre contact after our compression has been applied.
    o_compressDist
        Compression distance in metres.
    o_compressNorm
        Compression as a fraction of maximum compression.
    bump_altitude_override
        For testing; if >= 0, we use this instead of getting a live value from
        getBumpAltitude().
*/
bool gearCompressionOld(
        const float (&ground)[4],
        const GearVector& compression,
        const float (&pos)[3],
        std::function< float ()> bump_fn,
        float (&o_contact)[3],
        float& o_compression_distance_vertical,
        float& o_compression_norm
        );

}; // namespace yasim
#endif // _GEAR_HPP
