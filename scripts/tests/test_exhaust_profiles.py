"""Reject invented flames; retain explicit source capability and state provenance."""
import tempfile,unittest
from pathlib import Path
from bvr_game.exhaust_profiles import inspect_fdm


class ExhaustProfileTests(unittest.TestCase):
    def inspect(self,text,files=None):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'fdm.xml').write_text(text)
            for name,data in (files or {}).items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(data)
            return inspect_fdm(root/'fdm.xml',root)

    def test_dry_jet_does_not_gain_flame_from_throttle_or_named_output(self):
        result=self.inspect('<airplane><jet thrust="9000"><control-output control="REHEAT" prop="fake/afterburner"/></jet></airplane>')
        engine=result['engines'][0];self.assertFalse(engine['afterburner_declared']);self.assertEqual(engine['mode'],'disabled');self.assertEqual(engine['property'],'')

    def test_reheat_requires_positive_capability_and_explicit_normalized_output(self):
        for output,expected in [('', 'unavailable'),('<control-output control="REHEAT" prop="engines/engine[1]/afterburner"/>','property'),('<control-output control="REHEAT" prop="temperature" max="1000"/>','unavailable')]:
            with self.subTest(output=output):
                result=self.inspect('<airplane><jet thrust="9000" afterburner="15000">'+output+'</jet></airplane>')
                self.assertEqual(result['engines'][0]['mode'],expected)
                self.assertEqual(len(result['sources']),1)

    def test_included_jsbsim_engine_capability_is_separate_from_missing_telemetry(self):
        result=self.inspect('<fdm_config><propulsion file="Systems/propulsion"/></fdm_config>',{
            'Systems/propulsion.xml':'<propulsion><engine file="hot"/><engine file="dry"/><engine file="missing"/></propulsion>',
            'Systems/Engines/hot.xml':'<turbine_engine><augmented>1</augmented></turbine_engine>',
            'Systems/Engines/dry.xml':'<turbine_engine><augmented>0</augmented></turbine_engine>'})
        self.assertEqual([e['afterburner_declared'] for e in result['engines']],[True,False,None])
        self.assertEqual([e['mode'] for e in result['engines']],['unavailable','disabled','unavailable'])
        self.assertEqual(len(result['sources']),4)

    def test_propeller_has_no_invented_jet_engine(self):
        result=self.inspect('<airplane><propeller/></airplane>')
        self.assertEqual(result['engines'],[]);self.assertTrue(result['unresolved'])


if __name__=='__main__':unittest.main()
