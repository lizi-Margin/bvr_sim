"""JSON boundary adapters only; motion, contacts, damage and sensors remain in core."""
def route_from_data(native,data):
    route=native.VehicleRoute()
    for key,value in data.items():
        if key not in ('points','speed','loop'):raise ValueError('Unknown route field: '+key)
        setattr(route,key,value)
    return route

def spec_from_data(native,data):
    spec=native.GroundUnitSpec()
    for key,value in data.items():
        if key=='route':value=route_from_data(native,value)
        if not hasattr(spec,key):raise ValueError('Unknown ground specification field: '+key)
        setattr(spec,key,value)
    return spec

def apply_config(native,config,data):
    for key,value in data.items():
        if key=='ground_units':value=[spec_from_data(native,v) for v in value]
        setattr(config,key,value)

def replay_ground_action(native,session,action):
    if 'spawn_ground' in action:session.spawn_ground(spec_from_data(native,action['spawn_ground']));return True
    if 'ground_route' in action:
        session.set_ground_route(action['uid'],route_from_data(native,action['ground_route']));return True
    if 'ground_parked' in action:session.park_ground(action['uid'],action['ground_parked']);return True
    return False
