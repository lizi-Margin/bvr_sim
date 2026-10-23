"""Reproducible native, input, legacy, headless/render, and performance validation."""
import argparse,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def main():
    p=argparse.ArgumentParser();p.add_argument('--render',action='store_true');p.add_argument('--output',type=Path,default=ROOT/'game/captures/validation');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    results=[]
    (ROOT/'scripts/test_logs').mkdir(parents=True,exist_ok=True)
    def run(name,args):
        start=time.perf_counter()
        with (out/(name+'.log')).open('w',encoding='utf8') as log:r=subprocess.run([str(x) for x in args],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        results.append({'name':name,'returncode':r.returncode,'seconds':time.perf_counter()-start});print(json.dumps(results[-1]),flush=True)
        (out/'checks.json').write_text(json.dumps(results,indent=2),encoding='utf8')
        if r.returncode:raise RuntimeError('Validation failed: '+name+'; see '+str(out/(name+'.log')))
    for name,args in [
        ('game_session',[sys.executable,'-m','unittest','discover','-s','scripts/tests','-p','test_game_session.py','-v']),
        ('flight_game',[sys.executable,'-m','unittest','discover','-s','scripts/tests','-p','test_flight_game.py','-v']),
        ('native',[ROOT/'bvr_sim/build/Release/bvr_sim_unit_tests.exe']),
        ('rl',[sys.executable,'-m','pytest','scripts/tests/test_bvr_sim_rl.py','-q']),
        ('legacy_game',[sys.executable,'scripts/tests/test_game_mode_smoke.py']),
        ('telemetry',[sys.executable,'scripts/tests/test_web_bridge_smoke.py'])]:run(name,args)
    for mission in ['air','strike','combined']:
        run('headless_'+mission,[sys.executable,'-m','bvr_game','run','--mission',mission,'--map',ROOT/'game/maps/training.json','--output',out/('headless_'+mission)])
        if a.render:
            run('render_'+mission,[sys.executable,'-m','bvr_game','run','--mission',mission,'--render','--hidden','--map',ROOT/'game/maps/training.json','--output',out/('render_'+mission)])
            headless=json.loads((out/('headless_'+mission)/(mission+'_report.json')).read_text())['frame']
            rendered=json.loads((out/('render_'+mission)/(mission+'_report.json')).read_text())['frame']
            if headless!=rendered:raise AssertionError('Rendering changed simulation frame: '+mission)
    if a.render:
        run('ui',[sys.executable,'game/tools/ui_acceptance.py','--output',out/'ui'])
        for quality in ['low','medium','high']:run('benchmark_'+quality,[sys.executable,'-m','bvr_game','benchmark','--hidden','--frames','300','--map',ROOT/'game/maps/training.json','--quality',quality,'--output',out/('benchmark_'+quality)])
    print('ALL CHECKS PASSED',flush=True)
if __name__=='__main__':main()
