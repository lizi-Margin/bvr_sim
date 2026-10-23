"""Assemble measured evidence; this does not manufacture passing validation results."""
from pathlib import Path
import argparse,json,sys,shutil,re,hashlib
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.aircraft import aircraft_catalog
from bvr_game.content import write_json,sha,ASSETS

def package(out):
    out=Path(out);reports=out/'reports';work=ROOT.parent/'work/multi_ground_alpha';map_dir=ROOT/'game/maps/training_range_v3';d=json.loads((map_dir/'generated-map.json').read_text());catalog=aircraft_catalog()
    read=lambda p:json.loads(Path(p).read_text(encoding='utf8'))
    controls=read(reports/'aircraft-flight-probe.json');menu=read(reports/'aircraft-menu-probe.json')
    tapes=[read(p) for p in sorted((reports/'input-tapes').glob('*.json')) if not p.stem.endswith('_branch')]
    missions=[{'id':t['id'],'status':t['status'],'result':t['final_frame']['result'],'tick':t['final_frame']['tick'],'sim_seconds':t['final_frame']['sim_time'],'enemy_attacks':t['config']['enemy_attacks'],'captures':t.get('captures',{}),'shader_errors':t.get('shader_errors'),'input_tape':str(reports/'input-tapes'/(t['id']+'.json'))} for t in tapes]
    write_json(out/'mission-report.json',{'status':'passed' if all(t['status']=='passed' and t.get('rendered') for t in tapes) else 'failed','missions':missions,'map_sha256':sha(map_dir/'generated-map.json'),'method':'Real typed commands, core weapons, sensor/LOS-driven SAM and deterministic inputs. F16/F15/F18 air qualification uses a maneuvering non-firing aggressor; F22 also completes an armed duel. F18 strike uses neutral manual aileron on a straight declared run.'})
    write_json(out/'aircraft-catalog.json',catalog)
    integration=[]
    for row in catalog['aircraft']:
        probe=next(x for x in controls if x['id']==row['id']);qualified=[m for m in missions if m['id'].startswith(row['id']+'_')]
        fdm=ROOT/'bvr_sim/resources'/row['fdm']['file'];dependency_hashes={str(p.relative_to(ROOT)):sha(p) for p in sorted(fdm.parent.rglob('*.xml'))}
        integration.append({'id':row['id'],'available':row['available'],'appearance':row['appearance'],'controller':row['flight_controller'],'radar':row['radar'],'legal_loadouts':row['legal_loadouts'],'response_metrics':probe['metrics'],'all_response_scenarios_alive':all(probe[k]['final']['alive'] for k in ['level','turn','climb','low_throttle','high_throttle']),'fdm_aircraft_folder_hashes':dependency_hashes,'dependency_inventory_scope':'Conservative XML inventory of the actual selected aircraft folder; shared engine/system library is installed in the repository and not claimed runtime-traced here.','weapon_qualification':qualified,'approximation':row['provenance']})
    write_json(out/'aircraft-integration-report.json',{'status':'passed' if len(integration)==5 and all(r['available'] and r['all_response_scenarios_alive'] and all(m['status']=='passed' for m in r['weapon_qualification']) for r in integration) and menu['status']=='passed' else 'failed','aircraft':integration,'hangar':{'status':menu['status'],'cache_stable':menu['cache_stable'],'shader_errors':menu['shader_errors']},'response_source':str(reports/'aircraft-flight-probe.json'),'ordinary_ids':[r['id'] for r in catalog['aircraft']]})
    models=[]
    ids=sorted(set(d['resource_versions'])|{r['appearance']['asset_id'] for r in catalog['aircraft']}|{'WillysJeep'})
    for id in ids:
        p=ASSETS/'registered'/id/'manifest.json';m=read(p);models.append(m);target=out/'assets'/id;target.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target/'manifest.json')
        write_json(target/'conversion-recipe.json',m.get('conversion_recipe',{}))
        if m.get('distribution_allowed') and m.get('license')=='CC0-1.0':
            for lod in m.get('lods',[]):shutil.copy2(p.parent/lod['file'],target/lod['file'])
        for i,evidence in enumerate(m.get('license_evidence',[])):
            f=Path(evidence.get('file',''));f=f if f.is_absolute() else Path(m.get('conversion_recipe',{}).get('provider_manifest',str(ASSETS/'missing'))).parent/f
            if f.is_file():shutil.copy2(f,target/('license-evidence-'+str(i)+'.txt'))
    write_json(out/'asset-inventory.json',{'models':models,'materials':d['materials'],'scene_model_ids':sorted(d['resource_versions']),'vehicle_model':'WillysJeep','distribution_policy':'Only verified CC0 scenery GLBs copied into this evidence bundle; local FlightGear aircraft and Jeep binaries remain referenced at their registered paths.'})
    rows=['# Asset license evidence','', 'Local-use evidence inventory. Distribution decisions follow each registration manifest; this is not a license override.','', '| Asset | Declared license | Binary copied | Source |','|---|---|---|---|']
    for m in models:rows.append('| '+m['id']+' | '+str(m.get('license','unresolved')).replace('|','/')+' | '+('yes' if m.get('distribution_allowed') and m.get('license')=='CC0-1.0' else 'no; local reference only')+' | '+str(m.get('source_url','source archive in manifest'))+' |')
    rows+=['','PBR textures retain ambientCG source URLs, source file hashes and CC0 declarations in generated-map.json. Derived sample color/normal/roughness files preserve those source records.','WillysJeep README declares GPL v2 and identifies Detlef Faber. Its manifest records the exact README and archive hashes; no Jeep binary is copied into this bundle.','F4N exterior is a generic FlightGear F-4, explicitly not verified F-4N geometry. No War Thunder extraction or AI-invented aircraft geometry is used.']
    (out/'asset-license-report.md').write_text('\n'.join(rows)+'\n',encoding='utf8')
    for target in [out,out/'maps']:
        target.mkdir(parents=True,exist_ok=True)
        for file in ['generated-map.json','terrain.npz','sample_color.png','sample_normal.png','sample_roughness.png']:shutil.copy2(map_dir/file,target/file)
    shutil.copy2(ROOT/'game/recipes/training_range_v3.json',out/'scene-recipe.json')
    shutil.copy2(ROOT/'game/docs/multi-aircraft-ground-alpha.md',reports/'workflow.md')
    for name in ['core-final-noise-build.log','core-object-tests-build.log','core-object-tests.log','python-regression.log','legacy-smoke.log','telemetry-smoke.log','core-dependencies.log','renderer-final-build.log','diff-check.log','agent-checks.log','map-build.log']:
        if (work/name).exists():shutil.copy2(work/name,reports/name)
    binaries={str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'bvr_sim/build/Release/bvr_sim_cpp.cp314-win_amd64.pyd',ROOT/'game/build/Release/bvr_game_render.cp314-win_amd64.pyd']}
    write_json(reports/'build-manifest.json',{'native_viewers':'OFF','binaries':binaries,'cmake_cache':str(ROOT/'bvr_sim/build/CMakeCache.txt'),'core_dependencies':str(reports/'core-dependencies.log'),'git_commit_performed':False,'push_performed':False})
    (out/'core-object-migration-report.md').write_text('''# Core object migration

Terrain/TerrainTile and shared contacts live in simulator/environment.hxx/.cxx.
Mk82Bomb, ballistic_step and predict_ballistic_impact live in simulator/bomb/.
GameSession adapts release commands and scores actual core deaths. SimCore owns
aircraft environment collisions; vehicles, SAM sensors and motion belong to core.
There is no simulator include of GameSession.

Before changing physical surfaces, the directory/dependency migration replayed
321 complete GameFrame samples exactly, through tick 1603 and successful impact.
See reports/bomb-migration-baseline.json and bomb-migration-parity.json. That proof
is for the pure migration stage, before new snapshot fields/contact semantics.

Unchanged bomb constants: gravity 9.80665 m/s², v² drag coefficient 0.00003,
2 m release offset, 45 m blast radius. Existing missile speed/damage parameters
were not retuned. Live impact uses the shared predictor's integration and refines
surface intersection; the legacy predictor end-step convention was preserved.

Later intentional environment changes add raised drivable triangles, oriented
building/fence boxes, water exclusions and aircraft/core terrain collisions.
CCIP and bombs can now intersect real declared roofs/decks instead of riverbeds.
The Agent release check targets a footprint because a declared target base can
lie below its roof; it does not change physical impacts or damage.

Direct native tests create/advance bombs, vehicles and surfaces without any
GameSession: release prediction/live impact/damage/reclamation; route/turn/park/
resume/damage/reset/determinism; water/obstacle/slope blocking; raised bridge travel.
The SAM/missile ownership cycle is explicitly broken on pool cleanup and tested
with weak pointers. 49/49 native tests pass, including the legacy tests.

The real map vehicle test crosses the physical bridge above the unchanged riverbed.
SAM creates actual AIM-120 objects after core range/LOS observation and the original
firing gates. Its AIM-120 sensor adapter accepts the real SAM track; no weapon
speed/damage edits or fabricated hits were used.

Final full-frame parity exposed a separate RWR/MWS noise issue: DataObj used
random_device without resetting the generator. Core now accepts an optional noise
seed; GameSession resets it alongside the task seed and clears it on close.
Position/velocity noise remain nonzero with unchanged standard deviations and
independent streams. Unseeded legacy clients retain random-device behavior.
Native and Python regressions verify repeated noisy intermediate observations,
not only the final empty-warning outcome.
''',encoding='utf8')
    python=sys.executable
    (out/'Launch-Game.cmd').write_text('@echo off\ncd /d "'+str(ROOT)+'"\n"'+python+'" -m bvr_game play --map "'+str(map_dir/'generated-map.json')+'" --aircraft F22 --quality high\nif errorlevel 1 pause\n',encoding='utf8')
    return {'models':len(models),'aircraft':len(integration),'missions':len(missions),'map_sha256':sha(map_dir/'generated-map.json')}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);print(json.dumps(package(p.parse_args().output),indent=2))
