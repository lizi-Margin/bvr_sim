"""Offline deterministic map baker: terrain, land-use, transport and rule-based instances.

Coordinates are north/west/up metres; recipes, baked data and runtime state are separate.
"""
from __future__ import annotations
import argparse,hashlib,io,json,math,random,zipfile
from pathlib import Path
import numpy as np
from shapely.geometry import Point,Polygon,LineString,box
from shapely.ops import unary_union
from shapely import contains_xy
from .content import ROOT,ASSETS,sha,write_json
from .heightfield import sample_grid

SURFACES=['grass','farmland','forest','soil','rock','pavement','water','marking']
def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def segments(points):return zip(points[:-1],points[1:])
def clip_poly(poly,normal,offset):
    result=[]
    for a,b in zip(poly,poly[1:]+poly[:1]):
        fa=a[0]*normal[0]+a[1]*normal[1]-offset;fb=b[0]*normal[0]+b[1]*normal[1]-offset
        if fa<=1e-8:result.append(a)
        if (fa<=0)!=(fb<=0):
            t=fa/(fa-fb);result.append([a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])])
    return result
def pieces(geometry):
    if geometry.is_empty:return []
    if geometry.geom_type=='Polygon':return [geometry]
    return [p for p in getattr(geometry,'geoms',[]) if p.geom_type=='Polygon' and p.area>100]
def deterministic_npz(path,arrays):
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,array in sorted(arrays.items()):
            content=io.BytesIO();np.lib.format.write_array(content,np.asarray(array),allow_pickle=False)
            member=zipfile.ZipInfo(name+'.npy',date_time=(1980,1,1,0,0,0));member.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(member,content.getvalue())
class BakedTerrain:
    def __init__(self,base,fine,base_meta,fine_meta):self.base,self.fine,self.base_meta,self.fine_meta=base,fine,base_meta,fine_meta
    def height(self,n,w):
        m=self.fine_meta
        if m['origin_north']<=n<=m['origin_north']+m['spacing']*(m['columns']-1) and m['origin_west']<=w<=m['origin_west']+m['spacing']*(m['rows']-1):return float(sample_grid(self.fine,m,n,w))
        return float(sample_grid(self.base,self.base_meta,n,w))
    def slope(self,n,w):return math.hypot(self.height(n+25,w)-self.height(n-25,w),self.height(n,w+25)-self.height(n,w-25))/50

class Baker:
    def __init__(self,recipe):
        self.r=recipe;self.rng=random.Random(recipe['seed']);self.instances=[];self.surfaces=[];self.occupied={};self.rejections={};self.serial=0
        self.water=unary_union([LineString(r['points']).buffer(r['width_m']/2,cap_style=2) for r in recipe['rivers']])
        self.banks=unary_union([LineString(r['points']).buffer(r['width_m']/2+r['bank_width_m'],cap_style=2) for r in recipe['rivers']])
        self.roads=[(r,LineString(r['points'])) for r in recipe['roads']]
        self.road_exclusion=unary_union([l.buffer(r['width_m']/2+10) for r,l in self.roads])
        self.forests={z['id']:Polygon(z['polygon']) for z in recipe['zones'] if z['type']=='forest'}
        self.industry=next(Polygon(z['polygon']) for z in recipe['zones'] if z['type']=='industrial')
        self.exclusions=[(e,box(e['center'][0]-e['size_m'][0]/2,e['center'][1]-e['size_m'][1]/2,e['center'][0]+e['size_m'][0]/2,e['center'][1]+e['size_m'][1]/2)) for e in recipe['exclusion_zones']]
        self.metadata={}
        self.imported_elevation=None
        elevation=recipe.get('geographic_import',{}).get('elevation')
        if elevation:
            if sha(elevation['file'])!=elevation['sha256']:raise ValueError('Imported DEM hash mismatch')
            self.imported_elevation=(np.load(elevation['file'],allow_pickle=False),elevation)
        for role,ids in recipe['asset_roles'].items():
            for id in ids if isinstance(ids,list) else [ids]:
                if id not in self.metadata:
                    path=ASSETS/'registered'/id/'manifest.json'
                    if not path.exists():raise FileNotFoundError('Recipe requires registered asset: '+id)
                    m=json.loads(path.read_text(encoding='utf8'))
                    if not m.get('distribution_allowed') or m['license']!='CC0-1.0':raise ValueError('Uncleared scene resource '+id)
                    for lod in m['lods']:
                        if sha(path.parent/lod['file'])!=lod['sha256']:raise ValueError('Resource hash changed: '+id)
                    self.metadata[id]=m
    def distance_river(self,n,w):
        best=np.full(np.broadcast(n,w).shape,np.inf)
        for river in self.r['rivers']:
            for a,b in segments(river['points']):
                dn=b[0]-a[0];dw=b[1]-a[1];t=np.clip(((n-a[0])*dn+(w-a[1])*dw)/(dn*dn+dw*dw),0,1)
                best=np.minimum(best,np.hypot(n-a[0]-t*dn,w-a[1]-t*dw))
        return best
    def terrain_rule(self,n,w):
        p=self.r['terrain'];d=self.distance_river(n,w)
        ridges=(.5+.5*np.sin(n/2100+.8*np.sin(w/3400)))**2
        hills=60*np.sin(n/530)*np.cos(w/750)+30*np.cos((n+w)/280)
        h=p['river_level_m']+90+p['hill_amplitude_m']*ridges*(1-np.exp(-(np.abs(w)/5500)**2))+hills
        valley=p['river_level_m']+0.0002*n+32*(np.maximum(d-105,0)/850)**1.3
        blend=np.clip((d-450)/1100,0,1);h=np.where(d<1550,valley*(1-blend)+h*blend,h)
        if self.imported_elevation is not None:
            data,meta=self.imported_elevation;h=sample_grid(data,meta,n,w)
        if self.r.get('landscape'):
            from .river_valley import height_rule
            return height_rule(self,n,w,h)
        for a in self.r['airfields']:
            c=a['center'];edge=np.maximum(np.abs(n-c[0])-2050,np.abs(w-(c[1]+650))-1400)
            t=np.clip(edge/450,0,1);t=t*t*(3-2*t)
            h=p['airport_height_m']*(1-t)+h*t
        for town in self.r['settlements']:
            distance=np.hypot(n-town['center'][0],w-town['center'][1]);t=np.clip((distance-town['radius_m']-200)/400,0,1);t=t*t*(3-2*t)
            h=town['height_m']*(1-t)+h*t
        bounds=self.industry.bounds;cn=(bounds[0]+bounds[2])/2;cw=(bounds[1]+bounds[3])/2
        edge=np.maximum(np.abs(n-cn)-(bounds[2]-bounds[0])/2-150,np.abs(w-cw)-(bounds[3]-bounds[1])/2-150);t=np.clip(edge/350,0,1);t=t*t*(3-2*t)
        h=p['industrial_height_m']*(1-t)+h*t
        return np.maximum(0,h).astype(np.float32)
    def build_terrain(self):
        extent=self.r['outer_extent_km'];bs=self.r['outer_height_spacing_m'];fs=self.r['height_spacing_m'];focus=self.r['focus_area_km']
        bm={'origin_north':-extent[0]*500,'origin_west':-extent[1]*500,'spacing':bs,'columns':int(extent[0]*1000/bs)+1,'rows':int(extent[1]*1000/bs)+1}
        fm={'origin_north':-focus[0]*500,'origin_west':-focus[1]*500,'spacing':fs,'columns':int(focus[0]*1000/fs)+1,'rows':int(focus[1]*1000/fs)+1}
        n,w=np.meshgrid(bm['origin_north']+np.arange(bm['columns'])*bs,bm['origin_west']+np.arange(bm['rows'])*bs)
        base=self.terrain_rule(n,w)
        n,w=np.meshgrid(fm['origin_north']+np.arange(fm['columns'])*fs,fm['origin_west']+np.arange(fm['rows'])*fs)
        fine=self.terrain_rule(n,w)
        # Stitch the fine boundary onto the independently generated coarse mesh, not interpolated detail.
        border=np.minimum(focus[0]*500-np.abs(n),focus[1]*500-np.abs(w));t=np.clip(border/300,0,1)
        fine=(t*fine+(1-t)*sample_grid(base,bm,n,w)).astype(np.float32)
        self.terrain=BakedTerrain(base,fine,bm,fm);return self.terrain
    def forbidden(self,n,w,category,radius=0):
        point=Point(n,w)
        if point.distance(self.water)<=radius:return 'water'
        if point.distance(self.road_exclusion)<=radius:return 'road'
        for e,poly in self.exclusions:
            rules=e['rules']
            if point.distance(poly)<=radius and (('no_vegetation' in rules and category=='vegetation') or ('no_building' in rules and category=='building') or 'no_tall_objects' in rules):return e['id']
        if category=='vegetation' and any(point.distance(Point(s['center']))<s['radius_m'] for s in self.r['settlements']):return 'settlement'
        if category=='vegetation' and self.industry.buffer(100).contains(point):return 'industry'
        return None
    def place(self,model,n,w,*,category,zone,scale=1,yaw=None,minimum=0,lod=1700,cull=35000,clearance=True):
        m=self.metadata[model];span=m['bounds_blender']['span'];radius=max(span[0],span[1])*scale*.48
        reason=self.forbidden(n,w,category,radius) if clearance else None
        key=(math.floor(n/50),math.floor(w/50));search=math.ceil((radius+55)/50)
        if not reason:
            for i in range(key[0]-search,key[0]+search+1):
                for j in range(key[1]-search,key[1]+search+1):
                    if any(math.hypot(n-x,w-y)<max(minimum,radius+r) for x,y,r in self.occupied.get((i,j),[])):reason='spacing';break
                if reason:break
        if reason:self.rejections[reason]=self.rejections.get(reason,0)+1;return False
        self.serial+=1;h=self.terrain.height(n,w)-m['bounds_blender']['min'][2]*scale
        self.instances.append({'id':f'{zone}_{self.serial:05d}','model':model,'position':[round(n,4),round(w,4),round(h,5)],'yaw':round(yaw if yaw is not None else self.rng.uniform(-math.pi,math.pi),6),'scale':round(scale,5),'category':category,'zone':zone,'chunk':f'{math.floor(n/self.r["chunk_m"])}:{math.floor(w/self.r["chunk_m"])}','lod_distance':lod,'cull_distance':cull,'collision_type':m['collision_type'],'radius_m':round(radius,3)})
        self.occupied.setdefault(key,[]).append((n,w,radius));return True
    def surface_ribbon(self,id,points,width,material,offset=.035):
        line=LineString(points);distance=np.linspace(0,line.length,max(2,int(line.length/25)+1));vertices=[];indices=[]
        for d in distance:
            point=line.interpolate(d);before=line.interpolate(max(0,d-1));after=line.interpolate(min(line.length,d+1));dn=after.x-before.x;dw=after.y-before.y;length=math.hypot(dn,dw)
            for sign in [-1,1]:
                n=point.x-sign*dw/length*width/2;w=point.y+sign*dn/length*width/2
                vertices.append([round(n,4),round(w,4),round(self.terrain.height(n,w)+offset,5)])
        for i in range(len(distance)-1):
            a=i*2;indices.extend([a,a+2,a+1,a+1,a+2,a+3])
        self.surfaces.append({'id':id,'material':material,'vertices':vertices,'indices':indices,'width_m':width,'length_m':line.length,'collision_height_offset':offset})
    def surface_rectangle(self,id,center,size,material):
        # Dense ribbons conform to the shared height field, even on a gently sloping courtyard.
        self.surface_ribbon(id,[[center[0]-size[0]/2,center[1]],[center[0]+size[0]/2,center[1]]],size[1],material,.095 if material=='marking' else .035)
    def build_airport(self):
        if self.r.get('landscape'):
            from .river_valley import build_airfield
            return build_airfield(self)
        for a in self.r['airfields']:
            n,w=a['center'];length=a['runway_length_m'];width=a['runway_width_m'];lo=n-length/2;hi=n+length/2
            self.surface_ribbon('runway_shoulder',[[lo-30,w],[hi+30,w]],width+28,'soil')
            self.surface_ribbon('runway',[[lo,w],[hi,w]],width,'pavement',.06)
            for i,d in enumerate(np.arange(lo+80,hi-80,90)):self.surface_rectangle(f'runway_center_{i}',[float(d),w],[32,1.6],'marking')
            for end in [lo+55,hi-55]:
                for lane in [-18,-12,-6,6,12,18]:self.surface_rectangle(f'threshold_{end}_{lane}',[end,w+lane],[28,2.5],'marking')
            self.surface_ribbon('taxiway',[[lo+100,w+300],[hi-100,w+300]],22,'pavement')
            for cross in [lo+180,n,hi-180]:self.surface_ribbon('taxi_link_'+str(cross),[[cross,w],[cross,w+300]],22,'pavement')
            self.surface_ribbon('apron_link',[[n,w+300],a['apron']],26,'pavement')
            self.surface_rectangle('apron',a['apron'],a['apron_size_m'],'pavement')
            self.surface_ribbon('airport_service',[[lo,w+900],[n-500,w+1150],[n+200,w+1150]],8,'pavement')
            for i in range(a['hangars']):self.place(self.r['asset_roles']['hangar'],n-650+i*310,w+1450,category='building',zone='airport_hangars',yaw=math.pi/2,clearance=False)
            self.place(self.r['asset_roles']['utility'],n+850,w+1350,category='building',zone='airport_utility',clearance=False)
            self.place(self.r['asset_roles']['airport_admin'],n+630,w+1350,category='building',zone='airport_administration',yaw=math.pi/2,clearance=False)
            for i in range(4):self.place(self.r['asset_roles']['supply'],n-1400+i*55,w+1300,category='building',zone='airport_supply',clearance=False)
            for i in range(10):self.place(self.r['asset_roles']['equipment'],n-700+i*60,w+1190,category='prop',zone='airport_equipment',clearance=False)
            for i in range(12):self.place(self.r['asset_roles']['apron_equipment'],n-500+i*65,w+1050,category='prop',zone='apron_equipment',minimum=4,clearance=False)
            for side in [-1,1]:
                for d in np.arange(lo-200,hi+200,80):self.place(self.r['asset_roles']['fence'],float(d),w+side*560,category='prop',zone='airport_fence',yaw=0,minimum=5,clearance=False)
    def build_settlements(self):
        for settlement in self.r['settlements']:
            road=next(l for r,l in self.roads if r['id']==settlement['road']);center=Point(settlement['center']);start=road.project(center)
            count=0
            for attempt in range(settlement['houses']*30):
                d=min(max(10,start+self.rng.uniform(-settlement['radius_m'],settlement['radius_m'])),road.length-10)
                p=road.interpolate(d);a=road.interpolate(d-2);b=road.interpolate(d+2);dn=b.x-a.x;dw=b.y-a.y;l=math.hypot(dn,dw);side=self.rng.choice([-1,1]);offset=self.rng.uniform(32,130)
                n=p.x-dw/l*offset*side;w=p.y+dn/l*offset*side
                if self.terrain.slope(n,w)>.25:continue
                if self.place(self.rng.choice(self.r['asset_roles']['residential']),n,w,category='building',zone=settlement['id'],scale=self.rng.uniform(.85,1.12),yaw=math.atan2(dw,dn)+side*math.pi/2,minimum=14):count+=1
                if count==settlement['houses']:break
            if count<settlement['houses']*.8:raise RuntimeError('Settlement could not meet recipe density: '+settlement['id'])
            for distance in np.arange(max(10,start-settlement['radius_m']),min(road.length-10,start+settlement['radius_m']),100):
                p=road.interpolate(distance);a=road.interpolate(distance-1);b=road.interpolate(distance+1);dn=b.x-a.x;dw=b.y-a.y;l=math.hypot(dn,dw)
                self.place(self.r['asset_roles']['lamp'],p.x-dw/l*9,p.y+dn/l*9,category='prop',zone=settlement['id']+'_street_equipment',minimum=5,clearance=bool(self.r.get('landscape')))
    def build_industry(self):
        if self.r.get('landscape'):
            from .river_valley import build_industry
            return build_industry(self)
        n0,w0,n1,w1=self.industry.bounds
        target=self.r['mission']['target'];self.place(self.r['asset_roles']['target'],*target,category='building',zone='mission_objective',minimum=0,clearance=False)
        for i in range(7):
            for j in range(4):self.place(self.rng.choice(self.r['asset_roles']['warehouse']),n0+250+i*(n1-n0-500)/6,w0+350+j*(w1-w0-700)/3,category='building',zone='industry',yaw=0,minimum=20)
        for i in range(8):self.place(self.r['asset_roles']['supply'],n0+450+i*(n1-n0-850)/7,w1-220,category='building',zone='industry_supply',minimum=10)
        for i in range(14):self.place(self.r['asset_roles']['equipment'],n0+250+i*(n1-n0-700)/13,w0+150,category='prop',zone='industry_equipment',minimum=8)
        self.place(self.r['asset_roles']['utility'],n1-300,w1-400,category='building',zone='communications_station',minimum=10)
        for w in [w0-100,w1+100]:
            for n in np.arange(n0-60,n1+100,80):self.place(self.r['asset_roles']['fence'],float(n),w,category='prop',zone='industrial_fence',yaw=0,clearance=False)
        for n in [n0-100,n1+100]:
            for w in np.arange(w0-60,w1+100,80):self.place(self.r['asset_roles']['fence'],n,float(w),category='prop',zone='industrial_fence',yaw=math.pi/2,clearance=False)
    def build_fields(self):
        exclusions=[self.water.buffer(160),self.road_exclusion,*self.forests.values(),self.industry.buffer(100)]
        exclusions.extend(poly for _,poly in self.exclusions)
        exclusions.extend(Point(s['center']).buffer(s['radius_m']) for s in self.r['settlements'])
        farm=box(-9800,-9800,9800,9800).difference(unary_union(exclusions))
        field_spacing=self.r.get('field_spacing_m',1600)
        seeds=[[n+self.rng.uniform(-350,350),w+self.rng.uniform(-350,350)] for n in range(-8800,8801,field_spacing) for w in range(-8800,8801,field_spacing)]
        fields=[]
        for index,a in enumerate(seeds):
            poly=[[-10000,-10000],[10000,-10000],[10000,10000],[-10000,10000]]
            for b in seeds:
                if a is b:continue
                normal=[b[0]-a[0],b[1]-a[1]];poly=clip_poly(poly,normal,(b[0]**2+b[1]**2-a[0]**2-a[1]**2)/2)
                if not poly:break
            for piece in pieces(Polygon(poly).intersection(farm)):
                if piece.area>20000:fields.append({'id':f'field_{index:03d}_{len(fields)}','polygon':list(map(list,piece.exterior.coords)),'holes':[list(map(list,r.coords)) for r in piece.interiors],'color':self.rng.choice(self.r.get('field_palette_linear',[[.78,.72,.38,1],[.53,.62,.28,1],[.7,.5,.24,1],[.62,.65,.31,1]])),'area_m2':piece.area})
        if self.r.get('landscape'):
            from .river_valley import subdivide_fields
            fields=subdivide_fields(self,fields)
        self.fields=fields;return fields
    def build_scatter(self):
        role=self.r['asset_roles']
        for rule in self.r['scatter_rules']:
            count=0;cluster=None;cluster_steps=0;shapes=[self.forests[x] for x in rule.get('zones',[])]
            for attempt in range(rule['count']*80):
                if rule.get('bank_only'):
                    river=self.rng.choice(self.r['rivers']);line=LineString(river['points']).intersection(box(-9800,-9800,9800,9800));d=self.rng.uniform(1,line.length-1);p=line.interpolate(d);a=line.interpolate(d-1);b=line.interpolate(d+1);dn=b.x-a.x;dw=b.y-a.y;l=math.hypot(dn,dw);side=self.rng.choice([-1,1]);off=self.rng.uniform(river['width_m']/2+15,river['width_m']/2+river['bank_width_m'])
                    n=p.x-dw/l*off*side;w=p.y+dn/l*off*side
                elif rule.get('field_edges'):
                    f=self.rng.choice(self.fields);line=Polygon(f['polygon']).exterior;p=line.interpolate(self.rng.uniform(0,line.length));n,w=p.x,p.y
                elif shapes:
                    if cluster is None or cluster_steps>=rule.get('cluster_size',34):
                        poly=self.rng.choice(shapes);bounds=poly.bounds
                        for _ in range(200):
                            center=(self.rng.uniform(bounds[0],bounds[2]),self.rng.uniform(bounds[1],bounds[3]))
                            if poly.contains(Point(center)):break
                        cluster=(poly,center);cluster_steps=0
                    poly,center=cluster;cluster_steps+=1
                    n=self.rng.gauss(center[0],rule.get('cluster_radius_m',100)/3);w=self.rng.gauss(center[1],rule.get('cluster_radius_m',100)/3)
                    if not poly.contains(Point(n,w)):continue
                else:
                    n=self.rng.uniform(-9500,9500);w=self.rng.uniform(-9500,9500)
                    if self.terrain.slope(n,w)<rule.get('slope_min',0):continue
                if self.terrain.slope(n,w)>.65:continue
                if self.place(self.rng.choice(role[rule['roles']]),n,w,category='prop' if rule['roles']=='rocks' else 'vegetation',zone=rule['id'],scale=self.rng.uniform(*rule['scale_range']),minimum=rule['min_spacing_m'],lod=rule['lod_distance_m'],cull=rule['cull_distance_m']):count+=1
                if count>=rule['count']:break
            if count<rule['count']*.9:raise RuntimeError('Scatter could not meet requested density: '+rule['id']+' '+str(count))
    def landcover(self):
        m=self.terrain.fine_meta;s=m['spacing'];n,w=np.meshgrid(m['origin_north']+(np.arange(m['columns']-1)+.5)*s,m['origin_west']+(np.arange(m['rows']-1)+.5)*s)
        labels=np.zeros(n.shape,dtype=np.uint8);colors=np.ones((*n.shape,4),dtype=np.float32)
        for index,f in enumerate(self.fields):
            mask=contains_xy(Polygon(f['polygon'],f['holes']),n,w);labels[mask]=0 if f.get('surface')=='grass' else 1;colors[mask]=f['color']
        for poly in self.forests.values():labels[contains_xy(poly,n,w)]=2
        height=sample_grid(self.terrain.fine,m,n,w);slope=np.hypot(np.gradient(height,s,axis=0),np.gradient(height,s,axis=1))
        labels[(slope>.3)&(labels!=2)]=4
        labels[contains_xy(self.industry,n,w)]=3
        if not self.r.get('landscape'):
            for r,line in self.roads:labels[contains_xy(line.buffer(r['width_m']/2),n,w)]=5
            labels[contains_xy(self.water,n,w)]=6
        # The focus boundary is a resolution transition, not a rectangular biome.
        # Coarse regional land-use continues past it and provides the seam labels.
        bm=self.terrain.base_meta;bs=bm['spacing']
        bn,bw=np.meshgrid(bm['origin_north']+(np.arange(bm['columns']-1)+.5)*bs,bm['origin_west']+(np.arange(bm['rows']-1)+.5)*bs)
        region=np.sin(bn/11000)*np.cos(bw/17000)+.3*np.sin((bn+bw)/4000)
        outer=np.zeros(bn.shape,dtype=np.uint8)
        outer_colors=np.ones((*outer.shape,4),dtype=np.float32)
        outer_colors[...,0]=.83+.10*region;outer_colors[...,1]=.86+.06*region;outer_colors[...,2]=.67+.10*region
        row=np.clip(((w-bm['origin_west'])/bs).astype(int),0,bm['rows']-2);col=np.clip(((n-bm['origin_north'])/bs).astype(int),0,bm['columns']-2)
        border=np.minimum(self.r['focus_area_km'][0]*500-np.abs(n),self.r['focus_area_km'][1]*500-np.abs(w))
        width=4500+1200*np.sin(n/1100)*np.cos(w/1200)
        transition=(border<width)&~np.isin(labels,[5,6])
        # Fade detailed land-use into the regional macro palette over several
        # kilometres. The former ~1 km strip looked like a hard square at altitude.
        t=np.clip(border/width,0,1);t=t*t*(3-2*t)
        blended=outer_colors[row,col]+(colors-outer_colors[row,col])*t[...,None]
        labels[transition]=outer[row,col][transition];colors[transition]=blended[transition]
        self.outer_landcover,self.outer_colors=outer,outer_colors
        return labels,colors
    def bake(self,out):
        out=Path(out);out.mkdir(parents=True,exist_ok=True);terrain=self.build_terrain();self.build_airport();self.build_settlements();self.build_industry();self.build_fields()
        for r,line in self.roads:
            if self.r.get('landscape'):self.surface_ribbon(r['id']+'_shoulder',r['points'],r['width_m']+3,'soil',.015)
            self.surface_ribbon(r['id'],r['points'],r['width_m'],'pavement')
        for river in self.r['rivers']:self.surface_ribbon(river['id'],river['points'],river['width_m'],'water',.025)
        self.build_scatter();labels,colors=self.landcover();terrain_file=out/'terrain.npz'
        deterministic_npz(terrain_file,{'base':terrain.base,'focus':terrain.fine,'landcover':labels,'macro_color':colors,'outer_landcover':self.outer_landcover,'outer_macro_color':self.outer_colors})
        chunks={}
        for o in self.instances:chunks.setdefault(o['chunk'],[]).append(o['id'])
        counts={k:sum(o['category']==k for o in self.instances) for k in ['vegetation','building','prop']}
        for k,key in [('vegetation','vegetation_instances'),('building','building_instances'),('prop','prop_instances')]:
            if counts[k]>self.r['budgets'][key]:raise ValueError('Scene exceeds '+key)
        materials={}
        for name,m in self.r['materials'].items():
            entry=dict(m)
            if m['provider']=='ambientcg':
                folder=ASSETS/'cache/ambientcg'/m['id'];provider=json.loads((folder/'manifest.json').read_text(encoding='utf8'))
                for slot,pattern in [('base_color','*Color.jpg'),('normal','*NormalDX.jpg'),('roughness_map','*Roughness.jpg')]:
                    files=list((folder/'unpacked').glob(pattern))
                    if len(files)!=1:raise FileNotFoundError('Missing/ambiguous material '+m['id']+':'+slot)
                    entry[slot]=str(files[0].resolve());entry[slot+'_sha256']=sha(files[0])
                entry['license']=provider['license'];entry['source_url']=provider['source_url']
            else:entry['license']='GPL-3.0-or-later';entry['source_url']='authored:game/recipes/training_range_v2.json'
            materials[name]=entry
        target=self.r['mission']['target'];mission=dict(self.r['mission']);mission['target']=[*target,round(terrain.height(*target),5)]
        result={'schema_version':2,'name':self.r['name'],'seed':self.r['seed'],'recipe_sha256':hashlib.sha256(canonical(self.r)).hexdigest(),'coordinates':{'units':'meters','source':'north,west,up','wicked':'-west,up,north','origin_lla':self.r['geographic_import']['origin_lla']},'terrain':{'version':2,'file':terrain_file.name,'sha256':sha(terrain_file),'base':terrain.base_meta,'details':[terrain.fine_meta],'cell_diagonal':'lower-left to upper-right in NWU grid; same triangle planes everywhere'},'focus_area_km':self.r['focus_area_km'],'materials':materials,'instances':self.instances,'surfaces':self.surfaces,'fields':self.fields,'zones':self.r['zones'],'roads':self.r['roads'],'rivers':self.r['rivers'],'airfields':self.r['airfields'],'settlements':self.r['settlements'],'exclusion_zones':self.r['exclusion_zones'],'chunks':chunks,'chunk_m':self.r['chunk_m'],'budgets':self.r['budgets'],'counts':counts,'placement_rejections':self.rejections,'mission':mission,'resource_versions':{id:{'sha256':m['glb_sha256'],'lods':m['lods']} for id,m in self.metadata.items()},'geographic_import':self.r['geographic_import']}
        if self.r.get('detail_sample'):
            from .detail_bake import refine
            result=refine(self,result,out)
        if self.r.get('landscape'):
            from .river_valley import finish_world
            from .detail_bake import _bake_material
            arrays=dict(np.load(out/'terrain.npz',allow_pickle=False))
            regional={**self.r['detail_sample'],'size_m':[x*1000 for x in self.r['focus_area_km']],
                'texture_resolution':self.r['landscape']['macro_resolution'],'seam_blend_m':self.r['landscape']['regional_transition_m'],
                'material_detail_strength':.03}
            _bake_material(result,arrays,result['terrain']['details'][0],regional,out,self,material_id='regional_1',prefix='regional')
            result['terrain']['details'][0]['material']='regional_1'
            # Fine-patch edges sample the actual parent macro material, rather
            # than the old 25m landcover approximation that made a rectangle.
            _bake_material(result,arrays,result['terrain']['details'][1],self.r['detail_sample'],out,self)
            result=finish_world(self,result,out)
        write_json(out/'scene-recipe.json',self.r);write_json(out/'generated-map.json',result)
        return {'map':str(out/'generated-map.json'),'terrain_sha256':result['terrain']['sha256'],'generated_map_sha256':sha(out/'generated-map.json'),'instances':len(self.instances),'counts':counts,'chunks':len(chunks),'fields':len(self.fields),'focus_spacing':terrain.fine_meta['spacing']}
def main():
    p=argparse.ArgumentParser();p.add_argument('--recipe',type=Path,default=ROOT/'game/recipes/training_range_v2.json');p.add_argument('--output',type=Path,default=ROOT/'game/maps/training_range_v2');a=p.parse_args()
    print(json.dumps(Baker(json.loads(a.recipe.read_text(encoding='utf8'))).bake(a.output),indent=2))
if __name__=='__main__':main()
