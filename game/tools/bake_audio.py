"""Deterministic authored Alpha sounds; no simulation or audio-device dependency."""
from pathlib import Path
import json,hashlib,wave
import numpy as np
ROOT=Path(__file__).resolve().parents[2]

def bake():
    out=ROOT/'game/assets/registered/audio';out.mkdir(parents=True,exist_ok=True);rate=22050;rng=np.random.default_rng(7);records={}
    definitions={'engine':(2,90),'search':(.12,700),'lock':(.3,1200),'rwr':(.28,1650),'launch':(.65,180),'explosion':(1.6,65),'result':(.8,540)}
    for name,(duration,frequency) in definitions.items():
        t=np.arange(int(duration*rate))/rate
        tone=np.sin(2*np.pi*frequency*t)
        if name=='engine':
            noise=rng.normal(0,1,len(t));filtered=np.convolve(noise,np.ones(8)/8,mode='same')
            signal=.22*tone+.12*np.sin(2*np.pi*180*t)+.28*filtered
        elif name in ['explosion','launch']:
            signal=(rng.normal(0,.33,len(t))+.3*np.sin(2*np.pi*(frequency*t-15*t*t)))*np.exp(-t*(3 if name=='explosion' else 7))
        else:signal=.45*tone*np.minimum(t/.015,1)*np.minimum((duration-t)/.03,1)
        if name=='result':signal+=.23*np.sin(2*np.pi*810*t)
        pcm=(np.clip(signal,-1,1)*27000).astype('<i2');path=out/(name+'.wav')
        with wave.open(str(path),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate);w.writeframes(pcm.tobytes())
        records[name]={'file':str(path.resolve()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'duration_s':duration,'sample_rate':rate,'peak':int(np.max(abs(pcm))),'rms':float(np.sqrt(np.mean(pcm.astype(float)**2))),'license':'GPL-3.0-or-later','source_url':'authored:game/tools/bake_audio.py','recipe':{'seed':7,'tone_hz':frequency,'generator':'bake_audio_v1'}}
    (out/'manifest.json').write_text(json.dumps({'id':'audio','sounds':records},indent=2));runtime=ROOT/'game/runtime.json';r=json.loads(runtime.read_text());r['audio']={k:v['file'] for k,v in records.items()};runtime.write_text(json.dumps(r,indent=2));return records
if __name__=='__main__':print(json.dumps(bake(),indent=2))
