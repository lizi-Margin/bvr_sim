"""Real DX12 material comparison, using a fresh renderer for each saved probe."""
from pathlib import Path
import argparse,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import sha,write_json

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--maps',type=Path,nargs='+',required=True)
    p.add_argument('--runtime',type=Path,default=ROOT/'game/runtime.json');p.add_argument('--visual-profile',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--views',nargs='+',default=['bridge_oblique'])
    p.add_argument('--warmup-frames',type=int,default=8);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    reports=[]
    for number,file in enumerate(a.maps):
        output=a.output/str(number)
        subprocess.run([sys.executable,str(ROOT/'game/tools/capture_reference_map.py'),'--map',str(file),
            '--runtime',str(a.runtime),'--visual-profile',str(a.visual_profile),'--output',str(output),
            '--views',*a.views,'--warmup-frames',str(a.warmup_frames),'--render-scale','2'],check=True)
        reports.append(json.loads((output/'report.json').read_text(encoding='utf8')))
        write_json(a.output/'progress.json',{'reports':reports})
    for key in ['renderer_sha256','core_sha256']:
        assert len({report[key] for report in reports})==1,'Comparison runtime changed'
    assert all(report['shader_errors']==0 for report in reports)
    write_json(a.output/'report.json',{'status':'rendered_pending_visual_review','reports':reports,
        'tool_sha256':sha(__file__),'scope':'Fresh native renderer per map to isolate material changes from map-switch state. Same runtime/profile/cameras;bounded diagnostic,not full-map acceptance or measured BRDF.'})
if __name__=='__main__':main()
