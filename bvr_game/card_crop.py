"""Tighten source cards without discarding any nonzero source opacity."""
import copy,hashlib,io,json,struct
from pathlib import Path
import numpy as np
from PIL import Image
from .content import ASSETS,sha


def crop_rectangle(albedo,normal,padding=8):
    if albedo.shape!=normal.shape or albedo.ndim!=3 or albedo.shape[2]!=4:raise ValueError('Matching RGBA source images required')
    h,w=albedo.shape[:2]
    if padding<1 or any(s<1 or s&(s-1) for s in [h,w]):raise ValueError('Power-of-two source and positive border required')
    ys,xs=np.where((albedo[:,:,3]>0)|(normal[:,:,3]>0))
    if not len(xs):raise ValueError('Source card is entirely transparent')
    def axis(values,total):
        lo,hi=int(values.min()),int(values.max())+1
        span=min(total,1<<((hi-lo+2*padding-1).bit_length()))
        first=max(0,min(total-span,(lo+hi-span)//2))
        assert first<=lo and first+span>=hi
        return first,span
    x,width=axis(xs,w);y,height=axis(ys,h)
    return x,y,width,height


def reparameterize_quad(position,uv,rectangle,source_size):
    """Return a tighter planar quad; preserve every retained source UV point."""
    if position.shape!=(4,3) or uv.shape!=(4,2) or len(np.unique(uv,axis=0))!=4 or not np.all((uv==0)|(uv==1)):raise ValueError('Four unit-square source card corners required')
    basis=np.column_stack([np.ones(4),uv]);transform=np.linalg.lstsq(basis,position,rcond=None)[0]
    if np.max(np.abs(basis@transform-position))>1e-4:raise ValueError('Source card is not planar affine geometry')
    x,y,w,h=rectangle;sw,sh=source_size;source_uv=uv*np.array([w/sw,h/sh])+np.array([x/sw,y/sh])
    return (np.column_stack([np.ones(4),source_uv])@transform).astype('<f4')


def crop_glb(data):
    if struct.unpack_from('<III',data)!=(0x46546c67,2,len(data)):raise ValueError('Expected GLB2')
    size,kind=struct.unpack_from('<II',data,12)
    if kind!=0x4e4f534a:raise ValueError('Expected GLB JSON')
    doc=json.loads(data[20:20+size]);length,kind=struct.unpack_from('<II',data,20+size)
    if kind!=0x004e4942 or len(doc['buffers'])!=1:raise ValueError('Expected one embedded GLB buffer')
    blob=bytearray(data[28+size:28+size+length]);original=copy.deepcopy(doc);records=[]
    def append(raw):
        blob.extend(b'\0'*(-len(blob)%4));index=len(doc['bufferViews']);doc['bufferViews'].append({'buffer':0,'byteOffset':len(blob),'byteLength':len(raw)});blob.extend(raw);return index
    def accessor(index):
        item=doc['accessors'][index];view=doc['bufferViews'][item['bufferView']]
        if item['componentType']!=5126 or view.get('byteStride') or item.get('sparse'):raise ValueError('Expected packed float source card attributes')
        count={'VEC2':2,'VEC3':3}[item['type']];offset=view.get('byteOffset',0)+item.get('byteOffset',0)
        return np.frombuffer(blob,dtype='<f4',count=item['count']*count,offset=offset).reshape(-1,count).copy()
    def image(index):
        view=doc['bufferViews'][doc['images'][index]['bufferView']];start=view.get('byteOffset',0);raw=bytes(blob[start:start+view['byteLength']]);return np.asarray(Image.open(io.BytesIO(raw)).convert('RGBA')),raw
    used=set()
    for mesh in doc['meshes']:
        for primitive in mesh['primitives']:
            material=doc['materials'][primitive['material']];name=material.get('name','')
            if not name.startswith('source_impostor_'):continue
            slots=[material['pbrMetallicRoughness']['baseColorTexture']['index'],material['normalTexture']['index']];indices=[doc['textures'][i]['source'] for i in slots]
            if any(i in used for i in indices):raise ValueError('Shared source card image needs an explicit separate view')
            used.update(indices);(color,color_png),(normal,normal_png)=[image(i) for i in indices]
            rect=crop_rectangle(color,normal);x,y,w,h=rect;sh,sw=color.shape[:2]
            attrs=primitive['attributes'];positions=accessor(attrs['POSITION']);uv=accessor(attrs['TEXCOORD_0']);anchors=accessor(attrs['TEXCOORD_1']);result=positions.copy();max_error=0
            for tree in np.unique(anchors[:,0]):
                mask=anchors[:,0]==tree
                if mask.sum()!=4 or not np.all(anchors[mask]==anchors[mask][0]):raise ValueError('One source quad per tree and primitive required')
                result[mask]=reparameterize_quad(positions[mask],uv[mask],rect,(sw,sh))
                # Independent sampled oldUV->newUV->world comparison, including
                # interior texel centres. Quantization is float32 mesh storage.
                old_basis=np.column_stack([np.ones(4),uv[mask]]);old_transform=np.linalg.lstsq(old_basis,positions[mask],rcond=None)[0];new_transform=np.linalg.lstsq(old_basis,result[mask],rcond=None)[0]
                local=np.array([[0,0],[1,0],[0,1],[1,1],[.37,.61]]);expected=np.column_stack([np.ones(5),local*np.array([w/sw,h/sh])+np.array([x/sw,y/sh])])@old_transform
                actual=np.column_stack([np.ones(5),local])@new_transform;max_error=max(max_error,float(np.max(np.abs(expected-actual))))
            if max_error>1e-4:raise ValueError('Source crop pixel spatial correspondence exceeded0.1mm')
            item=doc['accessors'][attrs['POSITION']];item['bufferView']=append(result.tobytes());item.pop('byteOffset',None);item['min']=result.min(axis=0).tolist();item['max']=result.max(axis=0).tolist()
            image_records=[]
            for index,rgba,raw in zip(indices,[color,normal],[color_png,normal_png]):
                cropped=np.ascontiguousarray(rgba[y:y+h,x:x+w]);assert int(cropped[:,:,3].sum())==int(rgba[:,:,3].sum())
                encoded=io.BytesIO();Image.fromarray(cropped).save(encoded,format='PNG');doc['images'][index]['bufferView']=append(encoded.getvalue())
                image_records.append({'source_png_sha256':hashlib.sha256(raw).hexdigest(),'source_rgba_sha256':hashlib.sha256(rgba.tobytes()).hexdigest(),'cropped_rgba_sha256':hashlib.sha256(cropped.tobytes()).hexdigest(),'source_alpha_integer_sum':int(rgba[:,:,3].sum()),'cropped_alpha_integer_sum':int(cropped[:,:,3].sum())})
            records.append({'material':name,'source_dimensions':[sw,sh],'rectangle_xywh':list(rect),'quad_area_ratio':w*h/(sw*sh),'trees':len(np.unique(anchors[:,0])),'maximum_source_pixel_position_error_m':max_error,'images':image_records})
    if not records:raise ValueError('No marked source cards')
    # UV0, normals, indices, UV1 and every non-card accessor remain byte exact;
    # changing a quad's extent alone changes its physical source-UV mapping.
    blob.extend(b'\0'*(-len(blob)%4));doc['buffers'][0]['byteLength']=len(blob);encoded=json.dumps(doc,separators=(',',':')).encode();encoded+=b' '*(-len(encoded)%4)
    output=struct.pack('<III',0x46546c67,2,28+len(encoded)+len(blob))+struct.pack('<II',len(encoded),0x4e4f534a)+encoded+struct.pack('<II',len(blob),0x004e4942)+blob
    return output,{'source_glb_sha256':hashlib.sha256(data).hexdigest(),'cropped_glb_sha256':hashlib.sha256(output).hexdigest(),'materials':records,'unchanged_mesh_count':len(original['meshes'])}


def verify_variant(source_id,variant_id):
    """Recompute the narrow derivation; metadata alone never permits a swap."""
    for name in [source_id,variant_id]:
        if not name.replace('_','').replace('-','').isalnum():raise ValueError('Invalid registered asset id')
    source=ASSETS/'registered'/source_id;variant=ASSETS/'registered'/variant_id
    a=json.loads((source/'manifest.json').read_text());b=json.loads((variant/'manifest.json').read_text());crop=b.get('source_card_crop',{})
    if crop.get('source_asset')!=source_id or crop.get('source_manifest_sha256')!=sha(source/'manifest.json'):raise ValueError('Crop variant source version mismatch')
    if any(a[key]!=b[key] for key in ['cluster','bounds_blender','faces','triangles']):raise ValueError('Crop variant cannot change source poses, anchors, faces or conservative bounds')
    if len(a['lods'])!=len(b['lods']):raise ValueError('Crop variant LOD count differs')
    for old,new in zip(a['lods'],b['lods']):
        if any(old[k]!=new[k] for k in old if k!='sha256'):raise ValueError('Crop variant LOD declaration differs')
        if sha(source/old['file'])!=old['sha256']:raise ValueError('Source GLB changed')
        expected,_=crop_glb((source/old['file']).read_bytes())
        if hashlib.sha256(expected).hexdigest()!=new['sha256'] or sha(variant/new['file'])!=new['sha256']:raise ValueError('Crop variant GLB does not match the exact derivation')
    return True
