"""Offline sample-area refinement and explicit physical surfaces from scene declarations."""
from pathlib import Path
import json,math
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter
from shapely.geometry import Point,Polygon,LineString,box
from shapely import contains_xy
from .heightfield import sample_grid
from .content import sha,write_json

def _distance_line(n,w,line):
    result=np.full(np.broadcast(n,w).shape,np.inf)
    points=list(line.coords)
    for a,b in zip(points[:-1],points[1:]):
        dn,dw=b[0]-a[0],b[1]-a[1];t=np.clip(((n-a[0])*dn+(w-a[1])*dw)/(dn*dn+dw*dw),0,1)
        result=np.minimum(result,np.hypot(n-a[0]-t*dn,w-a[1]-t*dw))
    return result

def refine(baker,document,out):
    from .worldgen import deterministic_npz
    out=Path(out);r=baker.r;spec=r['detail_sample'];arrays=dict(np.load(out/'terrain.npz',allow_pickle=False))
    center=spec['center'];size=spec['size_m'];step=spec['height_spacing_m']
    if not 5<=step<=10:raise ValueError('Sample needs 5-10 m actual generated heights')
    meta={'origin_north':center[0]-size[0]/2,'origin_west':center[1]-size[1]/2,'spacing':step,
          'columns':int(size[0]/step)+1,'rows':int(size[1]/step)+1}
    n,w=np.meshgrid(meta['origin_north']+np.arange(meta['columns'])*step,meta['origin_west']+np.arange(meta['rows'])*step)
    border=np.minimum.reduce([n-meta['origin_north'],w-meta['origin_west'],meta['origin_north']+size[0]-n,meta['origin_west']+size[1]-w])
    edge=np.clip(border/spec.get('seam_blend_m',100),0,1);edge=edge*edge*(3-2*edge)
    micro=spec.get('relief_amplitude_m',3)*(np.sin(n/31)*np.cos(w/47)+.3*np.sin((n+w)/11))
    road_distance=np.full(n.shape,np.inf)
    for road,line in baker.roads:road_distance=np.minimum(road_distance,_distance_line(n,w,line)-road['width_m']/2)
    micro*=np.clip((road_distance-4)/12,0,1)
    if r.get('landscape'):
        # Preserve physical runway/taxi/apron grades in the fine tile too.
        for airfield in r['airfields']:
            cn,cw=airfield['center'];airport_edge=np.maximum(np.abs(n-cn)-airfield['runway_length_m']/2-50,np.abs(w-cw)-airfield['taxi_offset_m']-35)
            micro*=np.clip(airport_edge/30,0,1)
            cn,cw=airfield['apron'];airport_edge=np.maximum(np.abs(n-cn)-airfield['apron_size_m'][0]/2-20,np.abs(w-cw)-airfield['apron_size_m'][1]/2-20)
            micro*=np.clip(airport_edge/30,0,1)
    industry=baker.industry
    micro*=np.where(contains_xy(industry,n,w),0,1)
    # This calls the analytic terrain rules at 5m; the old grid only supplies a boundary seam.
    raw=baker.terrain_rule(n,w)+micro
    old=sample_grid(arrays['focus'],document['terrain']['details'][0],n,w)
    if not (np.all(np.isfinite(edge)) and np.all(edge>=0) and np.all(edge<=1)):
        raise ValueError('Refinement seam weights must form a convex blend in[0,1]')
    refined=(edge*raw+(1-edge)*old).astype(np.float32);arrays['sample']=refined
    detail={**meta,'array_key':'sample','material':'detail_1','generator':'analytic rules + independent metre-scale ridges/gullies; coarse interpolation only in seam band'}
    document['terrain']['details'].append(detail)
    def height(n,w):
        if meta['origin_north']<=n<=meta['origin_north']+size[0] and meta['origin_west']<=w<=meta['origin_west']+size[1]:return float(sample_grid(refined,meta,n,w))
        return baker.terrain.height(n,w)
    extra_obstacles=[]
    replacements=spec.get('building_replacements',{})
    choices=r['asset_roles'].get(replacements.get('role',''),[])
    selected=0
    for item in document['instances']:
        if choices and item['zone']==replacements.get('zone'):
            if selected%replacements.get('every_nth',3)==0:
                item['model']=choices[(selected//replacements.get('every_nth',3))%len(choices)]
                item['scale']=1
                item['radius_m']=max(baker.metadata[item['model']]['bounds_blender']['span'][:2])*.5
            selected+=1
    for i,sign in enumerate(spec.get('roadside_signs',[])):
        baker.place(r['asset_roles']['road_signs'][i%len(r['asset_roles']['road_signs'])],*sign['position'],
                    category='prop',zone='sample_sign',yaw=sign['yaw'],clearance=False)
    document['instances']=list(baker.instances)
    # Move existing scenery onto the new generated ground, retaining source model geometry.
    for item in document['instances']:
        model=baker.metadata[item['model']];x,y=item['position'][:2]
        item['position'][2]=round(height(x,y)-model['bounds_blender']['min'][2]*item['scale'],6)
    for surface in document['surfaces']:
        if surface['material']=='water':continue
        for p in surface['vertices']:
            offset=p[2]-baker.terrain.height(p[0],p[1])
            p[2]=round(height(p[0],p[1])+offset,6)
    # Choose a short clear connection to the nearest declared service road.
    services=[line for road,line in baker.roads if road['id'].startswith('industrial_')]
    footprints={o['id']:Point(*o['position'][:2]).buffer(o['radius_m']+1) for o in document['instances'] if o['category']=='building'}
    for item in document['instances']:
        if item['category']!='building' or not industry.contains(Point(*item['position'][:2])):continue
        point=Point(*item['position'][:2]);options=sorted((point.distance(line),i,line.interpolate(line.project(point))) for i,line in enumerate(services))
        candidate=next(((d,p) for d,_,p in options if not any(LineString([point,p]).intersects(poly) for id,poly in footprints.items() if id!=item['id'])),None)
        if candidate is None:continue
        distance,nearest=candidate
        if distance<20 or distance>spec.get('entrance_max_distance_m',110):continue
        model=baker.metadata[item['model']];span=model['bounds_blender']['span'];yaw=math.atan2(nearest.y-point.y,nearest.x-point.x);item['yaw']=yaw
        reach=span[1]*item['scale']/2+1
        entrance=[point.x+math.cos(yaw)*reach,point.y+math.sin(yaw)*reach]
        vertices=[]
        for station in np.linspace(0,1,max(2,int((distance-reach)/5)+1)):
            n0=nearest.x+(entrance[0]-nearest.x)*station;w0=nearest.y+(entrance[1]-nearest.y)*station
            for sign in [-1,1]:
                x=n0-sign*math.sin(yaw)*2.75;y=w0+sign*math.cos(yaw)*2.75;vertices.append([x,y,height(x,y)+.045])
        indices=[]
        for i in range(len(vertices)//2-1):a=i*2;indices.extend([a,a+1,a+2,a+1,a+3,a+2])
        document['surfaces'].append({'id':item['id']+'_entrance','material':'pavement','vertices':vertices,'indices':indices,'width_m':5.5,'core_contact':True})
    # Gate geometry and collision agree: remove entire source fence sections crossing declared entrances.
    gates=[Point(*g['center']).buffer(g['clearance_m']) for g in r.get('gates',[])]
    removed=[];kept=[]
    for item in document['instances']:
        if item['model']=='fence' and any(g.distance(Point(*item['position'][:2]))<item['radius_m'] for g in gates):removed.append(item['id'])
        else:kept.append(item)
    document['instances']=kept

    # Bridge declarations create an elevated deck and approaches without modifying the riverbed.
    for bridge in r.get('bridges',[]):
        road=next(road for road in r['roads'] if road['id']==bridge['road']);line=LineString(road['points'])
        station=line.project(Point(bridge['center']));length=bridge['length_m'];width=bridge['width_m']
        distances=np.linspace(station-length/2,station+length/2,int(length/5)+1);vertices=[]
        ends=[line.interpolate(distances[0]),line.interpolate(distances[-1])]
        end_heights=[height(p.x,p.y)+.06 for p in ends];deck=bridge['deck_height_m'];ramp=bridge['ramp_length_m']
        for d in distances:
            p=line.interpolate(d);a=line.interpolate(d-1);b=line.interpolate(d+1);dn,dw=b.x-a.x,b.y-a.y;l=math.hypot(dn,dw)
            along=d-distances[0];z=deck
            if along<ramp:z=end_heights[0]+(deck-end_heights[0])*along/ramp
            elif along>length-ramp:z=deck+(end_heights[1]-deck)*(along-(length-ramp))/ramp
            for sign in [-1,1]:vertices.append([p.x-sign*dw/l*width/2,p.y+sign*dn/l*width/2,z])
        indices=[]
        for i in range(len(distances)-1):a=i*2;indices.extend([a,a+2,a+1,a+1,a+2,a+3])
        footprint=LineString([[p.x,p.y] for p in ends]).buffer(width/2+1)
        for surface in document['surfaces']:
            if surface['material']!='pavement':continue
            kept=[]
            for i in range(0,len(surface['indices']),3):
                tri=surface['indices'][i:i+3];mid=np.mean([surface['vertices'][j][:2] for j in tri],axis=0)
                if not footprint.contains(Point(*mid)) and not baker.water.contains(Point(*mid)):kept.extend(tri)
            surface['indices']=kept
        document['surfaces'].append({'id':bridge['id'],'material':'pavement','vertices':vertices,'indices':indices,'drivable':True,'core_contact':True,'bridge':True})
        for side in [0,1]:
            segment=[vertices[i+side] for i in range(0,len(vertices),2)]
            a=segment[int(ramp/5)];b=segment[-int(ramp/5)-1];dn,dw=b[0]-a[0],b[1]-a[1];l=math.hypot(dn,dw)
            rail={'id':bridge['id']+'_rail_'+str(side),'center':[(a[0]+b[0])/2,(a[1]+b[1])/2,deck+.55],
                  'half_size':[l/2,.06,.55],'yaw':math.atan2(dw,dn),'approximation':'bridge guard rail box'}
            extra_obstacles.append(rail)
            document['surfaces'].append({'id':rail['id'],'material':'marking','vertices':[[a[0],a[1],deck+.25],[b[0],b[1],deck+.25],[a[0],a[1],deck+1],[b[0],b[1],deck+1]],'indices':[0,1,2,1,3,2,2,1,0,2,3,1],'drivable':False})
        # A real separate lower structure makes the raised deck legible above the river.
        def structural_box(id,center,half,yaw):
            vertices=[]
            for z in [-1,1]:
                for x,y in [(-1,-1),(1,-1),(1,1),(-1,1)]:
                    dn=x*half[0];dw=y*half[1]
                    vertices.append([center[0]+dn*math.cos(yaw)-dw*math.sin(yaw),center[1]+dn*math.sin(yaw)+dw*math.cos(yaw),center[2]+z*half[2]])
            indices=[0,2,1,0,3,2,4,5,6,4,6,7,0,1,5,0,5,4,1,2,6,1,6,5,2,3,7,2,7,6,3,0,4,3,4,7]
            document['surfaces'].append({'id':id,'material':'pavement','vertices':vertices,'indices':indices,'drivable':False,'core_contact':False})
        mid=line.interpolate(station);a=line.interpolate(station-1);b=line.interpolate(station+1);yaw=math.atan2(b.y-a.y,b.x-a.x)
        structural_box(bridge['id']+'_soffit',[mid.x,mid.y,deck-.65],[(length-2*ramp)/2,width/2,.65],yaw)
        for i,offset in enumerate([-65,65]):
            p=line.interpolate(station+offset);bottom=height(p.x,p.y);half_h=(deck-1.3-bottom)/2
            if half_h>0:
                center=[p.x,p.y,bottom+half_h];half=[1.5,width*.38,half_h]
                structural_box(bridge['id']+'_pier_'+str(i),center,half,yaw)
                extra_obstacles.append({'id':bridge['id']+'_pier_'+str(i),'center':center,'half_size':half,'yaw':yaw,'approximation':'authored structural pier box'})

    # Core environment uses the same surface triangles as rendering, plus marked solid footprints.
    contacts=[]
    for surface in document['surfaces']:
        if surface['material']=='pavement' and surface['indices'] and surface.get('drivable',True):
            contacts.append({'id':surface['id'],'material':'pavement','vertices':surface['vertices'],'indices':surface['indices'],'drivable':True})
    obstacles=[];decorative=[]
    for item in document['instances']:
        n0,w0,z0=item['position'];model=baker.metadata[item['model']];bounds=model['bounds_blender'];scale=item['scale'];angle=item['yaw']
        if item['category']!='building' and item['model']!='fence':decorative.append(item['id']);continue
        mn,mx=bounds['min'],bounds['max'];local_n=(mn[1]+mx[1])*scale/2;local_w=-(mn[0]+mx[0])*scale/2
        center=[n0+local_n*math.cos(angle)-local_w*math.sin(angle),w0+local_n*math.sin(angle)+local_w*math.cos(angle),z0+(mn[2]+mx[2])*scale/2]
        half=[(mx[1]-mn[1])*scale/2,(mx[0]-mn[0])*scale/2,(mx[2]-mn[2])*scale/2]
        obstacles.append({'id':item['id'],'center':center,'half_size':half,'yaw':angle,'approximation':'source-model oriented bounding box; not per-triangle building collision'})
    waters=[]
    polys=list(baker.water.geoms) if hasattr(baker.water,'geoms') else [baker.water]
    for i,p in enumerate(polys):waters.append({'id':'water_'+str(i),'polygon':list(map(list,p.exterior.coords))})
    document['environment']={'version':1,'contact_surfaces':contacts,'obstacles':obstacles+extra_obstacles,'water_regions':waters,'decorative_instance_ids':decorative}
    document['detail_sample']={**spec,'terrain':detail,'raw_refinement_difference_rms_m':float(np.sqrt(np.mean((raw-old)**2))),
                              'collision_model':'Explicit core surface triangles, oriented bounding boxes, and water polygons; terrain remains an independent lower layer'}
    document['detail_sample']['removed_gate_fence_sections']=removed
    document['chunks']={}
    for item in document['instances']:document['chunks'].setdefault(item['chunk'],[]).append(item['id'])
    document['counts']={k:sum(o['category']==k for o in document['instances']) for k in ['vegetation','building','prop']}
    target=document['mission']['target'];target[2]=height(*target[:2])
    if 'convoy_target' in document['mission']:
        target=document['mission']['convoy_target'];document['mission']['convoy_target']=[*target[:2],height(*target[:2])]
    _bake_material(document,arrays,meta,spec,out,baker)
    deterministic_npz(out/'terrain.npz',arrays);document['terrain']['sha256']=sha(out/'terrain.npz')
    document['terrain']['version']=3
    return document

def _bake_material(document,arrays,meta,spec,out,baker,*,material_id='detail_1',prefix='sample'):
    resolution=int(spec.get('texture_resolution',2048));extent=spec['size_m'];pixel=extent[0]/resolution
    n,w=np.meshgrid(meta['origin_north']+(np.arange(resolution)+.5)*pixel,
                    meta['origin_west']+(np.arange(resolution)+.5)*extent[1]/resolution)
    labels=np.zeros(n.shape,dtype=np.uint8);macro=np.ones((*n.shape,3),dtype=np.float32)
    for field in document['fields']:
        poly=Polygon(field['polygon'],field['holes']);a,b,c,d=poly.bounds
        x0=max(0,int((a-meta['origin_north'])/pixel)-1);x1=min(resolution,int((c-meta['origin_north'])/pixel)+2)
        y0=max(0,int((b-meta['origin_west'])/pixel)-1);y1=min(resolution,int((d-meta['origin_west'])/pixel)+2)
        if x0>=x1 or y0>=y1:continue
        area=np.s_[y0:y1,x0:x1];mask=contains_xy(poly,n[area],w[area]);labels[area][mask]=0 if field.get('surface')=='grass' else 1;macro[area][mask]=field['color'][:3]
    for forest in baker.forests.values():labels[contains_xy(forest,n,w)]=2
    labels[contains_xy(baker.industry,n,w)]=3
    for road,line in baker.roads:
        shoulder=_distance_line(n,w,line)<road['width_m']/2+3;labels[shoulder]=3
    names=['grass','farmland','forest','soil','rock','pavement','water','marking']
    color=np.zeros((*n.shape,3),dtype=np.float32);normal=np.zeros_like(color);rough=np.zeros(n.shape,dtype=np.float32)
    source_files={}
    for index in np.unique(labels):
        material=document['materials'][names[int(index)]]
        weight=gaussian_filter((labels==index).astype(np.float32),sigma=spec.get('material_blend_m',7)/pixel,mode='nearest')
        for slot in ['base_color','normal','roughness_map']:
            if slot not in material:continue
            file=material[slot];source_files[file]=sha(file)
            image=np.asarray(Image.open(file).convert('RGB'),dtype=np.float32)/255
            if slot=='base_color':image=np.where(image<=.04045,image/12.92,((image+.055)/1.055)**2.4)
            # Slow deterministic UV warping breaks the grid while retaining actual source PBR detail.
            u=((n/4+.15*np.sin(w/61))*image.shape[1]).astype(np.int64)%image.shape[1]
            v=((w/4+.15*np.cos(n/73))*image.shape[0]).astype(np.int64)%image.shape[0]
            sample=image[v,u]
            if slot=='base_color':
                strength=spec.get('material_detail_strength',.5)
                sample=sample*strength+image.mean(axis=(0,1))*(1-strength)
            if slot=='base_color':color+=weight[...,None]*sample*np.array(material['color'][:3],dtype=np.float32)*macro
            elif slot=='normal':normal+=weight[...,None]*(sample*2-1)
            else:rough+=weight*sample[...,0]
    # Match the actual surrounding 50m mesh materials in a smooth boundary band.
    # Its per-cell biome and interpolated macro tint remain unchanged outside the sample.
    parent=document['terrain']['details'][0];cover=arrays['landcover']
    ci=np.clip(((n-parent['origin_north'])/parent['spacing']).astype(int),0,cover.shape[1]-1)
    ri=np.clip(((w-parent['origin_west'])/parent['spacing']).astype(int),0,cover.shape[0]-1)
    coarse_labels=cover[ri,ci]
    cm={**parent,'columns':cover.shape[1],'rows':cover.shape[0],
        'origin_north':parent['origin_north']+parent['spacing']/2,'origin_west':parent['origin_west']+parent['spacing']/2}
    tint=np.stack([sample_grid(arrays['macro_color'][...,i],cm,n,w) for i in range(3)],axis=2)
    boundary=np.minimum.reduce([n-meta['origin_north'],w-meta['origin_west'],meta['origin_north']+extent[0]-n,meta['origin_west']+extent[1]-w])
    fade=np.clip(boundary/spec.get('seam_blend_m',100),0,1);fade=fade*fade*(3-2*fade)
    parent_material=document['materials'].get(parent.get('material','')) if material_id=='detail_1' else None
    if parent_material:
        from scipy.ndimage import map_coordinates
        for slot in ['base_color','normal','roughness_map']:
            file=parent_material[slot];source_files[file]=sha(file)
            image=np.asarray(Image.open(file).convert('RGB'),dtype=np.float32)/255
            if slot=='base_color':image=np.where(image<=.04045,image/12.92,((image+.055)/1.055)**2.4)
            u=(n-parent['origin_north'])/(parent['spacing']*(parent['columns']-1))*image.shape[1]-.5
            v=(w-parent['origin_west'])/(parent['spacing']*(parent['rows']-1))*image.shape[0]-.5
            sample=np.stack([map_coordinates(image[...,i],[v,u],order=1,mode='nearest') for i in range(3)],axis=2)
            if slot=='base_color':color=color*fade[...,None]+sample*(1-fade[...,None])
            elif slot=='normal':normal=normal*fade[...,None]+(sample*2-1)*(1-fade[...,None])
            else:rough=rough*fade+sample[...,0]*(1-fade)
    for index in ([] if parent_material else np.unique(coarse_labels)):
        m=document['materials'][names[int(index)]];weight=(coarse_labels==index)*(1-fade)
        for slot in ['base_color','normal','roughness_map']:
            if slot not in m:continue
            image=np.asarray(Image.open(m[slot]).convert('RGB'),dtype=np.float32)/255
            if slot=='base_color':image=np.where(image<=.04045,image/12.92,((image+.055)/1.055)**2.4)
            u=(np.mod(n/m['tile_m'],1)*image.shape[1]).astype(int)%image.shape[1]
            v=(np.mod(w/m['tile_m'],1)*image.shape[0]).astype(int)%image.shape[0]
            sample=image[v,u]
            if slot=='base_color':
                if index==np.unique(coarse_labels)[0]:color*=fade[...,None]
                color+=weight[...,None]*sample*tint*np.array(m['color'][:3])
            elif slot=='normal':
                if index==np.unique(coarse_labels)[0]:normal*=fade[...,None]
                normal+=weight[...,None]*(sample*2-1)
            else:
                if index==np.unique(coarse_labels)[0]:rough*=fade
                rough+=weight*sample[...,0]
    normal/=np.maximum(np.linalg.norm(normal,axis=2,keepdims=True),1e-5)
    paths={}
    color=np.where(color<=.0031308,color*12.92,1.055*np.maximum(color,0)**(1/2.4)-.055)
    for name,data in [('color',color),('normal',normal*.5+.5),('roughness',rough)]:
        path=out/(prefix+'_'+name+'.png');Image.fromarray(np.clip(data*255,0,255).astype(np.uint8)).save(path);paths[name]=path
    document['materials'][material_id]={'provider':'offline PBR blend','id':prefix+'_linear_pbr_blend','tile_m':extent[0],
        'color':[1,1,1,1],'roughness':.92,'base_color':str(paths['color'].resolve()),'base_color_sha256':sha(paths['color']),
        'normal':str(paths['normal'].resolve()),'normal_sha256':sha(paths['normal']),
        'roughness_map':str(paths['roughness'].resolve()),'roughness_map_sha256':sha(paths['roughness']),
        'license':'CC0 source PBR textures; authored bake recipe follows project license','source_url':'derived:ambientCG sources recorded below','source_files':source_files}
    document['materials'][material_id]['repeat_detail']=True
    report=document['detail_sample'] if material_id=='detail_1' else document.setdefault('regional_surface',{})
    report['material_bake']={'resolution':[resolution,resolution],'pixel_m':pixel,'blend_m':spec.get('material_blend_m',7),'source_textures':source_files,
        'generator':'analytic land-use masks + linear-light source sampling/blending + sRGB color encoding; normals/roughness stay linear'}
