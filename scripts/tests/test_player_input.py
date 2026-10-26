"""World-intent invariants independent of camera and physical steering."""
import math,unittest
from types import SimpleNamespace
from bvr_game.player_input import FREE_LOOK_KEY,PlayerInputAdapter
from bvr_game.player_profiles import PlayerProfileStore


class PlayerInputTests(unittest.TestCase):
    def setUp(self):
        self.adapter=PlayerInputAdapter(PlayerProfileStore().resolve('F16'))
        self.camera={'eye':[0,0,0],'target':[0,0,1],'up':[0,1,0],'fov':1.}
    def update(self,x=1200,y=450,*,camera=None,width=1920,height=1080,hold=False,keys=()):
        event=SimpleNamespace(held=list(keys),x=x,y=y,active=True)
        return self.adapter.update(event,.02,None,camera or self.camera,width,height,hold_direction=hold)
    def settled(self):
        for _ in range(120):self.update()
        return list(self.adapter.direction)
    def assertDirection(self,expected):
        self.assertLess(max(abs(a-b) for a,b in zip(expected,self.adapter.direction)),1e-10)
    def test_camera_rotation_roll_translation_and_zoom_cannot_steer_stationary_pointer(self):
        intent=self.settled()
        for camera in [
            {'eye':[100,800,900],'target':[101,800,900],'up':[0,1,0],'fov':.55},
            {'eye':[0,0,0],'target':[1,.5,-1],'up':[1,1,0],'fov':1.4},
            self.camera]:
            for _ in range(100):self.update(camera=camera)
            self.assertDirection(intent)
    def test_resize_rebases_pointer_without_rotating_intent(self):
        intent=self.settled()
        for w,h in [(1600,1000),(1280,720),(1920,1080)]:
            for _ in range(100):self.update(x=w*.6,y=h*.45,width=w,height=h)
            self.assertDirection(intent)
    def test_free_look_release_at_window_edge_does_not_arm_a_turn(self):
        intent=self.settled()
        for _ in range(50):self.update(x=1919,y=50,hold=True,keys=[FREE_LOOK_KEY,83])
        self.assertDirection(intent)
        for _ in range(200):self.update(x=1919,y=50)
        self.assertDirection(intent)
        # Actual pointer motion can resume flight input after observation.
        for _ in range(30):self.update(x=1900,y=60)
        self.assertGreater(math.dist(intent,self.adapter.direction),.01)
    def test_both_pitch_keys_explicitly_own_a_neutral_axis(self):
        values=self.update(keys=[87,83])
        self.assertTrue(values['manual_pitch']);self.assertEqual(values['pitch_input'],0)
        self.assertFalse(values['manual_roll'])
    def test_external_vertical_and_aft_intents_survive_pointer_rebase_and_camera_changes(self):
        from bvr_game.player_input import unit
        self.settled()
        for requested in [[0,0,1],[0,0,-1],[-1,.01,.1]]:
            target=unit(requested);self.adapter.adopt_direction(target)
            for index in range(100):
                self.update(x=1919,y=5,camera=self.camera if index%2 else
                    {'eye':[50,200,800],'target':[-100,300,790],'up':[1,1,0],'fov':.5})
                self.assertDirection(target)


if __name__=='__main__':unittest.main()
