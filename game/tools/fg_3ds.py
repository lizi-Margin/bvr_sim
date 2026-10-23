"""Minimal legacy 3DS triangle/UV reader for FlightGear exterior submeshes.

Reads object vertices, triangle faces, texture coordinates and material groups.
Unsupported chunks are retained in the original source archive. No executable
scene content is evaluated. Used for the A380 pylon geometry in this collection.
"""
import struct
import bpy


def import_mesh(path):
    data = path.read_bytes()
    objects = []
    def string(offset):
        end = data.index(b'\0', offset)
        return data[offset:end].decode('latin1'), end + 1
    def chunks(start, end, current=None):
        while start + 6 <= end:
            tag, length = struct.unpack_from('<HI', data, start)
            if length < 6 or start + length > end:
                raise ValueError('Invalid 3DS chunk bounds: ' + str(path))
            pos, stop = start + 6, start + length
            if tag in {0x4D4D, 0x3D3D, 0x4100}:
                chunks(pos, stop, current)
            elif tag == 0x4000:
                name, pos = string(pos)
                current = {'name': name, 'vertices': [], 'faces': [], 'uv': [], 'materials': {}}
                objects.append(current)
                chunks(pos, stop, current)
            elif current is not None and tag == 0x4110:
                count = struct.unpack_from('<H', data, pos)[0]
                current['vertices'] = [struct.unpack_from('<fff', data, pos + 2 + i * 12) for i in range(count)]
            elif current is not None and tag == 0x4120:
                count = struct.unpack_from('<H', data, pos)[0]
                current['faces'] = [struct.unpack_from('<HHH', data, pos + 2 + i * 8) for i in range(count)]
                chunks(pos + 2 + count * 8, stop, current)
            elif current is not None and tag == 0x4130:
                name, pos = string(pos)
                count = struct.unpack_from('<H', data, pos)[0]
                current['materials'][name] = [struct.unpack_from('<H', data, pos + 2 + i * 2)[0] for i in range(count)]
            elif current is not None and tag == 0x4140:
                count = struct.unpack_from('<H', data, pos)[0]
                current['uv'] = [struct.unpack_from('<ff', data, pos + 2 + i * 8) for i in range(count)]
            start = stop
    chunks(0, len(data))
    for record in objects:
        if not record['faces']:
            continue
        mesh = bpy.data.meshes.new(record['name'])
        mesh.from_pydata(record['vertices'], [], record['faces'])
        mesh.update()
        obj = bpy.data.objects.new(record['name'], mesh)
        bpy.context.collection.objects.link(obj)
        if record['uv']:
            layer = mesh.uv_layers.new(name='UVMap')
            for loop in mesh.loops:
                if loop.vertex_index < len(record['uv']):
                    layer.data[loop.index].uv = record['uv'][loop.vertex_index]
        for name, faces in record['materials'].items():
            mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
            mat.diffuse_color = (.55, .55, .58, 1)
            index = len(mesh.materials)
            mesh.materials.append(mat)
            for face in faces:
                if face < len(mesh.polygons):
                    mesh.polygons[face].material_index = index
    return len(objects)
