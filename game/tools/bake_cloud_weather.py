"""Offline seeded volumetric-cloud coverage/type/rain data; no runtime noise generation."""
from pathlib import Path
import argparse,json,sys
import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import sha,write_json

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seed',type=int,default=144);p.add_argument('--tile-m',type=float,default=64000);p.add_argument('--size',type=int,default=1024)
    a=p.parse_args()
    if not 128<=a.size<=4096 or not 10000<=a.tile_m<=1000000:raise ValueError('Invalid weather-map dimensions')
    rng=np.random.default_rng(a.seed);axis=np.arange(a.size,dtype=float)/a.size;u,v=np.meshgrid(axis,axis)
    def noise(cells):
        grid=rng.uniform(0,1,(cells,cells))
        return np.clip(map_coordinates(grid,[v*cells,u*cells],order=3,mode='grid-wrap'),0,1)
    field=.5*noise(6)+.3*noise(24)+.2*noise(80)
    coverage=np.clip((field-.25)*1.65,0,1)
    kind=np.clip(.62+.3*noise(12),0,1)
    rain=np.zeros_like(coverage)
    rgba=np.stack([coverage,kind,rain,np.ones_like(coverage)],axis=2)
    a.output.mkdir(parents=True,exist_ok=False);file=a.output/'cloud-weather-rgba.png';Image.fromarray(np.round(rgba*255).astype(np.uint8)).save(file)
    write_json(a.output/'manifest.json',{'file':str(file.resolve()),'sha256':sha(file),'baker_sha256':sha(__file__),
        'seed':a.seed,'size':[a.size,a.size],'tile_m':a.tile_m,'weather_scale_per_m':1/a.tile_m,
        'channels':{'R':'coverage','G':'cloud type','B':'rain','A':'one'},'color_space':'linear data, no sRGB transfer',
        'coverage_mean':float(coverage.mean()),'scope':'Authored multiscale coverage data for the existing Wicked Engine volumetric marcher. Not a photograph or measured meteorology.'})
    print('BAKED_CLOUD_WEATHER',file,sha(file),flush=True)

if __name__=='__main__':main()
