#pragma once
// Presentation-only maintenance apron. No simulation objects or contact data.
template<class Cube>
void build_hangar_apron(Cube cube,std::vector<wi::ecs::Entity>& entities) {
    auto& scene=wi::scene::GetScene();
    auto add=[&](const std::string& name,DirectX::XMFLOAT3 position,DirectX::XMFLOAT3 scale,DirectX::XMFLOAT4 color){
        auto e=cube(name,position,scale,color);scene.layers.GetComponent(e)->layerMask=2;entities.push_back(e);return e;
    };
    add("apron_concrete",{0,-.38f,0},{140,.3f,140},{.26f,.27f,.27f,1});
    // Floor joints, paint and a clear aircraft service bay establish scale.
    for(int i=-6;i<=6;++i){
        add("concrete_joint",{i*10.f,-.065f,0},{.018f,.007f,135},{.11f,.12f,.12f,1});
        add("concrete_joint",{0,-.065f,i*10.f},{135,.007f,.018f},{.11f,.12f,.12f,1});
    }
    for(float x:{-14.f,14.f})add("service_bay_paint",{x,-.047f,-4},{.055f,.008f,19},{.62f,.48f,.18f,1});
    for(float z:{-23.f,15.f})add("service_bay_paint",{0,-.047f,z},{14,.008f,.055f},{.62f,.48f,.18f,1});
    add("hangar_wall",{0,12,42},{65,12,.45f},{.18f,.21f,.22f,1});
    add("hangar_door",{0,9,41.4f},{27,9,.18f},{.09f,.12f,.14f,1});
    for(int i=-65;i<=65;++i)add("wall_seam",{float(i),12,41.45f},{.04f,12,.08f},{.23f,.26f,.26f,1});
    for(int i=0;i<35;++i)add("roller_door_rib",{0,.5f+i*.5f,41.1f},{27,.025f,.06f},{.16f,.19f,.20f,1});
    for(float x:{-31.f,31.f})add("hangar_door_post",{x,10,40},{.65f,10,1.1f},{.31f,.33f,.32f,1});
    add("door_header",{0,21,40},{32,1,1.2f},{.29f,.31f,.30f,1});
    add("hangar_roof",{0,25,53},{68,.4f,13},{.16f,.18f,.19f,1});
    for(int i=0;i<8;++i){
        float x=-43.f+i*3.8f;
        add("safety_block",{x,.65f,28},{1.7f,.65f,.55f},i%2?DirectX::XMFLOAT4(.62f,.19f,.13f,1):DirectX::XMFLOAT4(.65f,.64f,.58f,1));
    }
    for(float x:{-25.f,24.f}){
        add("tool_cart",{x,.9f,10},{1.4f,.7f,.6f},{.25f,.11f,.09f,1});
        for(int j=0;j<3;++j)add("tool_drawer",{x,.55f+j*.4f,9.38f},{1.2f,.025f,.04f},{.51f,.52f,.48f,1});
        for(float dx:{-1.f,1.f})add("cart_wheel",{x+dx,.25f,10},{.2f,.25f,.6f},{.035f,.04f,.04f,1});
    }
}
