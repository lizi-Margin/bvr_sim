import os,time,cv2,copy,re,uuid
import threading
import json
import numpy as np
import tqdm
from random import sample
from bvr_sim.uhtk.UTIL.colorful import *
from bvr_sim.uhtk.siri.utils.lprint import lprint, lprint_
from bvr_sim.uhtk.siri.utils.iterable_tools import iterable_eq
from bvr_sim.uhtk.siri.utils.is_basic_type import is_basic_type
from bvr_sim.uhtk.siri.utils.video_io import dump_FRAMEs_to_video, load_FRAMEs_from_video

UUID_KEY = "_UUID"
def get_traj_uuid():
    t_code = time.strftime('%Y%m%d%H%M%S')
    uuid_code = uuid.uuid4().hex
    return f"{t_code}{uuid_code}"

import platform
IS_WINDOWS = (platform.system() == 'Windows')
USE_VIDEO_IO = True
VIDEO_IO_COMPRESS_QUALITY = 90

class cfg:
    if IS_WINDOWS:
        logdir = 'G:/HMP_IL/'
    else:
        logdir = '../HMP_IL/'

def _is_traj(traj_name: str) -> bool:
    traj_name = os.path.basename(traj_name)
    return traj_name.endswith(".d") and traj_name.startswith("traj-")

##############################################################################################################

def save_and_compress_FRAMEs(FRAMEs: np.ndarray, path, FRAMEs_name):
    FRAMES_dir_name = f"{FRAMEs_name}.d"
    FRAMEs_dir = os.path.join(path, FRAMES_dir_name)
    if not os.path.exists(FRAMEs_dir):
        os.makedirs(FRAMEs_dir)

    if USE_VIDEO_IO:
        vid_path =              os.path.join(FRAMEs_dir,      f"{FRAMEs_name}.mp4")
        vid_file_name_to_load = os.path.join(FRAMES_dir_name, f"{FRAMEs_name}.mp4")
        dump_FRAMEs_to_video(
            FRAMEs,
            vid_path,
            fps=30,
            quality=VIDEO_IO_COMPRESS_QUALITY
        )
        assert os.path.exists(vid_path)

        image_data = {
            'file_name': vid_file_name_to_load,
            'save_time': time.strftime('%Y%m%d-%H:%M:%S'),
            'tick_time_may_be_wrong': cfg.tick,
            'num_frames': len(FRAMEs),
        }
        json_path = os.path.join(path, f"{FRAMEs_name}.json")
        with open(json_path, 'w') as f:
            json.dump(image_data, f, indent=2)
        return

    image_data = []
    for i, img_np in enumerate(FRAMEs):
        file_name = os.path.join(FRAMES_dir_name, f"{FRAMEs_name}_{i}.png")
        if np.any(np.isnan(img_np), axis=None) or np.all(img_np == 0):
            is_nan = True
        else:
            is_nan = False
            img_path = os.path.join(path, file_name)
            cv2.imwrite(img_path, img_np)
        print(f"\r[save_and_compress_FRAMEs] saving {file_name}, is_nan={is_nan}", end='')
        image_data.append({
            'file_name': file_name,
            'shape': img_np.shape,
            'is_nan': is_nan
        })
    print(end='\n')

    json_path = os.path.join(path, f"{FRAMEs_name}.json")
    with open(json_path, 'w') as f:
        json.dump(image_data, f, indent=2)


def load_compressed_FRAMEs(path, FRAMEs_name):
    with open(os.path.join(path, f"{FRAMEs_name}.json"), 'r') as f:
        meta_data = json.load(f)
    
    if isinstance(meta_data, dict):
        vid_file_name = meta_data['file_name']
        vid_path = os.path.join(path, vid_file_name)
        images = load_FRAMEs_from_video(vid_path)
        assert isinstance(images, list)
        assert len(images) > 0
    else:
        assert isinstance(meta_data, list), f"type(meta_data)={type(meta_data)}, which should be list in old png dir format"
        images = []
        for img_info in meta_data:
            file_name = img_info['file_name']
            expected_shape = img_info['shape']
            if ('is_nan' in img_info) and img_info['is_nan'] == True:
                is_nan = True
                img_np = np.zeros(expected_shape, dtype=np.uint8)
                # img_np[...] = np.nan
            else:
                is_nan = False
                img_path = os.path.join(path, file_name)
                img_np = cv2.imread(img_path).astype(np.uint8)
                loaded_shape = img_np.shape

                if not iterable_eq(expected_shape, loaded_shape):
                    raise ValueError(f"Image {file_name} has inconsistent shape. "
                                    f"Expected: {expected_shape}, Got: {loaded_shape}")
                
            print(f"\r[load_compressed_FRAMEs] loading {file_name}, is_nan={is_nan}", end='')

            # if len(expected_shape) == 3 and expected_shape[2] == 3:
            #     img_np = cv2.cvtColor(img_np, cv2.COLOR_BGR2RGB)

            images.append(img_np)
        print(end='\n')
    
    return np.array(images)

##############################################################################################################

NPY_special_key = 'npy_filenames'
FRAME_special_key = 'FRAMEs_filenames'
BUNDLED_ARRAY_KEY = '__npz_bundle__'
BUNDLED_KEYS_KEY = '__npz_keys__'
MANIFEST_FILENAME = ".traj_manifest.json"

def safe_dump(obj, path):
    if not os.path.exists(path): os.makedirs(path)
    cls_name = obj.__class__.__name__
    serializable_data = {}
    numpy_arrays = {}
    FRAMEs = {}
    for attr, value in obj.__dict__.items():
        if str(attr).startswith("FRAME"): 
            assert isinstance(value, np.ndarray)
            print(f"[safe_dump] {obj.__class__.__name__}.{attr} is FRAME type")
            FRAMEs[attr] = value
        elif isinstance(value, np.ndarray):
            numpy_arrays[attr] = value
        elif is_basic_type(value):
            serializable_data[attr] = value
        else:
            assert False, f'not implemented yet, key={attr} type={type(value)}'

    assert not NPY_special_key in serializable_data
    assert not FRAME_special_key in serializable_data

    if numpy_arrays:
        bundle_filename = f"{cls_name}_arrays.npz"
        # consolidate arrays into single archive to reduce tiny-file overhead
        np.savez_compressed(os.path.join(path, bundle_filename), **numpy_arrays)
        serializable_data[NPY_special_key] = {
            BUNDLED_ARRAY_KEY: bundle_filename,
            BUNDLED_KEYS_KEY: list(numpy_arrays.keys()),
        }
    else:
        serializable_data[NPY_special_key] = {}

    FRAMEs_filenames = {}
    for key, frame in FRAMEs.items():
        FRAMEs_name = f"{cls_name}_{key}"
        save_and_compress_FRAMEs(frame, path, FRAMEs_name)
        FRAMEs_filenames[key] = FRAMEs_name
    serializable_data[FRAME_special_key] = FRAMEs_filenames

    if not UUID_KEY in serializable_data:
        serializable_data[UUID_KEY] = get_traj_uuid()

    with open(f"{path}/{cls_name}.json", 'w') as f:
        json.dump(serializable_data, f, indent=2)

old_dataset_names = [
    'traj-Grabber-tick=0.1-limit=200-pp19',
    'traj-Grabber-tick=0.1-limit=200-nav',
    'traj-Grabber-tick=0.1-limit=200-pure',
    'traj-Grabber-tick=0.1-limit=200-old',
]
def has_old_dataset_name(path :str):
    for name in old_dataset_names:
        if name in path:
            return True
    return False

def safe_load(obj, path):
    if not os.path.exists(path):
        print亮黄(f"warning: {path} not found, skip loading")
        return obj

    cls_name = obj.__class__.__name__
    serializable_data = {}
    numpy_arrays = {}
    FRAMEs = {}
    try:
        with open(f"{path}/{cls_name}.json", 'r') as f:
            serializable_data = json.load(f)
    except json.decoder.JSONDecodeError:
        # print亮黄(f"Warning: {path}/{cls_name}.json is broken, skip loading")
        with open(f"./rm_broken_traj.sh", 'a') as f:
            f.write(f"rm -r '{path}'\n")
        return None
    assert isinstance(serializable_data, dict)

    npy_filenames = serializable_data.pop(NPY_special_key)
    if (
        isinstance(npy_filenames, dict)
        and BUNDLED_ARRAY_KEY in npy_filenames
        and npy_filenames[BUNDLED_ARRAY_KEY] is not None
    ):
        bundle_filename = npy_filenames[BUNDLED_ARRAY_KEY]
        bundle_path = os.path.join(path, bundle_filename)
        bundle_keys = npy_filenames.get(BUNDLED_KEYS_KEY)
        with np.load(bundle_path, allow_pickle=True, mmap_mode='r') as bundle:
            keys_to_load = bundle_keys or bundle.files
            for key in keys_to_load:
                numpy_arrays[key] = bundle[key]
    else:
        legacy_arrays = {}
        legacy_file_paths = {}
        for key, npy_filename in npy_filenames.items():
            file_path = os.path.join(path, npy_filename)
            arr = np.load(file_path, allow_pickle=True)
            numpy_arrays[key] = arr
            legacy_arrays[key] = np.asarray(arr)
            legacy_file_paths[key] = file_path

            if has_old_dataset_name(path):
                if key == "mouse":
                    print亮黄(f"[safe_load] warning: {path} has old dataset signiture, load key={key} in legacy mode")
                    print亮黄(f"[safe_load] key={key}, shape={numpy_arrays[key].shape}, max={np.max(numpy_arrays[key])}, min={np.min(numpy_arrays[key])}, processing")
                    numpy_arrays[key] = numpy_arrays[key] / 2
                    legacy_arrays[key] = np.asarray(numpy_arrays[key])
                    print亮黄(f"[safe_load] key={key}, shape={numpy_arrays[key].shape}, max={np.max(numpy_arrays[key])}, min={np.min(numpy_arrays[key])}, processed")

        if legacy_arrays:
            bundle_filename = f"{cls_name}_arrays.npz"
            bundle_path = os.path.join(path, bundle_filename)
            try:
                np.savez_compressed(bundle_path, **legacy_arrays)
                metadata_for_write = dict(serializable_data)
                metadata_for_write[NPY_special_key] = {
                    BUNDLED_ARRAY_KEY: bundle_filename,
                    BUNDLED_KEYS_KEY: list(legacy_arrays.keys()),
                }
                _rewrite_traj_metadata(path, cls_name, metadata_for_write)

                with np.load(bundle_path, allow_pickle=True, mmap_mode='r') as bundle:
                    for key in legacy_arrays.keys():
                        numpy_arrays[key] = bundle[key]
                for file_path in legacy_file_paths.values():
                    try:
                        os.remove(file_path)
                    except OSError as e:
                        print亮黄(f"[safe_load] failed to remove legacy file {file_path}: {e}")
            except Exception as e:
                print亮黄(f"[safe_load] failed to auto-convert legacy arrays at {path}: {e}")
            # print_blue(f"converted legacy arrays at {path}")

    if FRAME_special_key in serializable_data:
        FRAMEs_filenames = serializable_data.pop(FRAME_special_key)
        for key, FRAMEs_name in FRAMEs_filenames.items():
            FRAMEs[key] = load_compressed_FRAMEs(path, FRAMEs_name)

    for attr, value in {**serializable_data, **numpy_arrays, **FRAMEs}.items():
        setattr(obj, attr, value)
    
    return obj

def _rewrite_traj_metadata(path: str, cls_name: str, metadata: dict):
    json_path = os.path.join(path, f"{cls_name}.json")
    try:
        with open(json_path, "w") as f:
            json.dump(metadata, f, indent=2)
    except Exception as e:
        print亮黄(f"[safe_load] failed to update metadata {json_path}: {e}")
##############################################################################################################

def safe_dump_traj_pool(traj_pool, pool_name, traj_dir=None):
    if isinstance(pool_name, list):
        assert len(pool_name) == len(traj_pool)
    elif isinstance(pool_name, str):
        pool_name = [pool_name] * len(traj_pool)
    else: raise ValueError(f"pool_name must be str or list of str, but got {type(pool_name)}")
    # default_traj_dir = f"{cfg.logdir}/traj_pool_safe/"
    if traj_dir is None:
        if IS_WINDOWS:
            traj_dir = f"{cfg.logdir}/Default/{time.strftime('%Y%m%d-%H#%M#%S')}/"
        else:
            traj_dir = f"{cfg.logdir}/Default/{time.strftime('%Y%m%d-%H:%M:%S')}/"
    
    
    os.makedirs(traj_dir, exist_ok=True)
    all_files_existing = [f for f in os.listdir(traj_dir) if _is_traj(f)]
    try:
        # extract index from existing files
        # existing_indexs = [int(f.split(f"traj-{pool_name}-")[1].split(".d")[0]) for f in all_files_existing]
        res = re.findall(r"traj-[\w\-]+-(\d+).d", " ".join(all_files_existing))
        if len(res) == 0:
            index_start = 0
        else:
            existing_indexs = [int(x) for x in res]
            max_index = max(existing_indexs) if len(existing_indexs) > 0 else -1
            index_start = max_index + 1
    except:
        print_bold_red(f"Warning: failed to extract index from existing files, start from 0")
        index_start = 0
        
    for i, traj in enumerate(traj_pool):
        index = i + index_start
        traj_name = f"traj-{pool_name[i]}-{index}.d"
        safe_dump(obj=traj, path=f"{traj_dir}/{traj_name}")
    
        print亮黄(f"traj saved in file: {traj_dir}/{traj_name}")

    # if os.path.islink(default_traj_dir[:-1]):
    #     os.unlink(default_traj_dir[:-1])
    # os.symlink(os.path.abspath(traj_dir), os.path.abspath(default_traj_dir))

###############################################################################################
# # cache
# def _manifest_path(dir_path: str) -> str:
#     return os.path.join(dir_path, MANIFEST_FILENAME)

# def _load_dir_manifest(dir_path: str):
#     manifest_path = _manifest_path(dir_path)
#     if not os.path.exists(manifest_path):
#         return None
#     try:
#         with open(manifest_path, "r") as f:
#             data = json.load(f)
#         return data
#     except Exception as e:
#         print黄(f"[safe_load_traj_pool] manifest at {manifest_path} broken ({e}), rebuilding")
#         return None

# def _save_dir_manifest(dir_path: str, traj_names):
#     manifest_path = _manifest_path(dir_path)
#     data = {
#         "dir_mtime": os.path.getmtime(dir_path),
#         "traj_names": traj_names,
#     }
#     try:
#         with open(manifest_path, "w") as f:
#             json.dump(data, f)
#     except Exception as e:
#         print亮黄(f"[safe_load_traj_pool] failed to write manifest {manifest_path}: {e}")

###############################################################################################

class safe_load_traj_pool:
    def __init__(self,
        max_len=None,
        traj_dir="traj_pool_safe",
        logdir='./',
        verbose=False,
        use_cache=True,
        preload_cache=True,
        preload_cache_percent=0.25,
    ):
        self.verbose = verbose
        if isinstance(traj_dir, str): traj_dir = [traj_dir]
        self.traj_names = []
        for i in range(len(traj_dir)):
            traj_dir[i] = f"{logdir}/{traj_dir[i]}/"
            dir_path = traj_dir[i]
            # manifest = _load_dir_manifest(dir_path)
            # need_rebuild = True
            # if manifest:
            #     recorded_mtime = manifest.get("dir_mtime", -1)
            #     if abs(recorded_mtime - os.path.getmtime(dir_path)) < 1e-3:
            #         traj_entries = manifest.get("traj_names", [])
            #         if traj_entries:
            #             self.traj_names.extend([os.path.join(dir_path, name) for name in traj_entries])
            #             need_rebuild = False
            # if need_rebuild:
            #     traj_entries = [name for name in os.listdir(dir_path) if _is_traj(name)]
            #     self.traj_names.extend([os.path.join(dir_path, name) for name in traj_entries])
            #     _save_dir_manifest(dir_path, traj_entries)

            traj_entries = [name for name in os.listdir(dir_path) if _is_traj(name)]
            self.traj_names.extend([os.path.join(dir_path, name) for name in traj_entries])

        # self.lock = threading.Lock()  # 🔒
            
        self.used_traj_names = []
        self.n_full_data_used = 0
        if max_len is not None:
            assert max_len > 0
            if max_len < len(self.traj_names):
                self.traj_names = self.traj_names[:max_len]
        
        self.use_cache = use_cache
        self._traj_cache = {}
        if preload_cache and use_cache:
            self._load_cache()
            old_cache_size = len(self._traj_cache)

            trajs_altered = False
            self._load_dataset(preload_cache_percent)
            new_names_set = set(self.traj_names)
            names_to_delete = []
            for k, o in self._traj_cache.items():
                if not k in new_names_set:
                    trajs_altered =True
                    print_yellow(f"[safe_load_traj_pool] preload cache: {k} not found in self.traj_names, deleted")
                    names_to_delete.append(k)
            for k in names_to_delete:
                del self._traj_cache[k]

            # if not os.path.exists(self._cache_path()):
            if trajs_altered or old_cache_size < len(self._traj_cache):
                self.save_cache()
    
    def _load_dataset(self, percent):
        try:
            traj_names = self.traj_names.copy()
            traj_names = traj_names[:int(len(traj_names) * percent)]
            return self._load(traj_names=traj_names, use_tqdm=True)
        except KeyboardInterrupt:
            print(f"[safe_load_traj_pool] load dataset interrupted by user")
    
    def _cache_path(self):
        user_path = os.path.expanduser("~")
        cwd_path = os.getcwd()
        cache_dir = os.path.join(cwd_path, ".uhtk", "safe_load_traj_pool")
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, "_traj_cache.pkl")
        return cache_path
    
    def save_cache(self):
        import pickle
        # /home/user/.uhtk/safe_load_traj_pool
        cache_path = self._cache_path()
        with open(cache_path, "wb") as f:
            print(f"[safe_load_traj_pool] cache size: {len(self._traj_cache)}")
            print(f"[safe_load_traj_pool] saving cache to {cache_path}...")
            pickle.dump(self._traj_cache, f)
            print(f"[safe_load_traj_pool] cache file size: {os.path.getsize(cache_path)}")
    
    def _load_cache(self):
        import pickle
        # /home/user/.uhtk/safe_load_traj_pool
        cache_path = self._cache_path()
        if os.path.exists(cache_path):
            # print the cache file size
            print(f"[safe_load_traj_pool] cache file size: {os.path.getsize(cache_path)}")
            with open(cache_path, "rb") as f:
                print(f"[safe_load_traj_pool] loading cache from {cache_path}...")
                self._traj_cache = pickle.load(f)
    
    def __call__(self, pool_name='', n_samples=200):
        if len(self.traj_names) > n_samples:
            n_samples = max(n_samples, 1)

            # with self.lock:  # 🔒
            if len(self.used_traj_names) > (len(self.traj_names) - n_samples):
                self.used_traj_names = []
                self.n_full_data_used += 1

            # traj_names_to_sample = copy.copy(self.traj_names)
            # for traj in self.used_traj_names:
            #     ## this is TOO expensive
            #     # if traj not in traj_names_to_sample: print亮红(lprint_(self, f"ERROR: {traj} not found in self.traj_names !!!"))
            #     # else: traj_names_to_sample.remove(traj)
            #     traj_names_to_sample.remove(traj)
            used_set = set(self.used_traj_names)
            traj_names_to_sample = [t for t in self.traj_names if t not in used_set]
                    

            # traj_names = sample(traj_names_to_sample, n_samples)
            traj_names_to_sample_np = np.array(traj_names_to_sample)
            sample_idx = np.random.choice(len(traj_names_to_sample_np), size=n_samples, replace=False)
            traj_names = traj_names_to_sample_np[sample_idx].tolist()

            self.used_traj_names.extend(traj_names)

            # if self.verbose:
            #     plt = ["o"] * len(self.traj_names)
            #     for traj in self.used_traj_names:
            #         index = self.traj_names.index(traj)
            #         plt[index] = "x"
            #     print("".join(plt))
            if self.verbose:
                index_map = {t: i for i, t in enumerate(self.traj_names)}  # O(N)
                plt = ["o"] * len(self.traj_names)
                for traj in self.used_traj_names:
                    if traj in index_map:
                        plt[index_map[traj]] = "x"
                print("".join(plt))

            print(f"Load Plan: sampled \033[0;36m{len(self.used_traj_names)}/{len(self.traj_names)}\033[0m trajs this turn, turn=\033[0;36m{self.n_full_data_used}\033[0m")
        else:
            self.used_traj_names = []
            traj_names = self.traj_names
            if self.verbose: print("x" * len(self.traj_names))
        traj_pool = self._load(traj_names, use_tqdm=False)
        return traj_pool
    
    def _load(self, traj_names, use_tqdm=True):
        from .traj import trajectory
        traj_pool = []

        if use_tqdm:
            pbar = tqdm.tqdm(total=len(traj_names), desc="Loading Trajectories")
        
        for i, path_to_traj in enumerate(traj_names):
            if use_tqdm: pbar.update(1)
            traj_name = os.path.basename(path_to_traj)
            # traj_dir = os.path.dirname(path_to_traj)
            if _is_traj(traj_name):
                if self.verbose: print(path_to_traj)
                if path_to_traj in self._traj_cache:
                    traj = self._traj_cache[path_to_traj]
                    # print_indigo("cache hit")
                else:
                    # print("cache miss")
                    traj = safe_load(
                        obj=trajectory(traj_limit='auto loaded', env_id='auto loaded'),
                        path=path_to_traj
                    )
                    if self.use_cache and traj is not None:
                        self._traj_cache[path_to_traj] = traj
                if traj is not None:
                    traj_pool.append(traj)  

                # print亮黄(f"traj loaded from file: {traj_dir}/{traj_name}")
            else:
                print亮红(lprint_(self, f"ERROR: traj_name invalid: {path_to_traj}"))
        
        # print(f"safe loaded {len(traj_pool)} trajs")
        return traj_pool

##############################################################################################################

def get_container_from_traj_pool(traj_pool, req_dict_rename, req_dict=None):
    container = {}
    if req_dict is None: req_dict = ['obs', 'action', 'action_index', 'actionLogProb', 'return', 'reward', 'value']
    assert len(req_dict_rename) == len(req_dict)

    # replace 'obs' to 'obs > xxxx'
    for key_index, key in enumerate(req_dict):
        key_name =  req_dict[key_index]
        key_rename = req_dict_rename[key_index]
        if not hasattr(traj_pool[0], key_name):
            real_key_list = [real_key for real_key in traj_pool[0].__dict__ if (key_name+'>' in real_key)]
            assert len(real_key_list) > 0, ('check variable provided!', key, key_index)
            for real_key in real_key_list:
                mainkey, subkey = real_key.split('>')
                req_dict.append(real_key)
                req_dict_rename.append(key_rename+'>'+subkey)
    big_batch_size = -1  # vector should have same length, check it!
    
    # load traj into a 'container'
    for key_index, key in enumerate(req_dict):
        key_name =  req_dict[key_index]
        key_rename = req_dict_rename[key_index]
        if not hasattr(traj_pool[0], key_name): continue
        set_item = np.concatenate([getattr(traj, key_name) for traj in traj_pool], axis=0)
        if not (big_batch_size==set_item.shape[0] or (big_batch_size<0)):
            print('error')
        assert big_batch_size==set_item.shape[0] or (big_batch_size<0), (key,key_index)
        big_batch_size = set_item.shape[0]
        container[key_rename] = set_item    # 指针赋值

    return container



def get_seq_container_from_traj_pool(traj_pool, req_dict_rename, req_dict):
    container = {}
    assert len(req_dict_rename) == len(req_dict)

    # replace 'obs' to 'obs > xxxx'
    for key_index, key in enumerate(req_dict):
        key_name =  req_dict[key_index]
        key_rename = req_dict_rename[key_index]
        if not hasattr(traj_pool[0], key_name):
            real_key_list = [real_key for real_key in traj_pool[0].__dict__ if (key_name+'>' in real_key)]
            assert len(real_key_list) > 0, ('check variable provided!', key, key_index)
            for real_key in real_key_list:
                mainkey, subkey = real_key.split('>')
                req_dict.append(real_key)
                req_dict_rename.append(key_rename+'>'+subkey)
    big_batch_size = -1  # vector should have same length, check it!
    
    # load traj into a 'container'
    for key_index, key in enumerate(req_dict):
        key_name =  req_dict[key_index]
        key_rename = req_dict_rename[key_index]
        if not hasattr(traj_pool[0], key_name): continue
        set_item = np.array([getattr(traj, key_name) for traj in traj_pool], axis=0)
        if not (big_batch_size==set_item.shape[0] or (big_batch_size<0)):
            print('error')
        assert big_batch_size==set_item.shape[0] or (big_batch_size<0), (key,key_index)
        big_batch_size = set_item.shape[0]
        container[key_rename] = set_item    # 指针赋值

    return container
