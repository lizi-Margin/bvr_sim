"""Offline local RIGz coverage + official dumpGrp landclass recipe import.

No runtime generation, terrain synthesis, source-file mutation or exact Dagor
planting equivalence. A local Oodle DLL is loaded in place when needed.
"""
from pathlib import Path
import argparse
import ctypes
import json
import re
import struct
import sys
import zlib
from compression import zstd
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from bvr_game.wt_landscape import RoBitmap, parse_exported_blk, sha


def decode_block(data, at, dll):
    if at + 4 > len(data):
        raise ValueError('Truncated RIGz compression block')
    length = int.from_bytes(data[at:at + 3], 'little')
    method = data[at + 3]
    end = at + 4 + length
    if end > len(data):
        raise ValueError('RIGz compression block leaves source')
    packed = data[at + 4:end]
    if method == 0x40:
        decoded = zstd.decompress(packed)
    elif method == 0x60:
        decoded = zlib.decompress(packed)
    elif method == 0x80:
        size = struct.unpack_from('<I', packed)[0]
        if not 0 < size < 512 * 1024 * 1024 or dll is None:
            raise ValueError('Oodle block requires a valid size and local DLL')
        fn = dll.OodleLZ_Decompress
        pointer, integer, length_type = ctypes.c_void_p, ctypes.c_int, ctypes.c_int64
        fn.argtypes = [pointer, length_type, pointer, length_type, integer, integer,
                       integer, pointer, length_type, pointer, pointer, pointer, length_type, integer]
        fn.restype = length_type
        src = ctypes.create_string_buffer(packed[4:], len(packed) - 4)
        dst = ctypes.create_string_buffer(size)
        if fn(src, len(packed) - 4, dst, size, 1, 0, 0, None, 0, None, None, None, 0, 3) != size:
            raise ValueError('Oodle decoded size differs from source header')
        decoded = dst.raw
    else:
        raise ValueError('Unsupported RIGz compression method: ' + hex(method))
    return decoded, end


def import_layer(payload, output, max_side):
    size = struct.unpack_from('<I', payload)[0]
    if not 160 <= size <= len(payload) - 4:
        raise ValueError('Invalid RIGz data header size')
    data = payload[4:4 + size]
    offset, count = struct.unpack_from('<II', data, 48)
    if not 0 <= count <= 256 or offset + count * 32 > size:
        raise ValueError('Invalid source landclass table')
    names = []
    for index in range(count):
        pointer = struct.unpack_from('<Q', data, offset + index * 32)[0]
        if pointer >= size:
            raise ValueError('Source landclass name leaves data')
        name = data[pointer:data.index(0, pointer)].decode('utf8')
        if not re.fullmatch('[A-Za-z0-9_.-]+', name):
            raise ValueError('Unsafe source landclass name')
        names.append(name)
    rows = []
    at = 4 + size
    for name in ['sweep', *names]:
        l1, l2, length = struct.unpack_from('<III', payload, at)
        at += 12
        if (l1, l2) != (4, 3) or at + length > len(payload):
            raise ValueError('Invalid source bitmap block')
        raw = payload[at:at + length]
        at += length
        bitmap = RoBitmap(raw)
        target = output / (name + '.bitmap.bin')
        target.write_bytes(raw)
        preview, stride = bitmap.image(max_side)
        png = output / (name + '.png')
        Image.fromarray(preview).save(png)
        rows.append({'name': name, 'bitmap': str(target.resolve()), 'bitmap_sha256': sha(target),
                     'source_size': [bitmap.width, bitmap.height], 'preview': str(png.resolve()),
                     'preview_sha256': sha(png), 'preview_stride': stride,
                     'preview_active_fraction': float(np.count_nonzero(preview) / preview.size)})
        print('WT_LANDCLASS_MASK', name, bitmap.width, bitmap.height, flush=True)
    if at != len(payload):
        raise ValueError('Unexpected unparsed RIGz generation payload')
    return {'world_origin_xz_m': list(struct.unpack_from('<2f', data, 64)),
            'grid_to_world_m': struct.unpack_from('<f', data, 112)[0],
            'density_map_origin_xz_m': list(struct.unpack_from('<2f', data, 116)), 'masks': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rigz-field', type=Path, required=True)
    parser.add_argument('--exported-assets', type=Path, required=True,
                        help='Official dumpGrp -exp output for locations.grp')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--oodle-dll', type=Path)
    parser.add_argument('--locations-pack', type=Path,
                        help='Original locations.grp for provenance; read only')
    parser.add_argument('--exporter', type=Path,
                        help='Official dumpGrp executable used for exported-assets provenance')
    parser.add_argument('--preview-side', type=int, default=2048)
    args = parser.parse_args()
    if not 1 <= args.preview_side <= 4096:
        parser.error('Use --preview-side 1..4096')
    source = args.rigz_field.resolve(strict=True)
    evidence = [{'file': str(p.resolve(strict=True)), 'sha256': sha(p)}
                for p in (args.locations_pack, args.exporter) if p is not None]
    data = source.read_bytes()
    if len(data) < 12 or data[4:8] != b'RIGz' or struct.unpack_from('<I', data)[0] + 4 != len(data):
        raise ValueError('Expected unchanged official RIGz.field.bin wrapper')
    dll = ctypes.CDLL(str(args.oodle_dll.resolve(strict=True))) if args.oodle_dll else None
    args.output.mkdir(parents=True, exist_ok=False)
    # This adapter currently supports the primary generation layer only.
    payload, end = decode_block(data, 8, dll)
    fixed_size = struct.unpack_from('<I', data, end)[0]
    tail = data[end + 4 + fixed_size:]
    if end + 4 + fixed_size > len(data) or tail != b'\0':
        raise ValueError('Additional RIGz layers require explicit support')
    layer = import_layer(payload, args.output, args.preview_side)
    recipes = []
    for row in layer['masks'][1:]:
        name = row['name']
        directory = args.exported_assets.resolve(strict=True) / (name + '.03FB59C4.land')
        file = directory / 'land.blk'
        recipe = parse_exported_blk(file)
        density_maps = []
        for raw in sorted(directory.glob('*.bin')):
            bitmap = RoBitmap(raw.read_bytes())
            target = args.output / (name + '-' + raw.name + '.png')
            pixels, stride = bitmap.image(4096)
            Image.fromarray(pixels).save(target)
            density_maps.append({'source': str(raw), 'source_sha256': sha(raw),
                                 'size': [bitmap.width, bitmap.height], 'png': str(target.resolve()),
                                 'png_sha256': sha(target), 'stride': stride})
        recipes.append({'name': name, 'source': str(file), 'source_sha256': sha(file),
                        'recipe': recipe, 'density_maps': density_maps})
    report = {'source': str(source), 'source_sha256': sha(source), 'importer_sha256': sha(__file__),
              'bitmap_decoder_sha256': sha(Path(sys.modules[RoBitmap.__module__].__file__)),
              'oodle_dll': str(args.oodle_dll.resolve()) if args.oodle_dll else None,
              'oodle_dll_sha256': sha(args.oodle_dll) if args.oodle_dll else None,
              'source_export_evidence': evidence,
              'layer': layer, 'recipes': recipes, 'distribution_allowed': False,
              'scope': 'Original generation coverage, source density bitmaps and typed official exported recipes. '
                       'Source axes preserved; preview fractions use stated point stride. '
                       'No tree geometry substitution, exact RNG placement, shader equivalence, physics integration or visual acceptance claim.'}
    (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print('WT_LANDCLASS_IMPORT', len(recipes), str(args.output / 'report.json'), flush=True)


if __name__ == '__main__':
    main()
