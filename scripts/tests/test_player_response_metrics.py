"""A floating timestamp at an intent boundary must not select the old target."""
import importlib.util,json,math,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('response_metrics',ROOT/'game/tools/summarize_player_response.py')
metrics=importlib.util.module_from_spec(spec);spec.loader.exec_module(metrics)


class ResponseMetricsTests(unittest.TestCase):
    def test_onset_uses_new_request_even_if_old_sample_time_rounds_above_four(self):
        samples=[]
        for tick in range(150,401,5):
            active=tick>200;target=[math.sqrt(.5),math.sqrt(.5),0] if active else [1,0,0]
            yaw=math.radians(min(45,(tick-200)*.25)) if active else 0
            measured={'velocity':[math.cos(yaw),math.sin(yaw),0],'body_rates':[0,0,0],'alpha':0,'beta':0,'normal_g':1,'density':1}
            samples.append({'tick':tick,'time':4.000000000000003 if tick==200 else tick*.02,'target':target,'direction_error_deg':abs(45-math.degrees(yaw)) if active else 0,
                'state':{'measured':measured,'protecting':False,'energy_limited':False,'controls':{'aileron':0,'elevator':0,'rudder':0}}})
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'samples.json').write_text(json.dumps(samples));(p/'intent-tape.json').write_text(json.dumps({'config':{'dt':.02},'sample_ticks':5}))
            result=metrics.summarize(p,{'case':'turn_45','sample_ticks':5})['step_response']
        self.assertEqual(result['command_onset_tick'],200)
        self.assertEqual(result['first_sample_with_new_request_tick'],205)
        self.assertAlmostEqual(result['command_amplitude_deg'],45.)
        self.assertGreater(result['response_delay_10pct_s'],0)


if __name__=='__main__':unittest.main()
