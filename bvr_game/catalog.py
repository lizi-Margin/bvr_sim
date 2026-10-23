"""Curated roles reference provider IDs; scene recipes remain provider-independent."""
import json,subprocess,sys
from pathlib import Path
from .content import ASSETS,ROOT,fetch_kenney,write_json,sha
CURATED=[
 ('tree_oak','nature-kit','tree_oak',14,['tree','forest'],'forest canopy',250,'decorative'),
 ('tree_pine','nature-kit','tree_pineTallA',18,['tree','forest'],'forest canopy',250,'decorative'),
 ('tree_small','nature-kit','tree_small',9,['tree','riverbank'],'shelter belt',200,'decorative'),
 ('bush','nature-kit','plant_bushLarge',1.7,['bush','vegetation'],'riverbank understory',400,'decorative'),
 ('rock_a','nature-kit','rock_largeA',3,['rock','terrain'],'rocky slopes',30,'box'),
 ('rock_b','nature-kit','rock_tallA',5,['rock','terrain'],'rocky outcrop',20,'box'),
 ('house_a','city-kit-suburban','building-type-a',8,['building','village'],'residential village',50,'box'),
 ('house_b','city-kit-suburban','building-type-f',7,['building','village'],'residential village',50,'box'),
 ('house_c','city-kit-suburban','building-type-j',9,['building','village'],'residential village',50,'box'),
 ('warehouse_a','city-kit-industrial','building-a',12,['building','industrial'],'warehouse and hangar',15,'box'),
 ('warehouse_b','city-kit-industrial','building-g',10,['building','industrial'],'industrial complex',15,'box'),
 ('warehouse_c','city-kit-industrial','building-k',14,['building','industrial'],'mission warehouse',10,'box'),
 ('tank','city-kit-industrial','detail-tank-large',8,['prop','industrial'],'fuel and supply',30,'box'),
 ('tower','city-kit-industrial','water-tower',20,['building','utility'],'utility water tower',1,'box'),
 ('container','city-kit-industrial','shipping-container-a',2.6,['equipment','industrial'],'service equipment',40,'box'),
 ('fence','city-kit-roads','construction-fence',2,['fence','equipment'],'boundary fence',300,'decorative'),
 ('lamp','city-kit-roads','light-square',7,['lamp','road'],'roadside light',30,'decorative'),
 ('cone','city-kit-roads','construction-cone',.7,['equipment','airport'],'apron equipment',40,'decorative'),
 ('road_module','city-kit-roads','road-straight',.2,['road','module'],'paved service road module',100,'surface')]
def prepare(blender=r'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe',rebuild=False):
    specs=[]
    for id,pack,stem,height,tags,use,density,collision in CURATED:
        provider=fetch_kenney(pack);files=[Path(provider['directory'])/p for p in provider['models'] if Path(p).stem==stem and Path(p).suffix=='.glb']
        if len(files)!=1:raise ValueError('Missing/ambiguous source model '+pack+':'+stem)
        output=ASSETS/'registered'/id;manifest=output/'manifest.json'
        spec={'id':id,'name':stem,'source':str(files[0]),'provider_manifest':str(ASSETS/'cache/kenney'/pack/'provider.json'),'output':str(output),'height_m':height,'tags':tags,'use':use,'density':density,'collision':collision,'material_policy':{'metallic':0,'roughness':.85,'temperate_foliage':pack=='nature-kit'}}
        spec['converter_sha256']=sha(ROOT/'game/tools/convert_catalog.py')
        dimensions={'warehouse_a':[72,48,12],'warehouse_b':[52,38,10],'warehouse_c':[95,55,14],'fence':[.84,78,2]}
        if id in dimensions:spec['dimensions_m']=dimensions[id]
        if manifest.exists():
            m=json.loads(manifest.read_text(encoding='utf8'))
            if m.get('source_sha256')!=sha(files[0]) or not all(sha(output/l['file'])==l['sha256'] for l in m.get('lods',[])):raise ValueError('Registered source or LOD changed: '+id)
            if m.get('conversion_recipe')==spec and len(m.get('lods',[]))==2:continue
            if not rebuild:raise ValueError('Conversion recipe changed; explicitly use --rebuild for '+id)
        specs.append(spec)
    if specs:
        recipe=ASSETS/'cache/kenney/catalog-conversion.json';write_json(recipe,specs)
        subprocess.run([blender,'--background','--python-exit-code','1','--python',str(ROOT/'game/tools/convert_catalog.py'),'--',str(recipe)],check=True,stdout=sys.stderr)
    runtime=ROOT/'game/runtime.json';r=json.loads(runtime.read_text(encoding='utf8'))
    for id,*_ in CURATED:
        directory=ASSETS/'registered'/id;m=json.loads((directory/'manifest.json').read_text(encoding='utf8'))
        for lod in m['lods']:r['models'][id+('' if lod['level']==0 else '::lod1')]=str(directory/lod['file'])
    write_json(runtime,r)
    inventory=[json.loads(p.read_text(encoding='utf8')) for p in (ASSETS/'registered').glob('*/manifest.json') if p.parent.name!='audio']
    write_json(ASSETS/'catalog.json',{'schema_version':2,'assets':inventory})
    return {'registered':len(CURATED),'lods':len(CURATED)*2,'catalog':str(ASSETS/'catalog.json')}
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--rebuild',action='store_true');a=p.parse_args()
    print(json.dumps(prepare(rebuild=a.rebuild),indent=2))
