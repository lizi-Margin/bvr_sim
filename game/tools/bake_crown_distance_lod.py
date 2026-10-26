"""Keep the registered opaque near crown, derive a coarser source-supported far crown."""
from pathlib import Path
import argparse,copy,json,math,shutil,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.source_crown_volume import source_points,crown,export_cluster
from bvr_game.content import sha,write_json
from scipy.spatial import ConvexHull

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--id',required=True);p.add_argument('--cell-m',type=float,default=8);p.add_argument('--support-hull',action='store_true');a=p.parse_args()
    parent=json.loads(a.parent.read_text());assert parent.get('source_crown_volume') and 2<a.cell_m<=16
    out=a.output;out.mkdir(exist_ok=False,parents=True);points,colors=source_points(parent)
    if a.support_hull:
        directions=np.array([[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1]]+[[x,y,z] for x in [-1,1] for y in [-1,1] for z in [-1,1]])
        ids=np.unique([np.argmax(points@d) for d in directions]);support=points[ids];hull=ConvexHull(support)
        triangles=hull.simplices.copy();normals=hull.equations[:,:3].copy();tri=support[triangles]
        winding=np.einsum('ij,ij->i',np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),normals);triangles[winding<0]=triangles[winding<0][:,[0,2,1]]
        vertices=support[triangles].reshape(-1,3);tint=np.r_[colors.mean(axis=0),1.]
        mesh=(vertices,np.repeat(normals,3,axis=0),np.tile(tint,(len(vertices),1)),1)
    else:mesh=crown(points,colors,a.cell_m)
    near=out/(a.id+'.glb');shutil.copy2(a.parent.parent/parent['file'],near);assert sha(near)==parent['glb_sha256']
    far=out/(a.id+'_lod1.glb');triangles,vertices=export_cluster(far,mesh,parent['cluster'])
    result=copy.deepcopy(parent);result.update(id=a.id,file=near.name);result['lods']=[{'level':0,'file':near.name,'sha256':sha(near),'triangles':parent['triangles']},{'level':1,'file':far.name,'sha256':sha(far),'triangles':triangles,'vertices':vertices}]
    for pose,bounds in zip(result['cluster']['poses_before_recentering'],result['cluster']['ground_conform']['tree_bounds_relative_blender']):
        c,s=math.cos(pose['yaw']),math.sin(pose['yaw']);rotation=np.array([[c,s,0],[-s,c,0],[0,0,1]])
        relative=mesh[0]@rotation*pose['scale']+np.array(pose['position'])-np.array(pose['base_anchor'])
        bounds['min']=np.minimum(bounds['min'],relative.min(axis=0)).tolist();bounds['max']=np.maximum(bounds['max'],relative.max(axis=0)).tolist()
    result['source_distance_lod']={'parent_asset':parent['id'],'parent_manifest_sha256':sha(a.parent),'high_detail_bytes_unchanged':True,'source_tree_positions_unchanged':True,'far_triangles_per_tree':triangles/parent['cluster']['source_copies'],'cell_m':a.cell_m,'source_vertices':len(points),'source_cells':mesh[3],'tool_sha256':sha(__file__),'scope':__doc__}
    result['source_distance_lod']['directional_source_support_hull']=a.support_hull
    result['parent_source_geometry_lods']=result.get('source_geometry_lods',{})
    result['source_geometry_lods']={'near_triangles_per_tree':parent['triangles']/parent['cluster']['source_copies'],'far_triangles_per_tree':triangles/parent['cluster']['source_copies'],'method':__doc__}
    result['source_distance_lod']['geometry_helper_sha256']=sha(ROOT/'bvr_game/source_crown_volume.py')
    write_json(out/'manifest.json',result);print('CROWN_DISTANCE',triangles,'total triangles',triangles//64,'per tree',flush=True)

if __name__=='__main__':main()
