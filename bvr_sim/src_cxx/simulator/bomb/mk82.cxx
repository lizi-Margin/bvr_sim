#include "mk82.hxx"
namespace bvr_sim {
Mk82Bomb::Mk82Bomb(std::string id,const SimulatedObject& parent,std::shared_ptr<const Terrain> surface,
                   double timestep,const Mk82Parameters& p)
    :SimulatedObject(id,parent.color,parent.position,parent.velocity,timestep,SOT::Bomb),
     terrain(std::move(surface)),owner(parent.uid),parameters(p) {
    if(!terrain||!std::isfinite(timestep)||timestep<=0||!std::isfinite(p.quadratic_drag)||p.quadratic_drag<0||
       !std::isfinite(p.gravity)||p.gravity<=0||!std::isfinite(p.release_drop)||p.release_drop<0||
       !std::isfinite(p.blast_radius)||p.blast_radius<0)throw std::invalid_argument("Invalid Mk-82 environment or parameters");
    position[2]-=parameters.release_drop;
}
void Mk82Bomb::step() {
    if(!is_alive)return;
    const auto previous=position;
    ballistic_step(position,velocity,dt,parameters);
    if(position[2]<=terrain->collision_height(position[0],position[1])) {
        position=refine_ballistic_contact(previous,position,*terrain);
        for(const auto& obj:SOPool::instance().get_all()) {
            if(obj->color==color||!obj->is_alive)continue;
            if(auto ground=std::dynamic_pointer_cast<GroundUnit>(obj))
                if(bomb_distance(position,ground->position)<=parameters.blast_radius)ground->hit();
        }
        impacted=true;is_alive=false;
    }
}
void ballistic_step(std::array<double, 3> &position, std::array<double, 3> &velocity, double dt,const Mk82Parameters& p) {
    const double speed = std::hypot(std::hypot(velocity[0], velocity[1]), velocity[2]);
    for (int i = 0; i < 3; ++i)
        velocity[i] -= p.quadratic_drag * speed * velocity[i] * dt;
    velocity[2] -= p.gravity * dt;
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
                                                              double dt, int max_steps,bool refined_contact,const Mk82Parameters& parameters) {
    p[2] -= parameters.release_drop;
    for (int i = 0; i < max_steps; ++i) {
        const auto previous=p;
        ballistic_step(p, v, dt,parameters);
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
