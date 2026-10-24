"""Load baked content only. No downloads, source-folder scans or Blender at runtime."""
import json,hashlib
from pathlib import Path
import numpy as np
from .content import sha
class BakedScene:
    def __init__(self,path,document=None):
        self.path=Path(path);self.document=document or json.loads(self.path.read_text(encoding='utf8'))
        terrain=self.document['terrain'];self.height_file=(self.path.parent/terrain['file']).resolve()
        if sha(self.height_file)!=terrain['sha256']:raise ValueError('Terrain version/hash mismatch')
        self.arrays=dict(np.load(self.height_file,allow_pickle=False))
        for material in self.document['materials'].values():
            for slot in ['base_color','normal','roughness_map']:
                if slot in material and sha(material[slot])!=material[slot+'_sha256']:raise ValueError('Material hash mismatch: '+material[slot])
        self.target=self.document['mission']['target']
    def terrain(self,native):
        terrain=native.GameTerrain();meta=self.document['terrain']
        # Material declarations belong to presentation, not the core terrain.
        for k in ['origin_north','origin_west','spacing','columns','rows']:setattr(terrain,k,meta['base'][k])
        terrain.heights=self.arrays['base'].astype(float).ravel().tolist()
        tiles=[]
        for config in meta['details']:
            tile=native.TerrainTile()
            for k in ['origin_north','origin_west','spacing','columns','rows']:setattr(tile,k,config[k])
            tile.heights=self.arrays[config.get('array_key','focus')].astype(float).ravel().tolist();tiles.append(tile)
        terrain.detail_tiles=tiles
        environment=self.document.get('environment',{})
        for name,type_name,fields in [('contact_surfaces','ContactSurface',['id','material','vertices','indices','drivable']),
                                      ('obstacles','CollisionBox',['id','center','half_size','yaw']),
                                      ('water_regions','WaterRegion',['id','polygon'])]:
            result=[]
            for value in environment.get(name,[]):
                item=getattr(native,type_name)()
                for key in fields:
                    if key in value:setattr(item,key,value[key])
                result.append(item)
            setattr(terrain,name,result)
        terrain.prepare_surfaces();return terrain
    def compatibility_view(self):
        result=dict(self.document);result['id']=result['name'];result['version']=2
        result['player_start']=result['mission']['player_start'];result['ground_target']={'id':'depot','position':self.target}
        from .heightfield import sample_grid
        airport=result['airfields'][0];height=float(sample_grid(self.arrays['focus'],result['terrain']['details'][0],*airport['center']))
        result['runway']={'position':[*airport['center'],height],'length_m':airport['runway_length_m'],'width_m':airport['runway_width_m']}
        return result
    def configure(self,renderer,bindings,terrain,visual_profile=None):
        from .content import ASSETS
        for id,version in self.document['resource_versions'].items():
            directory=ASSETS/'registered'/id
            for lod in version['lods']:
                if sha(directory/lod['file'])!=lod['sha256']:raise ValueError('Baked map resource version mismatch: '+id)
        materials=[];surfaces=[];placements=[]
        for id,data in self.document['materials'].items():
            m=bindings.SceneMaterial();m.id=id;m.color=data['color'];m.roughness=data['roughness'];m.tile_m=data['tile_m'];m.base_color=data.get('base_color','');m.normal=data.get('normal','');m.roughness_map=data.get('roughness_map','');m.water=id=='water';materials.append(m)
            if data.get('world_uv'):
                if not hasattr(m,'world_uv'):raise RuntimeError('Map requires the native world-aligned material UV interface; rebuild the renderer')
                m.world_uv=True;m.uv_origin_north=data['uv_origin_north'];m.uv_origin_west=data['uv_origin_west']
            if (id=='detail_1' or data.get('repeat_detail')) and visual_profile and visual_profile.get('terrain_detail'):
                d=visual_profile['terrain_detail']
                for slot in ['base_color','normal','roughness_map']:
                    if sha(d[slot])!=d[slot+'_sha256']:raise ValueError('Detail texture hash mismatch: '+d[slot])
                m.detail_color=d['base_color'];m.detail_normal=d['normal'];m.detail_roughness=d['roughness_map']
                m.detail_tile_m=d['tile_m'];m.detail_mean_linear=d['mean_linear_luminance'];m.detail_strength=d['strength']
        for data in self.document['surfaces']:
            s=bindings.SceneSurface();s.id=data['id'];s.material=data['material'];s.vertices=data['vertices'];s.indices=data['indices'];s.drivable=data.get('drivable',True);surfaces.append(s)
        for data in self.document['instances']:
            p=bindings.ScenePlacement()
            for k in ['id','model','chunk','category','position','yaw','scale','lod_distance','cull_distance']:setattr(p,k,data[k])
            if 'up_normal' in data:
                if not hasattr(p,'up_normal'):raise RuntimeError('Map requires the scenery up-normal interface; rebuild the renderer')
                p.up_normal=data['up_normal']
            p.target_uid='depot' if data['zone']=='mission_objective' else ''
            placements.append(p)
        args=[terrain,self.arrays['landcover'].astype(int).ravel().tolist(),self.arrays['macro_color'].reshape(-1,4).tolist(),materials,surfaces,placements,self.arrays['outer_landcover'].astype(int).ravel().tolist(),self.arrays['outer_macro_color'].reshape(-1,4).tolist()]
        terrain_materials=[d.get('material','' if i==0 else 'detail_'+str(i)) for i,d in enumerate(self.document['terrain']['details'])]
        base_material=self.document['terrain']['base'].get('material')
        if base_material:
            if not getattr(bindings,'TERRAIN_BASE_MATERIAL',False):raise RuntimeError('Map requires the native outer terrain material interface; rebuild the renderer')
            terrain_materials.append(base_material)
        if getattr(bindings,'TERRAIN_TILE_MATERIALS',False):args.append(terrain_materials)
        elif any(d.get('material') for d in self.document['terrain']['details']):
            raise RuntimeError('This map requires the native terrain tile material interface; rebuild the renderer')
        renderer.configure_scene(*args)
