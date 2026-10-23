"""Dependency-light indexed triangle interpolation for baked height archives."""
import numpy as np

def sample_grid(data,meta,north,west):
    u=np.clip((np.asarray(north)-meta['origin_north'])/meta['spacing'],0,meta['columns']-1)
    v=np.clip((np.asarray(west)-meta['origin_west'])/meta['spacing'],0,meta['rows']-1)
    col=np.minimum(np.floor(u).astype(int),meta['columns']-2);row=np.minimum(np.floor(v).astype(int),meta['rows']-2)
    a=u-col;b=v-row;h00=data[row,col].astype(float);h10=data[row,col+1].astype(float);h01=data[row+1,col].astype(float);h11=data[row+1,col+1].astype(float)
    return np.where(a+b<=1,h00+a*(h10-h00)+b*(h01-h00),h11+(1-a)*(h01-h11)+(1-b)*(h10-h11))
