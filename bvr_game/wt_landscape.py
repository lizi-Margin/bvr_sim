"""Read-only Dagor landscape bitmap and exported landclass metadata helpers.

Source coordinates remain X/Z. These are authoring inputs, not runtime terrain
or a claim to reproduce Dagor's random planting, collision, or material shader.
"""
from pathlib import Path
import hashlib
import re
import struct
import numpy as np


def sha(file):
    return hashlib.sha256(Path(file).read_bytes()).hexdigest()


class RoBitmap:
    """RoHugeHierBitMap2d<4,3>, sampled without expanding huge sweep masks."""
    def __init__(self, raw):
        self.raw = bytes(raw)
        if len(raw) < 16:
            raise ValueError('Truncated bitmap header')
        w, h, table = struct.unpack_from('<IIQ', raw)
        if not 0 < w <= 512 or not 0 < h <= 512:
            raise ValueError('Unsupported bitmap dimensions')
        self.width, self.height = w * 128, h * 128
        self.blocks_w = w
        self.table = self._words(table, w * h)
        # Validate every reachable offset before a query, including sparse
        # blocks outside an eventual preview crop.
        for offset in np.unique(self.table):
            if offset <= 1:
                continue
            for leaf in np.unique(self._words(int(offset), 64)):
                if leaf > 1:
                    self._words(int(leaf), 8)

    def _words(self, offset, count):
        if offset < 16 or offset % 4 or offset + count * 4 > len(self.raw):
            raise ValueError('Bitmap offset leaves source dump')
        return np.frombuffer(self.raw, dtype='<u4', count=count, offset=offset)

    def sample(self, x, y):
        x, y = np.broadcast_arrays(np.asarray(x, dtype=np.int64), np.asarray(y, dtype=np.int64))
        if np.any((x < 0) | (y < 0) | (x >= self.width) | (y >= self.height)):
            raise ValueError('Bitmap query outside source coverage')
        shape = x.shape
        x, y = x.ravel(), y.ravel()
        offset = self.table[(y >> 7) * self.blocks_w + (x >> 7)]
        result = (offset == 1).astype(np.uint8)
        for parent in np.unique(offset[offset > 1]):
            selected = np.flatnonzero(offset == parent)
            leaves = self._words(int(parent), 64)[((y[selected] & 127) >> 4) * 8 + ((x[selected] & 127) >> 4)]
            result[selected[leaves == 1]] = 1
            # A leaf is a 16x16 row-major array of little-endian uint32 bits.
            partial = selected[leaves > 1]
            if len(partial):
                bit = (y[partial] & 15) * 16 + (x[partial] & 15)
                words = np.frombuffer(self.raw, dtype='<u4')
                values = words[leaves[leaves > 1] // 4 + (bit >> 5)]
                result[partial] = ((values >> (bit & 31)) & 1).astype(np.uint8)
        return result.reshape(shape)

    def image(self, max_side=4096):
        """Nearest point preview; full resolution only when below max_side."""
        if max_side <= 0:
            raise ValueError('Positive preview size required')
        scale = max(1, int(np.ceil(max(self.width, self.height) / max_side)))
        xs = np.arange(0, self.width, scale)
        # Bounded strips avoid a full 65536-square temporary allocation.
        ys = np.arange(0, self.height, scale)
        image = np.empty((len(ys), len(xs)), dtype=np.uint8)
        for row in range(0, len(ys), 64):
            image[row:row + 64] = self.sample(xs[None, :], ys[row:row + 64, None]) * 255
        return image, scale


def parse_exported_blk(file):
    """Typed text emitted by official dumpGrp, preserving repeated blocks."""
    root = {'parameters': {}, 'blocks': []}
    stack = [root]
    for line in Path(file).read_text(encoding='utf8').splitlines():
        line = line.strip()
        if not line or line.startswith('//'):
            continue
        if line == '}':
            if len(stack) == 1:
                raise ValueError('Unbalanced exported BLK')
            stack.pop()
            continue
        match = re.fullmatch(r'([\w]+)\{(\})?', line)
        if match:
            block = {'name': match[1], 'parameters': {}, 'blocks': []}
            stack[-1]['blocks'].append(block)
            if not match[2]:
                stack.append(block)
            continue
        match = re.fullmatch(r'(\w+):(\w+)=(.*)', line)
        if not match:
            raise ValueError('Unsupported exported BLK line: ' + line)
        key, kind, raw = match.groups()
        if kind == 't':
            if not (raw.startswith('"') and raw.endswith('"')):
                raise ValueError('Expected quoted source text')
            value = raw[1:-1]
        elif kind == 'b':
            if raw not in ('yes', 'no'):
                raise ValueError('Invalid source boolean')
            value = raw == 'yes'
        elif kind == 'i':
            value = int(raw)
        elif kind == 'r':
            value = float(raw)
        elif kind == 'm':
            groups = re.fullmatch(r'\[\[([^\[\]]+)\] \[([^\[\]]+)\] \[([^\[\]]+)\] \[([^\[\]]+)\]\]', raw)
            if not groups:
                raise ValueError('Invalid source matrix')
            value = [[float(v) for v in group.split(',')] for group in groups.groups()]
            if any(len(row) != 3 for row in value):
                raise ValueError('Invalid source matrix row')
        elif kind in ('p2', 'p3', 'p4', 'c'):
            value = [float(v) if kind != 'c' else int(v) for v in raw.split(',')]
            if len(value) != (4 if kind == 'c' else int(kind[1:])):
                raise ValueError('Invalid source vector')
        else:
            raise ValueError('Unsupported exported BLK type: ' + kind)
        if key in stack[-1]['parameters']:
            raise ValueError('Repeated source parameter requires explicit handling: ' + key)
        stack[-1]['parameters'][key] = value
    if len(stack) != 1:
        raise ValueError('Unterminated exported BLK')
    return root
