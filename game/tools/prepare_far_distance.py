"""Keep finite draw-sort distances beyond half-float's 65504 metre limit."""
from pathlib import Path
import argparse,hashlib,json

def prepare(engine):
    engine=Path(engine).resolve();file=engine/'WickedEngine/wiRenderer.cpp'
    if not (engine/'bvr-wide-primitive.json').exists():raise ValueError('Use an owned prepared engine fork')
    text=file.read_text();before=hashlib.sha256(file.read_bytes()).hexdigest()
    for old,new in [
        ('this->distance = XMConvertFloatToHalf(distance);','this->distance = XMConvertFloatToHalf(distance * 0.001f); // kilometres: same 16-bit sort key, finite beyond 65.5km'),
        ('return XMConvertHalfToFloat(HALF(distance));','return XMConvertHalfToFloat(HALF(distance)) * 1000.f;'),
    ]:
        if text.count(old)!=1:raise ValueError('Draw-distance codec source changed')
        text=text.replace(old,new,1)
    anchor='struct RenderQueue'
    if text.count(anchor)!=1:raise ValueError('Render queue source changed')
    text=text.replace(anchor,'''float BvrDrawDistanceRoundTrip(float value){RenderBatch batch;batch.Create(0,0,value,0);return batch.GetDistance();}

'''+anchor,1)
    file.write_text(text,encoding='utf8')
    (engine/'bvr-far-distance.json').write_text(json.dumps({'input_sha256':before,'output_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'units':'half-float kilometres; GetDistance returns metres','scope':__doc__},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--engine',type=Path,required=True);prepare(p.parse_args().engine)
