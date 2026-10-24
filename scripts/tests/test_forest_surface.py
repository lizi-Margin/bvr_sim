"""Ground coverage follows canopy edges while protected surfaces keep ownership."""
import unittest
from types import SimpleNamespace
import numpy as np
from shapely.geometry import box
from bvr_game.detail_bake import forest_floor_density,material_mask
from bvr_game.source_tree_layout import edge_density_probability


class ForestSurfaceTests(unittest.TestCase):
    def baker(self):
        cfg={'width_m':160,'variation_m':72,'patch_scale_m':180}
        return SimpleNamespace(r={'seed':3124,'scatter_rules':[{'id':'canopy','roles':'canopy','zones':['forest'],'edge_density':cfg}]},forests={'forest':box(-1000,-1000,1000,1000)})

    def test_source_mixture_follows_actual_canopy_field_and_sums_to_one(self):
        b=self.baker();n,w=np.meshgrid(np.linspace(-999,-600,71),np.linspace(-500,500,129));labels=np.full(n.shape,2)
        density=forest_floor_density(b,labels,n,w);expected=edge_density_probability(b.forests['forest'],np.column_stack([n.ravel(),w.ravel()]),b.r['scatter_rules'][0]['edge_density'],3124).reshape(n.shape)
        np.testing.assert_allclose(density,expected,rtol=1e-7,atol=1e-7)
        grass=material_mask(labels,0,density);wood=material_mask(labels,2,density)
        np.testing.assert_allclose(grass+wood,1);self.assertGreater(grass[:,0].mean(),.99);self.assertTrue(np.all(grass[:,-1]==0))

    def test_road_soil_water_and_farm_masks_are_protected(self):
        b=self.baker();n,w=np.meshgrid(np.linspace(-900,900,7),np.linspace(-900,900,9));labels=np.tile(np.arange(7),(9,1));original=labels.copy()
        density=forest_floor_density(b,labels,n,w);self.assertTrue(np.all(density[labels!=2]==0))
        for index in [1,3,4,5,6]:np.testing.assert_array_equal(material_mask(labels,index,density),labels==index)
        np.testing.assert_allclose(sum(material_mask(labels,k,density) for k in range(7)),1);np.testing.assert_array_equal(labels,original)

    def test_missing_canopy_coverage_is_rejected(self):
        b=self.baker();n,w=np.meshgrid([3000],[3000]);labels=np.full(n.shape,2)
        with self.assertRaisesRegex(ValueError,'no declared'):forest_floor_density(b,labels,n,w)


if __name__=='__main__':unittest.main()
