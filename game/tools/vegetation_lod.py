"""Blender helper for the existing environment registration pipeline.

Source-derived albedo impostors, not AI imagery or replacement plant geometry.
"""
import bpy,math,struct,json,random,shutil
from mathutils import Vector,Matrix

def make_cluster(objects,spec,source_base_override=None,source_bounds_override=None):
    """Seeded source copies; no generated botanical geometry or global RNG."""
    count=int(spec['count']);radius=float(spec['radius_m']);minimum=float(spec['minimum_spacing_m'])
    if not 2<=count<=64 or not 0<minimum<radius<100:raise ValueError('Invalid vegetation cluster policy')
    rng=random.Random(int(spec['seed']));positions=[]
    for _ in range(count*1000):
        angle=rng.uniform(-math.pi,math.pi);distance=radius*math.sqrt(rng.random());p=(math.cos(angle)*distance,math.sin(angle)*distance)
        if any(math.dist(p,q)<minimum for q in positions):continue
        positions.append(p)
        if len(positions)==count:break
    if len(positions)!=count:raise ValueError('Cluster could not fit source copies at its declared spacing')
    # Locate the selected source's actual lowest geometry, rather than assuming
    # the normalized bounding-box XY centre is the stem base.
    if source_base_override is None:
        points=[o.matrix_world@v.co for o in objects for v in o.data.vertices]
        base_z=min(p.z for p in points);base_points=[p for p in points if p.z<=base_z+.03]
        source_base=sum(base_points,Vector())/len(base_points)
        del points
    else:source_base=Vector(source_base_override)
    result=[];poses=[];source_corners=[]
    if source_bounds_override:
        low,high=source_bounds_override
        source_corners=[Vector((x,y,z)) for x in [low[0],high[0]] for y in [low[1],high[1]] for z in [low[2],high[2]]]
    bounded_points=[]
    for i,(x,y) in enumerate(positions):
        angle=rng.uniform(-math.pi,math.pi);scale=rng.uniform(*spec.get('scale_range',[.85,1.15]))
        base_anchor=Vector((x,y,0))+Matrix.Rotation(angle,3,'Z')@source_base*scale
        z=-base_anchor.z if spec.get('ground_conform') else 0.
        base_anchor.z+=z
        poses.append({'position':[x,y,z],'yaw':angle,'scale':scale,'base_anchor':list(base_anchor)})
        transform=Matrix.Translation(Vector((x,y,z)))@Matrix.Rotation(angle,4,'Z')@Matrix.Scale(scale,4)
        bounded_points.extend(transform@p for p in source_corners)
        for original in objects:
            o=original.copy();o.data=original.data.copy();o.name=f'{original.name}_source_copy_{i}'
            bpy.context.scene.collection.objects.link(o);o.matrix_world=transform@original.matrix_world
            if spec.get('ground_conform'):
                o['bvr_base_anchor']=list(base_anchor);o['bvr_tree_index']=i
            result.append(o)
    for o in objects:bpy.data.objects.remove(o,do_unlink=True)
    bpy.context.view_layer.update();points=bounded_points or [o.matrix_world@Vector(c) for o in result for c in o.bound_box]
    lo=[min(p[i] for p in points) for i in range(3)];hi=[max(p[i] for p in points) for i in range(3)]
    center=Vector(((lo[0]+hi[0])/2,(lo[1]+hi[1])/2,lo[2]))
    if spec.get('ground_conform'):center.z=0
    for o in result:o.location-=center
    encoding=None
    if spec.get('ground_conform'):
        anchors=[Vector(p['base_anchor'])-center for p in poses]
        minimum=[min(p[i] for p in anchors) for i in range(2)];span=[max(p[i] for p in anchors)-minimum[i] for i in range(2)]
        bpy.ops.object.select_all(action='DESELECT')
        for o in result:o.hide_set(False);o.select_set(True)
        bpy.context.view_layer.objects.active=result[0]
        bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
        tree_bounds=[{'min':[math.inf]*3,'max':[-math.inf]*3} for _ in poses]
        for o in result:
            if len(o.data.uv_layers)!=1:raise ValueError('Ground-anchor metadata requires an unused UV1')
            uv=o.data.uv_layers.new(name='BVR_BASE_ANCHOR');a=Vector(o['bvr_base_anchor'])-center
            pair=((a.x-minimum[0])/span[0],1-(a.y-minimum[1])/span[1])
            if spec.get('independent_tree_positions'):pair=((int(o['bvr_tree_index'])+.5)/count,1.)
            for loop in uv.data:loop.uv=pair
            bounds=tree_bounds[o['bvr_tree_index']]
            for vertex in o.data.vertices:
                p=vertex.co-a
                for axis in range(3):
                    bounds['min'][axis]=min(bounds['min'][axis],p[axis]);bounds['max'][axis]=max(bounds['max'][axis],p[axis])
        encoding={'method':'UV1 normalized actual tree base anchors; glTF V flip accounted for; identity mesh nodes',
                  'min_local_xz':minimum,'span_local_xz':span,'anchor_local_y':0.,'all_passes_required':True,
                  'tree_bounds_relative_blender':tree_bounds}
        if spec.get('independent_tree_positions'):
            encoding.update(anchor_encoding='source_tree_index_uv1',source_tree_count=count,
                method='UV1.x=(source_tree_index+0.5)/count, UV1.y=0 after glTF V flip. Source bases are registered separately; actual tree positions are per-instance data.')
    bounds={'min':[lo[i]-center[i] for i in range(3)],'max':[hi[i]-center[i] for i in range(3)]}
    return result,bounds,{'source_copies':count,'seed':spec['seed'],'poses_before_recentering':poses,'recentering':list(center),
        'source_base_anchor_blender':list(source_base),'base_anchor_method':'Mean of source vertices within0.03m of its lowest geometry, transformed per source copy',
        'ground_conform':encoding,
        'method':'Copies of the exact selected source tree; rigid transforms, uniform scale and offline mesh LOD simplification only'}

def triangles(objects):return sum(sum(len(p.vertices)-2 for p in o.data.polygons) for o in objects if o.type=='MESH')

def source_foliage_cards(objects,out,height,width,policy,render_engine,reuse_bake=None):
    """Keep source wood in 3D; replace fragile needle geometry with source views."""
    bpy.ops.object.select_all(action='DESELECT')
    for o in objects:
        o.hide_set(False);o.select_set(True)
    bpy.context.view_layer.objects.active=objects[0]
    bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.separate(type='MATERIAL');bpy.ops.object.mode_set(mode='OBJECT')
    parts=list(bpy.context.selected_objects);names=set(policy['materials'])
    # A source-material split may retain unused slots; use actual polygon slots.
    foliage=[o for o in parts if any(o.data.materials[p.material_index].name in names for p in o.data.polygons)]
    wood=[o for o in parts if o not in foliage]
    if not foliage or not wood:raise ValueError('Source material partition failed')
    for o in bpy.context.scene.objects:
        if o.type=='MESH':o.hide_render=True
    for o in foliage:o.hide_render=False
    out.mkdir(parents=True,exist_ok=True)
    cards,report=impostors(foliage,out,height,width,policy.get('resolution',1024),render_engine,
        normal_maps=policy.get('normal_maps',False),reuse_bake=reuse_bake)
    for o in foliage:bpy.data.objects.remove(o,do_unlink=True)
    before=triangles(wood);reduce_meshes(wood,int(policy.get('wood_triangles_per_tree',2000)))
    return wood+cards,{'source_materials':sorted(names),'source_wood_triangles':before,'retained_wood_triangles':triangles(wood),
        'foliage_card_triangles_per_tree':triangles(cards),'bake':report,
        'method':'Source woody geometry with mesh LOD; individual-tree crossed source-albedo/opacity foliage views. Explicit visual approximation, no invented botanical shape. Full source grove is separately baked for far LOD.'}
def reduce_meshes(objects,budget):
    total=triangles(objects)
    if total<=budget:return
    for o in objects:
        if o.type!='MESH':continue
        bpy.context.view_layer.objects.active=o
        mod=o.modifiers.new('source_distance_LOD','DECIMATE');mod.ratio=min(1,budget/total)
        bpy.ops.object.modifier_apply(modifier=mod.name)

def alpha_mask_glb(path):
    data=path.read_bytes();length=struct.unpack_from('<I',data,12)[0];doc=json.loads(data[20:20+length])
    for m in doc.get('materials',[]):m['alphaMode']='MASK';m['alphaCutoff']=.4;m['doubleSided']=True
    encoded=json.dumps(doc,separators=(',',':')).encode();encoded+=b' '*((-len(encoded))%4)
    rest=data[20+length:];path.write_bytes(struct.pack('<III',0x46546c67,2,20+len(encoded)+len(rest))+struct.pack('<II',len(encoded),0x4e4f534a)+encoded+rest)

def impostors(objects,out,height,width,resolution=512,render_engine='BLENDER_EEVEE',*,normal_maps=False,reuse_bake=None):
    if render_engine not in ['BLENDER_EEVEE','CYCLES']:raise ValueError('Unsupported source-albedo bake engine')
    out.mkdir(parents=True,exist_ok=True)
    scene=bpy.context.scene;scene.render.engine=render_engine;scene.render.film_transparent=True
    if render_engine=='CYCLES':scene.cycles.device='CPU';scene.cycles.samples=8;scene.cycles.use_denoising=False
    scene.render.resolution_x=scene.render.resolution_y=resolution;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA'
    scene.view_settings.view_transform='Standard';scene.view_settings.look='None';scene.view_settings.exposure=0;scene.view_settings.gamma=1
    # Render source albedo with its original opacity. Lighting is applied again
    # by the game; the bake does not freeze a studio light or shadow into it.
    restored={};copies={}
    for o in objects:
        if o.type!='MESH':continue
        restored[o]=list(o.data.materials)
        for i,original in enumerate(restored[o]):
            if original not in copies:
                m=original.copy();nodes=m.node_tree.nodes;links=m.node_tree.links
                bsdf=next(n for n in nodes if n.type=='BSDF_PRINCIPLED');output=next(n for n in nodes if n.type=='OUTPUT_MATERIAL')
                emission=nodes.new('ShaderNodeEmission');color=bsdf.inputs['Base Color'];alpha=bsdf.inputs['Alpha']
                if color.is_linked:links.new(color.links[0].from_socket,emission.inputs['Color'])
                else:emission.inputs['Color'].default_value=color.default_value
                transparent=nodes.new('ShaderNodeBsdfTransparent');mix=nodes.new('ShaderNodeMixShader')
                links.new(transparent.outputs[0],mix.inputs[1]);links.new(emission.outputs[0],mix.inputs[2])
                if alpha.is_linked:links.new(alpha.links[0].from_socket,mix.inputs[0])
                else:mix.inputs[0].default_value=alpha.default_value
                links.new(mix.outputs[0],output.inputs['Surface']);copies[original]=m
            o.data.materials[i]=copies[original]
    camera_data=bpy.data.cameras.new('source_albedo_bake');camera=bpy.data.objects.new('source_albedo_bake',camera_data)
    scene.collection.objects.link(camera);scene.camera=camera;camera_data.type='ORTHO'
    side=max(height,width)*1.06;camera_data.ortho_scale=side;target=Vector((0,0,height/2));views=[];normal_views=[]
    for i,angle in enumerate([0,math.pi/3,2*math.pi/3,None]):
        distance=max(20,side*2)
        camera.location=Vector((0,0,height+distance)) if angle is None else Vector((math.sin(angle)*distance,-math.cos(angle)*distance,height/2))
        camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
        file=out/f'source_albedo_view_{i}.png';scene.render.filepath=str(file)
        if reuse_bake:shutil.copy2(reuse_bake['views'][i],file)
        else:bpy.ops.render.render(write_still=True)
        views.append((angle,file))
    if normal_maps:
        # Bake actual source surface normals into each card's tangent frame.
        # Emission + Raw avoids both illumination and sRGB encoding of vectors.
        # Keep the source opacity graph, including its transparent cutouts.
        normal_nodes=[]
        for m in copies.values():
            nodes=m.node_tree.nodes;links=m.node_tree.links
            emission=next(n for n in nodes if n.type=='EMISSION')
            geometry=nodes.new('ShaderNodeNewGeometry');combine=nodes.new('ShaderNodeCombineXYZ');axes=[]
            for axis in range(3):
                dot=nodes.new('ShaderNodeVectorMath');dot.operation='DOT_PRODUCT'
                links.new(geometry.outputs['Normal'],dot.inputs[0])
                encode=nodes.new('ShaderNodeMath');encode.operation='MULTIPLY_ADD';encode.inputs[1].default_value=.5;encode.inputs[2].default_value=.5
                links.new(dot.outputs['Value'],encode.inputs[0]);links.new(encode.outputs[0],combine.inputs[axis]);axes.append(dot)
            links.new(combine.outputs[0],emission.inputs['Color']);normal_nodes.append(axes)
        scene.view_settings.view_transform='Raw'
        for i,(angle,_) in enumerate(views):
            if angle is None:
                basis=[(1,0,0),(0,1,0),(0,0,1)];camera.location=(0,0,height+distance)
            else:
                basis=[(math.cos(angle),math.sin(angle),0),(0,0,1),(math.sin(angle),-math.cos(angle),0)]
                camera.location=(math.sin(angle)*distance,-math.cos(angle)*distance,height/2)
            camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
            for axes in normal_nodes:
                for node,axis in zip(axes,basis):node.inputs[1].default_value=axis
            file=out/f'source_normal_view_{i}.png';scene.render.filepath=str(file)
            if reuse_bake:shutil.copy2(reuse_bake['normal_views'][i],file)
            else:bpy.ops.render.render(write_still=True)
            normal_views.append(file)
        scene.view_settings.view_transform='Standard'
    for o,materials in restored.items():
        for i,m in enumerate(materials):o.data.materials[i]=m
        o.hide_render=True;o.select_set(False)
    bpy.data.objects.remove(camera,do_unlink=True);planes=[]
    for i,(angle,file) in enumerate(views):
        if angle is None:
            vertices=[(-side/2,-side/2,height*.6),(side/2,-side/2,height*.6),(side/2,side/2,height*.6),(-side/2,side/2,height*.6)]
        else:
            ux,uy=math.cos(angle),math.sin(angle);low=(height-side)/2;high=low+side
            vertices=[(-ux*side/2,-uy*side/2,low),(ux*side/2,uy*side/2,low),(ux*side/2,uy*side/2,high),(-ux*side/2,-uy*side/2,high)]
        mesh=bpy.data.meshes.new(f'source_impostor_{i}');mesh.from_pydata(vertices,[],[(0,1,2,3)]);mesh.uv_layers.new()
        for polygon in mesh.polygons:
            for loop,uv in zip(polygon.loop_indices,[(0,0),(1,0),(1,1),(0,1)]):mesh.uv_layers.active.data[loop].uv=uv
        material=bpy.data.materials.new(f'source_impostor_{i}');material.use_nodes=True;material.surface_render_method='DITHERED'
        bsdf=material.node_tree.nodes.get('Principled BSDF');bsdf.inputs['Roughness'].default_value=1;bsdf.inputs['Specular IOR Level'].default_value=0
        tex=material.node_tree.nodes.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(file));tex.image.pack()
        material.node_tree.links.new(tex.outputs['Color'],bsdf.inputs['Base Color']);material.node_tree.links.new(tex.outputs['Alpha'],bsdf.inputs['Alpha'])
        if normal_maps:
            normal_tex=material.node_tree.nodes.new('ShaderNodeTexImage');normal_tex.image=bpy.data.images.load(str(normal_views[i]))
            normal_tex.image.colorspace_settings.name='Non-Color';normal_tex.image.pack()
            normal=material.node_tree.nodes.new('ShaderNodeNormalMap')
            material.node_tree.links.new(normal_tex.outputs['Color'],normal.inputs['Color']);material.node_tree.links.new(normal.outputs['Normal'],bsdf.inputs['Normal'])
        mesh.materials.append(material);obj=bpy.data.objects.new(f'source_impostor_{i}',mesh);scene.collection.objects.link(obj);planes.append(obj)
    # One shared mesh/object per far tree; four independent objects would
    # multiply scene traversal/instance transforms even with only eight faces.
    bpy.ops.object.select_all(action='DESELECT')
    for o in planes:o.select_set(True)
    bpy.context.view_layer.objects.active=planes[0];bpy.ops.object.join();planes=[bpy.context.view_layer.objects.active]
    return planes,{'views':[str(file) for _,file in views],'resolution':resolution,'triangles':8,
        'normal_views':[str(file) for file in normal_views],
        'normal_basis':'Actual source geometry normals projected onto per-card tangent/bitangent/front-normal, Raw linear RGB; no baked directional lighting' if normal_maps else None,
        'render_engine':render_engine,'reused_registered_bake':reuse_bake,
        'method':'Three source-albedo vertical views and one top view, alpha-tested crossed planes. Approximate silhouette; not full source geometry or a measured BRDF.'}
