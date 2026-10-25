"""Offline NWU sampling of retained landclass weights and original color tiles."""
from pathlib import Path
import json
import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates
from .content import sha


def to_linear(color):
    color=np.asarray(color,dtype=np.float32)/255
    return np.where(color<=.04045,color/12.92,((color+.055)/1.055)**2.4)


def to_srgb(color):
    color=np.asarray(color)
    return np.clip(np.where(color<=.0031308,color*12.92,1.055*np.maximum(color,0)**(1/2.4)-.055)*255+.5,0,255).astype(np.uint8)


def weight_coordinates(north,west,cell_side=128):
    """Original per-cell clamping; archive rows are W, columns are N."""
    n,w=np.broadcast_arrays(north,west)
    coordinates=[]
    for axis in [w,n]:
        pixel=(axis+65536)/32
        start=np.floor(pixel/cell_side)*cell_side
        coordinates.append(np.clip(pixel-.5,start,start+cell_side-1))
    return coordinates


class SourceMacro:
    def __init__(self,class_report,macro_report,texture_report):
        paths=[Path(p) for p in [class_report,macro_report,texture_report]]
        classes,macro,textures=[json.loads(p.read_text(encoding='utf8')) for p in paths]
        if sha(paths[0])!=macro['class_report_sha256'] or sha(paths[2])!=macro['texture_report_sha256']:
            raise ValueError('Source class/texture reports differ from the retained weight bake')
        if sha(macro['weights'])!=macro['weights_sha256']:raise ValueError('Source weight archive changed')
        self.weights=np.load(macro['weights'],allow_pickle=False)['weights'].astype(np.float32)/255
        self.cell_side=classes['texture_size'];self.definitions=[]
        decoded={Path(x['source']).stem:x for x in textures['textures'] if x['status']=='decoded'}
        for row in classes['classes']:
            params={x['name']:x['value'] for x in row['parameters']}
            item=decoded[params['texture'].rstrip('*')]
            if sha(item['png'])!=item['png_sha256']:raise ValueError('Source class color changed')
            self.definitions.append({'name':row['name'],'image':to_linear(Image.open(item['png']).convert('RGB')),
                'size':params['size'],'offset':params.get('offset',[0,0]),'source':item})
        self.provenance={'reports':[{ 'file':str(p.resolve()),'sha256':sha(p)} for p in paths],
            'weights_sha256':macro['weights_sha256'],
            'materials':[{k:v for k,v in d.items() if k!='image'} for d in self.definitions]}

    def sample_linear(self,north,west):
        n,w=np.broadcast_arrays(north,west)
        if ((n<-65536)|(n>=65536)|(w<=-65536)|(w>65536)).any():
            raise ValueError('Macro samples outside retained source extent')
        coordinates=weight_coordinates(n,w,self.cell_side)
        result=np.zeros((*n.shape,3),dtype=np.float32);total=np.zeros(n.shape,dtype=np.float32)
        # Source X=-W, Z=N. Source color UV is (X/size,-Z/size),
        # independently of the positive-Z placement density bitmap convention.
        for index,d in enumerate(self.definitions):
            weight=map_coordinates(self.weights[...,index],coordinates,order=1,mode='nearest',prefilter=False)
            u=np.mod((-w-d['offset'][0])/d['size'][0],1)*d['image'].shape[1]-.5
            v=np.mod(-(n-d['offset'][1])/d['size'][1],1)*d['image'].shape[0]-.5
            color=np.stack([map_coordinates(d['image'][...,c],[v,u],order=1,mode='grid-wrap',prefilter=False) for c in range(3)],axis=-1)
            result+=color*weight[...,None];total+=weight
        return result/np.maximum(total[...,None],1e-6)
