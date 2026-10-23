"""Landscape rules extending the existing Baker; no separate resource pipeline."""
import math
import numpy as np
from shapely.geometry import Point,Polygon

def smooth(x):
    t=np.clip(x,0,1);return t*t*(3-2*t)

def height_rule(baker,n,w,outer):
    r=baker.r;cfg=r['landscape'];d=baker.distance_river(n,w)
    h=r['terrain']['river_level_m']+cfg['valley_base_rise_m']*(1-np.exp(-(d/cfg['valley_scale_m'])**2))
    sides=1-np.exp(-(np.maximum(d-cfg['ridge_start_m'],0)/cfg['ridge_scale_m'])**2)
    ridge=(.6+.4*np.sin(n/2600+.5*np.sin(w/2100)))
    h+=cfg['ridge_amplitude_m']*sides*ridge
    h+=cfg['undulation_m']*(np.sin(n/730)*np.cos(w/1100)+.3*np.sin((n+w)/350))*smooth((d-120)/600)
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
        baker.surface_ribbon('runway',[[lo,w],[hi,w]],a['runway_width_m'],'pavement',.06)
        for i,d in enumerate(np.arange(lo+90,hi-90,100)):baker.surface_rectangle(f'runway_center_{i}',[float(d),w],[30,1.5],'marking')
        for end in [lo+55,hi-55]:
            for lane in [-16,-10,-4,4,10,16]:baker.surface_rectangle(f'threshold_{end}_{lane}',[end,w+lane],[28,2.5],'marking')
        baker.surface_ribbon('taxiway',[[lo+130,taxi],[hi-130,taxi]],22,'pavement',.06)
        for i,cross in enumerate([lo+160,n,hi-160]):baker.surface_ribbon('taxi_link_'+str(i),[[cross,w],[cross,taxi]],22,'pavement',.06)
        baker.surface_ribbon('apron_link',[[a['apron'][0],taxi],a['apron']],24,'pavement',.06)
        baker.surface_rectangle('apron',a['apron'],a['apron_size_m'],'pavement')
        for i in range(a['hangars']):
            model=baker.r['asset_roles']['warehouse'][i%len(baker.r['asset_roles']['warehouse'])]
            baker.place(model,a['apron'][0]-a['apron_size_m'][0]*.4+i*a['apron_size_m'][0]*.8/max(1,a['hangars']-1),
                a['apron'][1]+a['apron_size_m'][1]/2+50,category='building',zone='airport_hangars',yaw=math.pi,scale=1.15,clearance=False)
        for role,dn,dw,zone in [('utility',920,360,'airport_tower'),('airport_admin',970,550,'airport_administration'),('supply',-800,660,'airport_fuel')]:
            baker.place(baker.r['asset_roles'][role],n+dn,w+dw,category='building',zone=zone,yaw=math.pi/2,clearance=False)
        for i in range(12):baker.place(baker.r['asset_roles']['apron_equipment'],a['apron'][0]-400+i*65,a['apron'][1]-170,category='prop',zone='apron_equipment',minimum=4,clearance=False)

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
            result.append({'id':field['id']+'_parcel_'+str(len(result)),'polygon':list(map(list,parcel.exterior.coords)),
                'holes':[list(map(list,h.coords)) for h in parcel.interiors],
                'surface':'grass' if baker.rng.random()<.6 else 'farmland',
                'color':baker.rng.choice(baker.r['field_palette_linear']),'heading_rad':heading,'area_m2':parcel.area})
    return result

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
    for item in document['instances']:
        if item['category']!='building':continue
        bounds=baker.metadata[item['model']]['bounds_blender'];mn,mx=bounds['min'],bounds['max'];scale=item['scale'];yaw=item['yaw']
        n,w,z=item['position'];hn=(mx[1]-mn[1])*scale/2+1.5;hw=(mx[0]-mn[0])*scale/2+1.5
        local_n=(mn[1]+mx[1])*scale/2;local_w=-(mn[0]+mx[0])*scale/2
        cn=n+local_n*math.cos(yaw)-local_w*math.sin(yaw);cw=w+local_n*math.sin(yaw)+local_w*math.cos(yaw)
        footprint=[[cn+dn*math.cos(yaw)-dw*math.sin(yaw),cw+dn*math.sin(yaw)+dw*math.cos(yaw)] for dn,dw in [(-hn,-hw),(hn,-hw),(hn,hw),(-hn,hw)]]
        heights=[height(*v) for v in footprint];deck=max(heights)+.05
        vertices=[[*v,deck] for v in footprint]+[[*v,h] for v,h in zip(footprint,heights)]
        indices=[0,1,2,0,2,3]
        for i in range(4):j=(i+1)%4;indices.extend([i,j,j+4,i,j+4,i+4])
        document['surfaces'].append({'id':'foundation_'+item['id'],'material':'pavement','vertices':vertices,'indices':indices,'drivable':True,'authored':'local footprint earthwork from registered source bounds'})
        item['position'][2]=round(deck-mn[2]*scale,6)
        obstacles.append({'id':item['id'],'center':[cn,cw,item['position'][2]+(mn[2]+mx[2])*scale/2],
            'half_size':[(mx[1]-mn[1])*scale/2,(mx[0]-mn[0])*scale/2,(mx[2]-mn[2])*scale/2],'yaw':yaw,'approximation':'registered source oriented bounds'})
    contacts=[{'id':s['id'],'material':'pavement','vertices':s['vertices'],'indices':s['indices'],'drivable':True}
        for s in document['surfaces'] if s['material']=='pavement' and s.get('drivable',True)]
    water=list(baker.water.geoms) if hasattr(baker.water,'geoms') else [baker.water]
    ids={o['id'] for o in obstacles};obstacles.extend(o for o in document.get('environment',{}).get('obstacles',[]) if o['id'] not in ids)
    document['environment']={'version':2,'contact_surfaces':contacts,'obstacles':obstacles,
        'water_regions':[{'id':'river_'+str(i),'polygon':list(map(list,p.exterior.coords))} for i,p in enumerate(water)],
        'decorative_instance_ids':[x['id'] for x in document['instances'] if x['category']!='building']}
    document['landscape']=baker.r['landscape']
    return document
