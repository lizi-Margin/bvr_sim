"""Plot recorded physical response candidates; never regenerates simulation data."""
from pathlib import Path
import argparse,json,math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runs',type=Path,nargs='+',required=True)
    p.add_argument('--labels',nargs='+');p.add_argument('--speed',default='500.0');p.add_argument('--case',default='vertical')
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    labels=a.labels or [r.name for r in a.runs]
    for model in ['F22','F16','FG-A-10']:
        fig,axes=plt.subplots(3,2,figsize=(13,11),sharex=True,layout='constrained')
        for label,run in zip(labels,a.runs):
            data=json.loads((run/f'{model}-{a.speed}-{a.case}'/'samples.json').read_text())
            t=[x['time'] for x in data];m=[x['state']['measured'] for x in data]
            values=[[x['direction_error_deg'] for x in data],[x['speed'] for x in m],
                [math.degrees(x['body_rates'][0]) for x in m],[math.degrees(x['body_rates'][1]) for x in m],
                [math.degrees(x['alpha']) if x['alpha'] is not None else math.nan for x in m],
                [x['normal_g'] if x['normal_g'] is not None else math.nan for x in m]]
            for axis,y in zip(axes.flat,values):axis.plot(t,y,label=label,linewidth=1)
        for axis,title in zip(axes.flat,['Raw intent/path error (deg)','Airspeed (m/s)','Body roll rate (deg/s)',
            'Body pitch rate (deg/s)','Alpha (deg)','Normal load (G; absent for YASim)']):
            axis.set_title(title);axis.grid(alpha=.3);axis.set_xlabel('Simulation time (s)')
        axes.flat[0].legend();fig.suptitle(f'{model} / initial {a.speed} m/s / {a.case} / candidate diagnostics')
        for suffix in ['png','svg']:fig.savefig(a.output/(model+'-'+a.case+'.'+suffix),dpi=130)
        plt.close(fig)
if __name__=='__main__':main()
