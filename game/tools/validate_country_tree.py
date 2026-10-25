"""Render every country tree with actual client input, without starting a sortie."""
import argparse,json,os,sys
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,serialize
from bvr_game.aircraft_tree import countries,history
from bvr_game.content import sha,write_json

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime',type=Path,default=ROOT/'game/runtime-ui.json')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--width',type=int,default=1920);p.add_argument('--height',type=int,default=1080)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sorties')
    g=FlightGame(render=True,visible=False,runtime=a.runtime,width=a.width,height=a.height,
                 output=a.output/'client',user_settings=a.output/'preferences.json')
    captures=[]
    def event(keys=(),x=0,y=0):
        return g.input(SimpleNamespace(pressed=list(keys),held=[],x=x*a.width/1920,y=y*a.height/1080,quit=False,wheel=0),.02)
    def click(id):
        g.frontend.layout();_,(x,y,w,h),_=next(r for r in g.frontend.regions if r[0]==id)
        assert event([1],x+w/2,y+h/2)
    def capture(name):
        for _ in range(4):g.draw()
        return g.capture(name)
    try:
        before=serialize(g.sim.frame());config=serialize(g.config);seen=[]
        toggle_closed=capture('toggle-left-closed')
        click('tree_toggle');assert g.frontend.tree_open
        toggle_open=capture('toggle-left-open')
        assert sum(r[2]==('tree',) for r in g.frontend.regions)==1
        click('tree_toggle');assert not g.frontend.tree_open
        toggle_return=capture('toggle-left-return')
        assert serialize(g.sim.frame())==before and serialize(g.config)==config
        for c in countries(g.aircraft_rows):
            click('country_'+c['id']);assert g.frontend.tree_open
            rows=g.frontend.rows();assert len(rows)==c['count']
            assert all(history(r)['country']==c['id'] for r in rows)
            seen.extend(r['id'] for r in rows)
            top=capture('country-'+c['id'])
            event([35]);g.frontend.layout();bottom=capture('country-'+c['id']+'-last') if g.frontend.tree_scroll>0 else None
            captures.append({'country':c['id'],'label':c['label'],'aircraft':len(rows),'top':top,'bottom':bottom})
            assert serialize(g.sim.frame())==before and serialize(g.config)==config
        assert len(seen)==len(set(seen))==len(g.aircraft_rows)==152
        assert set(seen)=={r['id'] for r in g.aircraft_rows}
        event([27]);assert not g.frontend.tree_open
        assert g.renderer.shader_errors()==0
        write_json(a.output/'report.json',{'status':'passed','countries':captures,'aircraft':len(seen),
            'resolution':[a.width,a.height],'shader_errors':g.renderer.shader_errors(),
            'renderer_sha256':sha(Path(g.r.__file__)),'history_sha256':sha(ROOT/'bvr_game/data/aircraft_history.json'),
            'toggle_captures':[toggle_closed,toggle_open,toggle_return],
            'single_fixed_toggle_roundtrip_passed':True,
            'full_core_frame_unchanged':True,'scope':'Country browsing invokes actual client input and native DX12 captures. No OS key injection, model tuning or performance certification.'})
        print(json.dumps({'status':'passed','countries':len(captures),'aircraft':len(seen)}))
    finally:g.close()

if __name__=='__main__':main()
