"""Landscape rules extending the existing Baker; no separate resource pipeline."""
import math
import numpy as np
from shapely.geometry import Point,Polygon

def smooth(x):
    t=np.clip(x,0,1);return t*t*(3-2*t)

def channel_profile(baker,n,w):
    """Offline channel earthwork, shared by every generated height resolution."""
    cfg=baker.r['landscape'].get('river_channel')
    if not cfg:return np.zeros(np.broadcast(n,w).shape)
    depth=float(cfg['depth_m']);bank=float(cfg['bank_width_m']);rim=float(cfg['bank_height_m'])
    if not (1<=depth<=15 and 10<=bank<=100 and 0<=rim<=3):raise ValueError('Invalid authored river channel dimensions')
    # A single connected river reach has one declared width. Multiple reaches
    # with differing widths need their own cross sections rather than silently
    # applying the width of an unrelated river to the nearest centreline.
    widths={float(r['width_m']) for r in baker.r['rivers']}
    if len(widths)!=1:raise ValueError('Channel recipe requires a common river width')
    half=next(iter(widths))/2;d=baker.distance_river(n,w)
    bed=-depth*smooth((half-d)/(half*.55))
    shoulder=rim*smooth((d-half*.65)/(half*.35))*(1-smooth((d-half)/bank))
    return bed+shoulder

def height_rule(baker,n,w,outer):
    r=baker.r;cfg=r['landscape'];d=baker.distance_river(n,w)
    h=r['terrain']['river_level_m']+cfg['valley_base_rise_m']*(1-np.exp(-(d/cfg['valley_scale_m'])**2))
    sides=1-np.exp(-(np.maximum(d-cfg['ridge_start_m'],0)/cfg['ridge_scale_m'])**2)
    ridge=(.6+.4*np.sin(n/2600+.5*np.sin(w/2100)))
    h+=cfg['ridge_amplitude_m']*sides*ridge
    h+=cfg['undulation_m']*(np.sin(n/730)*np.cos(w/1100)+.3*np.sin((n+w)/350))*smooth((d-120)/600)
    if cfg.get('river_channel'):h+=channel_profile(baker,n,w)
    # Only the actual runway, taxiway and apron have graded earthworks. Towns
    # and industry follow the valley instead of sitting on rectangular mesas.
    for a in r['airfields']:
        cn,cw=a['center'];half=a['runway_length_m']/2
        pads=[(cn,cw,half+35,a['runway_width_m']/2+12),
              (cn,cw+a['taxi_offset_m'],half-80,18),
              (*a['apron'],a['apron_size_m'][0]/2,a['apron_size_m'][1]/2)]
        for pn,pw,hn,hw in pads:
            edge=np.maximum(np.abs(n-pn)-hn,np.abs(w-pw)-hw)
            t=smooth(edge/cfg['earthwork_blend_m'])
            h=r['terrain']['airport_height_m']*(1-t)+h*t
    # Preserve existing BVR outer coverage exactly outside the declared focus.
    halfn,halfw=(k*500 for k in r['focus_area_km'])
    border=np.minimum(halfn-np.abs(n),halfw-np.abs(w))
    blend=smooth(border/cfg['regional_transition_m'])
    return np.maximum(0,h*blend+outer*(1-blend)).astype(np.float32)

def build_airfield(baker):
    for a in baker.r['airfields']:
        n,w=a['center'];lo=n-a['runway_length_m']/2;hi=n+a['runway_length_m']/2;taxi=w+a['taxi_offset_m']
        baker.surface_ribbon('runway_shoulder',[[lo-20,w],[hi+20,w]],a['runway_width_m']+16,'soil',.02)
        if not a.get('ground_layout'):baker.surface_ribbon('runway',[[lo,w],[hi,w]],a['runway_width_m'],'pavement',.06)
        for i,d in enumerate(np.arange(lo+90,hi-90,100)):baker.surface_rectangle(f'runway_center_{i}',[float(d),w],[30,1.5],'marking')
        for end in [lo+55,hi-55]:
            for lane in [-16,-10,-4,4,10,16]:baker.surface_rectangle(f'threshold_{end}_{lane}',[end,w+lane],[28,2.5],'marking')
        if not a.get('ground_layout'):
            baker.surface_ribbon('taxiway',[[lo+130,taxi],[hi-130,taxi]],22,'pavement',.06)
            for i,cross in enumerate([lo+160,n,hi-160]):baker.surface_ribbon('taxi_link_'+str(i),[[cross,w],[cross,taxi]],22,'pavement',.06)
        plans=None
        if a.get('ground_layout'):
            from .airport_layout import build_courts
            plans=build_courts(baker,a)
        else:
            baker.surface_ribbon('apron_link',[[a['apron'][0],taxi],a['apron']],24,'pavement',.06)
            baker.surface_rectangle('apron',a['apron'],a['apron_size_m'],'pavement')
        for i in range(a['hangars']):
            model=baker.r['asset_roles']['warehouse'][i%len(baker.r['asset_roles']['warehouse'])]
            position=plans[i]['position'] if plans else [a['apron'][0]-a['apron_size_m'][0]*.4+i*a['apron_size_m'][0]*.8/max(1,a['hangars']-1),a['apron'][1]+a['apron_size_m'][1]/2+50]
            baker.place(model,*position,category='building',zone='airport_hangars',yaw=plans[i]['yaw'] if plans else math.pi,scale=1.15,clearance=False)
        for role,dn,dw,zone in [('utility',920,360,'airport_tower'),('airport_admin',970,550,'airport_administration'),('supply',-800,660,'airport_fuel')]:
            baker.place(baker.r['asset_roles'][role],n+dn,w+dw,category='building',zone=zone,yaw=math.pi/2,clearance=False)
        if plans:
            from .airport_layout import equipment_plans
            equipment=equipment_plans(a)
        else:equipment=[[a['apron'][0]-400+i*65,a['apron'][1]-170] for i in range(12)]
        for point in equipment:baker.place(baker.r['asset_roles']['apron_equipment'],*point,category='prop',zone='apron_equipment',minimum=4,clearance=False)

def build_industry(baker):
    target=baker.r['mission']['target'];baker.place(baker.r['asset_roles']['target'],*target,category='building',zone='mission_objective',clearance=False)
    service=[l for r,l in baker.roads if r['id'].startswith('industrial_')]
    count=0
    for attempt in range(3000):
        line=baker.rng.choice(service);d=baker.rng.uniform(20,line.length-20);p=line.interpolate(d)
        a=line.interpolate(d-2);b=line.interpolate(d+2);dn=b.x-a.x;dw=b.y-a.y;length=math.hypot(dn,dw)
        side=baker.rng.choice([-1,1]);offset=baker.rng.uniform(35,100)
        n=p.x-dw/length*side*offset;w=p.y+dn/length*side*offset
        if not baker.industry.contains(Point(n,w)) or baker.terrain.slope(n,w)>.06:continue
        if baker.place(baker.rng.choice(baker.r['asset_roles']['warehouse']),n,w,category='building',zone='industry',
                       yaw=math.atan2(dw,dn)+side*math.pi/2+baker.rng.uniform(-.04,.04),scale=baker.rng.uniform(.9,1.2),minimum=18):count+=1
        if count>=28:break
    if count<20:raise RuntimeError('Functional industrial road frontage could not meet its footprint budget')
    for i in range(8):
        n=target[0]+baker.rng.uniform(-160,160);w=target[1]+baker.rng.uniform(-150,150)
        baker.place(baker.r['asset_roles']['supply'],n,w,category='building',zone='industry_supply',minimum=12)

def subdivide_fields(baker,fields):
    if baker.r['landscape'].get('field_layout')=='warped_merged_parcels':
        return agricultural_parcels(baker,fields)
    from shapely.ops import split
    from shapely.geometry import LineString
    result=[]
    for field in fields:
        source=Polygon(field['polygon'],field['holes']);center=source.centroid
        road=min((line for _,line in baker.roads),key=lambda line:line.distance(center))
        d=road.project(center);a=road.interpolate(max(0,d-2));b=road.interpolate(min(road.length,d+2))
        heading=math.atan2(b.y-a.y,b.x-a.x)
        parcels=[source]
        for depth in range(2 if source.area<900000 else 3):
            divided=[]
            for parcel in parcels:
                if parcel.area<60000:divided.append(parcel);continue
                c=parcel.centroid;axis=heading+(depth%2)*math.pi/2+baker.rng.uniform(-.05,.05)
                offset=baker.rng.uniform(-.12,.12)*math.sqrt(parcel.area)
                cn=c.x-math.sin(axis)*offset;cw=c.y+math.cos(axis)*offset
                cutter=LineString([(cn-math.cos(axis)*30000,cw-math.sin(axis)*30000),(cn+math.cos(axis)*30000,cw+math.sin(axis)*30000)])
                divided.extend(p for p in split(parcel,cutter).geoms if p.area>1000)
            parcels=divided
        for parcel in parcels:
            cover=baker.rng.choice([1.,1.,.95,.8,.65,.4,.05])
            result.append({'id':field['id']+'_parcel_'+str(len(result)),'polygon':list(map(list,parcel.exterior.coords)),
                'holes':[list(map(list,h.coords)) for h in parcel.interiors],
                'surface':'grass' if cover==1 else 'farmland','crop_cover':cover,
                'color':baker.rng.choice(baker.r['field_palette_linear']),'heading_rad':heading,'area_m2':parcel.area})
    return result

def agricultural_parcels(baker,fields):
    """Authored rural parcel topology, sharing warped block edges and T junctions.

    The union retains the existing road, river, forest and town exclusions. A
    private seeded RNG prevents layout choices changing other map generators.
    """
    import random
    from shapely.ops import unary_union
    from .worldgen import pieces
    rng=random.Random(baker.r['seed']^0x4649454c)
    farm=unary_union([Polygon(f['polygon'],f['holes']) for f in fields])
    def axis():
        values=[-18000.]
        while values[-1]<18000:values.append(values[-1]+rng.uniform(280,780))
        return values
    us,vs=axis(),axis();angle=.22;c,s=math.cos(angle),math.sin(angle)
    def warp(u,v):
        return [u*c-v*s+140*math.sin(v/1400)+80*math.sin(u/2400),
                u*s+v*c+120*math.sin(u/1800)]
    cells={}
    for j in range(len(vs)-1):
        for i in range(len(us)-1):
            poly=Polygon([warp(us[i],vs[j]),warp(us[i+1],vs[j]),warp(us[i+1],vs[j+1]),warp(us[i],vs[j+1])])
            if poly.intersects(farm):cells[i,j]=poly
    used=set();result=[]
    for (i,j),cell in cells.items():
        if (i,j) in used:continue
        di,dj=rng.choice([(1,1),(1,1),(2,1),(1,2),(2,2)])
        keys=[(i+x,j+y) for x in range(di) for y in range(dj)]
        if any(k not in cells or k in used for k in keys):keys=[(i,j)]
        used.update(keys);region=unary_union([cells[k] for k in keys]).intersection(farm)
        for parcel in pieces(region):
            if parcel.area<5000:continue
            n,w=parcel.centroid.x,parcel.centroid.y;draw=rng.random()
            cover=1. if draw<.18 else (.1 if draw<.28 else np.clip(.75+.18*math.sin(n/1600+.9*math.sin(w/2000))+rng.uniform(-.12,.12),.4,.98))
            result.append({'id':'rural_parcel_'+str(len(result)),'polygon':list(map(list,parcel.exterior.coords)),
                'holes':[list(map(list,h.coords)) for h in parcel.interiors],
                'surface':'grass' if cover==1 else 'farmland','crop_cover':float(cover),
                'color':rng.choice(baker.r['field_palette_linear']),'heading_rad':angle,'area_m2':parcel.area,
                'appearance_source':'Authored crop-cover/season variation, not measured GIS or crop species'})
    return result

def building_foundation(item,manifest,height):
    """One footprint/pose calculation for full bakes and local scene edits."""
    bounds=manifest['bounds_blender'];mn,mx=bounds['min'],bounds['max'];scale=item['scale'];yaw=item['yaw']
    n,w,z=item['position'];hn=(mx[1]-mn[1])*scale/2+1.5;hw=(mx[0]-mn[0])*scale/2+1.5
    local_n=(mn[1]+mx[1])*scale/2;local_w=-(mn[0]+mx[0])*scale/2
    cn=n+local_n*math.cos(yaw)-local_w*math.sin(yaw);cw=w+local_n*math.sin(yaw)+local_w*math.cos(yaw)
    footprint=[[cn+dn*math.cos(yaw)-dw*math.sin(yaw),cw+dn*math.sin(yaw)+dw*math.cos(yaw)] for dn,dw in [(-hn,-hw),(hn,-hw),(hn,hw),(-hn,hw)]]
    heights=[height(*v) for v in footprint];deck=max(heights)+.05
    vertices=[[*v,deck] for v in footprint]+[[*v,h] for v,h in zip(footprint,heights)]
    indices=[0,1,2,0,2,3]
    for i in range(4):j=(i+1)%4;indices.extend([i,j,j+4,i,j+4,i+4])
    foundation={'id':'foundation_'+item['id'],'material':'pavement','vertices':vertices,'indices':indices,'drivable':True,'authored':'local footprint earthwork from registered source bounds'}
    item['position'][2]=round(deck-mn[2]*scale,6)
    obstacle={'id':item['id'],'center':[cn,cw,item['position'][2]+(mn[2]+mx[2])*scale/2],
        'half_size':[(mx[1]-mn[1])*scale/2,(mx[0]-mn[0])*scale/2,(mx[2]-mn[2])*scale/2],'yaw':yaw,'approximation':'registered source oriented bounds'}
    return foundation,obstacle


def finish_world(baker,document,out):
    # Individual footprint foundations, not landscape-wide flattening. The same
    # triangles/boxes feed rendering and the core environment.
    from pathlib import Path
    from .heightfield import sample_grid
    arrays=dict(np.load(Path(out)/document['terrain']['file'],allow_pickle=False));obstacles=[]
    def height(n,w):
        for meta in reversed(document['terrain']['details']):
            if meta['origin_north']<=n<=meta['origin_north']+meta['spacing']*(meta['columns']-1) and meta['origin_west']<=w<=meta['origin_west']+meta['spacing']*(meta['rows']-1):
                return float(sample_grid(arrays[meta.get('array_key','focus')],meta,n,w))
        return baker.terrain.height(n,w)
    def heights(n,w):
        n,w=np.broadcast_arrays(n,w);result=baker.terrain.height_many(n,w)
        for meta in document['terrain']['details']:
            inside=(n>=meta['origin_north'])&(n<=meta['origin_north']+meta['spacing']*(meta['columns']-1))&(w>=meta['origin_west'])&(w<=meta['origin_west']+meta['spacing']*(meta['rows']-1))
            result=np.where(inside,sample_grid(arrays[meta.get('array_key','focus')],meta,n,w),result)
        return result
    accepted=[];grove_fits=[];grove_conforms=[];rejected=0
    for item in document['instances']:
        manifest=baker.metadata[item['model']]
        if manifest.get('cluster'):
            from .grove_grounding import fit_grove,conform_grove
            if manifest['cluster'].get('ground_conform'):
                conform=conform_grove(manifest,*item['position'][:2],item['yaw'],item['scale'],height,sample_heights=heights,ground_stems=item.get('ground_stems'))
                item.update(up_normal=[0,1,0],grove_ground_conform=conform);item['position'][2]=conform['height'];grove_conforms.append(conform)
            else:
                fit=fit_grove(manifest,*item['position'][:2],item['yaw'],item['scale'],height,sample_heights=heights)
                if fit is None:rejected+=1;continue
                item.update(up_normal=fit['up_normal'],grove_ground_fit=fit)
                item['position'][2]=fit['height'];grove_fits.append(fit)
        accepted.append(item)
    document['instances']=accepted
    document['chunks']={}
    for item in accepted:document['chunks'].setdefault(item['chunk'],[]).append(item['id'])
    document['counts']={k:sum(o['category']==k for o in accepted) for k in ['vegetation','building','prop']}
    if grove_fits:
        document['forest_representation']={'grove_instances':len(grove_fits),'source_tree_copies':sum(x['source_trees'] for x in grove_fits),
            'final_terrain_fit_rejections':rejected,'maximum_source_base_error_m':max(x['max_anchor_error_m'] for x in grove_fits),
            'maximum_rigid_tilt_rad':max(x['tilt_rad'] for x in grove_fits),
            'approximation':'Rigid source-tree groves aligned to local terrain plane; source base anchors within0.25m, slope <=0.2rad. Anchor method is recorded per instance; legacy sources may use bounds reference anchors. No terrain grading. Distant canopy aggregate is separately recorded in material bake.'}
    if grove_conforms:
        document['forest_representation']={**document.get('forest_representation',{}),
            'independently_grounded_groves':len(grove_conforms),'independently_grounded_source_trees':sum(x['source_trees'] for x in grove_conforms),
            'maximum_per_grove_height_span_m':max(x['source_height_span_m'] for x in grove_conforms),
            'ground_conform_approximation':'Shared upright source trees translated vertically per encoded base anchor using an aligned core terrain atlas in all raster passes. No terrain grading. GPU error/culling and natural appearance require separate runtime inspection.'}
    for item in document['instances']:
        if item['category']!='building':continue
        foundation,obstacle=building_foundation(item,baker.metadata[item['model']],height)
        document['surfaces'].append(foundation);obstacles.append(obstacle)
    contacts=[{'id':s['id'],'material':'pavement','vertices':s['vertices'],'indices':s['indices'],'drivable':True}
        for s in document['surfaces'] if s['material']=='pavement' and s.get('drivable',True)]
    water=list(baker.water.geoms) if hasattr(baker.water,'geoms') else [baker.water]
    ids={o['id'] for o in obstacles};obstacles.extend(o for o in document.get('environment',{}).get('obstacles',[]) if o['id'] not in ids)
    document['environment']={'version':2,'contact_surfaces':contacts,'obstacles':obstacles,
        'water_regions':[{'id':'river_'+str(i),'polygon':list(map(list,p.exterior.coords))} for i,p in enumerate(water)],
        'decorative_instance_ids':[x['id'] for x in document['instances'] if x['category']!='building']}
    document['landscape']=baker.r['landscape']
    return document
