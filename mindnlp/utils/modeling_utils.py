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
"""MindNLP Model Utils"""

import mindspore

from typing import Optional, Tuple, Union, Callable
from activations import get_activation, ACT2CLS
from mindspore import nn, ops, Parameter, Tensor, dtype_to_nptype
from .configuration_utils import PretrainedConfig


try:
    from mindspore.nn import Identity
except ImportError:
    # Older MindSpore compatibility
    class Identity(nn.cell):
        r"""A placeholder identity operator that is argument-insensitive."""

        def __init__(self, *args, **kwargs):
            super().__init__()

        def construct(self, hidden_states):
            return hidden_states