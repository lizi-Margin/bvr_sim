"""Blender: immutable source grove plus per-tree source-albedo/normal far cards.

The original high-detail GLB is copied byte-for-byte. Every far tree retains the
original grove slot, yaw, scale and UV1 tree index; no placement is discarded.
"""
import argparse,copy,hashlib,json,re,shutil,sys
from pathlib import Path
import bpy
from mathutils import Matrix,Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
from vegetation_lod import impostors,make_cluster,alpha_mask_glb,triangles

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--id',required=True);p.add_argument('--resolution',type=int,default=512)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    if not re.fullmatch(r'[A-Za-z0-9_-]+',a.id):p.error('Invalid immutable asset ID')
    if not 128<=a.resolution<=2048 or a.resolution&(a.resolution-1):p.error('Resolution must be power-of-two128..2048')
    parent=json.loads(a.parent.read_text(encoding='utf8'))
    a.output.mkdir(parents=True,exist_ok=False)
    source=Path(parent['conversion_recipe']['source']);policy=parent['conversion_recipe']['policy']
    if sha(source)!=parent['source_sha256']:raise ValueError('Original single-tree source changed')
    bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(source))
    objects=[o for o in bpy.context.scene.objects if o.type=='MESH'];bpy.context.view_layer.update()
    points=[o.matrix_world@Vector(c) for o in objects for c in o.bound_box]
    lo=[min(v[i] for v in points)for i in range(3)];hi=[max(v[i] for v in points)for i in range(3)]
    transform=Matrix.Translation(Vector((-(lo[0]+hi[0])/2,-(lo[1]+hi[1])/2,-lo[2])))
    for o in objects:world=o.matrix_world.copy();o.parent=None;o.matrix_world=transform@world
    height=hi[2]-lo[2];width=max(hi[i]-lo[i]for i in range(2))
    # Use the exact original per-axis normalization, including buried roots.
    normalized=([-(hi[0]-lo[0])/2,-(hi[1]-lo[1])/2,0],[(hi[0]-lo[0])/2,(hi[1]-lo[1])/2,height])
    anchor=list(transform@Vector(policy['source_ground_anchor_blender']))
    cards,bake=impostors(objects,a.output/'source-bake',height,width,a.resolution,'CYCLES',normal_maps=True)
    far,bounds,cluster=make_cluster(cards,policy['cluster'],anchor,normalized)
    old=parent['cluster']
    for key in ['recentering','source_base_anchor_blender','poses_before_recentering']:
        if json.dumps(cluster[key],sort_keys=True)!=json.dumps(old[key],sort_keys=True):
            def flatten(x):
                if isinstance(x,dict):return [v for k in sorted(x)for v in flatten(x[k])]
                if isinstance(x,list):return [v for y in x for v in flatten(y)]
                return [x]
            if max(abs(x-y)for x,y in zip(flatten(cluster[key]),flatten(old[key])))>1e-5:
                raise ValueError('Far source anchors/poses differ: '+key)
    # Original high-detail bytes and all original per-tree bounds are retained.
    result=copy.deepcopy(parent);result['id']=a.id;result['name']=parent['name']+' with source-derived distance LOD'
    result['file']=a.id+'.glb';near=a.output/result['file'];shutil.copy2(a.parent.parent/parent['file'],near)
    if sha(near)!=parent['glb_sha256']:raise ValueError('Near source geometry changed')
    for original,new in zip(result['cluster']['ground_conform']['tree_bounds_relative_blender'],cluster['ground_conform']['tree_bounds_relative_blender']):
        for axis in range(3):original['min'][axis]=min(original['min'][axis],new['min'][axis]);original['max'][axis]=max(original['max'][axis],new['max'][axis])
    bpy.ops.object.select_all(action='DESELECT')
    for o in far:o.hide_set(False);o.hide_render=False;o.select_set(True)
    bpy.context.view_layer.objects.active=far[0];bpy.ops.object.join();far=[bpy.context.view_layer.objects.active]
    target=a.output/(a.id+'_lod1.glb')
    bpy.ops.export_scene.gltf(filepath=str(target),export_format='GLB',use_selection=True,export_extras=True)
    alpha_mask_glb(target)
    result['lods']=[{'level':0,'file':near.name,'sha256':sha(near),'triangles':parent['triangles']},
                    {'level':1,'file':target.name,'sha256':sha(target),'triangles':triangles(far)}]
    result['impostor']={'view_facing_alpha':True,'source_tree_bake':bake,'requires_directional_view_selection':False,
        'method':'Three vertical source views plus top view per tree. Source-derived silhouette/normal approximation at distance; no whole-grove billboard.'}
    result['source_distance_lod']={'parent_asset':parent['id'],'parent_manifest_sha256':sha(a.parent),
        'high_detail_bytes_unchanged':True,'source_tree_positions_unchanged':True,'far_triangles_per_tree':8,
        'tool_sha256':sha(__file__),'vegetation_helper_sha256':sha(Path(__file__).with_name('vegetation_lod.py')),
        'scope':'Original WT far shader requires Dagor-specific impostor reconstruction. This independent fallback bakes actual existing high-detail source; wind and exact parallax remain approximations.'}
    (a.output/'manifest.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print('TREE_DISTANCE_LOD',a.id,triangles(far),flush=True)

if __name__=='__main__':main()
