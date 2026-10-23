"""Offline geographic import contract and a local raster/GeoJSON adapter.

Provider downloaders are outside the runtime. GeoTIFF reprojection belongs in
an adapter which produces the explicit metre grid accepted here; unsupported
formats raise instead of silently creating terrain. No actual DEM is bundled.
"""
from dataclasses import dataclass,asdict
from pathlib import Path
from typing import Protocol
import hashlib,json,math
import numpy as np

@dataclass
class GeoRequest:
    bounds_wgs84: list # [west,south,east,north] degrees
    origin_lla: list # [longitude,latitude,altitude] WGS84
    spacing_m: float=50
    projection: str='WGS84 ECEF tangent NWU'

@dataclass
class GeoSource:
    provider: str # Copernicus DEM / Sentinel-2 / ESA WorldCover / OSM-Geofabrik
    layer: str # elevation / imagery / landcover / vectors
    file: str
    sha256: str
    license: str
    source_url: str
    grid: dict | None=None # projected raster origin_north/origin_west/spacing

class OfflineGeoAdapter(Protocol):
    def fetch_to_cache(self,request:GeoRequest,cache:Path)->list[GeoSource]:...
    def project_and_resample(self,request:GeoRequest,sources:list[GeoSource],output:Path)->dict:...

def local_nwu(longitude,latitude,altitude,origin):
    def ecef(lon,lat,alt):
        lon,lat=math.radians(lon),math.radians(lat);a=6378137.;e2=6.6943799901413165e-3
        radius=a/math.sqrt(1-e2*math.sin(lat)**2)
        return np.array([(radius+alt)*math.cos(lat)*math.cos(lon),(radius+alt)*math.cos(lat)*math.sin(lon),(radius*(1-e2)+alt)*math.sin(lat)])
    delta=ecef(longitude,latitude,altitude)-ecef(*origin);lon,lat=map(math.radians,origin[:2])
    east=np.dot(delta,[-math.sin(lon),math.cos(lon),0]);north=np.dot(delta,[-math.sin(lat)*math.cos(lon),-math.sin(lat)*math.sin(lon),math.cos(lat)])
    up=np.dot(delta,[math.cos(lat)*math.cos(lon),math.cos(lat)*math.sin(lon),math.sin(lat)])
    return [float(north),float(-east),float(up)]

def prepare_offline(request:GeoRequest,sources:list[GeoSource],output):
    """Verify cached sources, normalize vectors and declare a bakeable recipe overlay.

Elevation/landcover arrays must be preprojected .npy; their metre-grid metadata
is mandatory. Worldgen applies its existing airport/settlement flattening after
sampling the imported elevation. Imagery is retained for a future macro-texture
adapter, explicitly not claimed to be rendered by this function.
"""
    out=Path(output);out.mkdir(parents=True,exist_ok=True);overlay={'geographic_import':{'request':asdict(request),'sources':[],'runtime_requires_network':False},'roads':[],'rivers':[],'building_footprints':[]}
    for source in sources:
        p=Path(source.file)
        if hashlib.sha256(p.read_bytes()).hexdigest()!=source.sha256:raise ValueError('Geographic source hash mismatch: '+str(p))
        if not source.license or not source.source_url:raise ValueError('Geographic source requires provenance')
        overlay['geographic_import']['sources'].append(asdict(source))
        if source.layer in ['elevation','landcover']:
            if p.suffix!='.npy' or not source.grid:raise ValueError('Adapter must provide projected .npy and metre-grid metadata')
            data=np.load(p,allow_pickle=False)
            if data.ndim!=2 or min(data.shape)<2 or not np.all(np.isfinite(data)):raise ValueError('Invalid geographic raster')
            overlay['geographic_import'][source.layer]={'file':str(p.resolve()),'sha256':source.sha256,**source.grid,'rows':data.shape[0],'columns':data.shape[1]}
        elif source.layer=='vectors':
            document=json.loads(p.read_text(encoding='utf8'))
            for index,feature in enumerate(document['features']):
                props=feature.get('properties',{});geometry=feature['geometry'];kind=geometry['type']
                coords=geometry['coordinates'];id=str(props.get('id',index))
                if kind=='LineString':
                    points=[local_nwu(*v[:2],0,request.origin_lla)[:2] for v in coords]
                    if props.get('highway'):overlay['roads'].append({'id':'osm_'+id,'width_m':float(props.get('width',9)),'points':points})
                    elif props.get('waterway'):overlay['rivers'].append({'id':'osm_'+id,'width_m':float(props.get('width',30)),'bank_width_m':100,'points':points})
                elif kind=='Polygon' and props.get('building'):
                    overlay['building_footprints'].append({'id':'osm_'+id,'polygon':[local_nwu(*v[:2],0,request.origin_lla)[:2] for v in coords[0]],'tags':props})
        elif source.layer!='imagery':raise ValueError('Unknown geographic layer: '+source.layer)
    path=out/'geographic-overlay.json';path.write_text(json.dumps(overlay,indent=2),encoding='utf8');return overlay
