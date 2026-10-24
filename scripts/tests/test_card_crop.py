"""A crop must conserve source opacity and its physical pixel locations."""
import unittest
import numpy as np
from bvr_game.card_crop import crop_rectangle,reparameterize_quad


class CardCropTests(unittest.TestCase):
    def test_union_preserves_tiny_normal_and_albedo_opacity_without_thresholding(self):
        albedo=np.zeros((128,128,4),dtype=np.uint8);normal=albedo.copy()
        albedo[37:90,51:63,3]=255;normal[30,43,3]=1
        x,y,w,h=crop_rectangle(albedo,normal)
        self.assertEqual((w,h),(64,128))
        for source in [albedo,normal]:self.assertEqual(int(source[:,:,3].sum()),int(source[y:y+h,x:x+w,3].sum()))
        with self.assertRaises(ValueError):crop_rectangle(np.zeros_like(albedo),np.zeros_like(normal))

    def test_rotated_scaled_quad_keeps_source_pixel_in_world_position(self):
        uv=np.array([[0,0],[1,0],[1,1],[0,1]],dtype=float)
        u=np.array([2.,3.,.2]);v=np.array([.4,.5,6.]);origin=np.array([-12.,8.,11.])
        p=origin+uv[:,:1]*u+uv[:,1:]*v;rect=(32,0,64,128)
        result=reparameterize_quad(p,uv,rect,(128,128))
        # Original pixel centre(61.5,40.5) lies within the crop. Solve its new
        # UV and verify the same physical position, independently of the helper.
        old=np.array([61.5/128,40.5/128]);new=np.array([(61.5-32)/64,40.5/128])
        expected=origin+old[0]*u+old[1]*v
        actual=result[0]+new[0]*(result[1]-result[0])+new[1]*(result[3]-result[0])
        np.testing.assert_allclose(actual,expected,rtol=0,atol=2e-6)
        bad=p.copy();bad[3,2]+=.1
        with self.assertRaisesRegex(ValueError,'not planar'):reparameterize_quad(bad,uv,rect,(128,128))


if __name__=='__main__':unittest.main()
