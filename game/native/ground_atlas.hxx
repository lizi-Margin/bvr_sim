#pragma once
// Decorative source-tree deformation only. Heights are a checked copy of the
// shared core terrain; this class never changes simulation or contact state.
struct GroundAtlasState {
    uint32_t columns=0, rows=0;
    float origin_north=0, origin_west=0, spacing=0;
    uint64_t bytes=0;
    uint64_t tree_positions_count=0, tree_positions_bytes=0;
    std::string source_sha256;
};
struct GroundBoundsUpdate {
    uint32_t index, tree_offset_plus1=0, tree_count=0, pad=0;
    std::array<float,4> sphere;
};
class GroundBoundsUpdater {
    wi::graphics::GPUBuffer instances[wi::graphics::GraphicsDevice::GetBufferCount()];
    wi::graphics::GPUBuffer patches[wi::graphics::GraphicsDevice::GetBufferCount()];
    int structured_views[wi::graphics::GraphicsDevice::GetBufferCount()]{};
    wi::graphics::Shader shader;
  public:
    void apply(wi::scene::Scene& scene,const std::vector<GroundBoundsUpdate>& values) {
        using namespace wi::graphics;
        if(values.empty())return;
        auto device=GetDevice();const auto frame=scene.cpu_gpu_mapped_resource_index;
        const auto& source=scene.instanceBuffer[frame].IsValid()?scene.instanceBuffer[frame]:scene.instanceUploadBuffer[frame];
        auto& output=instances[frame];auto& input=patches[frame];bool fresh=false;
        if(!shader.IsValid()&&!wi::renderer::LoadShader(ShaderStage::CS,shader,"bvrGroundBoundsCS.cso"))throw std::runtime_error("Cannot compile source grove instance bounds update");
        if(output.desc.size<source.desc.size){
            GPUBufferDesc desc=source.desc;desc.usage=Usage::DEFAULT;desc.bind_flags=BindFlag::SHADER_RESOURCE|BindFlag::UNORDERED_ACCESS;
            desc.misc_flags=ResourceMiscFlag::BUFFER_RAW;desc.stride=0;
            if(!device->CreateBuffer(&desc,nullptr,&output))throw std::runtime_error("Cannot allocate source grove draw instances");
            // The shader reads this as the engine's structured instance type.
            // Keep a structured SRV and a raw UAV on the same buffer.
            const uint32_t stride=sizeof(ShaderMeshInstance);
            structured_views[frame]=device->CreateSubresource(&output,SubresourceType::SRV,0,~0ull,nullptr,&stride);
            fresh=true;
        }
        if(input.desc.size<values.size()*sizeof(GroundBoundsUpdate)){
            GPUBufferDesc desc;desc.size=values.size()*sizeof(GroundBoundsUpdate)*2;desc.usage=Usage::UPLOAD;
            desc.bind_flags=BindFlag::SHADER_RESOURCE;desc.misc_flags=ResourceMiscFlag::BUFFER_RAW;
            if(!device->CreateBuffer(&desc,nullptr,&input))throw std::runtime_error("Cannot allocate source grove bounds patches");
        }
        std::memcpy(input.mapped_data,values.data(),values.size()*sizeof(GroundBoundsUpdate));
        const auto cmd=device->BeginCommandList();
        device->Barrier(GPUBarrier::Buffer(&output,fresh?ResourceState::UNDEFINED:ResourceState::SHADER_RESOURCE,ResourceState::COPY_DST),cmd);
        if(source.desc.usage!=Usage::UPLOAD)device->Barrier(GPUBarrier::Buffer(&source,ResourceState::UNDEFINED,ResourceState::COPY_SRC),cmd);
        device->CopyBuffer(&output,0,&source,0,scene.instanceArraySize*sizeof(ShaderMeshInstance),cmd);
        if(source.desc.usage!=Usage::UPLOAD)device->Barrier(GPUBarrier::Buffer(&source,ResourceState::COPY_SRC,ResourceState::UNDEFINED),cmd);
        device->Barrier(GPUBarrier::Buffer(&output,ResourceState::COPY_DST,ResourceState::UNORDERED_ACCESS),cmd);
        std::array<uint32_t,8> push{uint32_t(device->GetDescriptorIndex(&input,SubresourceType::SRV)),uint32_t(device->GetDescriptorIndex(&output,SubresourceType::UAV)),uint32_t(values.size()),sizeof(ShaderMeshInstance),offsetof(ShaderMeshInstance,center),offsetof(ShaderMeshInstance,padding),0,0};
        device->BindComputeShader(&shader,cmd);device->PushConstants(push.data(),sizeof(push),cmd);device->Dispatch(uint32_t((values.size()+63)/64),1,1,cmd);
        device->Barrier(GPUBarrier::Buffer(&output,ResourceState::UNORDERED_ACCESS,ResourceState::SHADER_RESOURCE),cmd);
        scene.shaderscene.instancebuffer=device->GetDescriptorIndex(&output,SubresourceType::SRV,structured_views[frame]);
        // Do not submit/wait here. The app submits this earlier command list
        // before its render lists and synchronizes the engine's async uploads.
        // Never rewrite Scene's upload memory after its copy was submitted.
    }
};
class GroundAtlas {
    wi::graphics::Texture texture;
    wi::graphics::GPUBuffer metadata;
    wi::graphics::GPUBuffer tree_positions;
    wi::graphics::Shader height_shader, vertex_shader;
    GroundAtlasState info;
    struct Metadata {
        uint32_t texture_srv, columns, rows, pad=0;
        float north, west, spacing, pad1=0;
    };
    Metadata cpu_metadata{};
    template<class Push>
    std::vector<float> dispatch(wi::graphics::Shader& shader, const char* filename,
            const void* input_data, size_t input_bytes, size_t count, size_t output_floats, Push push) {
        using namespace wi::graphics;
        auto device=GetDevice();
        if(!shader.IsValid() && !wi::renderer::LoadShader(ShaderStage::CS,shader,filename))
            throw std::runtime_error(std::string("Cannot compile ground query: ")+filename);
        if(count==0 || count>1000000)throw std::invalid_argument("Ground query count must be 1..1000000");
        GPUBuffer input, output, readback;
        GPUBufferDesc desc;desc.size=input_bytes;desc.bind_flags=BindFlag::SHADER_RESOURCE;desc.misc_flags=ResourceMiscFlag::BUFFER_RAW;
        if(!device->CreateBuffer(&desc,input_data,&input))throw std::runtime_error("Cannot upload ground queries");
        desc.size=count*output_floats*sizeof(float);desc.bind_flags=BindFlag::UNORDERED_ACCESS;
        if(!device->CreateBuffer(&desc,nullptr,&output))throw std::runtime_error("Cannot allocate ground query output");
        desc.usage=Usage::READBACK;desc.bind_flags=BindFlag::NONE;desc.misc_flags=ResourceMiscFlag::NONE;
        if(!device->CreateBuffer(&desc,nullptr,&readback))throw std::runtime_error("Cannot allocate ground readback");
        push[0]=device->GetDescriptorIndex(&input,SubresourceType::SRV);
        push[1]=device->GetDescriptorIndex(&output,SubresourceType::UAV);push[2]=uint32_t(count);
        const auto cmd=device->BeginCommandList();
        device->Barrier(GPUBarrier::Buffer(&output,ResourceState::UNDEFINED,ResourceState::UNORDERED_ACCESS),cmd);
        device->BindComputeShader(&shader,cmd);device->PushConstants(push.data(),sizeof(push),cmd);
        device->Dispatch(uint32_t((count+63)/64),1,1,cmd);
        device->Barrier(GPUBarrier::Buffer(&output,ResourceState::UNORDERED_ACCESS,ResourceState::COPY_SRC),cmd);
        device->CopyResource(&readback,&output,cmd);device->SubmitCommandLists();device->WaitForGPU();
        std::vector<float> result(count*output_floats);std::memcpy(result.data(),readback.mapped_data,result.size()*sizeof(float));
        return result;
    }
  public:
    bool valid() const {return texture.IsValid()&&metadata.IsValid();}
    GroundAtlasState state() const {return info;}
    uint32_t metadata_srv() const {
        if(!valid())throw std::runtime_error("Source-tree grounding requires an uploaded terrain atlas");
        return wi::graphics::GetDevice()->GetDescriptorIndex(&metadata,wi::graphics::SubresourceType::SRV);
    }
    void upload(const float* data, uint32_t columns, uint32_t rows, float north, float west, float spacing, const std::string& source_sha256) {
        using namespace wi::graphics;
        if(columns<2||rows<2||columns>16384||rows>16384||!std::isfinite(north)||!std::isfinite(west)||!std::isfinite(spacing)||spacing<=0)
            throw std::invalid_argument("Invalid terrain atlas dimensions/grid");
        const uint64_t size=uint64_t(columns)*rows;
        for(uint64_t i=0;i<size;++i)if(!std::isfinite(data[i]))throw std::invalid_argument("Terrain atlas contains a nonfinite height");
        auto device=GetDevice();device->WaitForGPU();
        Texture next;TextureDesc desc;desc.width=columns;desc.height=rows;desc.format=Format::R32_FLOAT;desc.bind_flags=BindFlag::SHADER_RESOURCE;
        SubresourceData sub;sub.data_ptr=data;sub.row_pitch=columns*sizeof(float);sub.slice_pitch=uint32_t(size*sizeof(float));
        if(!device->CreateTexture(&desc,&sub,&next))throw std::runtime_error("Cannot upload terrain atlas");
        device->SetName(&next,"BVR shared core terrain height atlas");
        Metadata value{uint32_t(device->GetDescriptorIndex(&next,SubresourceType::SRV)),columns,rows,0,north,west,spacing,0};
        value.pad=tree_positions.IsValid()?uint32_t(device->GetDescriptorIndex(&tree_positions,SubresourceType::SRV))+1:0;
        if(metadata.IsValid()){
            // Stable metadata SRV keeps already imported shared materials valid
            // when a new immutable map replaces the atlas in this renderer.
            auto cmd=device->BeginCommandList();
            device->Barrier(GPUBarrier::Buffer(&metadata,ResourceState::SHADER_RESOURCE,ResourceState::COPY_DST),cmd);
            device->UpdateBuffer(&metadata,&value,cmd,sizeof(value));
            device->Barrier(GPUBarrier::Buffer(&metadata,ResourceState::COPY_DST,ResourceState::SHADER_RESOURCE),cmd);
            device->SubmitCommandLists();device->WaitForGPU();
        } else {
            GPUBufferDesc buffer;buffer.size=sizeof(value);buffer.bind_flags=BindFlag::SHADER_RESOURCE;buffer.misc_flags=ResourceMiscFlag::BUFFER_RAW;
            if(!device->CreateBuffer(&buffer,&value,&metadata))throw std::runtime_error("Cannot upload terrain atlas metadata");
            auto cmd=device->BeginCommandList();device->Barrier(GPUBarrier::Buffer(&metadata,ResourceState::UNDEFINED,ResourceState::SHADER_RESOURCE),cmd);
            device->SubmitCommandLists();device->WaitForGPU();
        }
        texture=std::move(next);cpu_metadata=value;
        info.columns=columns;info.rows=rows;info.origin_north=north;info.origin_west=west;info.spacing=spacing;info.bytes=size*sizeof(float);info.source_sha256=source_sha256;
    }
    void set_tree_positions(const std::vector<std::array<float,2>>& points) {
        using namespace wi::graphics;
        if(points.empty()&&!valid())return;
        metadata_srv();auto device=GetDevice();device->WaitForGPU();GPUBuffer next;
        if(!points.empty()){
            for(auto p:points)if(!std::isfinite(p[0])||!std::isfinite(p[1])||!covers(p[0],p[1]))throw std::invalid_argument("Streamed source tree lies outside ground atlas");
            GPUBufferDesc desc;desc.size=points.size()*sizeof(points[0]);desc.bind_flags=BindFlag::SHADER_RESOURCE;desc.misc_flags=ResourceMiscFlag::BUFFER_RAW;
            if(!device->CreateBuffer(&desc,points.data(),&next))throw std::runtime_error("Cannot upload independent source tree positions");
        }
        auto value=cpu_metadata;value.pad=next.IsValid()?uint32_t(device->GetDescriptorIndex(&next,SubresourceType::SRV))+1:0;
        auto cmd=device->BeginCommandList();device->Barrier(GPUBarrier::Buffer(&metadata,ResourceState::SHADER_RESOURCE,ResourceState::COPY_DST),cmd);
        device->UpdateBuffer(&metadata,&value,cmd,sizeof(value));device->Barrier(GPUBarrier::Buffer(&metadata,ResourceState::COPY_DST,ResourceState::SHADER_RESOURCE),cmd);
        device->SubmitCommandLists();device->WaitForGPU();tree_positions=std::move(next);cpu_metadata=value;
        info.tree_positions_count=points.size();info.tree_positions_bytes=points.size()*sizeof(points[0]);
    }
    wi::graphics::GPUBuffer parameters(const std::array<float,4>& range,const std::vector<std::array<float,2>>& anchors={}) const {
        using namespace wi::graphics;
        struct Params {uint32_t atlas, mode, count, pad=0;std::array<float,4> range;};
        Params value{metadata_srv(),anchors.empty()?0u:1u,uint32_t(anchors.size()),0,range};
        std::vector<uint8_t> bytes(sizeof(value)+anchors.size()*sizeof(anchors[0]));std::memcpy(bytes.data(),&value,sizeof(value));
        if(!anchors.empty())std::memcpy(bytes.data()+sizeof(value),anchors.data(),anchors.size()*sizeof(anchors[0]));
        GPUBuffer result;GPUBufferDesc desc;desc.size=bytes.size();
        desc.bind_flags=BindFlag::SHADER_RESOURCE;desc.misc_flags=ResourceMiscFlag::BUFFER_RAW;
        if(!GetDevice()->CreateBuffer(&desc,bytes.data(),&result))throw std::runtime_error("Cannot upload source-tree anchor encoding");
        return result;
    }
    bool covers(double north, double west) const {
        return valid() && north>=info.origin_north && west>=info.origin_west &&
            north<=info.origin_north+(info.columns-1)*double(info.spacing) && west<=info.origin_west+(info.rows-1)*double(info.spacing);
    }
    std::vector<float> heights(const std::vector<std::array<float,2>>& points) {
        for(auto p:points)if(!std::isfinite(p[0])||!std::isfinite(p[1])||!covers(p[0],p[1]))throw std::invalid_argument("Ground query outside atlas");
        std::array<uint32_t,4> push{0,0,0,metadata_srv()};
        return dispatch(height_shader,"bvrGroundHeightCS.cso",points.data(),points.size()*sizeof(points[0]),points.size(),1,push);
    }
    std::vector<std::array<float,20>> vertices(const wi::scene::Scene& scene, const std::vector<std::array<uint32_t,4>>& queries) {
        metadata_srv();
        if(scene.shaderscene.instancebuffer<0||scene.shaderscene.geometrybuffer<0||scene.shaderscene.materialbuffer<0)
            throw std::runtime_error("Draw a complete scene frame before querying GPU vertices");
        std::array<uint32_t,8> push{0,0,0,uint32_t(scene.shaderscene.instancebuffer),uint32_t(scene.shaderscene.geometrybuffer),uint32_t(scene.shaderscene.materialbuffer),0,0};
        auto raw=dispatch(vertex_shader,"bvrGroundVertexCS.cso",queries.data(),queries.size()*sizeof(queries[0]),queries.size(),20,push);
        std::vector<std::array<float,20>> result(queries.size());std::memcpy(result.data(),raw.data(),raw.size()*sizeof(float));return result;
    }
};
