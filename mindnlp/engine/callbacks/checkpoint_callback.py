# Copyright 2022 Huawei Technologies Co., Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ============================================================================
"""
Callback for load and save checkpoint.
"""
import os

import mindspore

from ...abc import Callback

class CheckpointCallback(Callback):
    r"""
    Save checkpoint of the model. save the current Trainer state at the end of each epoch, which can be used to
    resume previous operations.
    Continue training a sample code using the most recent epoch

    Args:
        save_path (str): The path to save the state. A specific path needs to be specified,
                         such as 'checkpoints/chtp.pt'. If it is checked that the file exists,
                         it will automatically start running from this Checkpoint
                         when the Trainer starts training. Default: None.
        epochs (int): Save a checkpoint file every n epochs.


    """
    def __init__(self, save_path=None, epochs=None):
        if save_path is not None:
            os.makedirs(save_path, exist_ok=True)
        else:
            os.makedirs(os.path.expanduser('~'), exist_ok=True)
        self.save_path = save_path
        self.epochs = epochs

        # to do

        # self.steps = steps
        # if (self.epochs is not None) & (self.steps is not None):
        #     raise ValueError("The parameter epochs and steps cannot be assigned at the same time,\
        #                         you can only keep one of them.")
        # elif (self.epochs is None) & (self.steps is None):
        #     raise ValueError("The parameter epochs and steps both are None,\
        #                         you must assign one of them.")

    def train_begin(self, run_context):
        print("\nThe train will start from the checkpoint saved in {}.\n".format(self.save_path))

    def train_epoch_end(self, run_context):
        r"""
        Save checkpoint every n epochs at the end of the epoch.
        """
        if self.epochs is None:
            return
        if (run_context.cur_epoch_nums % self.epochs != 0) & (run_context.cur_epoch_nums != run_context.epochs):
            return
        model = run_context.network
        ckpt_name = type(model).__name__ + '_epoch_' + str(run_context.cur_epoch_nums-1) + '.ckpt'
        mindspore.save_checkpoint(model, self.save_path + '/' + ckpt_name)
        print("Checkpoint: {} has been saved in epoch:{}.".format(ckpt_name, run_context.cur_epoch_nums-1))
