"""Typed, headless bounds for retained source grids inside a regional terrain."""
import tempfile,unittest
from pathlib import Path
from bvr_game.app import native

class LargeDetailTerrainTests(unittest.TestCase):
    def test_wide_retained_grid_is_used_by_the_core_and_session(self):
        terrain=native.GameTerrain();terrain.spacing=2000;terrain.heights=[0,0,0,0]
        tile=native.TerrainTile();tile.spacing=1;tile.columns=1057;tile.rows=3;tile.heights=[float(c+2*r) for r in range(3) for c in range(1057)]
        terrain.detail_tiles=[tile];self.assertAlmostEqual(terrain.height(1025.25,1.5),1028.25)
        with tempfile.TemporaryDirectory() as folder:
            session=native.GameSession(str(Path(folder)/'session.log'))
            try:
                session.set_terrain(terrain);self.assertAlmostEqual(session.terrain().height(1025.25,1.5),1028.25)
                self.assertEqual(session.frame().tick,0)
            finally:session.close()
    def test_detail_grid_above_4096_is_rejected(self):
        terrain=native.GameTerrain();tile=native.TerrainTile();tile.columns=4097;tile.rows=2;tile.heights=[0.]*(4097*2);terrain.detail_tiles=[tile]
        with tempfile.TemporaryDirectory() as folder:
            session=native.GameSession(str(Path(folder)/'session.log'))
            try:
                with self.assertRaisesRegex(ValueError,'Invalid detail height field'):session.set_terrain(terrain)
            finally:session.close()

if __name__=='__main__':unittest.main()
