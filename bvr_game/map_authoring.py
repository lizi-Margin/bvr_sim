"""Offline-only editable workspaces and content-addressed baked map releases."""
from pathlib import Path
import copy,hashlib,json,re,shutil,uuid,time
from .content import sha,write_json,ASSETS
from .map_library import read,inside,catalog_storage,ENVIRONMENT_KEYS

def create_workspace(output,recipe):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    shutil.copy2(recipe,output/'scene-recipe.json')
    write_json(output/'workspace.json',{'schema_version':1,'recipe_source':str(Path(recipe).resolve()),'recipe_source_sha256':sha(recipe)})
    return output/'scene-recipe.json'

def bake(workspace):
    from .worldgen import Baker
    workspace=Path(workspace).resolve();recipe=workspace/'scene-recipe.json'
    target=workspace/'bakes'/sha(recipe)[:24]
    if target.exists():raise FileExistsError('This recipe already has a bake; edit its recipe or inspect the existing version')
    result=Baker(read(recipe)).bake(target)
    return result

def finish_release(stage,catalog):
    """Resume an already frozen package after a Windows file-lock interruption."""
    stage=Path(stage).resolve();catalog=Path(catalog).resolve()
    manifest=read(stage/'release.json');name,key=manifest['id'].split('@')
    if not re.fullmatch('[A-Za-z0-9_-]+',name) or not re.fullmatch('[a-f0-9]{24}',key):raise ValueError('Invalid release ID')
    index=read(catalog) if catalog.exists() else {'schema_version':1,'maps':[]}
    alias=manifest.get('storage_root');storage=catalog_storage(catalog,index,alias)
    target=inside(storage,Path('published')/name/key)
    if not stage.is_relative_to(storage):raise ValueError('Release staging must stay inside the map library')
    for file in manifest['files']:
        if sha(inside(stage,file['path']))!=file['sha256']:raise ValueError('Incomplete staged release: '+file['path'])
    if stage!=target:
        if target.exists():raise FileExistsError('Release already exists; existing version was preserved')
        target.parent.mkdir(parents=True,exist_ok=True)
        for attempt in range(6):
            try:stage.rename(target);break
            except PermissionError:
                if attempt==5:raise
                time.sleep(.2*(attempt+1))
    if any(row['id']==manifest['id'] for row in index['maps']):raise FileExistsError('Version is already in the map catalog')
    index['maps'].append({'id':manifest['id'],'label':manifest['label'],'quality':manifest['quality'],
                         'supports_convoy':manifest.get('supports_convoy',bool(read(target/'generated-map.json')['mission'].get('ground_units'))),
                         'manifest':(target/'release.json').relative_to(storage).as_posix(),'manifest_sha256':sha(target/'release.json'),
                         **({'storage_root':alias} if alias is not None else {})})
    pending=catalog.with_suffix('.pending.json');write_json(pending,index);pending.replace(catalog)
    return {'id':manifest['id'],'map':str(target/'generated-map.json'),'manifest':str(target/'release.json'),'quality':manifest['quality']}

def publish(map_path,catalog,*,name,label,review,storage_root=None):
    """Freeze generated dependencies; the game never follows a mutable draft."""
    from .scene_runtime import BakedScene
    if not re.fullmatch('[A-Za-z0-9_-]+',name):raise ValueError('Use an ASCII map family ID')
    map_path=Path(map_path).resolve();catalog=Path(catalog).resolve();review=Path(review).resolve()
    index=read(catalog) if catalog.exists() else {'schema_version':1,'maps':[]}
    if storage_root is None:storage_root=index.get('default_storage_root')
    storage=catalog_storage(catalog,index,storage_root)
    scene=BakedScene(map_path);source=scene.document;assessment=read(review)
    if assessment.get('map_sha256')!=sha(map_path):raise ValueError('Review belongs to another map version')
    quality=assessment.get('quality')
    if quality not in ('baseline','candidate','reference_matched'):raise ValueError('Review must explicitly declare visual quality')
    if not assessment.get('notes'):raise ValueError('Review needs an actual visual assessment')
    capture_report=Path(assessment['capture_report']).resolve();captures=read(capture_report)
    if captures.get('map_sha256')!=sha(map_path) or captures.get('shader_errors')!=0:raise ValueError('Review needs successful renders of this exact map')
    if quality=='reference_matched' and not assessment.get('reference_images'):raise ValueError('Reference match needs the actual comparison images')
    catalog.parent.mkdir(parents=True,exist_ok=True)
    storage.mkdir(parents=True,exist_ok=True)
    stage=storage/('._publish-'+uuid.uuid4().hex);stage.mkdir()
    doc=copy.deepcopy(source)
    def freeze(file):
        file=Path(file).resolve();relative=Path('data')/(sha(file)[:16]+'-'+file.name)
        target=stage/relative;target.parent.mkdir(exist_ok=True)
        if not target.exists():shutil.copy2(file,target)
        return relative.as_posix()
    if captures.get('visual_profile'):
        profile_file=Path(captures['visual_profile']).resolve()
        if sha(profile_file)!=captures.get('visual_profile_sha256'):raise ValueError('Reviewed visual profile changed')
        profile=read(profile_file)
        environment=copy.deepcopy(captures.get('effective_environment',{k:profile[k] for k in ENVIRONMENT_KEYS if k in profile}))
        if not isinstance(environment,dict) or set(environment)-set(ENVIRONMENT_KEYS):raise ValueError('Invalid reviewed environment')
        if environment.get('cloud_weather_map'):
            cloud=environment['cloud_weather_map'];file=Path(cloud['file'])
            if not file.is_absolute():file=profile_file.parent/file
            if sha(file)!=cloud['sha256']:raise ValueError('Reviewed cloud weather map changed')
            cloud['file']=freeze(file)
        doc['baked_environment']={'schema_version':1,'profile':environment,
            'source_profile_sha256':sha(profile_file),'source_profile_file':freeze(profile_file)}
    doc['terrain']['file']=freeze(scene.height_file)
    if doc['terrain'].get('ground_atlas'):
        atlas=doc['terrain']['ground_atlas'];atlas['file']=freeze(map_path.parent/atlas['file'])
    if (map_path.parent/'water-footprint.wkb').is_file():shutil.copy2(map_path.parent/'water-footprint.wkb',stage/'water-footprint.wkb')
    bridge=doc.get('source_road_bake',{}).get('bridge')
    if bridge:
        file=Path(bridge['source_deck'])
        if not file.is_absolute():file=map_path.parent/file
        if sha(file)!=bridge['source_deck_sha256']:raise ValueError('Source bridge deck changed before publishing')
        bridge['source_deck']=freeze(file)
    for mat in doc['materials'].values():
        for layer in [mat]+([mat['ground_detail']] if mat.get('ground_detail') else []):
            for slot in ('base_color','normal','roughness_map'):
                if layer.get(slot):layer[slot]=freeze(layer[slot])
    for id,version in doc['resource_versions'].items():
        directory=ASSETS/'registered'/id
        for lod in version['lods']:
            if sha(directory/lod['file'])!=lod['sha256']:raise ValueError('Changed registered map resource: '+id)
        expected=version.get('manifest_sha256')
        swap=doc.get('source_card_resource_swap',{})
        if not expected and id==swap.get('asset_id'):expected=swap.get('registered_manifest_sha256')
        if expected and sha(directory/'manifest.json')!=expected:raise ValueError('Changed registered source manifest: '+id)
        version['manifest_sha256']=sha(directory/'manifest.json')
    write_json(stage/'generated-map.json',doc)
    recipe=map_path.parent/'scene-recipe.json'
    if recipe.is_file():shutil.copy2(recipe,stage/'scene-recipe.json')
    write_json(stage/'review.json',{**assessment,'capture_report_sha256':sha(capture_report)})
    shutil.copy2(capture_report,stage/'capture-report.json')
    images=[]
    for row in captures.get('captures',[]):
        capture=row['capture'];file=Path(capture['image'] if isinstance(capture,dict) and 'image' in capture else capture['png'] if isinstance(capture,dict) else capture)
        images.append(freeze(file))
    if not images:raise ValueError('No actual rendered images in capture report')
    files=[{'path':p.relative_to(stage).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(stage.rglob('*')) if p.is_file()]
    key=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()[:24]
    id=name+'@'+key
    manifest={'schema_version':1,'id':id,'label':label,'quality':quality,'supports_convoy':bool(source['mission'].get('ground_units')),'map_sha256':sha(stage/'generated-map.json'),
              'source_map_sha256':sha(map_path),'source_map':str(map_path),'files':files,'preview_images':images,
              'assets':'Registered models stay in the shared hash-checked asset library. All terrain and map material files are frozen here.'}
    if storage_root is not None:manifest['storage_root']=storage_root
    if recipe.is_file() and read(recipe).get('resource_use'):manifest['resource_use']=read(recipe)['resource_use']
    write_json(stage/'release.json',manifest)
    return finish_release(stage,catalog)
