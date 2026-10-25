"""Client adapter for the simulator's developer-authored weapon/station catalog."""
import sys
from contextlib import redirect_stdout
with redirect_stdout(sys.stderr):
    from bvr_sim.bvr_env_cpp import bvr_sim_cpp as native

def weapons():
    return {w.id:w for w in native.weapon_catalog()}

def stations(row):
    return native.aircraft_stations(row['simulation_model'])

def preset(row,id):
    return dict(native.loadout_preset(row['simulation_model'],id))

def counts(mounts):
    result={}
    for weapon in mounts.values():
        if weapon:result[weapon]=result.get(weapon,0)+1
    return result

def totals(mounts):
    catalog=weapons();c=counts(mounts)
    return tuple(sum(n for w,n in c.items() if catalog[w].category==kind) for kind in ('missile','bomb'))

def configure(config,row,mounts):
    errors=native.validate_loadout(row['simulation_model'],mounts)
    if errors:raise ValueError('; '.join(errors))
    missiles,bombs=totals(mounts)
    config.use_station_loadout=True;config.loadout=dict(mounts)
    config.missiles=missiles;config.bombs=bombs

def initial_weapon(mounts):
    c=counts(mounts)
    return next((w for w in ['AIM-120C7','AIM-120C5','AIM-9M','Mk-82'] if c.get(w)), '')

def summary(mounts):
    return ' / '.join(f'{w} × {n}' for w,n in counts(mounts).items()) or '无挂载'
