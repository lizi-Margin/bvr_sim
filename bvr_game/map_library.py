"""Read-only runtime index of maps published by the separate offline tool.

No generators, downloads, Blender, or terrain edits are imported here.
"""
from pathlib import Path
import copy,hashlib,json,math,re

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_CATALOG=ROOT/'game/maps/catalog.json'
ENVIRONMENT_KEYS=('physical_sky','aerial_perspective','high_quality_sky','volumetric_clouds','planet_albedo',
                  'sky_exposure','ambient','sun_rotation','sun_energy','exposure','saturation','horizon_height_fog','cloud_layer','cloud_weather_map','sun_shadow_cascades_m','sun_shadow_resolution')

def shadow_cascades(profile):
    values=profile.get('sun_shadow_cascades_m',[8,80,800])
    if not isinstance(values,(list,tuple)) or not 1<=len(values)<=4:raise ValueError('Shadow cascades require1..4 increasing distances')
    previous=0
    for value in values:
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not previous<value<=50000:
            raise ValueError('Shadow cascade distances must increase in(0,50000] metres')
        previous=value
    resolution=profile.get('sun_shadow_resolution',-1)
    if isinstance(resolution,bool) or not isinstance(resolution,int) or (resolution!=-1 and (not 128<=resolution<=8192 or resolution&(resolution-1) or resolution*len(values)>16384)):
        raise ValueError('Sun shadow resolution must be auto(-1) or power-of-two128..8192 and fit16384 atlas width')
    return list(values)

def scene_profile(base,document,*,use_environment=True,asset_root=None):
    result=copy.deepcopy(base)
    saved=document.get('baked_environment') if use_environment else None
    if saved is not None:
        if saved.get('schema_version')!=1:raise ValueError('Unsupported baked environment')
        profile=saved.get('profile')
        if not isinstance(profile,dict) or set(profile)-set(ENVIRONMENT_KEYS):raise ValueError('Invalid baked environment profile')
        result.update(copy.deepcopy(profile))
    if result.get('cloud_weather_map'):
        source=result['cloud_weather_map'];file=Path(source['file'])
        if not file.is_absolute():
            if asset_root is None:raise ValueError('Weather map requires a map package root')
            file=inside(Path(asset_root),source['file'])
        if digest(file)!=source['sha256']:raise ValueError('Cloud weather map hash changed')
        source['file']=str(file.resolve())
    shadow_cascades(result)
    return result

def digest(path):
    # Multi-gigabyte map packages must not allocate another whole-file copy.
    with Path(path).open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf8'))
def inside(root,path):
    result=(root/path).resolve()
    if not result.is_relative_to(root.resolve()):raise ValueError('Map package path escapes its release directory')
    return result

def catalog_storage(catalog,data,alias=None):
    """Resolve an explicitly configured volume; release paths stay inside it."""
    if alias is None:return Path(catalog).resolve().parent
    roots=data.get('storage_roots',{})
    if not isinstance(alias,str) or not isinstance(roots,dict) or alias not in roots:
        raise ValueError('Unknown map storage root: '+str(alias))
    value=roots[alias]
    # Portable distributions anchor self-contained map packages beside the
    # catalog, without embedding the build machine's absolute drive path.
    if value=='$catalog':return Path(catalog).resolve().parent
    if not isinstance(value,str) or not Path(value).is_absolute():
        raise ValueError('Map storage root must be an absolute directory')
    return Path(value).resolve()


def registered_directory(registered,asset_id,catalog):
    """An asset junction may target only the same ID in a declared library."""
    if not isinstance(asset_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]+',asset_id):
        raise ValueError('Invalid registered asset ID')
    roots=[Path(registered).resolve()]
    external=catalog.get('registered_storage_roots',[])
    if not isinstance(external,list):raise ValueError('Registered storage roots must be a list')
    for value in external:
        if not isinstance(value,str) or not Path(value).is_absolute():
            raise ValueError('Registered storage root must be an absolute directory')
        roots.append(Path(value).resolve())
    directory=(Path(registered)/asset_id).resolve()
    if not any(directory==root/asset_id for root in roots):
        raise ValueError('Registered asset path escapes its declared library')
    return directory

class MapLibrary:
    def __init__(self,path=DEFAULT_CATALOG):self.path=Path(path).resolve()
    def versions(self):
        if not self.path.is_file():return []
        data=read(self.path)
        if data.get('schema_version')!=1:raise ValueError('Unsupported map catalog')
        result=[];seen=set()
        for item in data['maps']:
            row=dict(item)
            if row['id'] in seen:raise ValueError('Duplicate map version: '+row['id'])
            seen.add(row['id'])
            root=catalog_storage(self.path,data,row.get('storage_root'))
            row['manifest']=str(inside(root,row['manifest']))
            row['map']=str(inside(Path(row['manifest']).parent,'generated-map.json'))
            result.append(row)
        return result
    def resolve(self,id,*,with_document=False):
        from .startup import progress
        row=next((r for r in self.versions() if r['id']==id),None)
        if row is None:raise ValueError('Unknown published map version: '+id)
        root=Path(row['manifest']).parent
        if digest(row['manifest'])!=row['manifest_sha256']:raise ValueError('Map release manifest changed')
        manifest=read(row['manifest'])
        for index,file in enumerate(manifest['files']):
            progress('verify_map',f"正在校验地图文件 {index+1}/{len(manifest['files'])}")
            if digest(inside(root,file['path']))!=file['sha256']:raise ValueError('Map package file changed: '+file['path'])
        if digest(row['map'])!=manifest['map_sha256']:raise ValueError('Map version changed')
        from .content import ASSETS
        registered=(ASSETS/'registered').resolve()
        catalog=read(self.path)
        progress('read_map','正在读取大型地图，请稍候；可随时取消')
        document=read(row['map'])
        progress('verify_models','正在校验地图模型')
        for id,version in document['resource_versions'].items():
            directory=registered_directory(registered,id,catalog)
            if digest(directory/'manifest.json')!=version['manifest_sha256']:raise ValueError('Registered map manifest changed: '+id)
            for lod in version['lods']:
                if digest(inside(directory,lod['file']))!=lod['sha256']:raise ValueError('Registered map model changed: '+id)
        # The CLI can hand this exact verified document to FlightGame rather
        # than parsing a gigabyte-sized JSON a second time before its window.
        return (row,document) if with_document else row

def choices(library,current):
    """Keep an explicit --map usable, without pretending it is published."""
    current=Path(current).resolve();rows=library.versions()
    if not any(Path(r['map'])==current for r in rows):
        rows.insert(0,{'id':str(current),'label':'当前地图 / '+current.parent.name,'map':str(current),'quality':'external'})
    return rows
