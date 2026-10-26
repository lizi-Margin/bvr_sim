"""Command entry point; interactive play starts through the cancellable loader."""
import os,sys

def main(args=None):
    args=list(sys.argv[1:] if args is None else args)
    if args and args[0]=='play' and os.environ.get('BVR_GAME_STARTUP_WORKER')!='1':
        from .launcher import main as launch
        return launch(args)
    from .app import main as run
    return run()

if __name__=='__main__':raise SystemExit(main())
