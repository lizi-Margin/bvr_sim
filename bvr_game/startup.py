"""Lightweight startup messages; never imports native simulation or rendering."""
import json,os

PREFIX='BVR_STARTUP '

def progress(stage,message,**details):
    if os.environ.get('BVR_GAME_STARTUP_PROGRESS')=='1':
        # The worker's stdout is redirected by the launcher. Keep the wire
        # format ASCII so Windows' active console code page cannot crash the
        # frozen build when a Chinese progress message is emitted.
        print(PREFIX+json.dumps({'stage':stage,'message':message,**details},ensure_ascii=True),flush=True)
