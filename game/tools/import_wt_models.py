"""Read-only local WT RendInst source LOD -> OBJ using an existing DAE checkout.

Requires PyQt5 (only parser QObject support, no window is constructed), Python3.14
and an existing local Oodle DLL. Original parser files/game files remain intact.
Textures are imported separately with import_wt_textures.py.
"""
from pathlib import Path
import argparse,ast,ctypes as c,hashlib,json,lzma,re,struct,sys,traceback,types,zlib
from compression import zstd

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def codecs(parser_root,dll):
    import util.fileread as fileread
    import util.log as log
    library=c.CDLL(str(dll));oodle=library.OodleLZ_Decompress
    pointer=c.c_void_p;size=c.c_int64;integer=c.c_int
    oodle.argtypes=[pointer,size,pointer,size,integer,integer,integer,pointer,size,pointer,pointer,pointer,size,integer];oodle.restype=size
    def decode(source,maxOriginalSize=None):
        if not maxOriginalSize:maxOriginalSize=int.from_bytes(source[:4],'little');source=source[4:]
        if not 0<maxOriginalSize<512*1024*1024:raise ValueError('Invalid decoded block size')
        src=c.create_string_buffer(source,len(source));dst=c.create_string_buffer(maxOriginalSize)
        got=oodle(src,len(source),dst,maxOriginalSize,1,0,0,None,0,None,None,None,0,3)
        if got!=maxOriginalSize:raise ValueError('Oodle decoded size differs from the block header')
        return dst.raw
    codec=types.ModuleType('util.decompression')
    codec.__dict__.update({k:v for k,v in vars(fileread).items() if not k.startswith('__')});codec.log=log
    codec.zstdDecompress=lambda src,maxOriginalSize=None:zstd.decompress(src)
    codec.zlibDecompress=zlib.decompress;codec.lzmaDecompress=lzma.decompress;codec.lzmaCompress=lzma.compress;codec.oodleDecompress=decode
    file=parser_root/'src/dae/util/decompression.py';tree=ast.parse(file.read_text())
    node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='CompressedData')
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(file),'exec'),codec.__dict__)
    sys.modules['util.decompression']=codec
    return library,codec

def install_voxel_mesh_reader():
    """Read RenderableInstanceResource's meshSize/voxelDataOffset pair.

    The old DAE parser calls the second field reserved and asserts zero.
    Dagor's loadResourceInternal names it voxelDataOffset, limits the first
    element's render vertices and then reads a size-prefixed voxel tail.
    Those voxels are source shading data, not exported triangle geometry.
    """
    import parse.mesh as mesh
    from util.fileread import readInt
    def read(self,file):
        size=readInt(file);voxel_offset=readInt(file)
        if size<40 or size>file.getSize()-file.tell():raise ValueError('Shader mesh size leaves source resource: '+str((size,voxel_offset,file.tell(),file.getSize())))
        self.shaderMesh=self.setSubTask(mesh.ShaderMesh(file.readBlock(size)))
        self.voxel_data_offset=voxel_offset;self.voxel_tail_bytes=0
        if voxel_offset:
            if not self.shaderMesh.elems or not 0<voxel_offset<self.shaderMesh.elems[0].numV:
                raise ValueError('Source voxel offset leaves first mesh vertex range')
            self.shaderMesh.elems[0].numV=voxel_offset
            tail=readInt(file)
            if tail>file.getSize()-file.tell():raise ValueError('Voxel tail leaves source resource')
            file.seek(tail,1);self.voxel_tail_bytes=tail
        self.clearSubTask()
    mesh.InstShaderMeshResource.__init__=read
    # The complete lod/impostor dump size is in the initial resource header.
    # The older reader reconstructs an impostor size from pointer fields and
    # can seek into its floating-point data instead of the following mesh.
    import parse.realres as realres
    def read_lods(self,file):
        size=self._RendInst__lodHdrSz&0xFFFFFF
        if size<64 or size>file.getSize()-file.tell():raise ValueError('LOD dump leaves source resource')
        data=file.read(size);offset,count=struct.unpack_from('<II',data)
        if not 1<=count<=64 or offset<64 or offset+count*16>size:raise ValueError('LOD table leaves source dump')
        self._setLodCount(count)
        self._RendInst__occ=tuple(struct.unpack_from('<Qf',data,offset+i*16) for i in range(count))
        self.source_bounds_y_up=struct.unpack_from('<6f',data,16)
        self.source_lod_dump_bytes=size
        self.source_impostor_offset=struct.unpack_from('<H',data,60)[0]
    realres.RendInst._readModelData=read_lods

def export_frozen_facing_obj(item,target):
    """Original half4 centers + half4 offsets in the no-animation identity pose.

    This is an explicit static authoring pose, not a camera-facing shader.
    Raw centers/offsets are retained separately for later native reconstruction.
    """
    from parse.mesh import MatVData
    from util.fileread import BinFile
    import numpy as np
    item.mvd.computeData();raw=item.mvd._MatVData__file.getData();index_cache={};lines=[];uvlines=[];faces=[];mats={};offset=0;payload={}
    for subset,e in enumerate(item._RendInst__shaderMesh[0].shaderMesh.elems):
        material=item.materials[e.mat];cls=material.cls
        if cls not in ('rendinst_simple','rendinst_facing_leaves'):raise ValueError('Unsupported source pose material '+cls)
        vd=item.mvd.getGlobalVertexData(e.vData);stride=vd.getVertexStride();at=item.mvd.getVertexDataOffset(e.vData)
        if stride!=24:raise ValueError('Unsupported source pose vertex stride '+str(stride))
        if e.vData not in index_cache:
            decoder=object.__new__(MatVData.VertexData);decoder._VertexData__gvData=vd;decoder._VertexData__unimplemented=False
            begin=at+vd.getVertexBlockSz();size=vd.getFullVertexDataSz()-vd.getVertexBlockSz()
            decoder.__processFaces__(BinFile(raw[begin:begin+size]));index_cache[e.vData]=np.asarray(decoder.getFaces(),dtype=np.int64)
        selected=index_cache[e.vData][e.startI//3:e.startI//3+e.numFace]+e.baseVertex
        if len(selected)!=e.numFace or selected.min()<0 or selected.max()>=vd.getVertexCnt():raise ValueError('Source face range leaves vertex buffer')
        unique,inverse=np.unique(selected,return_inverse=True);points=[];uvs=[];centers=[];deltas=[]
        for index in unique:
            p=at+int(index)*stride
            if cls=='rendinst_facing_leaves':
                center=struct.unpack_from('<4e',raw,p);delta=struct.unpack_from('<4e',raw,p+12)
                if delta[3] not in (0,3,6,9):raise ValueError('Unknown source leaf wind group')
                point=[center[0]+delta[0],center[1]+delta[1],center[2]-delta[2]]
                uv=struct.unpack_from('<2h',raw,p+8);uv=(uv[0]/4096,1-uv[1]/4096)
                centers.append(center);deltas.append(delta)
            else:point=struct.unpack_from('<3f',raw,p);u,v=struct.unpack_from('<2f',raw,p+16);uv=(u,-v)
            points.append(point);uvs.append(uv)
        payload['subset_'+str(subset)+'_source_indices']=unique
        if centers:
            payload['subset_'+str(subset)+'_center_half4']=np.asarray(centers,dtype='<f2')
            payload['subset_'+str(subset)+'_offset_half4']=np.asarray(deltas,dtype='<f2')
        for point,uv in zip(points,uvs):
            lines.append('v %.7f %.7f %.7f'%(point[0],point[1],-point[2]));uvlines.append('vt %.7f %.7f'%uv)
        name=material.getName();mats[name]=material.getTextureSlots()[0]
        faces.append('usemtl '+name)
        for face in inverse.reshape(-1,3)+offset+1:faces.append('f '+' '.join(str(int(v))+'/'+str(int(v)) for v in face))
        offset+=len(points)
    obj=target/(item.name+'_0.obj');mtl=obj.with_suffix('.mtl')
    obj.write_text('\n'.join(['mtllib '+mtl.name,*lines,*uvlines,*faces])+'\n')
    mtl.write_text('\n'.join('newmtl '+name+'\n\tillum 3\n\tmap_Kd textures/'+texture.rstrip('*')+'.dds' for name,texture in mats.items())+'\n')
    sidecar=target/(item.name+'-source-leaf-data.npz');np.savez_compressed(sidecar,**payload)
    return {'pose':'identity_source_axes_no_animation','camera_facing_dynamic':False,'source_payload':str(sidecar.resolve()),'source_payload_sha256':sha(sidecar),
        'reference':'https://github.com/GaijinEntertainment/DagorEngine/blob/dagor_2026_08_01/prog/gameLibs/bvh/shaders/bvh_process_leaves_vertices.dshl',
        'no_animation_basis_reference':'https://github.com/GaijinEntertainment/DagorEngine/blob/dagor_2026_08_01/prog/engine/libFx/leavesWind.cpp'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parser-root',type=Path,required=True);p.add_argument('--deps-root',type=Path)
    p.add_argument('--oodle-dll',type=Path,required=True);p.add_argument('--description',type=Path,required=True)
    p.add_argument('--pack',type=Path,nargs='+',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--names',nargs='+',help='Optional exact resource names')
    p.add_argument('--lod',type=int,default=0,help='Original source LOD index; geometry is never simplified by this importer')
    p.add_argument('--facing-pose',choices=['reject','identity'],default='reject',help='Explicit static pose for old camera-facing source leaves; native facing animation is not reconstructed')
    a=p.parse_args();a.parser_root=a.parser_root.resolve(strict=True);a.oodle_dll=a.oodle_dll.resolve(strict=True)
    sys.path.insert(0,str(a.parser_root/'src/dae'))
    if a.deps_root:sys.path.insert(0,str(a.deps_root.resolve(strict=True)))
    library,codec=codecs(a.parser_root,a.oodle_dll)
    from parse.gameres import GameResourcePack,GameResDesc
    install_voxel_mesh_reader()
    import parse.realres as realres
    from util.assetcacher import AssetCacher
    # Python3.14 removed the old chained classmethod/property descriptor.
    # Resolve constant class metadata only. No mesh parser algorithm is changed.
    for name,module in list(sys.modules.items()):
        if not name.startswith(('parse.','util.')) or module is codec:continue
        for cls in list(vars(module).values()):
            if not isinstance(cls,type):continue
            for key,value in list(vars(cls).items()):
                if isinstance(value,classmethod) and isinstance(value.__func__,property):setattr(cls,key,value.__func__.fget(cls))
    realres.REALRES_CLASSES_DICT.clear();realres.REALRES_CLASSES_DICT.update({cls.staticClassId:cls for cls in realres.REALRES_CLASSES_LIST})
    description=GameResDesc(str(a.description.resolve(strict=True)));description.loadDataBlock();AssetCacher.appendGameResDesc(description)
    a.output.mkdir(parents=True,exist_ok=False);rows=[]
    for file in a.pack:
        file=file.resolve(strict=True);target=a.output/file.stem;target.mkdir(exist_ok=False)
        pack=GameResourcePack(str(file))
        for item in pack.getPackedFiles():
            if a.names and item.name not in a.names:continue
            row={'name':item.name,'class':type(item).__name__,'pack':str(file),'pack_sha256':sha(file)}
            try:
                if isinstance(item,realres.RendInst):
                    if not re.fullmatch(r'[A-Za-z0-9_.-]+',item.name):raise ValueError('Unsupported output resource name')
                    item.computeData()
                    if not 0 <= a.lod < item.lodCount:raise ValueError('Requested LOD outside original source table')
                    row['source_lods']=[{'lod':i,'triangles':sum(e.numFace for e in lod.shaderMesh.elems),
                        'range_m':item._RendInst__occ[i][1]} for i,lod in enumerate(item._RendInst__shaderMesh)]
                    facing=any(item.materials[e.mat].cls=='rendinst_facing_leaves' for e in item._RendInst__shaderMesh[a.lod].shaderMesh.elems)
                    if facing:
                        if a.lod!=0:raise ValueError('Frozen facing-leaf adapter supports only source LOD0')
                        if a.facing_pose!='identity':raise ValueError('Source facing-leaf shader requires explicit --facing-pose identity for a static authoring pose')
                        row['facing_leaf_pose']=export_frozen_facing_obj(item,target)
                    else:model=item.getModel(a.lod);model.exportObj(str(target),exportTexture=False)
                    obj=target/(item.name+'_'+str(a.lod)+'.obj');mtl=obj.with_suffix('.mtl');lines=obj.read_text().splitlines()
                    verts=[[float(x) for x in line.split()[1:]] for line in lines if line.startswith('v ')]
                    columns=list(zip(*verts))
                    # A successful binary parse is not evidence of valid geometry.
                    # Catch packed leaf fields incorrectly interpreted as float XYZ.
                    bounds=item.source_bounds_y_up;source_lo=[bounds[0],bounds[1],-bounds[5]];source_hi=[bounds[3],bounds[4],-bounds[2]]
                    excess=max(max(source_lo[i]-min(v),max(v)-source_hi[i]) for i,v in enumerate(columns))
                    if excess>.05:raise ValueError('Decoded vertices exceed independent source bounds by '+str(excess)+' meters')
                    row['maximum_source_bounds_excess_m']=max(0,excess)
                    row.update(status='exported',lod=a.lod,obj=str(obj.resolve()),obj_sha256=sha(obj),mtl=str(mtl.resolve()),mtl_sha256=sha(mtl),
                        vertices=len(verts),triangles=sum(line.startswith('f ') for line in lines),
                        bounds_obj={'min':[min(v) for v in columns],'max':[max(v) for v in columns]},
                        materials=sorted({line[7:] for line in lines if line.startswith('usemtl ')}))
                    row['source_voxel_lods']=[{'vertex_offset':lod.voxel_data_offset,'tail_bytes':lod.voxel_tail_bytes}
                        for lod in item._RendInst__shaderMesh]
                    row['source_bounds_y_up']={'min':list(item.source_bounds_y_up[:3]),'max':list(item.source_bounds_y_up[3:])}
                    row['source_lod_dump_bytes']=item.source_lod_dump_bytes;row['source_impostor_offset']=item.source_impostor_offset
                else:row['status']='not-render-mesh'
            except Exception as error:row.update(status='failed',error=repr(error),traceback=traceback.format_exc())
            rows.append(row);print('WT_MODEL',row['name'],row['status'],row.get('error',''),flush=True)
    report={'scope':f'Original local game LOD{a.lod} geometry via DAE OBJ. OBJ rounds positions/UV to four decimals and recomputes normals. Verify axes, source pivot, material maps and native appearance before registering.',
        'source_url':'https://github.com/quentin-dh/Dagor-Asset-Explorer','license':'user-owned-local-War-Thunder-resource','distribution_allowed':False,
        'voxel_layout_reference':'https://github.com/GaijinEntertainment/DagorEngine/blob/dagor_2026_08_01/prog/engine/shaders/rendInstRes.cpp#L93-L129',
        'importer_sha256':sha(__file__),'description':str(a.description.resolve()),'description_sha256':sha(a.description),
        'oodle_dll':str(a.oodle_dll),'oodle_dll_sha256':sha(a.oodle_dll),
        'parser_sources':[{ 'file':str(f.relative_to(a.parser_root)),'sha256':sha(f)} for f in sorted((a.parser_root/'src/dae').rglob('*.py'))],
        'exported':sum(r['status']=='exported' for r in rows),'failed':sum(r['status']=='failed' for r in rows),'models':rows}
    (a.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print('WT_MODEL_IMPORT',report['exported'],report['failed'],flush=True)
    if not report['exported']:raise RuntimeError('No source mesh was exported; inspect the import report')

if __name__=='__main__':main()
