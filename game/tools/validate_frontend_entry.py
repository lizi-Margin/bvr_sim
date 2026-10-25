"""Exercise ordinary play CLI defaults in a bounded native client process."""
from pathlib import Path
from unittest.mock import patch
import argparse,json,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,main as play_main,native
from bvr_game.content import write_json,sha

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=False)
def bounded_frame(game,event,dt,accumulator=0.):
    expected=json.loads((ROOT/'game/runtime-ui.json').read_text())['renderer_module']
    assert Path(game.r.__file__).parent==Path(expected)
    assert hasattr(game.renderer,'set_ui_font')
    images=[game.capture('normal-play-hangar')]
    game.frontend.open_settings();images.append(game.capture('normal-play-chinese-settings'))
    write_json(a.output/'entry-report.json',{'status':'passed','renderer':str(game.r.__file__),'renderer_sha256':sha(Path(game.r.__file__)),
        'core':str(native.__file__),'core_sha256':sha(Path(native.__file__)),
        'font':str(Path('C:/Windows/Fonts/msyh.ttc')),'font_sha256':sha(Path('C:/Windows/Fonts/msyh.ttc')),
        'captures':images,'scope':'Actual ordinary play CLI default runtime selection, native render and Chinese page capture; bounded frame hook closes only this owned test client. No OS keyboard injection.'})
    return False,0.
with patch.object(FlightGame,'run_client_frame',bounded_frame),patch.object(sys,'argv',
        ['bvr_game','play','--hidden','--map',str(ROOT/'game/maps/training.json'),'--output',str(a.output/'client')]):
    play_main()
print('DEFAULT_PLAY_CHINESE_RENDERER_PASSED',flush=True)
