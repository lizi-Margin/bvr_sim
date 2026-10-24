"""Paused DX12 source-grove inspection at fixed near/far LODs and azimuths.

The isolated visual placement is deliberately above terrain to distinguish
card lighting from terrain contact and terrain shadows. It changes no core
object, source mesh, input or physical time. Diagnostic shader profiles must
be explicitly supplied; normal gameplay never selects them.
"""
from pathlib import Path
import argparse,json,math,os,sys
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import sha,write_json


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--map',type=Path,required=True)
    p.add_argument('--visual-profile',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--classify-normals',action='store_true',help='Only for a profile explicitly encoding up=green/down=red')
    p.add_argument('--expect-up',action='store_true',help='Assert<0.1percent down pixels; ONLY for the explicitly known-up-vector probe shader')
    p.add_argument('--normal-error-probe',action='store_true',help='Private shader: green=within1degree of original RGB normal, red=error')
    p.add_argument('--expect-rgb-match',action='store_true',help='Assert<0.1percent error pixels, with --normal-error-probe')
    p.add_argument('--split-rgb-probe',action='store_true',help='Private probe uses legacy RG decoding on left, full RGB on right; require the negative control to fail')
    p.add_argument('--views',type=int,default=12)
    a=p.parse_args()
    inspector_sha256=sha(Path(__file__))
    if a.expect_up and not a.classify_normals:p.error('--expect-up requires the known-vector normal diagnostic')
    if a.expect_rgb_match and not a.normal_error_probe:p.error('--expect-rgb-match requires --normal-error-probe')
    if a.normal_error_probe and a.classify_normals:p.error('Choose one explicitly matching diagnostic shader')
    if a.split_rgb_probe and not a.normal_error_probe:p.error('--split-rgb-probe requires --normal-error-probe')
    if not 4<=a.views<=36:raise ValueError('Use4..36 azimuths')
    if (a.output/'report.json').exists():raise FileExistsError(a.output/'report.json')
    a.output.mkdir(parents=True,exist_ok=True)
    document=json.loads(a.map.read_text(encoding='utf8'))
    document['terrain']['file']=str((a.map.parent/document['terrain']['file']).resolve())
    source=next(i for i in document['instances'] if i['model']=='fir_grove_normal_a')
    # Keep map/terrain resources as registered, replace only visual placements.
    source={**source,'id':'lighting_grove','position':[0,0,1500],
            'up_normal':[0,1,0],'yaw':0,'scale':1.,'lod_distance':100000.,'cull_distance':100000.}
    source.pop('grove_ground_fit',None)
    document['instances']=[source]
    diagnostic=a.output/'diagnostic-map.json';write_json(diagnostic,document)
    os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sortie-logs')
    from bvr_game.app import FlightGame,serialize
    g=FlightGame(render=True,visible=False,map_path=diagnostic,
                 visual_profile=a.visual_profile,output=a.output/'client')
    rows=[]
    try:
        g.select_aircraft('F16');g.config.mission='training';g.start()
        g.sim.set_paused(True);g.show_hud=False;g.quality='high';g.renderer.set_quality('high')
        initial=serialize(g.sim.frame())
        for lod in ['near','far']:
            source['lod_distance']=100000. if lod=='near' else 0.
            g.baked_scene.document['instances']=[source]
            g.baked_scene.configure(g.renderer,g.r,g.sim.terrain(),g.visual_profile)
            for index in range(a.views):
                angle=math.tau*index/a.views
                g.set_camera([120*math.sin(angle),1530,120*math.cos(angle)],[0,1510,0],.7)
                for _ in range(40):g.draw()
                capture=g.capture(f'{lod}-{index:02d}')
                image=Path(capture)
                row={'lod':lod,'azimuth_rad':angle,'capture':capture,'statistics':serialize(g.renderer.statistics())}
                if hasattr(g.renderer,'source_card_materials'):
                    row['source_card_materials']=serialize(g.renderer.source_card_materials())
                    if g.visual_profile.get('source_card_full_rgb_normals'):
                        assert row['source_card_materials'] and all(m['rgb_preserved'] for m in row['source_card_materials']),'Source normal blue channel was not preserved'
                if a.classify_normals or a.normal_error_probe:
                    rgb=np.asarray(Image.open(image).convert('RGB'),dtype=float)
                    # ACES transforms pure linear green toward yellow. Use
                    # signed channel dominance instead of a red/green ratio.
                    red=(rgb[:,:,0]>rgb[:,:,1]+30)&(rgb[:,:,0]>rgb[:,:,2]*2)&(rgb[:,:,0]>180)
                    green=(rgb[:,:,1]>rgb[:,:,0]+20)&(rgb[:,:,1]>rgb[:,:,2]*2)&(rgb[:,:,1]>180)
                    fraction=float(red.sum()/max(1,(red|green).sum()))
                    if a.normal_error_probe:
                        row.update(rgb_normal_error_pixels=int(red.sum()),rgb_normal_match_pixels=int(green.sum()),rgb_normal_error_fraction=fraction)
                        if a.split_rgb_probe:
                            mid=rgb.shape[1]//2
                            left=float(red[:,:mid].sum()/max(1,(red|green)[:,:mid].sum()))
                            right=float(red[:,mid:].sum()/max(1,(red|green)[:,mid:].sum()))
                            row.update(legacy_left_error_fraction=left,rgb_right_error_fraction=right)
                            if a.expect_rgb_match:assert left>.5 and right<.001,('RGB split probe failed',lod,index,left,right)
                        elif a.expect_rgb_match:assert fraction<.001,('RGB source normal mismatch',lod,index,fraction)
                    else:
                        row.update(up_pixels=int(green.sum()),down_pixels=int(red.sum()),down_fraction=fraction)
                    assert (red|green).sum()>1000,'Diagnostic shader/visible source-card pixels missing'
                    if a.expect_up:assert row['down_fraction']<.001,('Known upward probe inverted',lod,index,row['down_fraction'])
                rows.append(row)
                assert serialize(g.sim.frame())==initial,'Paused visual inspection changed core frame'
                assert g.renderer.shader_errors()==0
                print('VEGETATION_VIEW',lod,index,row.get('down_fraction','beauty'),flush=True)
        write_json(a.output/'report.json',{'source_map':str(a.map),'source_map_sha256':sha(a.map),
            'inspector_sha256':inspector_sha256,
            'visual_profile':str(a.visual_profile),'visual_profile_sha256':sha(a.visual_profile),
            'shader_sha256':sha(Path(g.visual_profile['shader_source'])/'objectHF.hlsli'),
            'source_asset':g.baked_scene.document['resource_versions']['fir_grove_normal_a'],
            'captures':rows,'shader_errors':g.renderer.shader_errors(),'core_frame_unchanged':True,
            'classification':'ACES signed channel dominance: red>green+30, green>red+20;dominant>180 and>2blue' if a.classify_normals or a.normal_error_probe else None,
            'expected_up_assertion':a.expect_up,
            'rgb_normal_match_assertion':a.expect_rgb_match,
            'split_rgb_probe':a.split_rgb_probe,
            'vram':serialize(g.renderer.memory_usage()),
            'scope':'Actual paused renderer, isolated unmodified source grove, matched camera/illumination and forced LOD; not natural-forest, flight, terrain-contact or performance acceptance.'})
    finally:g.close()


if __name__=='__main__':main()
