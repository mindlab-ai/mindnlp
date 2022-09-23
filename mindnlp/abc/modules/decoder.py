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
"""Decoder basic model"""

import mindspore.nn as nn


class DecoderBase(nn.Cell):
    r"""
    Basic class for dedcoders

    Inputs:
        - **prev_output_tokens** (Tensor) - output tokens for teacher forcing with shape [batch, tgt_len].
        - **encoder_out** (Tensor) - output of encoder.

    Returns:
        - **result** (Tensor) - The result vector of decoder.
    """

    def __init__(self):
        super().__init__()
        self.softmax = nn.Softmax()
        self.log_softmax = nn.LogSoftmax()

    def construct(self, prev_output_tokens, encoder_out=None):
        result = self.extract_features(prev_output_tokens, encoder_out)
        result = self.output_layer(result)
        return result

    def extract_features(self, prev_output_tokens, encoder_out=None):
        """Extract features of encoder output"""
        raise NotImplementedError

    def output_layer(self, features):
        """Project features to the default output size"""
        raise NotImplementedError

    def get_normalized_probs(self, net_output, log_probs):
        """Get normalized probabilities from net's output"""
        logits = net_output[0]
        if log_probs:
            result = self.log_softmax(logits)
        else:
            result = self.softmax(logits)
        return result
