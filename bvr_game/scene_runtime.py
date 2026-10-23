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
        for k,v in meta['base'].items():setattr(terrain,k,v)
        terrain.heights=self.arrays['base'].astype(float).ravel().tolist()
        tiles=[]
        for config in meta['details']:
            tile=native.TerrainTile()
            for k,v in config.items():setattr(tile,k,v)
            tile.heights=self.arrays['focus'].astype(float).ravel().tolist();tiles.append(tile)
        terrain.detail_tiles=tiles;return terrain
    def compatibility_view(self):
        result=dict(self.document);result['id']=result['name'];result['version']=2
        result['player_start']=result['mission']['player_start'];result['ground_target']={'id':'depot','position':self.target}
        from .heightfield import sample_grid
        airport=result['airfields'][0];height=float(sample_grid(self.arrays['focus'],result['terrain']['details'][0],*airport['center']))
        result['runway']={'position':[*airport['center'],height],'length_m':airport['runway_length_m'],'width_m':airport['runway_width_m']}
        return result
    def configure(self,renderer,bindings,terrain):
        from .content import ASSETS
        for id,version in self.document['resource_versions'].items():
            directory=ASSETS/'registered'/id
            for lod in version['lods']:
                if sha(directory/lod['file'])!=lod['sha256']:raise ValueError('Baked map resource version mismatch: '+id)
        materials=[];surfaces=[];placements=[]
        for id,data in self.document['materials'].items():
            m=bindings.SceneMaterial();m.id=id;m.color=data['color'];m.roughness=data['roughness'];m.tile_m=data['tile_m'];m.base_color=data.get('base_color','');m.normal=data.get('normal','');m.water=id=='water';materials.append(m)
        for data in self.document['surfaces']:
            s=bindings.SceneSurface();s.id=data['id'];s.material=data['material'];s.vertices=data['vertices'];s.indices=data['indices'];surfaces.append(s)
        for data in self.document['instances']:
            p=bindings.ScenePlacement()
            for k in ['id','model','chunk','category','position','yaw','scale','lod_distance','cull_distance']:setattr(p,k,data[k])
            p.target_uid='depot' if data['zone']=='mission_objective' else ''
            placements.append(p)
        renderer.configure_scene(terrain,self.arrays['landcover'].astype(int).ravel().tolist(),self.arrays['macro_color'].reshape(-1,4).tolist(),materials,surfaces,placements,self.arrays['outer_landcover'].astype(int).ravel().tolist(),self.arrays['outer_macro_color'].reshape(-1,4).tolist())
