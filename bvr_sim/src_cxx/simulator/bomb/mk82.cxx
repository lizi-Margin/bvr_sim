#include "mk82.hxx"
namespace bvr_sim {
void ballistic_step(std::array<double, 3> &position, std::array<double, 3> &velocity, double dt) {
    const double speed = std::hypot(std::hypot(velocity[0], velocity[1]), velocity[2]);
    for (int i = 0; i < 3; ++i)
        velocity[i] -= 0.00003 * speed * velocity[i] * dt;
    velocity[2] -= 9.80665 * dt;
    for (int i = 0; i < 3; ++i)
        position[i] += velocity[i] * dt;
}

std::array<double,3> refine_ballistic_contact(const std::array<double,3>& previous,
                                             const std::array<double,3>& candidate,const Terrain& terrain) {
    // The existing physical weapon's24-step segment refinement, shared with
    // precise typed-player prediction. No trajectory or damage rule changes.
    double low=0,high=1;
    for(int n=0;n<24;++n){
        const double t=(low+high)/2;
        const double x=previous[0]+(candidate[0]-previous[0])*t;
        const double y=previous[1]+(candidate[1]-previous[1])*t;
        const double z=previous[2]+(candidate[2]-previous[2])*t;
        if(z>terrain.collision_height(x,y))low=t;else high=t;
    }
    std::array<double,3> result;
    for(int i=0;i<3;++i)result[i]=previous[i]+(candidate[i]-previous[i])*high;
    return result;
}

std::optional<std::array<double, 3>> predict_ballistic_impact(std::array<double, 3> p,
                                                              std::array<double, 3> v, const Terrain &terrain,
                                                              double dt, int max_steps,bool refined_contact) {
    p[2] -= 2;
    for (int i = 0; i < max_steps; ++i) {
        const auto previous=p;
        ballistic_step(p, v, dt);
        if (p[2] <= terrain.collision_height(p[0], p[1])) {
            if(refined_contact)return refine_ballistic_contact(previous,p,terrain);
            // Exact legacy endpoint remains available to the old AI/RL frame
            // contract; typed player CCIP requests the physical contact above.
            p[2] = terrain.collision_height(p[0], p[1]);
            return p;
        }
    }
    return std::nullopt;
}
} // namespace bvr_sim
