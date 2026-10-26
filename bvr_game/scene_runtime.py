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
        self.ground_atlas=None
        if terrain.get('ground_atlas'):
            from .ground_atlas import load_atlas
            self.ground_atlas=load_atlas(terrain['ground_atlas'],self.path,terrain['sha256'])
        for material in self.document['materials'].values():
            for layer in [material]+([material['ground_detail']] if material.get('ground_detail') else []):
                for slot in ['base_color','normal','roughness_map']:
                    if slot in layer:
                        layer[slot]=str((self.path.parent/layer[slot]).resolve())
                        if sha(layer[slot])!=layer[slot+'_sha256']:raise ValueError('Material hash mismatch: '+layer[slot])
            if material.get('ground_detail'):
                d=material['ground_detail']
                if not all(k in d for k in ['base_color','normal','roughness_map']) or not 0<float(d['tile_m'])<=100 or not 0<float(d['mean_linear_luminance'])<=1 or not 0<=float(d['strength'])<=1:raise ValueError('Invalid saved ground detail')
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
        airport=result['airfields'][0];n,w=airport['center'];meta=result['terrain'];selected=meta['base'];key='base'
        for tile in meta['details']:
            if tile['origin_north']<=n<=tile['origin_north']+(tile['columns']-1)*tile['spacing'] and tile['origin_west']<=w<=tile['origin_west']+(tile['rows']-1)*tile['spacing'] and (key=='base' or tile['spacing']<selected['spacing']):
                selected=tile;key=tile.get('array_key','focus')
        height=float(sample_grid(self.arrays[key],selected,n,w))
        result['runway']={'position':[*airport['center'],height],'length_m':airport['runway_length_m'],'width_m':airport['runway_width_m']}
        return result
    def configure(self,renderer,bindings,terrain,visual_profile=None):
        for capability in self.document.get('required_renderer_capabilities',[]):
            if not isinstance(capability,str) or not capability.replace('_','').isalnum() or not getattr(bindings,capability,False):raise RuntimeError('Map requires renderer capability: '+str(capability))
        from .content import ASSETS
        if any(self.document['materials'][s['material']].get('ground_detail') for s in self.document['surfaces']) and not getattr(bindings,'SURFACE_DETAIL_UVS_V1',False):
            raise RuntimeError('Surface detail materials require the matching native world-detail UV interface')
        if self.ground_atlas is not None:
            meta=self.document['terrain']['ground_atlas']
            if not hasattr(renderer,'configure_ground_atlas'):raise RuntimeError('Map requires the native source-tree ground atlas interface; rebuild the renderer')
            renderer.configure_ground_atlas(self.ground_atlas,meta['origin_north'],meta['origin_west'],meta['spacing'],meta['sha256'])
        frozen_canopy_assets={p['model'] for p in self.document.get('instances',[]) if 'ground_stems' in p}
        swap=self.document.get('source_card_resource_swap',{})
        models={}
        for id,version in self.document['resource_versions'].items():
            directory=ASSETS/'registered'/id
            for i,lod in enumerate(version['lods']):
                if sha(directory/lod['file'])!=lod['sha256']:raise ValueError('Baked map resource version mismatch: '+id)
                models[id if i==0 else id+'::lod'+str(i)]=str(directory/lod['file'])
            manifest_file=directory/'manifest.json';manifest=json.loads(manifest_file.read_text(encoding='utf8'))
            if (manifest.get('impostor') or {}).get('requires_directional_view_selection'):raise RuntimeError('Offline aerial source views require a directional source view sampler; overlapping all source planes is unsupported')
            expected_manifest=version.get('manifest_sha256')
            if not expected_manifest and (manifest.get('source_card_mips') or id in frozen_canopy_assets or id==swap.get('asset_id')):
                # v53/v55 immutable replacement maps already froze this hash
                # in their swap provenance. Retain that exact recorded version.
                expected_manifest=swap.get('registered_manifest_sha256')
            if expected_manifest and sha(manifest_file)!=expected_manifest:raise ValueError('Baked map resource manifest version mismatch: '+id)
            if manifest.get('source_card_mips'):
                if not expected_manifest:raise ValueError('Explicit source-card mips require a versioned manifest: '+id)
                if not getattr(bindings,'SOURCE_CARD_AREA_MIPS',False):raise RuntimeError('Map requires native explicit source-card mip loading; rebuild the renderer')
                checked={}
                for materials in manifest['source_card_mips']['materials_by_lod_file'].values():
                    for slots in materials.values():
                        for item in slots.values():
                            path=(directory/item['file']).resolve()
                            if not path.is_relative_to(directory.resolve()):raise ValueError('Source-card mip path leaves registered asset')
                            if checked.setdefault(path,item['sha256'])!=item['sha256'] or sha(path)!=item['sha256']:raise ValueError('Source-card mip sidecar changed: '+id)
        from .render_assets import distance_lod_models
        models=distance_lod_models(models,visual_profile)
        if hasattr(renderer,'register_scene_models'):renderer.register_scene_models(models)
        materials=[];surfaces=[];placements=[]
        for id,data in self.document['materials'].items():
            m=bindings.SceneMaterial();m.id=id;m.color=data['color'];m.roughness=data['roughness'];m.tile_m=data['tile_m'];m.base_color=data.get('base_color','');m.normal=data.get('normal','');m.roughness_map=data.get('roughness_map','');m.water=id=='water';materials.append(m)
            if data.get('world_uv'):
                if not hasattr(m,'world_uv'):raise RuntimeError('Map requires the native world-aligned material UV interface; rebuild the renderer')
                m.world_uv=True;m.uv_origin_north=data['uv_origin_north'];m.uv_origin_west=data['uv_origin_west']
            d=data.get('ground_detail') or ((visual_profile or {}).get('terrain_detail') if id=='detail_1' or data.get('repeat_detail') else None)
            if d:
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
            if 'ground_stems' in data:
                if not hasattr(p,'ground_stems'):raise RuntimeError('Map requires the native independent source tree position interface; rebuild the renderer')
                p.ground_stems=data['ground_stems']
            p.target_uid='depot' if data['zone']=='mission_objective' else ''
            placements.append(p)
        # A source-map macro can bind every terrain tile explicitly. Its
        # legacy per-cell palette is then unused by native terrain_patch;
        # avoid materialising millions of redundant Python colour objects.
        bound_macro=self.document['terrain'].get('bound_macro_only',False)
        if bound_macro and any(t.get('material') not in self.document['materials'] for t in [self.document['terrain']['base'],*self.document['terrain']['details']]):
            raise ValueError('Bound macro terrain requires a declared material on every tile')
        args=[terrain,[] if bound_macro else self.arrays['landcover'].astype(int).ravel().tolist(),[] if bound_macro else self.arrays['macro_color'].reshape(-1,4).tolist(),materials,surfaces,placements,[] if bound_macro else self.arrays['outer_landcover'].astype(int).ravel().tolist(),[] if bound_macro else self.arrays['outer_macro_color'].reshape(-1,4).tolist()]
        terrain_materials=[d.get('material','' if i==0 else 'detail_'+str(i)) for i,d in enumerate(self.document['terrain']['details'])]
        base_material=self.document['terrain']['base'].get('material')
        if base_material:
            if not getattr(bindings,'TERRAIN_BASE_MATERIAL',False):raise RuntimeError('Map requires the native outer terrain material interface; rebuild the renderer')
            terrain_materials.append(base_material)
        if getattr(bindings,'TERRAIN_TILE_MATERIALS',False):args.append(terrain_materials)
        elif any(d.get('material') for d in self.document['terrain']['details']):
            raise RuntimeError('This map requires the native terrain tile material interface; rebuild the renderer')
        renderer.configure_scene(*args)
