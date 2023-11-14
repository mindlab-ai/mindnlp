# Copyright 2023 Huawei Technologies Co., Ltd
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
"""Test CPM Ant"""
import unittest
import numpy as np

from mindspore import Tensor
import mindnlp
from mindnlp.transformers import CpmAntModel, CpmAntForCausalLM, CpmAntConfig
from .....common import MindNLPTestCase


class TestModelingCpmAnt(MindNLPTestCase):
    r"""
    Test Cpm Ant
    """

    def setUp(self):
        """
        Set up.
        """
        super().setUp()
        self.config = CpmAntConfig(
            vocab_size=1000, hidden_size=128, num_attention_heads=8, num_hidden_layers=2
        )

    def test_cpm_ant_model(self):
        r"""
        Test Cpm Ant Model
        """
        model = CpmAntModel(self.config)

        input_ids = Tensor(np.random.randint(0, self.config.vocab_size, (2, 512)))

        outputs = model(input_ids)

        assert outputs.last_hidden_state.shape == (2, 512, self.config.hidden_size)
        assert outputs.past_key_values[0][0].shape == (
            2,
            self.config.num_attention_heads,
            512 + self.config.prompt_length,
            self.config.hidden_size,
        )
        assert outputs.past_key_values[1][0].shape == (
            2,
            self.config.num_attention_heads,
            512 + self.config.prompt_length,
            self.config.hidden_size,
        )

    def test_cpm_ant_for_causal_lm(self):
        r"""
        Test GPT2 LMHead Model
        """
        model = CpmAntForCausalLM(self.config)

        input_ids = Tensor(np.random.randint(0, self.config.vocab_size, (2, 512)))

        outputs = model(input_ids)
        assert outputs.logits.shape == (
            2,
            512,
            self.config.vocab_size
            + self.config.prompt_types * self.config.prompt_length,
        )
