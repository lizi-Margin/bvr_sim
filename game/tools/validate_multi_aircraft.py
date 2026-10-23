"""Exercise real hangar click/scroll handling, actual previews and sortie/reset for five catalog aircraft."""
from pathlib import Path
import argparse,json,sys
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,serialize
from bvr_game.aircraft import aircraft_catalog

def validate(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    game=FlightGame(render=True,visible=False,map_path=ROOT/'game/maps/training_range_v3/generated-map.json',output=out/'after/aircraft')
    records=[]
    def event(pressed=(),x=200,y=200,wheel=0):
        return game.input(SimpleNamespace(held=[],pressed=list(pressed),x=x,y=y,wheel=wheel,quit=False),.02)
    try:
        game.quality='high';game.renderer.set_quality('high');game.config.enemy_attacks=False
        for index,row in enumerate(game.aircraft_rows[:5]):
            assert row['available'],row['id']+': '+row['unavailable_reason']
            while game.aircraft_scroll>0:event(wheel=1)
            while index>=game.aircraft_scroll+4:event(wheel=-1)
            slot=index-game.aircraft_scroll;event([1],x=200,y=180+slot*74+22)
            assert game.config.player_model==row['id']
            assert game.player().model==row['simulation_model'] and game.mode=='hangar'
            for _ in range(15):game.draw()
            preview=game.capture('hangar_'+row['id'])
            event([13]);game.command(throttle=.85);game.step(10)
            assert game.player().model==row['simulation_model'] and game.mode=='flight'
            for _ in range(8):game.draw()
            flight=game.capture('flight_'+row['id'])
            records.append({'id':row['id'],'preview':preview,'flight':flight,'frame':serialize(game.sim.frame()),'selection':'click through same handler as native window; F4 requires actual wheel scroll','asset':row['appearance'],'shader_errors':game.renderer.shader_errors(),'aircraft_statistics':serialize(game.renderer.aircraft_statistics()),'aircraft_import_counts':serialize(game.renderer.aircraft_import_counts())})
            event([27]);assert game.mode=='hangar'
        first=game.aircraft_rows[0];event([49]);assert game.config.player_model==first['id']
        event([13]);assert game.sim.frame().tick==0;game.step(5);event([27]);game.draw()
        stats=serialize(game.renderer.aircraft_statistics()) if hasattr(game.renderer,'aircraft_statistics') else {}
        counts=serialize(game.renderer.aircraft_import_counts())
        for row in game.aircraft_rows[:5]:
            game.select_aircraft(row['id']);game.draw();event([13]);game.step(5);game.draw();event([27]);game.draw()
        after_stats=serialize(game.renderer.aircraft_statistics());after_counts=serialize(game.renderer.aircraft_import_counts())
        cache_stable=counts==after_counts and all(stats[k]==after_stats[k] for k in ['cached_models','mesh_resources','material_resources'])
        assert cache_stable,'Switching/reset re-imported meshes or leaked shared resources'
        report={'status':'passed','aircraft':records,'reset_and_change_aircraft':'passed','cache_stable':cache_stable,'imports_before':counts,'imports_after':after_counts,'aircraft_statistics':stats,'statistics_after_repeated_switching':after_stats,'shader_errors':game.renderer.shader_errors(),'catalog':aircraft_catalog()}
        p=out/'reports/aircraft-menu-probe.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(report,indent=2),encoding='utf8')
        assert game.renderer.shader_errors()==0
        print(json.dumps({'status':'passed','aircraft':[r['id'] for r in records],'statistics':stats}),flush=True)
    finally:game.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);validate(p.parse_args().output)
