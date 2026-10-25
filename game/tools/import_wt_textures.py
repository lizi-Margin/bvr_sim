"""Decode already extracted local DDSx textures without changing game files.

First use the official Dagor dumpGrp tool with -exp (raw extraction). This tool
decompresses that payload and delegates DDS format/mip ordering to ddsx2dds.
Oodle requires an existing local oo2core DLL; it is never downloaded or copied.
"""
from pathlib import Path
import argparse,ctypes,hashlib,json,struct,subprocess,zlib
from PIL import Image

HEADER=struct.Struct('<IIIHHBBHHBBII')
COMPRESSION_MASK=0xe0000000

def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()

def decode_payload(raw,oodle=None,max_bytes=512*1024*1024):
    if len(raw)<HEADER.size:raise ValueError('Truncated DDSx header')
    header=list(HEADER.unpack_from(raw))
    if header[0]!=0x78534444:raise ValueError('Not a DDSx file')
    size=header[11];packed=header[12];payload=raw[HEADER.size:]
    if not 0<size<=max_bytes:raise ValueError('DDSx decoded size exceeds the allowed range')
    compression=header[2]&COMPRESSION_MASK
    if compression and len(payload)!=packed:raise ValueError('DDSx packed payload size differs from header')
    if compression==0x60000000:
        if oodle is None:raise ValueError('Oodle texture requires --oodle-dll')
        source=ctypes.create_string_buffer(payload,len(payload));target=ctypes.create_string_buffer(size)
        actual=oodle(source,len(payload),target,size,1,0,0,None,0,None,None,None,0,3)
        if actual!=size:raise ValueError('Oodle decoded size differs from DDSx header')
        decoded=target.raw
    elif compression==0x20000000:
        from compression import zstd
        decoded=zstd.decompress(payload)
    elif compression==0x80000000:decoded=zlib.decompress(payload)
    elif compression==0:decoded=payload
    else:raise ValueError('Unsupported DDSx compression '+hex(compression))
    if len(decoded)!=size:raise ValueError('Decoded payload size differs from DDSx header')
    original_flags=header[2];header[2]&=~COMPRESSION_MASK;header[12]=0
    return HEADER.pack(*header)+decoded,{'width':header[3],'height':header[4],
        'mips':header[5],'format':hex(header[1]),'flags':hex(original_flags),
        'raw_bytes':size,'payload_sha256':hashlib.sha256(decoded).hexdigest()}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True,help='Raw DDSx extraction directory, grouped by pack name')
    parser.add_argument('--output',type=Path,required=True,help='New output directory')
    parser.add_argument('--converter',type=Path,required=True,help='Official ddsx2dds executable')
    parser.add_argument('--oodle-dll',type=Path)
    parser.add_argument('--packs-root',type=Path,help='Optional original content/base/res directory, used for source hashes')
    parser.add_argument('--max-mb',type=int,default=512)
    args=parser.parse_args()
    if args.max_mb<=0:parser.error('--max-mb must be positive')
    sources=sorted(args.source.rglob('*.ddsx'))
    if not sources:parser.error('No DDSx source files found')
    converter=args.converter.resolve(strict=True)
    # Validate the local dependency before creating the immutable output tree.
    library=None;oodle=None
    if args.oodle_dll:
        library=ctypes.CDLL(str(args.oodle_dll.resolve(strict=True)));oodle=library.OodleLZ_Decompress
        pointer=ctypes.c_void_p;size=ctypes.c_int64;integer=ctypes.c_int
        oodle.argtypes=[pointer,size,pointer,size,integer,integer,integer,pointer,size,pointer,pointer,pointer,size,integer]
        oodle.restype=size
    args.output.mkdir(parents=True,exist_ok=False)
    rows=[]
    for source in sources:
        row={'source':str(source.resolve()),'source_sha256':sha(source)}
        try:
            raw,metadata=decode_payload(source.read_bytes(),oodle,args.max_mb*1024*1024);row.update(metadata)
            target=args.output/source.relative_to(args.source).parent;target.mkdir(parents=True,exist_ok=True)
            unpacked=target/(source.stem+'.uncompressed.ddsx');dds=target/(source.stem+'.dds');png=target/(source.stem+'.png')
            unpacked.write_bytes(raw)
            result=subprocess.run([str(converter),str(unpacked.resolve()),str(dds.resolve())],capture_output=True,timeout=20)
            if result.returncode:raise ValueError(result.stdout.decode(errors='replace')+result.stderr.decode(errors='replace'))
            with Image.open(dds) as image:
                image.load()
                if image.size!=(metadata['width'],metadata['height']):raise ValueError('DDS image dimensions differ from DDSx')
                image.save(png);row['mode']=image.mode
            row.update(status='decoded',dds=str(dds.resolve()),dds_sha256=sha(dds),png=str(png.resolve()),png_sha256=sha(png))
        except Exception as error:row.update(status='failed',error=repr(error))
        rows.append(row);print('WT_DDSX',source.parent.name,source.name,row['status'],row.get('error',''),flush=True)
    report={'scope':'User-owned local War Thunder texture import. Original game files unchanged. No redistribution.',
        'importer_sha256':sha(__file__),'converter':str(converter),'converter_sha256':sha(converter),
        'decoder_dll':str(args.oodle_dll.resolve()) if args.oodle_dll else None,
        'decoder_dll_sha256':sha(args.oodle_dll) if args.oodle_dll else None,
        'source_reference':'https://github.com/GaijinEntertainment/DagorEngine/blob/dagor_2026_08_01/prog/engine/sharedInclude/3d/ddsxTex.h',
        'license':'user-owned-local-War-Thunder-resource','distribution_allowed':False,
        'decoded':sum(r['status']=='decoded' for r in rows),'failed':sum(r['status']=='failed' for r in rows),'textures':rows}
    if args.packs_root:
        report['original_packs']=[{'file':str(p.resolve()),'sha256':sha(p)} for p in
            [args.packs_root/(name+'.dxp.bin') for name in sorted({p.parent.name for p in sources})]]
    (args.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print('WT_TEXTURE_IMPORT',report['decoded'],report['failed'],flush=True)

if __name__=='__main__':main()
