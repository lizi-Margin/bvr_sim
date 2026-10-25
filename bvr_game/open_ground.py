"""Offline alias-free ground means plus a pinned real microdetail material."""
from pathlib import Path
import copy,json
import numpy as np
from PIL import Image
from .content import sha
from .source_macro import to_linear
from .regional_cover import smooth_noise


class OpenGround:
    def __init__(self,file):
        self.policy=json.loads(Path(file).read_text(encoding='utf8'));p=self.policy
        if p.get('kind')!='source_grass_dry_mix':raise ValueError('Unsupported open-ground policy')
        self.means={}
        for role in ['green','dry']+(['soil'] if 'soil' in p else []):
            material=p[role]
            for slot in ['base_color','normal','roughness_map']:
                if sha(material[slot])!=material[slot+'_sha256']:raise ValueError('Open-ground source changed: '+slot)
            self.means[role]=to_linear(Image.open(material['base_color']).convert('RGB')).mean(axis=(0,1),dtype=np.float64)
        self.detail=copy.deepcopy(p['dry']);self.detail.update(tile_m=2.,strength=.45,
            mean_linear_luminance=float(self.means['dry']@np.array([.2126,.7152,.0722])))
        self.provenance={'policy_file':str(Path(file).resolve()),'policy_sha256':sha(file),'means_linear':{k:v.tolist() for k,v in self.means.items()},
            'helper_sha256':sha(__file__),'scope':'Source grass/dry-grass/optional soil linear means prefilter unresolved microtexture;authored world variation,no baked buildings or terrain shading. Actual2m source maps used separately for close detail.'}
        if p.get('variation'):
            v=p['variation']
            for key in ['dry_scale_m','soil_scale_m','brightness_scale_m','mottle_scale_m']:
                if not np.isfinite(v[key]) or not 20<=v[key]<=5000:raise ValueError('Invalid ground variation scale')
            for key,maximum in [('dry_range',1.),('brightness_range',2.)]:
                low,high=v[key]
                if not np.isfinite([low,high]).all() or not 0<=low<=high<=maximum:raise ValueError('Invalid ground variation range')
            if not 0<=v['soil_max']<=.8 or not 0<=v['mottle_strength']<=.5:raise ValueError('Invalid ground variation strength')
            if v['soil_max'] and 'soil' not in self.means:raise ValueError('Ground soil variation requires pinned real soil maps')

    def color_linear(self,north,west):
        seed=int(self.policy.get('seed',212))
        if self.policy.get('variation'):
            v=self.policy['variation'];low,high=v['dry_range']
            field=.65*smooth_noise(north,west,v['dry_scale_m'],seed)+.35*smooth_noise(north,west,v['mottle_scale_m'],seed+1)
            fraction=low+(high-low)*np.clip((field-.2)/.6,0,1)
            color=self.means['green']*(1-fraction[...,None])+self.means['dry']*fraction[...,None]
            if v['soil_max']:
                soil=v['soil_max']*np.clip((smooth_noise(north,west,v['soil_scale_m'],seed+3)-.45)/.25,0,1)
                color=color*(1-soil[...,None])+self.means['soil']*soil[...,None]
            low,high=v['brightness_range'];brightness=low+(high-low)*smooth_noise(north,west,v['brightness_scale_m'],seed+2)
            brightness*=1+v['mottle_strength']*(2*smooth_noise(north,west,v['mottle_scale_m'],seed+4)-1)
            return color*brightness[...,None]
        fraction=.30+.50*(.8*smooth_noise(north,west,500,seed)+.2*smooth_noise(north,west,85,seed+1))
        brightness=.85+.27*smooth_noise(north,west,1100,seed+2)
        return (self.means['green']*(1-fraction[...,None])+self.means['dry']*fraction[...,None])*brightness[...,None]
