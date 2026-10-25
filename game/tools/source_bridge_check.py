"""Read-only actual GLB/native placement versus typed shared bridge deck."""
from pathlib import Path
import json,struct
import numpy as np
from scipy.spatial import cKDTree
from bvr_game.content import ASSETS,sha


def check_source_bridge(game,output):
    doc=game.baked_scene.document;spec=doc['source_road_bake']['bridge'];item=spec['placement'];file=Path(spec['source_deck'])
    if not file.is_absolute():file=game.baked_scene.path.parent/file
    if sha(file)!=spec['source_deck_sha256']:raise ValueError('Source deck changed since baking')
    deck=json.loads(file.read_text());points=np.asarray(deck['vertices'])[:,[0,2,1]]
    version=doc['resource_versions'][item['model']];model=ASSETS/'registered'/item['model']/version['lods'][0]['file']
    if sha(model)!=version['lods'][0]['sha256']:raise ValueError('Registered bridge geometry changed')
    raw=model.read_bytes();size=struct.unpack_from('<I',raw,12)[0];g=json.loads(raw[20:20+size]);at=28+size
    vertices=[]
    for node in g['nodes']:
        if 'mesh' not in node:continue
        if not np.allclose(node.get('matrix',np.eye(4).ravel()),np.eye(4).ravel(),atol=1e-6) or not np.allclose(node.get('translation',[0,0,0]),0,atol=1e-6) or not np.allclose(node.get('scale',[1,1,1]),1,atol=1e-6) or not np.allclose(node.get('rotation',[0,0,0,1]),[0,0,0,1],atol=1e-6):raise ValueError('Bridge validation requires identity source mesh nodes')
        for primitive in g['meshes'][node['mesh']]['primitives']:
            if g['materials'][primitive['material']]['name']!='moscow_bridge_mats_road_overlay':continue
            accessor=g['accessors'][primitive['attributes']['POSITION']];view=g['bufferViews'][accessor['bufferView']]
            if accessor['componentType']!=5126 or accessor['type']!='VEC3':raise ValueError('Unsupported bridge position accessor')
            v=np.ndarray((accessor['count'],3),dtype='<f4',buffer=raw,offset=at+view.get('byteOffset',0)+accessor.get('byteOffset',0),strides=(view.get('byteStride',12),4)).astype(float)
            v[:,2]*=-1;vertices.append(v)
    registered=np.concatenate(vertices);error,nearest=cKDTree(registered).query(points)
    assert error.max()<.0002,('Source deck does not match actual registered GLB',error.max())
    # Feed actual model vertices through the native scene root transform.
    native_world=np.asarray(game.renderer.scenery_points(item['id'],registered[nearest].tolist()))[:,[2,0,1]]*np.array([1,-1,1])
    surface=next(s for s in doc['environment']['contact_surfaces'] if s['id']=='original_bridge_deck');core_vertices=np.asarray(surface['vertices'])
    maximum=float(abs(native_world-core_vertices).max());assert maximum<.002,maximum
    triangles=core_vertices[np.asarray(surface['indices']).reshape(-1,3)];centers=triangles.mean(axis=1)
    contacts=[game._terrain.contact(float(n),float(w),0.,float(h),.005) for n,w,h in centers]
    height_error=max(abs(c.height-p[2]) for c,p in zip(contacts,centers));assert height_error<1e-6 and not any(c.water for c in contacts)
    np.savez_compressed(Path(output)/'source-bridge-native-placement.npz',registered_local=registered[nearest],native_world_nwu=native_world,core_deck_vertices=core_vertices)
    return {'status':'passed','source_deck_sha256':sha(file),'registered_model_sha256':sha(model),'source_vertex_samples':len(points),
        'maximum_source_registered_vertex_error_m':float(error.max()),'maximum_native_transform_core_vertex_error_m':maximum,
        'maximum_core_contact_plane_error_m':height_error,'contact_centroid_samples':len(centers),
        'scope':'Actual registered GLB road vertices,native scene transform and typed core contact planes. Not GPU raster readback,rail/pier volume collision or full ground-driving certification.'}
