"""Configure/build optional game and convert the two reviewed aircraft recipes."""
import argparse,json,shutil,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
WICKED_REV='fb6aaa4e79fd6861697f1e52d604d1e23404d594'
def run(*args):subprocess.run([str(a) for a in args],check=True)
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine-root',type=Path,required=True);p.add_argument('--engine-build',type=Path,required=True);p.add_argument('--aircraft-root',type=Path,required=True);p.add_argument('--addon-root',type=Path,required=True)
    p.add_argument('--blender',default=r'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe');p.add_argument('--cmake',default=shutil.which('cmake') or r'C:\Program Files\CMake\bin\cmake.exe');p.add_argument('--skip-build',action='store_true');p.add_argument('--legacy-only',action='store_true')
    a=p.parse_args();engine=a.engine_root.resolve();build=a.engine_build.resolve();addon=a.addon_root.resolve();aircraft=a.aircraft_root.resolve()
    if not engine.exists():run('git','clone','https://github.com/turanszkij/WickedEngine.git',engine);run('git','-C',engine,'checkout',WICKED_REV)
    rev=subprocess.check_output(['git','-C',str(engine),'rev-parse','HEAD'],text=True).strip()
    if rev!=WICKED_REV:raise RuntimeError('Wicked Engine version differs from validated revision: '+rev)
    if not (addon/'io_scene_ac3d').is_dir():raise FileNotFoundError('Install https://github.com/NikolaiVChr/Blender-AC3D at cf7fc194c547bc96486dc1c5147371e642143037 and pass its root')
    if not a.skip_build:
        run(a.cmake,'-S',engine,'-B',build,'-A','x64','-DWICKED_EDITOR=OFF','-DWICKED_TESTS=OFF','-DWICKED_IMGUI_EXAMPLE=OFF','-DWICKED_WINDOWS_TEMPLATE=ON','-DWICKED_EMBED_SHADERS=OFF','-DWICKED_ENABLE_RTTI=ON')
        run(a.cmake,'--build',build,'--config','Release','--target','Template_Windows','--parallel','4')
        run(a.cmake,'-S',ROOT/'bvr_sim','-B',ROOT/'bvr_sim/build','-A','x64','-DBVR_SIM_BUILD_NATIVE_VIEWERS=OFF','-DBVR_SIM_ENABLE_NATIVE_OPTIMIZATIONS=OFF','-DPYBIND11_FINDPYTHON=ON','-DPython3_EXECUTABLE='+sys.executable)
        run(a.cmake,'--build',ROOT/'bvr_sim/build','--config','Release','--target','bvr_sim_cpp','--parallel','4')
        run(a.cmake,'-S',ROOT/'game/native','-B',ROOT/'game/build','-A','x64','-DWICKED_SOURCE='+str(engine),'-DWICKED_BUILD='+str(build),'-DPython3_EXECUTABLE='+sys.executable)
        run(a.cmake,'--build',ROOT/'game/build','--config','Release','--parallel','4')
    models={}
    for id,package,filename,hide,span in [('F22','Lockheed-Martin-FA-22A-Raptor','Lockheed-Martin-FA-22A-Raptor.ac',['landing-gear'],[18,20]),('F16','f16','f16.ac',['LandingGear','Chute','ExternalFlame','FanSpinning','FanRHighSpeed','FanRHighSpeed.001'],[14,17])]:
        source=aircraft/package/'Models'/filename
        if not source.exists():
            run(sys.executable,HERE/'asset_library.py','fetch','aircraft',package,'--max-mb','700')
            unpacked=ROOT/'game/assets/cache/aircraft'/package/package
            if not unpacked.is_dir():raise FileNotFoundError('Unexpected aircraft archive layout: '+str(unpacked))
            shutil.copytree(unpacked,aircraft/package,dirs_exist_ok=True)
        out=ROOT/'game/assets/registered'/id
        recipe={'id':id,'source':str(source),'addon_root':str(addon),'output':str(out),'blender_z_rotation_deg':-90,'hide_roots':hide,'length_range_m':span,'source_url':'ssh://hulc@172.24.147.18:1145/home/hulc/Aircraft-2024/'+package+'.zip','license':'GPL-2.0; retain package notices'}
        out.mkdir(parents=True,exist_ok=True);r=out/'recipe_input.json';r.write_text(json.dumps(recipe),encoding='utf8')
        run(a.blender,'--background','--python-exit-code','1','--python',HERE/'convert_aircraft.py','--',r)
        models[id]=str(out/(id+'.glb'))
        notice=source.parents[1]/'LICENSE' if id=='F16' else source.parent/'F-22-JSBSIM-Model-File.xml'
        shutil.copy2(notice,out/notice.name)
    runtime={'engine_source':str(engine),'engine_revision':rev,'shader_cache':str((ROOT/'game/assets/cache/shaders').resolve()),'renderer_module':str((ROOT/'game/build/Release').resolve()),'models':models}
    (ROOT/'game/runtime.json').write_text(json.dumps(runtime,indent=2),encoding='utf8')
    run(sys.executable,HERE/'asset_library.py','fetch','polyhaven','concrete_road_barrier_02','--resolution','1k')
    cache=ROOT/'game/assets/cache'
    run(sys.executable,HERE/'assets.py','register','road_barrier','--entry',cache/'polyhaven/concrete_road_barrier_02/concrete_road_barrier_02_1k.gltf','--manifest',cache/'polyhaven/concrete_road_barrier_02/manifest.json','--blender',a.blender)
    run(sys.executable,HERE/'asset_library.py','fetch','ambientcg','Asphalt033','--resolution','1k')
    runtime=json.loads((ROOT/'game/runtime.json').read_text(encoding='utf8'))
    runtime['asphalt_texture']=str(cache/'ambientcg/Asphalt033/unpacked/Asphalt033_1K-JPG_Color.jpg')
    run(sys.executable,HERE/'asset_library.py','fetch','ambientcg','Grass001','--resolution','1k')
    runtime['terrain_texture']=str(cache/'ambientcg/Grass001/unpacked/Grass001_1K-JPG_Color.jpg')
    (ROOT/'game/runtime.json').write_text(json.dumps(runtime,indent=2),encoding='utf8')
    if not a.legacy_only:
        for material in ['Ground072','Ground068','Rock048']:run(sys.executable,HERE/'asset_library.py','fetch','ambientcg',material,'--resolution','1k')
        sys.path.insert(0,str(ROOT))
        from bvr_game.catalog import prepare
        prepare(blender=a.blender,rebuild=True)
        run(sys.executable,HERE/'bake_audio.py')
        run(sys.executable,HERE/'enrich_inventory.py')
        run(sys.executable,'-m','bvr_game.worldgen')
    print('Ready: python -m bvr_game play'+(' --map game/maps/training.json' if a.legacy_only else ''))
if __name__=='__main__':main()
