"""Declared airport courts, tessellated on the existing shared terrain triangles."""
import copy,math
import numpy as np
from shapely.geometry import Polygon,LineString,box
from shapely.ops import unary_union
from shapely import constrained_delaunay_triangles
from .heightfield import sample_grid


def court_recipe():
    return {'version':1,'mesh_spacing_m':5.,'taxi_width_m':28.,'shoulder_width_m':1.,
        'spine_offsets_m':[[-490,-75],[-450,-105],[460,-105],[515,-60]],
        'hangar_offsets_m':[[-420,160],[-250,175],[-60,157],[100,170],[275,155],[460,165]],
        'hangar_yaw_rad':math.pi/2,'court_widths_m':[116,100,120,104,112,100],
        'court_front_offset_m':-10.,'corner_bevel_m':10.,
        'service_offsets_m':[[-1140,285],[550,285],[690,190],[800,0]],'service_width_m':7.,
        'authored':'Generic dispersed maintenance courts using registered warehouse geometry; not a surveyed airport or a certified taxi/parking layout'}


def taxi_marking_material():
    return {'provider':'authored','color':[.95,.68,.08,1.],'roughness':.8,'tile_m':3.,'license':'GPL-3.0-or-later',
        'source_url':'authored:declared airport taxi/stand guides; not certified airport markings'}


class SharedHeightView:
    """Sample the frozen archive in the same tile precedence/diagonal as core."""
    def __init__(self,scene):self.scene=scene
    def height_many(self,n,w):
        n,w=np.broadcast_arrays(n,w);d=self.scene.document['terrain'];a=self.scene.arrays
        result=sample_grid(a['base'],d['base'],n,w)
        for meta in d['details']:
            inside=(n>=meta['origin_north'])&(n<=meta['origin_north']+meta['spacing']*(meta['columns']-1))&(w>=meta['origin_west'])&(w<=meta['origin_west']+meta['spacing']*(meta['rows']-1))
            result=np.where(inside,sample_grid(a[meta.get('array_key','focus')],meta,n,w),result)
        return result
    def height(self,n,w):return float(self.height_many(n,w))


def polygon_surface(id,polygon,height,material,step=5.,offset=.035):
    """Clip each shared-diagonal grid triangle, including holes and concavities.

    For the declared airport, all source tile origins/spacings align to5m.
    No long diagonal may bridge a terrain crease or a grass island.
    """
    if polygon.is_empty or not polygon.is_valid or not 1<=step<=10:raise ValueError('Invalid airport surface/grid')
    vertices=[];indices=[];lookup={};n0,w0,n1,w1=polygon.bounds
    for n in np.arange(math.floor(n0/step)*step,n1,step):
        for w in np.arange(math.floor(w0/step)*step,w1,step):
            cell=box(n,w,n+step,w+step)
            if not polygon.intersects(cell):continue
            for corners in [[(n,w),(n+step,w),(n,w+step)],[(n+step,w+step),(n,w+step),(n+step,w)]]:
                section=polygon.intersection(Polygon(corners))
                if section.is_empty or section.area<1e-9:continue
                # Constrained edges are essential: filtering an unconstrained
                # Delaunay result can leave gaps at concave service-road bends.
                for triangle in constrained_delaunay_triangles(section).geoms:
                    if triangle.area<1e-9:continue
                    xy=list(triangle.exterior.coords)[:3]
                    if (xy[1][0]-xy[0][0])*(xy[2][1]-xy[0][1])-(xy[1][1]-xy[0][1])*(xy[2][0]-xy[0][0])<0:xy.reverse()
                    for p in xy:
                        key=tuple(round(float(x),7) for x in p)
                        if key not in lookup:lookup[key]=len(vertices);vertices.append(key)
                        indices.append(lookup[key])
    xy=np.asarray(vertices);tri=xy[np.asarray(indices).reshape(-1,3)];a=tri[:,1]-tri[:,0];b=tri[:,2]-tri[:,0]
    mesh_area=float(np.sum((a[:,0]*b[:,1]-a[:,1]*b[:,0])/2))
    if abs(mesh_area-polygon.area)>.001:raise ValueError(f'Airport tessellation lost plan area: {id}: {mesh_area-polygon.area}m2')
    z=height.height_many(xy[:,0],xy[:,1])+offset
    return {'id':id,'material':material,'vertices':np.column_stack([xy,z]).tolist(),'indices':indices,
        'drivable':material=='pavement','collision_height_offset':offset,'mesh_spacing_m':step,
        'plan_area_m2':polygon.area,'authored':'Clipped shared terrain triangles; no heightfield grading'}


def build_courts(baker,airfield):
    baker.r['materials']['airport_taxi_marking']=taxi_marking_material()
    c=airfield['ground_layout'];origin=np.asarray(airfield['apron'],dtype=float)
    if c['version']!=1 or airfield.get('heading_deg',0)!=0:raise ValueError('Airport court layout currently requires north-aligned airfield version1')
    if len(c['hangar_offsets_m'])!=airfield['hangars'] or len(c['court_widths_m'])!=airfield['hangars']:raise ValueError('Airport court/hangar counts differ')
    step=float(c['mesh_spacing_m'])
    if step!=5:raise ValueError('Airport courts require the frozen5m shared terrain grid')
    spine=LineString(origin+np.asarray(c['spine_offsets_m']));pieces=[spine.buffer(c['taxi_width_m']/2,cap_style=1,join_style=1)]
    taxi=airfield['center'][1]+airfield['taxi_offset_m'];join_n=airfield['apron'][0]
    apron_join=LineString([[join_n,taxi],[join_n-20,origin[1]-190],[join_n,origin[1]-105]])
    pieces.append(apron_join.buffer(12,cap_style=1,join_style=1))
    runway_n,runway_w=airfield['center'];lo=runway_n-airfield['runway_length_m']/2;hi=runway_n+airfield['runway_length_m']/2
    # Retain the existing runway/taxi footprints, but tessellate them on the
    # shared grid too: a long ribbon chord can otherwise disappear into relief.
    pieces.extend([box(lo,runway_w-airfield['runway_width_m']/2,hi,runway_w+airfield['runway_width_m']/2),
        box(lo+130,taxi-11,hi-130,taxi+11)])
    for cross in [lo+160,runway_n,hi-160]:pieces.append(box(cross-11,runway_w,cross+11,taxi))
    plans=[];guides=[spine,apron_join]
    for i,(offset,width) in enumerate(zip(c['hangar_offsets_m'],c['court_widths_m'])):
        n,w=origin+offset;front=origin[1]+c['court_front_offset_m']
        model=baker.r['asset_roles']['warehouse'][i%len(baker.r['asset_roles']['warehouse'])]
        bounds=baker.metadata[model]['bounds_blender']
        back=w-(bounds['max'][1]-bounds['min'][1])*1.15/2+3.
        bevel=c['corner_bevel_m'];left=n-width/2;right=n+width/2
        if width<=2*bevel or back-front<=2*bevel:raise ValueError('Invalid beveled airport court')
        court=Polygon([(left+bevel,front),(right-bevel,front),(right,front+bevel),(right,back-bevel),(right-bevel,back),(left+bevel,back),(left,back-bevel),(left,front+bevel)])
        branch=LineString([[n,origin[1]-105],[n,back-20]])
        pieces.extend([court,branch.buffer(11,cap_style=1,join_style=1)]);guides.append(branch)
        plans.append({'position':[float(n),float(w)],'yaw':round(c['hangar_yaw_rad'],6)})
    service=LineString(origin+np.asarray(c['service_offsets_m']))
    service_lines=[service,LineString(origin+np.asarray([[800,0],[650,-45],[515,-60]]))]
    for plan in plans:
        n,w=plan['position'];service_lines.append(LineString([[n,origin[1]+285],[n,w+15]]))
    # The existing fuel, administration and tower positions remain explicit
    # functional destinations; the service road ends at the public road node.
    n,w=airfield['center']
    service_lines.extend([LineString([[n-800,origin[1]+285],[n-800,w+660]]),
        LineString([[origin[0]+690,origin[1]+190],[n+970,w+550],[n+970,w+360],[n+920,w+360]])])
    pieces.extend(line.buffer(c['service_width_m']/2,cap_style=1,join_style=1) for line in service_lines)
    paved=unary_union(pieces)
    if paved.geom_type!='Polygon':raise ValueError('Airport pavement must be one connected network')
    shoulder=paved.buffer(c['shoulder_width_m'],join_style=1).difference(paved)
    baker.surfaces.append(polygon_surface('airport_courts_shoulder',shoulder,baker.terrain,'soil',step,.012))
    baker.surfaces.append(polygon_surface('airport_courts',paved,baker.terrain,'pavement',step,.06))
    paint=unary_union([line.buffer(.18,cap_style=2,join_style=1) for line in guides])
    # Parking stop bars indicate each individual forecourt rather than a huge
    # undifferentiated hardstand. Source warehouses remain generic substitutes.
    bars=[LineString([[p['position'][0]-8,p['position'][1]-40],[p['position'][0]+8,p['position'][1]-40]]).buffer(.2,cap_style=2) for p in plans]
    paint=unary_union([paint,*bars]).intersection(paved)
    baker.surfaces.append(polygon_surface('airport_courts_guides',paint,baker.terrain,'airport_taxi_marking',step,.085))
    return plans


def equipment_plans(airfield):
    c=airfield['ground_layout'];n0,w0=airfield['apron'];result=[]
    for (dn,_),width in zip(c['hangar_offsets_m'],c['court_widths_m']):
        for side in [-1,1]:result.append([n0+dn+side*(width/2-15),w0+c['court_front_offset_m']+8])
    return result


def rebuild_airport(recipe,source,document):
    """Edit airport pavement, warehouse poses/bounds and forecourt equipment."""
    from .worldgen import Baker
    from .river_valley import building_foundation
    baker=Baker(recipe);baker.terrain=SharedHeightView(source)
    for meta in [document['terrain']['base'],*document['terrain']['details']]:
        if meta['spacing']%5 or meta['origin_north']%5 or meta['origin_west']%5:raise ValueError('Source terrain is not aligned with the airport grid')
    if len(recipe['airfields'])!=1:raise ValueError('Airport rebuild currently supports one declared airfield')
    airfield=recipe['airfields'][0];plans=build_courts(baker,airfield)
    items=[i for i in document['instances'] if i.get('zone')=='airport_hangars']
    if len(items)!=len(plans):raise ValueError('Source airport/hangar count differs')
    ids={i['id'] for i in items};removed={'runway','taxiway','taxi_link_0','taxi_link_1','taxi_link_2','apron','apron_link','airport_courts','airport_courts_shoulder','airport_courts_guides'}|{'foundation_'+id for id in ids}
    document['surfaces']=[s for s in document['surfaces'] if s['id'] not in removed]
    document['environment']['obstacles']=[o for o in document['environment']['obstacles'] if o['id'] not in ids]
    for item,plan in zip(items,plans):
        item['position'][:2]=plan['position'];item['yaw']=plan['yaw']
        item['chunk']=f'{math.floor(item["position"][0]/recipe["chunk_m"])}:{math.floor(item["position"][1]/recipe["chunk_m"])}'
        foundation,obstacle=building_foundation(item,baker.metadata[item['model']],baker.terrain.height)
        document['surfaces'].append(foundation);document['environment']['obstacles'].append(obstacle)
    equipment=[i for i in document['instances'] if i.get('zone')=='apron_equipment']
    points=equipment_plans(airfield)
    if len(equipment)!=len(points):raise ValueError('Source airport equipment count differs')
    for item,point in zip(equipment,points):
        item['position']=[*point,round(baker.terrain.height(*point)-baker.metadata[item['model']]['bounds_blender']['min'][2]*item['scale'],6)]
        item['chunk']=f'{math.floor(point[0]/recipe["chunk_m"])}:{math.floor(point[1]/recipe["chunk_m"])}'
    document['surfaces'].extend(baker.surfaces)
    document['environment']['contact_surfaces']=[{'id':s['id'],'material':'pavement','vertices':s['vertices'],'indices':s['indices'],'drivable':True} for s in document['surfaces'] if s['material']=='pavement' and s.get('drivable',True)]
    document['chunks']={}
    for item in document['instances']:document['chunks'].setdefault(item['chunk'],[]).append(item['id'])
    document['airfields']=copy.deepcopy(recipe['airfields'])
    paint=taxi_marking_material()
    recipe['materials']['airport_taxi_marking']=paint;document['materials']['airport_taxi_marking']=copy.deepcopy(paint)
    return document
