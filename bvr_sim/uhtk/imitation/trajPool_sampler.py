import math
import numpy as np
from torch.utils.data.sampler import BatchSampler, SubsetRandomSampler
from bvr_sim.uhtk.UTIL.colorful import *
# from config import GlobalConfig as cfg

class TrajPoolSampler():
    def __init__(
        self,
        n_div,
        traj_pool,
        flag, 
        req_dict,
        req_dict_rename,
        prevent_batchsize_oom=False,
        mcv=None,
        use_sequence_sampling=True
    ):
        self.n_pieces_batch_division = n_div
        self.prevent_batchsize_oom = prevent_batchsize_oom
        self.mcv = mcv
        self.use_sequence_sampling = use_sequence_sampling
        if self.prevent_batchsize_oom:
            assert self.n_pieces_batch_division==1, ('?')

        self.num_batch = None
        self.container = {}
        self.warned = False
        assert flag=='train'


        # replace 'obs' to 'obs > xxxx'
        for key_index, key in enumerate(req_dict):
            key_name =  req_dict[key_index]
            key_rename = req_dict_rename[key_index]
            if not hasattr(traj_pool[0], key_name):
                real_key_list = [real_key for real_key in traj_pool[0].__dict__ if (key_name+'>' in real_key)]
                assert len(real_key_list) > 0, ('check variable provided!', key,key_index)
                for real_key in real_key_list:
                    mainkey, subkey = real_key.split('>')
                    req_dict.append(real_key)
                    req_dict_rename.append(key_rename+'>'+subkey)

        if self.use_sequence_sampling:
            # NEW METHOD: Pad trajectories to maintain sequence structure
            self._init_sequence_sampling(traj_pool, req_dict, req_dict_rename)
        else:
            # OLD METHOD: Concatenate all trajectories (loses sequence boundaries)
            self._init_flat_sampling(traj_pool, req_dict, req_dict_rename)

    def _init_flat_sampling(self, traj_pool, req_dict, req_dict_rename):
        """Original concatenation-based sampling (loses trajectory boundaries)"""
        self.big_batch_size = -1  # vector should have same length, check it!

        # load traj into a 'container'
        for key_index, key in enumerate(req_dict):
            key_name =  req_dict[key_index]
            key_rename = req_dict_rename[key_index]
            if not hasattr(traj_pool[0], key_name): continue
            set_item = np.concatenate([getattr(traj, key_name) for traj in traj_pool], axis=0)
            if not (self.big_batch_size==set_item.shape[0] or (self.big_batch_size<0)):
                print('error')
            assert self.big_batch_size==set_item.shape[0] or (self.big_batch_size<0), (key,key_index)
            self.big_batch_size = set_item.shape[0]
            self.container[key_rename] = set_item    # 指针赋值

        # size of minibatch for each agent
        self.mini_batch_size = math.ceil(self.big_batch_size / self.n_pieces_batch_division)

    def _init_sequence_sampling(self, traj_pool, req_dict, req_dict_rename):
        """New padding-based sampling (preserves trajectory boundaries for GRU)"""
        for traj in traj_pool:
            if not hasattr(traj, 'traj_length'):
                # print黄(f'[TrajPoolSampler] traj_length not provided! Most likely you are using a old version of trajectory.py.')
                traj_length = None
                # if hasattr(traj, 'obs'):
                #     # print("try set traj_length to obs.shape[0]")
                #     traj_length = traj.traj_length = traj.obs.shape[0]
                for key_name in req_dict:
                    if hasattr(traj, key_name):
                        # print(f"try set traj_length to {key_name}.shape[0]")
                        traj.traj_length = getattr(traj, key_name).shape[0]
                        if traj_length is not None:
                            assert traj.traj_length == traj_length, (traj.traj_length, traj_length)
                    else:
                        raise ValueError(f'req_dict {key_name} not provided!')
            if not hasattr(traj, 'traj_length'):
                raise ValueError('traj_length not provided! Most likely you are using a old version of trajectory.py.')

        self.n_traj = len(traj_pool)
        self.traj_lengths = np.array([traj.traj_length for traj in traj_pool], dtype=np.int32)
        self.max_traj_length = int(self.traj_lengths.max())

        print(f'[TrajPoolSampler] Using sequence sampling: {self.n_traj} trajs, max_len={self.max_traj_length}')

        # Create mask for valid timesteps: (n_traj, max_len)
        self.traj_mask = np.zeros((self.n_traj, self.max_traj_length), dtype=np.float32)
        for i, length in enumerate(self.traj_lengths):
            self.traj_mask[i, :length] = 1.0

        # Pad trajectories to max_length
        for key_index, key in enumerate(req_dict):
            key_name = req_dict[key_index]
            key_rename = req_dict_rename[key_index]
            if not hasattr(traj_pool[0], key_name): continue

            # Get first trajectory to determine shape
            first_item = getattr(traj_pool[0], key_name)
            item_shape = first_item.shape[1:]  # shape after time dimension

            # Create padded array: (n_traj, max_len, *item_shape)
            padded_shape = (self.n_traj, self.max_traj_length) + item_shape
            padded_array = np.zeros(padded_shape, dtype=first_item.dtype)

            # Fill in actual trajectory data
            for i, traj in enumerate(traj_pool):
                traj_data = getattr(traj, key_name)
                traj_len = traj_data.shape[0]
                padded_array[i, :traj_len] = traj_data

            self.container[key_rename] = padded_array

        # Add mask to container
        self.container['traj_mask'] = self.traj_mask
        self.container['traj_lengths'] = self.traj_lengths

        # For sequence sampling, batch size is number of trajectories
        self.big_batch_size = self.n_traj
        self.mini_batch_size = math.ceil(self.big_batch_size / self.n_pieces_batch_division)

    def __len__(self):
        return self.n_pieces_batch_division

    def determine_max_n_sample(self):
        assert self.prevent_batchsize_oom
        if not hasattr(TrajPoolSampler,'MaxSampleNum'):
            # initialization
            TrajPoolSampler.MaxSampleNum =  [int(self.big_batch_size*(i+1)/50) for i in range(50)]
            max_n_sample = self.big_batch_size
        elif TrajPoolSampler.MaxSampleNum[-1] > 0:
            # meaning that oom never happen, at least not yet
            # only update when the batch size increases
            if self.big_batch_size > TrajPoolSampler.MaxSampleNum[-1]: TrajPoolSampler.MaxSampleNum.append(self.big_batch_size)
            max_n_sample = self.big_batch_size
        else:
            # meaning that oom already happened, choose TrajPoolSampler.MaxSampleNum[-2] to be the limit
            assert TrajPoolSampler.MaxSampleNum[-2] > 0
            max_n_sample = TrajPoolSampler.MaxSampleNum[-2]
        return max_n_sample

    def reset_and_get_iter(self):
        if not self.prevent_batchsize_oom:
            self.sampler = BatchSampler(SubsetRandomSampler(range(self.big_batch_size)), self.mini_batch_size, drop_last=False)
        else:
            max_n_sample = self.determine_max_n_sample()
            n_sample = min(self.big_batch_size, max_n_sample)
            if not hasattr(self,'reminded'):
                self.reminded = True
                drop_percent = (self.big_batch_size-n_sample)/self.big_batch_size*100
                if self.mcv is not None:
                    self.mcv.rec(drop_percent, 'drop percent')
                if drop_percent > 20:
                    print_ = print亮红
                    print_('droping %.1f percent samples..'%(drop_percent))
                    assert False, "GPU OOM!"
                else:
                    print_ = print
                    print_('droping %.1f percent samples..'%(drop_percent))
            self.sampler = BatchSampler(SubsetRandomSampler(range(n_sample)), n_sample, drop_last=False)

        for indices in self.sampler:
            selected = {}
            for key in self.container:
                selected[key] = self.container[key][indices]
            for key in [key for key in selected if '>' in key]:
                # 重新把子母键值组合成二重字典
                mainkey, subkey = key.split('>')
                if not mainkey in selected: selected[mainkey] = {}
                selected[mainkey][subkey] = selected[key]
                del selected[key]
            yield selected


def get_container_from_traj_pool(traj_pool, req_dict=None, req_dict_rename=None, use_sequence_sampling=True):
    """
    Helper function to convert trajectory pool to data container.
    This is used by BC training to prepare data for network training.

    Args:
        traj_pool: List of trajectory objects
        use_sequence_sampling: If True, use sequence mode (preserves trajectory boundaries)
                              If False, use flat mode (concatenates all trajectories)

    Returns:
        dict: Container with obs, action, and optionally traj_mask
    """
    req_dict = req_dict if req_dict is not None else ['avail_act', 'obs', 'action']
    req_dict_rename = req_dict_rename if req_dict_rename is not None else ['avail_act', 'obs', 'action']
    sampler = TrajPoolSampler(
        n_div=1,
        traj_pool=traj_pool,
        flag='train',
        req_dict=req_dict,
        req_dict_rename=req_dict_rename,
        prevent_batchsize_oom=False,
        mcv=None,
        use_sequence_sampling=use_sequence_sampling
    )

    # Get the full batch (since n_div=1, there's only one batch)
    sample_iter = sampler.reset_and_get_iter()
    data = next(sample_iter)

    return data
