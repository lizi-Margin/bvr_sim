import cv2, os
import numpy as np
import tqdm

def dump_FRAMEs_to_video(frames, vid_path, fps=10, quality=100):
    assert not os.path.exists(vid_path)
    if isinstance(frames, np.ndarray):
        assert len(frames.shape) == 4
    else:
        assert isinstance(frames, list)
        assert isinstance(frames[0], np.ndarray)
        assert len(frames[0].shape) == 3
    
    h, w = frames[0].shape[:2]
    is_color = len(frames[0].shape) == 3 and frames[0].shape[2] == 3
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(vid_path, fourcc, fps, (w, h), is_color)
    out.set(cv2.VIDEOWRITER_PROP_QUALITY, quality)
    # for frame in tqdm.tqdm(frames, desc=f'[dump_FRAMEs_to_video] vid_path={vid_path}'):
    for frame in tqdm.tqdm(frames, desc=f'[dump_FRAMEs_to_video] {os.path.basename(vid_path)}'):
        if not is_color and len(frame.shape) == 3:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        out.write(frame)
    out.release()

def load_FRAMEs_from_video(vid_path):
    assert os.path.exists(vid_path)

    cap = cv2.VideoCapture(vid_path)
    frames = []
    while True:
        ret, frame = cap.read()
        # print(f"\r[load_FRAMEs_from_video] loading {vid_path}, frame_cnt={len(frames)}", end='')
        print(f"\r[load_FRAMEs_from_video] loading {os.path.basename(vid_path)}, frame_cnt={len(frames)}", end='')
        if not ret:
            break
        frames.append(frame)
    cap.release()
    print(end='\n')
    return frames