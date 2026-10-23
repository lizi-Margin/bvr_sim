#pragma once
// Analytic, deterministic alpha mask. No external image or simulation randomness.
inline wi::ecs::Entity soft_sprite(wi::scene::Scene& scene,const std::string& name,
                                   DirectX::XMFLOAT4 color,float emission=0){
    auto e=scene.Entity_CreatePlane(name);
    auto mesh=scene.meshes.GetComponent(e);
    for(auto& p:mesh->vertex_positions){p.y=p.z;p.z=0;}
    for(auto& n:mesh->vertex_normals)n={0,0,1};
    mesh->CreateRenderData();
    wi::vector<uint8_t> rgba(64*64*4);
    for(int y=0;y<64;++y)for(int x=0;x<64;++x){
        float u=(x+.5f)/32-1,v=(y+.5f)/32-1,r2=u*u+v*v;
        // Low-amplitude crossed frequencies avoid visible diagonal scan bands.
        float noise=.9f+.06f*std::sin(x*.31f)*std::sin(y*.27f)+.04f*std::sin((x+y)*.15f);
        float a=std::pow(std::max(0.f,1-r2),2.f)*noise;
        auto i=(y*64+x)*4;rgba[i]=rgba[i+1]=rgba[i+2]=255;rgba[i+3]=uint8_t(a*255);
    }
    wi::graphics::Texture texture;
    if(!wi::texturehelper::CreateTexture(texture,rgba.data(),64,64))throw std::runtime_error("Cannot create analytic effect texture");
    auto m=scene.materials.GetComponent(e);m->textures[wi::scene::MaterialComponent::BASECOLORMAP].resource.SetTexture(texture);
    m->SetBaseColor(color);m->SetRoughness(1);m->SetCastShadow(false);m->SetDoubleSided(true);
    m->userBlendMode=wi::enums::BLENDMODE_ALPHA;m->SetEmissiveColor({color.x,color.y,color.z,emission});m->SetDirty();
    scene.objects.GetComponent(e)->SetCastShadow(false);return e;
}
