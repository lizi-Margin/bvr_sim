"""One data-driven game catalog shared with the core; appearance availability is explicit."""
from copy import deepcopy
from pathlib import Path
import hashlib,json
from .content import ROOT,ASSETS,sha

CATALOG=ROOT/'bvr_sim/resources/aircraft_catalog.json'
IMPORTED=ROOT/'bvr_sim/resources/imported_aircraft_catalog.json'

def imported_row(original,verify=False):
    row=deepcopy(original);reasons=[]
    fdm=ROOT/'bvr_sim/resources'/row['fdm']['file'];visual=ROOT/row['appearance']['file']
    if not row['available_for_test_flight']:reasons.append(row['unavailable_reason'] or 'Source validation failed')
    for file,expected in [(fdm,row['fdm']['sha256']),(visual,row['appearance']['glb_sha256'])]:
        if not file.is_file():reasons.append('Missing resource: '+str(file))
        elif verify and sha(file)!=expected:reasons.append('Resource hash changed: '+str(file))
    row['appearance']['file']=str(visual)
    row['appearance']['manifest']=str(ROOT/row['appearance']['manifest'])
    row['appearance']['variant_note']='Imported FlightGear aircraft; source systems/flight controls use host approximations. Unarmed test flight.'
    row.update(library_aircraft=True,available=not reasons,unavailable_reason='; '.join(reasons),missions=['training'],supported_weapons=[],default_loadout='unarmed',legal_loadouts=[{'id':'unarmed','missiles':0,'bombs':0}])
    row['validation']['flight']='SOURCE TEST FLIGHT / '+row['fdm']['type'].upper()+' / HOST ASSIST'
    return row

def aircraft_catalog(include_library=False):
    document=json.loads(CATALOG.read_text(encoding='utf8'));rows=[]
    for original in document['aircraft']:
        row=deepcopy(original);reasons=[];fdm=ROOT/'bvr_sim/resources'/row['fdm']['file']
        if not fdm.exists():reasons.append('Missing JSBSim aircraft file: '+str(fdm))
        elif sha(fdm)!=row['fdm']['sha256']:reasons.append('JSBSim model hash changed; review required')
        asset=row['appearance']['asset_id'];directory=ASSETS/'registered'/asset;manifest=directory/'manifest.json'
        if not manifest.exists():reasons.append('Appearance import not complete: '+asset)
        else:
            m=json.loads(manifest.read_text(encoding='utf8'));file=directory/m['file']
            if not file.is_file() or sha(file)!=m['glb_sha256']:reasons.append('Appearance GLB missing or hash mismatch: '+asset)
            row['appearance'].update({'manifest':str(manifest),'file':str(file),'glb_sha256':m['glb_sha256'],'bounds':m.get('bounds_blender'),'axes':m.get('runtime_axes'),'units':m.get('units'),'license':m.get('license'),'source_url':m.get('source_url'),'distribution_allowed':m.get('distribution_allowed',False),'lods':m.get('lods',[{'level':0,'file':m['file'],'sha256':m['glb_sha256'],'triangles':m.get('faces'),'bounds':m.get('bounds_blender'),'note':'Source exterior geometry; no decimated aircraft LOD registered'}])})
        row['available']=not reasons;row['unavailable_reason']='; '.join(reasons);rows.append(row)
    if include_library and IMPORTED.exists():
        rows.extend(imported_row(row) for row in json.loads(IMPORTED.read_text(encoding='utf8'))['aircraft'])
    return {'schema_version':document['schema_version'],'catalog_sha256':sha(CATALOG),'aircraft':rows}

def aircraft(id,require_available=False):
    row=next((r for r in aircraft_catalog()['aircraft'] if r['id']==id),None)
    if row is None and IMPORTED.exists():
        source=next((r for r in json.loads(IMPORTED.read_text(encoding='utf8'))['aircraft'] if r['id']==id),None)
        if source:row=imported_row(source,verify=True)
    if row is None:raise ValueError('Unknown aircraft ID: '+id)
    if require_available and not row['available']:raise ValueError(row['unavailable_reason'])
    return row

def loadout(row,id=None):
    id=id or row['default_loadout'];result=next((v for v in row['legal_loadouts'] if v['id']==id),None)
    if result is None:raise ValueError('Unsupported loadout '+id+' for '+row['id'])
    return result

def runtime_models(runtime,resource_versions=None):
    result=dict(runtime['models'])
    for row in aircraft_catalog()['aircraft']:
        # Explicit runtime entries have already passed manifest/hash validation.
        # Expand missing catalog aircraft without silently replacing a reviewed
        # registered variant supplied by a caller's runtime recipe.
        if row['available']:result.setdefault(row['id'],row['appearance']['file'])
    if IMPORTED.exists():
        for row in json.loads(IMPORTED.read_text(encoding='utf8'))['aircraft']:
            file=ROOT/row['appearance']['file']
            if row['available_for_test_flight'] and file.is_file():result[row['simulation_model']]=str(file)
    vehicle=ASSETS/'registered/WillysJeep/manifest.json'
    if vehicle.exists():
        m=json.loads(vehicle.read_text(encoding='utf8'));file=vehicle.parent/m['file']
        if sha(file)!=m['glb_sha256']:raise ValueError('Vehicle GLB registration/hash mismatch')
        result['WillysJeep']=str(file)
    for id,version in (resource_versions or {}).items():
        directory=ASSETS/'registered'/id
        for i,lod in enumerate(version['lods']):
            file=directory/lod['file']
            if sha(file)!=lod['sha256']:raise ValueError('Map resource hash mismatch: '+id)
            result[id if i==0 else id+'::lod'+str(i)]=str(file)
    return result
