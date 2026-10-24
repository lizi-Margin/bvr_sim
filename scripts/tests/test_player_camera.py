"""Camera framing, optical zoom and compatibility of recorded player profiles."""
import copy,math,unittest
from types import SimpleNamespace
from bvr_game.presentation import ChaseCamera
from bvr_game.player_input import camera_ray
from bvr_game.player_profiles import PlayerProfileStore


class PlayerCameraTests(unittest.TestCase):
    def settings(self):
        return {**PlayerProfileStore().resolve('F16')['camera'],'subject_y':.62,'zoom_dolly':1.}

    def test_subject_anchor_and_zoom_size_across_bank_climb_and_viewports(self):
        for pitch in [-math.pi/2,-1.3,0,1.3,math.pi/2]:
            for roll in [-1.5,0,1.5]:
                plane=SimpleNamespace(position=[500,200,8500],velocity=[300*math.cos(pitch),0,300*math.sin(pitch)],orientation=[roll,-pitch,0])
                saved=copy.deepcopy(vars(plane));camera=ChaseCamera(self.settings());scales=[]
                for width,height in [(1920,1080),(1600,1000),(1280,720)]:
                    for zoom in [False,True,False]:
                        for _ in range(60):
                            eye,target,fov,up=camera.update(plane,.02,False,(width/2,height/2),width,height,zoom)
                            view={'eye':eye,'target':target,'fov':fov,'up':up}
                            ray=camera_ray(width/2,height*.62,width,height,view)
                            direction=[plane.position[0]-eye[2],plane.position[1]+eye[0],plane.position[2]-eye[1]]
                            length=math.hypot(*direction);expected=[x/length for x in direction]
                            # Roll feedback permits a small horizontal offset;
                            # compare its ray using the actual camera right.
                            from bvr_game.player_input import unit,dot,cross
                            forward=unit([b-a for a,b in zip(eye,target)]);right=unit(cross(up,forward));vertical=unit(cross(forward,right))
                            subject=[-direction[1],direction[2],direction[0]]
                            projected_y=.5-dot(subject,vertical)/dot(subject,forward)/(2*math.tan(fov/2))
                            self.assertAlmostEqual(projected_y,.62,places=10)
                            if roll==0:self.assertLess(math.dist(ray,expected),1e-10)
                            scales.append(math.dist(eye,[-plane.position[1],plane.position[2],plane.position[0]])*math.tan(fov/2))
                self.assertLess(max(scales)-min(scales),1e-9)
                self.assertEqual(vars(plane),saved)

    def test_optional_camera_fields_accept_legacy_profiles_and_reject_bad_values(self):
        current=PlayerProfileStore();legacy_document=copy.deepcopy(current.document)
        for key in ['subject_y','zoom_dolly']:
            legacy_document['units']['camera'].pop(key,None)
            for template in legacy_document['templates'].values():template.get('camera',{}).pop(key,None)
            for row in legacy_document['aircraft'].values():row.get('overrides',{}).get('camera',{}).pop(key,None)
        old=PlayerProfileStore.from_document(legacy_document);document=copy.deepcopy(old.document)
        document['units']['camera'].update(subject_y='normalized viewport y',zoom_dolly='dimensionless ratio')
        document['templates']['base']['camera'].update(subject_y=.62,zoom_dolly=1.)
        store=PlayerProfileStore.from_document(document)
        from bvr_game.app import native
        # The old complete recorded profile keeps its original hash and can
        # still configure this core, even when current units know new fields.
        legacy=old.resolve('F16');restored=store.native_resolved(native,legacy)
        self.assertEqual(restored.source_hash,legacy['effective_sha256'])
        for key,value in [('subject_y',1.),('zoom_dolly',2.)]:
            broken=copy.deepcopy(document);broken['templates']['base']['camera'][key]=value
            with self.assertRaises(ValueError):PlayerProfileStore.from_document(broken)

    def test_imported_visual_centre_is_separate_from_physical_origin(self):
        from bvr_game.player_input import unit,dot,cross
        plane=SimpleNamespace(position=[100,200,5000],velocity=[250,0,0],orientation=[math.pi/2,0,0])
        camera=ChaseCamera(self.settings());camera.subject_offset_blender=[0,-8,1]
        eye,target,fov,up=camera.update(plane,.02,False,(960,540),1920,1080,False)
        # At90degstarboardbank, the source's +up offset points starboard; its aft
        # offset remains south. The simulation origin itself is untouched.
        subject=camera.framing_state['subject_position_wicked']
        self.assertAlmostEqual(subject[2],92.)
        self.assertAlmostEqual(subject[0],-199.)
        self.assertAlmostEqual(subject[1],5000.)
        f=unit([b-a for a,b in zip(eye,target)]);r=unit(cross(up,f));u=unit(cross(f,r));d=[a-b for a,b in zip(subject,eye)]
        self.assertAlmostEqual(.5-dot(d,u)/dot(d,f)/(2*math.tan(fov/2)),.62,places=10)
        self.assertEqual(plane.position,[100,200,5000])


if __name__=='__main__':unittest.main()
