import struct
import numpy as np
import pytest
from bvr_game.wt_landscape import RoBitmap, parse_exported_blk


def test_sparse_bitmap_and_little_endian_leaf():
    raw = bytearray(312)
    struct.pack_into('<IIQ', raw, 0, 2, 1, 16)
    struct.pack_into('<II', raw, 16, 24, 1)  # partial, then full 128x128 block
    struct.pack_into('<II', raw, 24, 280, 1)  # partial 16x16, then full leaf
    struct.pack_into('<I', raw, 280, 1 << 17)  # (x=1,y=1)
    bitmap = RoBitmap(raw)
    assert bitmap.sample([1, 2, 16, 127, 128], [1, 1, 0, 127, 127]).tolist() == [1, 0, 1, 0, 1]
    image, stride = bitmap.image(256)
    assert stride == 1 and image.shape == (128, 256)
    assert np.count_nonzero(image) == 1 + 256 + 128 * 128
    with pytest.raises(ValueError, match='outside'):
        bitmap.sample(-1, 0)
    struct.pack_into('<I', raw, 24, 300)
    with pytest.raises(ValueError, match='leaves'):
        RoBitmap(raw)


def test_official_exported_recipe_preserves_repeated_groups(tmp_path):
    file = tmp_path / 'land.blk'
    file.write_text('riResCount:i=2\nobj_plant_generate{\ndensity:r=0.25\nobject{\nriResId:i=1\n}\n}\n'
                    'obj_plant_generate{\nmapSize:p2=4096, 4096\n}\n'
                    'placed{\nmatrix:m=[[1, 0, 0] [0, 1, 0] [0, 0, 1] [12, 3, 45]]\n}\n')
    recipe = parse_exported_blk(file)
    assert len(recipe['blocks']) == 3
    assert recipe['blocks'][0]['blocks'][0]['parameters']['riResId'] == 1
    assert recipe['blocks'][2]['parameters']['matrix'][3] == [12, 3, 45]
    file.write_text('obj_plant_generate{\ndensity:r=0.25\n')
    with pytest.raises(ValueError, match='Unterminated'):
        parse_exported_blk(file)
