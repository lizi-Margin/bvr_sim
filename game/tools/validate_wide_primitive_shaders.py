"""Compile actual producer/consumer shaders before rendering direct64-bit IDs."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import argparse,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import write_json,sha

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--dxc',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    jobs=[(name,'vs_6_0',[]) for name in ['objectVS_prepass','objectVS_prepass_alphatest','objectVS_common']]
    jobs += [(name,'ps_6_0',[]) for name in ['objectPS_prepass','objectPS_prepass_alphatest','objectPS','hairparticlePS_prepass','impostorPS_prepass']]
    jobs += [('objectPS','ps_6_0',['WATER=1'])]
    for name in ['visibility_resolveCS','visibility_velocityCS','visibility_surfaceCS']:
        jobs += [(name,'cs_6_0',[]),(name,'cs_6_0',['PRIMITIVEID_UNIFORM=1'])]
    jobs += [('visibility_analyzeCS','cs_6_0',[]),('visibility_analyzeCS','cs_6_0',['PRIMITIVEID_MSAA=1'])]
    jobs += [(name,'cs_6_6',[]) for name in ['mesh_blend_prepareCS','mesh_blend_expandCS','rtaoCS','surfel_coverageCS']]
    jobs += [(name,'vs_6_0',[]) for name in ['hairparticleVS','impostorVS']]
    jobs += [('visibility_resolveCS','cs_6_0',['MATERIAL_BINNING=1']),
             ('visibility_resolveCS','cs_6_0',['MATERIAL_BINNING=1','PRIMITIVEID_UNIFORM=1'])]
    jobs += [('visibility_shadeCS','cs_6_0',defines) for defines in [[],['CLEARCOAT=1'],['UNLIT=1'],['PRIMITIVEID_UNIFORM=1']]]
    def compile(job):
        name,profile,defines=job;key=name+('-'+'-'.join(d.replace('=','_') for d in defines) if defines else '')
        source=a.source/(name+'.hlsl');command=[str(a.dxc),'-T',profile,'-E','main','-I',str(a.source),
            '-rootsig-define','WICKED_ENGINE_DEFAULT_ROOTSIGNATURE','-Wno-conversion','-Fo',str(a.output/(key+'.cso'))]
        for define in defines:command+=['-D',define]
        result=subprocess.run(command+[str(source)],capture_output=True,text=True)
        (a.output/(key+'.log')).write_text(result.stdout+result.stderr,encoding='utf8')
        return {'shader':name,'profile':profile,'defines':defines,'exit_code':result.returncode,'source_sha256':sha(source)}
    with ThreadPoolExecutor(max_workers=4) as executor:results=list(executor.map(compile,jobs))
    failed=[r for r in results if r['exit_code']]
    write_json(a.output/'report.json',{'status':'failed' if failed else 'passed','results':results,'failures':failed,
        'scope':'Actual DXC producer/consumer compilation,including divergent geometry and uniform sky paths. No rendered correctness or visual acceptance claim.'})
    print('WIDE_SHADER_COMPILATION',len(results),'FAILED',len(failed),flush=True)
    if failed:raise SystemExit(1)
if __name__=='__main__':main()
