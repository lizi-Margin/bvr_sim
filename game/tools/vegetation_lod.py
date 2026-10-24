"""Blender helper for the existing environment registration pipeline.

Source-derived albedo impostors, not AI imagery or replacement plant geometry.
"""
import bpy,math,struct,json,random
from mathutils import Vector,Matrix

def make_cluster(objects,spec):
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
    result=[];poses=[]
    for i,(x,y) in enumerate(positions):
        angle=rng.uniform(-math.pi,math.pi);scale=rng.uniform(*spec.get('scale_range',[.85,1.15]));poses.append({'position':[x,y,0],'yaw':angle,'scale':scale})
        transform=Matrix.Translation(Vector((x,y,0)))@Matrix.Rotation(angle,4,'Z')@Matrix.Scale(scale,4)
        for original in objects:
            o=original.copy();o.data=original.data.copy();o.name=f'{original.name}_source_copy_{i}'
            bpy.context.scene.collection.objects.link(o);o.matrix_world=transform@original.matrix_world;result.append(o)
    for o in objects:bpy.data.objects.remove(o,do_unlink=True)
    bpy.context.view_layer.update();points=[o.matrix_world@Vector(c) for o in result for c in o.bound_box]
    lo=[min(p[i] for p in points) for i in range(3)];hi=[max(p[i] for p in points) for i in range(3)]
    center=Vector(((lo[0]+hi[0])/2,(lo[1]+hi[1])/2,lo[2]))
    for o in result:o.location-=center
    bounds={'min':[lo[i]-center[i] for i in range(3)],'max':[hi[i]-center[i] for i in range(3)]}
    return result,bounds,{'source_copies':count,'seed':spec['seed'],'poses_before_recentering':poses,'recentering':list(center),
        'method':'Copies of the exact selected source tree; rigid transforms, uniform scale and offline mesh LOD simplification only'}

def triangles(objects):return sum(sum(len(p.vertices)-2 for p in o.data.polygons) for o in objects if o.type=='MESH')
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

def impostors(objects,out,height,width,resolution=512):
    scene=bpy.context.scene;scene.render.engine='BLENDER_EEVEE';scene.render.film_transparent=True
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
    side=max(height,width)*1.06;camera_data.ortho_scale=side;target=Vector((0,0,height/2));views=[]
    for i,angle in enumerate([0,math.pi/3,2*math.pi/3,None]):
        distance=max(20,side*2)
        camera.location=Vector((0,0,height+distance)) if angle is None else Vector((math.sin(angle)*distance,-math.cos(angle)*distance,height/2))
        camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
        file=out/f'source_albedo_view_{i}.png';scene.render.filepath=str(file);bpy.ops.render.render(write_still=True)
        views.append((angle,file))
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
        mesh.materials.append(material);obj=bpy.data.objects.new(f'source_impostor_{i}',mesh);scene.collection.objects.link(obj);planes.append(obj)
    # One shared mesh/object per far tree; four independent objects would
    # multiply scene traversal/instance transforms even with only eight faces.
    bpy.ops.object.select_all(action='DESELECT')
    for o in planes:o.select_set(True)
    bpy.context.view_layer.objects.active=planes[0];bpy.ops.object.join();planes=[bpy.context.view_layer.objects.active]
    return planes,{'views':[str(file) for _,file in views],'resolution':resolution,'triangles':8,
        'method':'Three source-albedo vertical views and one top view, alpha-tested crossed planes. Approximate far silhouette and flat shading; not full source geometry or a measured BRDF.'}
