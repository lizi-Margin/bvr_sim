
#ifdef HAVE_CONFIG_H
#  include "config.h"
#endif

#include <simgear/debug/logstream.hxx>

#include "Math.hpp"
#include "BodyEnvironment.hpp"
#include "Ground.hpp"
#include "RigidBody.hpp"

#include <cfloat>
#include <simgear/bvh/BVHMaterial.hxx>
// Standalone: unused FlightGear interface include removed.
#include "Gear.hpp"
namespace yasim {
static const float YASIM_PI = 3.14159265358979323846;
static const float DEG2RAD = YASIM_PI / 180.0;
static const float maxGroundBumpAmplitude=0.4;
        //Amplitude can be positive and negative

/* Sets <out> to unit vector along <v>, or all zeros if <v> is zero
length. Returns length of <v>. */
static float magnitudeUnit( const float* v, float* out)
{
    float magnitude = Math::mag3( v);
    if ( magnitude) {
        Math::mul3( 1 / magnitude, v, out);
    }
    else {
        Math::zero3( out);
    }
    return magnitude;
}

GearVector::GearVector( float v0, float v1, float v2)
{
    set( v0, v1, v2);
}

void GearVector::set( float v0, float v1, float v2)
{
    v[0] = v0;
    v[1] = v1;
    v[2] = v2;
    magnitude = magnitudeUnit( v, unit);
}

Gear::Gear()
{
    int i;
    for(i=0; i<3; i++)
        _pos[i] = _stuck[i] = 0;
    _spring = 1;
    _spring2 = 0;
    _damp = 0;
    _sfric = 0.8f;
    _dfric = 0.7f;
    _fric_spring = 0.005f; // Spring length = 5 mm
    _brake = 0;
    _rot = 0;
    _initialLoad = 0;
    _extension = 1;
    _castering = false;
    _frac = 0;
    _ground_frictionFactor = 1;
    _ground_rollingFriction = 0.02;
    _ground_loadCapacity = 1e30;
    _ground_loadResistance = 1e30;
    _ground_isSolid = 1;
    _ground_bumpiness = 0;
    _onWater = 0;
    _onSolid = 1;
    _global_x = 0.0;
    _global_y = 0.0;
    _reduceFrictionByExtension = 0;
    _spring_factor_not_planing = 1;
    _speed_planing = 0;
    _isContactPoint = 0;
    _ignoreWhileSolving = 0;
    _stiction = false;
    _stiction_abs = false;

    for(i=0; i<3; i++)
        _global_ground[i] = _global_vel[i] = 0;
    _global_ground[2] = 1;
    _global_ground[3] = -1e3;

    Math::zero3(_ground_trans);
    Math::identity33(_ground_rot);
    
    _wheelAxle.set(0, 1, 0);
    _wheelRadius = 0;
    _tyreRadius = 0;
}

void Gear::setCompression(float* compression)
{
    _cmpr.set( compression[0], compression[1], compression[2]);
}

void Gear::setWheelAxle(float* wheel_axle)
{
    _wheelAxle.set( wheel_axle[0], wheel_axle[1], wheel_axle[2]);
    if (_wheelAxle.magnitude == 0) {
        _wheelAxle.unit[1] = 1;
    }
}

void Gear::setGlobalGround(double *global_ground, float* global_vel,
                           double globalX, double globalY,
                           const simgear::BVHMaterial *material, unsigned int body)
{
    int i;
    double frictionFactor,rollingFriction,loadCapacity,loadResistance,bumpiness;
    bool isSolid;

    for(i=0; i<4; i++) _global_ground[i] = global_ground[i];
    for(i=0; i<3; i++) _global_vel[i] = global_vel[i];

    if (material) {
        bool is_lake = (*material).solid_is_prop();
        bool solid = (*material).get_solid();
        if (is_lake && solid) { // on ice
          frictionFactor = 0.3;
          rollingFriction = 0.05;
          bumpiness = 0.1;
        } else {
          frictionFactor = (*material).get_friction_factor();
          rollingFriction = (*material).get_rolling_friction();
          bumpiness = (*material).get_bumpiness();
        }

        loadCapacity = (*material).get_load_resistance();
        loadResistance = (*material).get_load_resistance();
        isSolid = (*material).get_solid();
    } else {
        // no material, assume solid
        loadCapacity = DBL_MAX;
        frictionFactor = 1.0;
        rollingFriction = 0.02;
        loadResistance = DBL_MAX;
        bumpiness = 0.0;
        isSolid = true;
    }
    _ground_frictionFactor = frictionFactor;
    _ground_rollingFriction = rollingFriction;
    _ground_loadCapacity = loadCapacity;
    _ground_loadResistance = loadResistance;
    _ground_bumpiness = bumpiness;
    _ground_isSolid = isSolid;
    _global_x = globalX;
    _global_y = globalY;
    _body_id = body;
}

void Gear::getGlobalGround(double* global_ground)
{
    for(int i=0; i<4; i++) global_ground[i] = _global_ground[i];
}

void Gear::getForce(float* force, float* contact)
{
    Math::set3(_force, force);
    Math::set3(_contact, contact);
}


float Gear::getBumpAltitude()
{
    if (_ground_bumpiness<0.001) return 0.0;
    double x = _global_x*0.1;
    double y = _global_y*0.1;
    x -= Math::floor(x);
    y -= Math::floor(y);
    x *= 2*YASIM_PI;
    y *= 2*YASIM_PI;
    //now x and y are in the range of 0..2pi
    //we need a function, that is periodically on 2pi and gives some
    //height. This is not very fast, but for a beginning.
    //maybe this should be done by interpolating between some precalculated
    //values
    float h = Math::sin(x)+Math::sin(7*x)+Math::sin(8*x)+Math::sin(13*x);
    h += Math::sin(2*y)+Math::sin(5*y)+Math::sin(9*y*x)+Math::sin(17*y);

    return h*(1/8.)*_ground_bumpiness*maxGroundBumpAmplitude;
}

void Gear::integrate(float dt)
{
    // Slowly spin down wheel
    if (_rollSpeed > 0) {
        // The brake factor of 13.0 * dt was copied from JSBSim's FGLGear.cpp and seems to work reasonably.
        // If more precise control is needed, then we need wheel mass and diameter parameters.
        _rollSpeed -= (13.0 * dt + 1300 * _brake * dt);
        if (_rollSpeed < 0) _rollSpeed = 0;
    }
    return;
}


bool gearCompression(
        const float (&ground)[4],
        const GearVector& compression,
        const float (&wheel_pos)[3],
        const GearVector (&wheel_axle),
        float wheel_radius,
        float tyre_radius,
        std::function< float ()> bump_fn,
        float (&o_contact)[3],
        float& o_compression_distance_vertical,
        float& o_compression_norm
        )
{
    /* In this diagram we are looking at wheel end on.

                N
                 \     S'
                  \   /
                   \ /
                    W--__
                   /     --> wheel_axle     |
                  /                         | G
                 S                          V

        ------------------------- Ground plus tyre_radius

        ========================= Ground

    W is wheel_pos, position of wheel centre at maximum extension.

    S is the lowest point of rim relative to ground. S' is the highest point
    of the rim relative to the ground. So SWS' is a diameter across middle of
    wheel. For most aircraft this will be vertical (relative to the aircraft),
    but we don't require this; might be useful for a Bf109 aircraft.

    N is position of wheel centre at maximum compression:
        N = W + compression.

    <wheel_axle> is wheel axle vector. Usually this is close to y axis, e.g. (
    0, 1, 0).

    G is ground normal, pointing downwards. Points p on ground satisfy:
        G[:3].p = G3

    Points p on (ground plus tyre_radius) satisfy:
        G[:3].p = G3 + tyre_radius.

    R is vector from W to S; to make S be lowest point on rim, this is radial
    vector of wheel that is most closely aligned with G. We use:
        R = - wheel_axle x G x wheel_axle

    Distance of S below (ground plus tyre_radius), is:
        a = S.G - ( G3 + tyre_radius)

    If a < 0, the point of maximum extension is above ground and we return
    false.

    Otherwise, a >= 0 and the point of maximum extension is below ground, so
    we are in contact with the ground and we compress the grear just enough to
    make S be on ground plus tyre_radius. The tyre surface is tyre_radius from
    S, so this ensures that the tyre will just touch the ground.

    Compressing the gear means we move S (and W and S') a distance
    compression_distance along vector <compression> (the vector from W to N),
    and the projection of this movement along G must be -a. So:
        ( compression_distance * compression) . G = -a
    So:
        compression_distance = -a / (compression . G)
    */
    
    float ground_unit[3];
    magnitudeUnit( ground, ground_unit);
    
    /* Find S, the lowest point on wheel. */
    float S[3];
    Math::set3( wheel_pos, S);
    
    if (wheel_radius) {
        /* Find radial wheel vector pointing closest to ground using two
        cross-products: wheel_axle_unit x ground_unit x wheel_axle_unit */
        float R[3];
        Math::cross3( wheel_axle.unit, ground_unit, R);
        Math::cross3( R, wheel_axle.unit, R);

        /* Scale R to be length wheel_radius so it is vector from W to S, and
        use it to find S. */
        Math::unit3( R, R);
        Math::mul3( wheel_radius, R, R);
        
        /* Add R to S to get lowest point on wheel. */
        Math::add3( S, R, S);
    }
    
    /* Calculate <a>, distance of S below ground. */
    float a = Math::dot3( ground, S) - ( ground[3] - tyre_radius);
    float bump_altitude = 0;
    if ( a > -maxGroundBumpAmplitude) {
        bump_altitude = bump_fn();
        a -= bump_altitude;
    }

    bool ret = true;
    
    if ( a < 0) {
        /* S is above ground so we are not on ground, so set ret=false.
        
        We force a=0 to pretend fully-extended gear is just on the ground, so
        that o_contact will be set to the fully extended gear position. This
        will be used by our caller to find /position/gear-agl-ft. */
        ret = false;
        a = 0;
    }
    
    /* Lowest part of wheel is below ground. */
    o_compression_distance_vertical = a;
    
    /* Find compression_norm. First we need to find compression_distance, the
    distance to compress the gear so that S (which is below ground+tyre_radius)
    would move to just touch ground+tyre_radius. We need to move gear further
    depending on how perpendicular <compression> is to the ground. */
    o_compression_norm = 0;
    float compression_distance = 0;
    float div = Math::dot3( compression.unit, ground_unit);
    if (div) {
        /* compression.unit points upwards, ground_unit points downwards, so
        div is -ve. */
        compression_distance = -a / div;
    }

    /* Set o_compression_norm. */
    if ( compression.magnitude) {
        o_compression_norm = compression_distance / compression.magnitude;
    }
    if (o_compression_norm > 1) {
        o_compression_norm = 1;
    }
    
    /* Contact point on ground-plus-tyre-radius is S plus compression
    vector. */
    float delta[3];
    Math::mul3( compression_distance, compression.unit, delta);
    Math::add3( S, delta, o_contact);

    if (ret)
    {
        /* If we are on the ground, verify that <o_contact> is tyre_radius
        above ground; this can fail e.g. when resetting so for now we just
        output a diagnostic rather than assert fail. */
        //assert( fabs( Math::dot3( o_contact, ground) - (ground[3] - tyre_radius + bump_altitude)) < 0.001);
        double s = Math::dot3( o_contact, ground) - (ground[3] - tyre_radius + bump_altitude);
        if (fabs( s) > 0.001)
        {
            SG_LOG(SG_GENERAL, SG_ALERT, "<o_contact> is not tyre_radius above ground."
                    << " o_contact=" << o_contact
                    << " ground=" << ground
                    << " tyre_radius=" << tyre_radius
                    << " bump_altitude=" << bump_altitude
                    << " s=" << s
                    );
        }
    }

    /* Correct for tyre_radius - need to move o_contact a distance tyre_radius
    towards ground. */
    if (tyre_radius) {
        Math::mul3( tyre_radius, ground_unit, delta);
        Math::add3( o_contact, delta, o_contact);
    }
    
    if (ret)
    {
        /* Verify that <o_contact> is on ground; this can fail e.g. when resetting so for now we
        just output a diagnostic rather than assert fail. */
        //assert( fabs( Math::dot3( o_contact, ground) - (ground[3] + bump_altitude)) < 0.001);
        double s = Math::dot3( o_contact, ground) - (ground[3] + bump_altitude);
        if ( fabs( s) > 0.001)
        {
            SG_LOG(SG_GENERAL, SG_ALERT, "<o_contact> is not on ground."
                    << " o_contact=" << o_contact
                    << " ground=" << ground
                    << " tyre_radius=" << tyre_radius
                    << " bump_altitude=" << bump_altitude
                    << " s=" << s
                    );
        }
    }
    
    return ret;
}

bool gearCompressionOld(
        const float (&ground)[4],
        const GearVector& compression,
        const float (&pos)[3],
        std::function< float ()> bump_fn,
        float (&o_contact)[3],
        float& o_compression_distance_vertical,
        float& o_compression_norm
        )
{
    // First off, make sure that the gear "tip" is below the ground.
    // If it's not, there's no force.
    float a = ground[3] - Math::dot3(pos, ground);
    float BumpAltitude=0;
    if (a<maxGroundBumpAmplitude)
    {
        BumpAltitude = bump_fn();
        a+=BumpAltitude;
    }
    
    if(a > 0) {
        o_compression_distance_vertical = 0;
        o_compression_norm = 0;
        return false;
    }

    o_compression_distance_vertical = -a;
    
    // Now a is the distance from the tip to ground, so make b the
    // distance from the base to ground.  We can get the fraction
    // (0-1) of compression from a/(a-b). Note the minus sign -- stuff
    // above ground is negative.
    float tmp[3];
    Math::add3(compression.v, pos, tmp);
    float b = ground[3] - Math::dot3(tmp, ground)+BumpAltitude;

    // Calculate the point of ground _contact.
    if(b < 0)
        o_compression_norm = 1;
    else
        o_compression_norm = a/(a-b);
    for(int i=0; i<3; i++)
        o_contact[i] = pos[i] + o_compression_norm * compression.v[i];
    return true;
}


void Gear::calcForce(Ground *g_cb, RigidBody* body, State *s, float* v, float* rot)
{
    // Init the return values
    int i;
    for(i=0; i<3; i++) _force[i] = _contact[i] = 0;

    // Don't bother if gear is retracted
    if(_extension < 1)
    {
        _wow = 0;
        _frac = 0;
        return;
    }

    // Dont bother if we are in the "wrong" ground
    if (!((_onWater&&!_ground_isSolid)||(_onSolid&&_ground_isSolid)))  {
         _wow = 0;
         _frac = 0;
        _compressDist = 0;
        _rollSpeed = 0;
        _casterAngle = 0;
        return;
    }

    // The ground plane transformed to the local frame.
    float ground[4];
    s->planeGlobalToLocal(_global_ground, ground);

    bool on_ground = gearCompression(
            ground,
            _cmpr,
            _pos,
            _wheelAxle,
            _wheelRadius,
            _tyreRadius,
            [this] { return this->getBumpAltitude(); },
            _contact,
            _compressDist,
            _frac
            );
    if (!on_ground) {
        _wow = 0;
        _frac = 0;
        _compressDist = 0;
        _casterAngle = 0;
        return;
    }

    // The velocity of the contact patch transformed to local coordinates.
    float glvel[3];
    s->globalToLocal(_global_vel, glvel);
    
    // Turn _cmpr into a unit vector and a magnitude
    const float (&cmpr)[3] = _cmpr.unit;
    const float &clen = _cmpr.magnitude;

    // Now get the velocity of the point of contact
    float cv[3];
    body->pointVelocity(_contact, rot, cv);
    Math::add3(cv, v, cv);
    Math::sub3(cv, glvel, cv);

    // Finally, we can start adding up the forces.  First the spring
    // compression.   (note the clamping of _frac to 1):
    _frac = (_frac > 1) ? 1 : _frac;

    // Add the initial load to frac, but with continous transistion around 0
    float frac_with_initial_load;
    if (_frac>0.2 || _initialLoad==0.0)
        frac_with_initial_load = _frac+_initialLoad;
    else
        frac_with_initial_load = (_frac+_initialLoad)
            *_frac*_frac*3*25-_frac*_frac*_frac*2*125;

    float fmag = clen * _spring *
            (
            frac_with_initial_load
            + _spring2 * pow( frac_with_initial_load, 2)
            );
    if (_speed_planing>0)
    {
        float v = Math::mag3(cv);
        if (v < _speed_planing)
        {
            float frac = v/_speed_planing;
            fmag = fmag*_spring_factor_not_planing*(1-frac)+fmag*frac;
        }
    }
    // Then the damping.  Use the only the velocity into the ground
    // (projection along "ground") projected along the compression
    // axis.  So Vdamp = ground*(ground dot cv) dot cmpr
    float tmp[3];
    Math::mul3(Math::dot3(ground, cv), ground, tmp);
    float dv = Math::dot3(cmpr, tmp);
    float damp = _damp * dv;
    if(damp > fmag) damp = fmag; // can't pull the plane down!
    if(damp < -fmag) damp = -fmag; // sanity

    // The actual force applied is only the component perpendicular to
    // the ground.  Side forces come from velocity only.
    _wow = (fmag - damp) * -Math::dot3(cmpr, ground);
    Math::mul3(-_wow, ground, _force);

    // Wheels are funky.  Split the velocity along the ground plane
    // into rolling and skidding components.  Assuming small angles,
    // we generate "forward" and "left" unit vectors (the compression
    // goes "up") for the gear, make a "steer" direction from these,
    // and then project it onto the ground plane.  Project the
    // velocity onto the ground plane too, and extract the "steer"
    // component.  The remainder is the skid velocity.

    float gup[3]; // "up" unit vector from the ground
    Math::set3(ground, gup);
    Math::mul3(-1, gup, gup);

    float xhat[] = {1,0,0};
    float steer[3], skid[3];
    Math::cross3(gup, xhat, skid);  // up cross xhat =~ skid
    Math::unit3(skid, skid);        //               == skid

    Math::cross3(skid, gup, steer); // skid cross up == steer

    if(_rot != 0) {
        // Correct for a rotation
        float srot = Math::sin(_rot);
        float crot = Math::cos(_rot);
        float tx = steer[0];
        float ty = steer[1];
        steer[0] =  crot*tx + srot*ty;
        steer[1] = -srot*tx + crot*ty;

        tx = skid[0];
        ty = skid[1];
        skid[0] =  crot*tx + srot*ty;
        skid[1] = -srot*tx + crot*ty;
    }

    float vsteer = Math::dot3(cv, steer);
    float vskid  = Math::dot3(cv, skid);
    float wgt = Math::dot3(_force, gup); // force into the ground

    if(_castering) {
        _rollSpeed = Math::sqrt(vsteer*vsteer + vskid*vskid);
        // Don't modify caster angle when the wheel isn't moving,
        // or else the angle will animate the "jitter" of a stopped
        // gear.
        if(_rollSpeed > 0.05)
            _casterAngle = Math::atan2(vskid, vsteer);
        return;
    } else {
        _rollSpeed = vsteer;
        _casterAngle = _rot;
    }

    if (!_stiction) {
        // original static friction function
        calcForceWithoutStiction(wgt, steer, skid, cv, _force);
    }
    else {
        // static friction feature based on spring attached to stuck point
        calcForceWithStiction(g_cb, s, wgt, steer, skid, cv, _force);
    }
}

void Gear::calcForceWithStiction(Ground *g_cb, State *s, float wgt, float steer[3], float skid[3], float *cv, float *force)
{
    float ffric[3];
    if(_ground_isSolid) {
        float stuckf[3];
        double stuckd[3], lVel[3], aVel[3];
        double body_xform[16];

        // get AI body transform
        g_cb->getBody(s->dt, body_xform, lVel, aVel, _body_id);
        Math::set3(&body_xform[12], _ground_trans);

        for (int i = 0; i < 3; i++) {
            for (int j = 0; j < 3; j++) {
                _ground_rot[i*3+j] = body_xform[i*4+j];
            }
        }

        // translate and rotate stuck point in global coordinate space - compensate
        // AI body movement
        getStuckPoint(stuckd);

        // convert global point to local aircraft reference coordinates
        s->posGlobalToLocal(stuckd, stuckf);
        calcFriction(stuckf, cv, steer, skid, wgt, ffric);
    }
    else {
        calcFrictionFluid(cv, steer, skid, wgt, ffric);
    }

    // Phoo!  All done.  Add it up and get out of here.
    Math::add3(ffric, force, force);
}

void Gear::calcForceWithoutStiction(float wgt, float steer[3], float skid[3], float *cv, float *force)
{
    // Get the velocities in the steer and skid directions
    float vsteer, vskid;
    vsteer = Math::dot3(cv, steer);
    vskid  = Math::dot3(cv, skid);

    float tmp[3];
    float fsteer,fskid;
    if(_ground_isSolid) {
        fsteer = (_brake * _ground_frictionFactor
                  +(1-_brake)*_ground_rollingFriction
                  )*calcFriction(wgt, vsteer);
        fskid  = calcFriction(wgt, vskid)*(_ground_frictionFactor);
    }
    else {
        fsteer = calcFrictionFluid(wgt, vsteer)*_ground_frictionFactor;
        fskid  = 10*calcFrictionFluid(wgt, vskid)*_ground_frictionFactor;
        //factor 10: floats have different drag in x and y.
    }
    if(vsteer > 0) fsteer = -fsteer;
    if(vskid > 0) fskid = -fskid;

    //reduce friction if wanted by _reduceFrictionByExtension
    float factor = (1-_frac)*(1-_reduceFrictionByExtension)+_frac*1;
    factor = Math::clamp(factor,0,1);
    fsteer *= factor;
    fskid *= factor;

    // Phoo!  All done.  Add it up and get out of here.
    Math::mul3(fsteer, steer, tmp);
    Math::add3(tmp, force, force);

    Math::mul3(fskid, skid, tmp);
    Math::add3(tmp, force, force);
}

float Gear::calcFriction(float wgt, float v) //used on solid ground
{
    // How slow is stopped?  10 cm/second?
    const float STOP = 0.1f;
    const float iSTOP = 1.0f/STOP;
    v = Math::abs(v);
    if(v < STOP) return v*iSTOP * wgt * _sfric;
    else         return wgt * _dfric;
}

float Gear::calcFrictionFluid(float wgt, float v) //used on fluid ground
{
    // How slow is stopped?  1 cm/second?
    const float STOP = 0.01f;
    const float iSTOP = 1.0f/STOP;
    v = Math::abs(v);
    if(v < STOP) return v*iSTOP * wgt * _sfric;
    else return wgt * _dfric*v*v*0.01;
    //*0.01: to get _dfric of the same size than _dfric on solid
}

//used on solid ground
void Gear::calcFriction(float *stuck, float *cv, float *steer, float *skid
                        , float wgt, float *force)
{
    // Calculate the gear's movement
    float dgear[3];
    Math::sub3(_contact, stuck, dgear);

    // Get the movement in the steer and skid directions
    float dsteer, dskid;
    dsteer = Math::dot3(dgear, steer);
    dskid  = Math::dot3(dgear, skid);

    // Get the velocities in the steer and skid directions
    float vsteer, vskid;
    vsteer = Math::dot3(cv, steer);
    vskid  = Math::dot3(cv, skid);

    // If rolling and slipping are false, the gear is stopped
    _rolling  = false;
    _slipping = false;
    // Detect if it is slipping
    if (Math::sqrt(dskid*dskid + dsteer*dsteer*(_brake/_sfric)) > _fric_spring)
    {
        // Turn on our ABS ;)
        // This is off by default, because we don't want ABS on helicopters
        // as their "wheels" should be locked all the time
        if (_stiction && _stiction_abs && (Math::abs(dskid) < _fric_spring))
            {
                float bl;
                bl = _sfric - _sfric * (Math::abs(dskid) / _fric_spring);
                if (_brake > bl) _brake = bl;
            }
        else
            _slipping = true;
    }


    float fric, fspring, fdamper, brake, tmp[3];
    if (!_slipping)
    {
        // Calculate the steer force.
        // Brake is limited between 0 and 1, wheel lock on 1.
        brake = _brake > _sfric ? 1 : _brake/_sfric;
        fspring = Math::abs((dsteer / _fric_spring) * wgt * _sfric);
        // Set _rolling so the stuck point is updated
        if ((Math::abs(dsteer) > _fric_spring) || (fspring > brake * wgt * _sfric))
        {
            _rolling = true;
            fric  = _ground_rollingFriction * wgt * _sfric; // Rolling
            fric += _brake * wgt * _sfric * _ground_frictionFactor; // Brake
            if (vsteer > 0) fric = -fric;
        }
        else // Stopped
        {
            fdamper  = Math::abs(vsteer * wgt * _sfric);
            fdamper *= ((dsteer * vsteer) > 0) ? 1 : -1;
            fric  = fspring + fdamper;
            fric *= brake * _ground_frictionFactor
                    + (1 - brake) * _ground_rollingFriction;
            if (dsteer > 0) fric = -fric;
        }
        Math::mul3(fric, steer, force);

        // Calculate the skid force.
        fspring = Math::abs((dskid / _fric_spring) * wgt * _sfric);
        fdamper  = Math::abs(vskid * wgt * _sfric);
        fdamper *= ((dskid * vskid) > 0) ? 1 : -1;
        fric = _ground_frictionFactor * (fspring + fdamper);
        if (dskid > 0) fric = -fric;

        Math::mul3(fric, skid, tmp);
        Math::add3(force, tmp, force);

        // The damper can add a lot of force,
        // if it is to big, then it will slip
        if (Math::mag3(force) > wgt * _sfric * _ground_frictionFactor)
        {
            _slipping = true;
            _rolling = false;
        }
    }
    if (_slipping)
    {
        // Get the direction of movement
        float dir[3];
        Math::unit3(dgear, dir);

        // Calculate the steer force.
        // brake is limited between 0 and 1, wheel lock on 1
        brake = _brake > _dfric ? 1 : _brake/_dfric;
        fric  = wgt * _dfric * Math::abs(Math::dot3(dir, steer));
        fric *= _ground_rollingFriction * (1 - brake)
                + _ground_frictionFactor * brake;
        if (vsteer > 0) fric = -fric;
        Math::mul3(fric, steer, force);

        // Calculate the skid force.
        fric  = wgt * _dfric * _ground_frictionFactor;
        // Multiply by 1 when no brake, else reduce the turning component
        fric *= (1 - brake) + Math::abs(Math::dot3(dir, skid)) * brake;
        if (vskid > 0) fric = -fric;

        Math::mul3(fric, skid, tmp);
        Math::add3(force, tmp, force);
    }

    //reduce friction if wanted by _reduceFrictionByExtension
    float factor = (1-_frac)*(1-_reduceFrictionByExtension)+_frac*1;
    factor = Math::clamp(factor,0,1);
    Math::mul3(factor, force, force);
}

//used on fluid ground
void Gear::calcFrictionFluid(float *cv, float *steer, float *skid, float wgt, float *force)
{
    // How slow is stopped?  1 cm/second?
    const float STOP = 0.01f;
    const float iSTOP = 1.0f/STOP;
    float vsteer, vskid;
    vsteer = Math::dot3(cv, steer);
    vskid  = Math::dot3(cv, skid);

    float tmp[3];
    float fric;
    // Calculate the steer force
    float v = Math::abs(vsteer);
    if(v < STOP) fric = v*iSTOP * wgt * _sfric;
    else fric = wgt * _dfric*v*v*0.01;
    //*0.01: to get _dfric of the same size than _dfric on solid
    if (v > 0) fric = -fric;
    Math::mul3(_ground_frictionFactor * fric, steer, force);

    // Calculate the skid force
    v = Math::abs(vskid);
    if(v < STOP) fric = v*iSTOP * wgt * _sfric;
    else fric = wgt * _dfric*v*v*0.01;
    //*0.01: to get _dfric of the same size than _dfric on solid
    if (v > 0) fric = -fric;
    Math::mul3(10 * _ground_frictionFactor * fric, skid, tmp);
    Math::add3(force, tmp, force);
    //factor 10: floats have different drag in x and y.
}

// account for translation and rotation due to movements of AI body
// doubles used since operations are taking place in global coordinate system
void Gear::getStuckPoint(double *out)
{
    // get stuck point and add in AI body movement
    Math::tmul33(_ground_rot, _stuck, out);
    out[0] += _ground_trans[0];
    out[1] += _ground_trans[1];
    out[2] += _ground_trans[2];
}

void Gear::setStuckPoint(double *in)
{
    // Undo stuck point AI body movement and save as global coordinate
    in[0] -= _ground_trans[0];
    in[1] -= _ground_trans[1];
    in[2] -= _ground_trans[2];
    Math::vmul33(_ground_rot, in, _stuck);
}

void Gear::updateStuckPoint(State* s)
{
    float stuck[3];
    double stuckd[3];

    // get stuck point and update with AI body movement
    getStuckPoint(stuckd);

    // Convert stuck point to aircraft coordinates
    s->posGlobalToLocal(stuckd, stuck);

    // The ground plane transformed to the local frame.
    float ground[4];
    s->planeGlobalToLocal(_global_ground, ground);
    float gup[3]; // "up" unit vector from the ground
    Math::set3(ground, gup);
    Math::mul3(-1, gup, gup);

    float xhat[] = {1,0,0};
    float skid[3], steer[3];
    Math::cross3(gup, xhat, skid);  // up cross xhat =~ skid
    Math::unit3(skid, skid);        //               == skid
    Math::cross3(skid, gup, steer); // skid cross up == steer

    if(_rot != 0) {
        // Correct for a rotation
        float srot = Math::sin(_rot);
        float crot = Math::cos(_rot);
        float tx = steer[0];
        float ty = steer[1];
        steer[0] =  crot*tx + srot*ty;
        steer[1] = -srot*tx + crot*ty;

        tx = skid[0];
        ty = skid[1];

        skid[0] =  crot*tx + srot*ty;
        skid[1] = -srot*tx + crot*ty;
    }

    if (_rolling)
    {
        // Calculate the gear's movement
        float tmp[3];
        Math::sub3(_contact, stuck, tmp);
        // Get the movement in the skid and steer directions
        float dskid, dsteer;
        dskid  = Math::dot3(tmp, skid);
        dsteer = Math::dot3(tmp, steer);
        // The movement is not always exactly on the steer axis
        // so we should allow some empirical "slip" because of
        // the wheel flexibility (max 5 degrees)
        // FIXME: This angle should depend on the tire type/condition
        //        Is 5 degrees a good value?
        float rad = (dskid / _fric_spring) * 5.0 * DEG2RAD;
        dskid -= Math::abs(dsteer) * Math::tan(rad);

        Math::mul3(dskid, skid, tmp);
        Math::sub3(_contact, tmp, stuck);
    }
    else if (_slipping) {
        Math::set3(_contact, stuck);
    }

    if (_rolling || _slipping)
    {
        // convert from local reference to global coordinates
        s->posLocalToGlobal(stuck, stuckd);

        // undo AI body rotations and translations and save stuck point in global coordinate space
        setStuckPoint(stuckd);
    }
}


}; // namespace yasim

