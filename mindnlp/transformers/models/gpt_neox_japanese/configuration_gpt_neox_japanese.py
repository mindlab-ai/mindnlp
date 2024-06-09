# coding=utf-8
# Copyright 2022 ABEJA, Inc. and The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""GPTNeoX Japanese model configuration"""

from mindnlp.utils import logging

from ...configuration_utils import PretrainedConfig

logger = logging.get_logger(__name__)


class GPTNeoXJapaneseConfig(PretrainedConfig):
    r"""
    This is the configuration class to store the configuration of a [`GPTNeoXModelJapanese`]. It is used to instantiate
    a GPTNeoX model according to the specified arguments, defining the model architecture. Instantiating a
    configuration with the defaults will yield a similar configuration to that of the GPTNeoXJapanese
    [abeja/gpt-neox-japanese-2.7b](https://huggingface.co/abeja/gpt-neox-japanese-2.7b) architecture.

    Configuration objects inherit from [`PretrainedConfig`] and can be used to control the model outputs. Read the
    documentation from [`PretrainedConfig`] for more information. Default configs is set as 2.7B model

    Args:
        vocab_size (`int`, *optional*, defaults to 32000):
            Vocabulary size of the GPTNeoXJapanese model. Defines the number of different tokens that can be
            represented by the `inputs_ids` passed when calling [`GPTNeoXJapanese`].
        hidden_size (`int`, *optional*, defaults to 2560):
            Dimension of the encoder layers and the pooler layer.
        num_hidden_layers (`int`, *optional*, defaults to 32):
            Number of hidden layers in the Transformer encoder.
        num_attention_heads (`int`, *optional*, defaults to 32):
            Number of attention heads for each attention layer in the Transformer encoder.
        intermediate_multiple_size (`int`, *optional*, defaults to 4):
            Dimension of the "intermediate" layer in the Transformer encoder is calculated by hidden_size *
            intermediate_multiple_size.
        hidden_act (`str` or `function`, *optional*, defaults to `"gelu"`):
            The non-linear activation function (function or string) in the encoder and pooler.
        rotary_pct (`float`, *optional*, defaults to 1.00):
            percentage of hidden dimensions to allocate to rotary embeddings
        rotary_emb_base (`int`, *optional*, defaults to 10000)
            base for computing rotary embeddings frequency
        max_position_embeddings (`int`, *optional*, defaults to 2048):
            The maximum sequence length that this model might ever be used with.
        initializer_range (`float`, *optional*, defaults to 0.02):
            The standard deviation of the truncated_normal_initializer for initializing all weight matrices.
        layer_norm_eps (`float`, *optional*, defaults to 1e-5):
            The epsilon used by the layer normalization layers.
        use_cache (`bool`, *optional*, defaults to `True`):
            Whether or not the model should return the last key/values attentions (not used by all models). Only
            relevant if `config.is_decoder=True`.
        attention_dropout (`float`, *optional*, defaults to 0.1):
            The dropout ratio for the attention.
        hidden_dropout (`float`, *optional*, defaults to 0.0):
            The dropout ratio for the hidden layer.

    Example:
        ```python
        >>> from transformers import GPTNeoXJapaneseConfig, GPTNeoXJapaneseModel

        >>> # Initializing a GPTNeoXJapanese gpt-neox-japanese-2.7b style configuration
        >>> configuration = GPTNeoXJapaneseConfig()

        >>> # Initializing a model (with random weights) from the gpt-neox-japanese-2.7b style configuration
        >>> model = GPTNeoXJapaneseModel(configuration)

        >>> # Accessing the model configuration
        >>> configuration = model.config
        ```
    """

    model_type = "gpt_neox_japanese"

    def __init__(
        self,
        vocab_size=32000,
        hidden_size=2560,
        num_hidden_layers=32,
        num_attention_heads=32,
        intermediate_multiple_size=4,
        hidden_act="gelu",
        rotary_pct=1.00,
        rotary_emb_base=10000,
        max_position_embeddings=2048,
        initializer_range=0.02,
        layer_norm_eps=1e-5,
        use_cache=True,
        bos_token_id=31996,
        eos_token_id=31999,
        attention_dropout=0.1,
        hidden_dropout=0.0,
        **kwargs,
    ):
        super().__init__(bos_token_id=bos_token_id, eos_token_id=eos_token_id, **kwargs)
        self.vocab_size = vocab_size
        self.max_position_embeddings = max_position_embeddings
        self.hidden_size = hidden_size
        self.num_hidden_layers = num_hidden_layers
        self.num_attention_heads = num_attention_heads
        self.intermediate_multiple_size = intermediate_multiple_size
        self.hidden_act = hidden_act
        self.rotary_pct = rotary_pct
        self.rotary_emb_base = rotary_emb_base
        self.initializer_range = initializer_range
        self.layer_norm_eps = layer_norm_eps
        self.use_cache = use_cache
        self.attention_dropout = attention_dropout
        self.hidden_dropout = hidden_dropout


__all__ = ["GPTNeoXJapaneseConfig"]
