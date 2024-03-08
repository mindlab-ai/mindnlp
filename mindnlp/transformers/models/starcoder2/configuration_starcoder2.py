# coding=utf-8
# Copyright 2024 BigCode and the HuggingFace Inc. team. All rights reserved.
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
""" Starcoder2 model configuration"""

from mindnlp.utils import logging
from ...configuration_utils import PretrainedConfig


logger = logging.get_logger(__name__)

STARCODER2_PRETRAINED_CONFIG_ARCHIVE_MAP = {}


class Starcoder2Config(PretrainedConfig):
    r"""
    This is the configuration class to store the configuration of a [`Starcoder2Model`]. It is used to instantiate a
    Starcoder2 model according to the specified arguments, defining the model architecture. Instantiating a configuration
    with the defaults will yield a similar configuration to that of the [bigcode/starcoder2-7b_16k](https://huggingface.co/bigcode/starcoder2-7b_16k) model.


    Configuration objects inherit from [`PretrainedConfig`] and can be used to control the model outputs. Read the
    documentation from [`PretrainedConfig`] for more information.


    Args:
        vocab_size (`int`, *optional*, defaults to 49152):
            Vocabulary size of the Starcoder2 model. Defines the number of different tokens that can be represented by the
            `inputs_ids` passed when calling [`Starcoder2Model`]
        hidden_size (`int`, *optional*, defaults to 3072):
            Dimension of the hidden representations.
        intermediate_size (`int`, *optional*, defaults to 12288):
            Dimension of the MLP representations.
        num_hidden_layers (`int`, *optional*, defaults to 30):
            Number of hidden layers in the Transformer encoder.
        num_attention_heads (`int`, *optional*, defaults to 24):
            Number of attention heads for each attention layer in the Transformer encoder.
        num_key_value_heads (`int`, *optional*, defaults to 2):
            This is the number of key_value heads that should be used to implement Grouped Query Attention. If
            `num_key_value_heads=num_attention_heads`, the model will use Multi Head Attention (MHA), if
            `num_key_value_heads=1 the model will use Multi Query Attention (MQA) otherwise GQA is used. When
            converting a multi-head checkpoint to a GQA checkpoint, each group key and value head should be constructed
            by meanpooling all the original heads within that group. For more details checkout [this
            paper](https://arxiv.org/pdf/2305.13245.pdf). If it is not specified, will default to `8`.
        hidden_act (`str` or `function`, *optional*, defaults to `"gelu_pytorch_tanh"`):
            The non-linear activation function (function or string) in the decoder.
        max_position_embeddings (`int`, *optional*, defaults to 4096):
            The maximum sequence length that this model might ever be used with. Starcoder2's sliding window attention
            allows sequence of up to 4096*32 tokens.
        initializer_range (`float`, *optional*, defaults to 0.02):
            The standard deviation of the truncated_normal_initializer for initializing all weight matrices.
        norm_epsilon (`float`, *optional*, defaults to 1e-05):
            Epsilon value for the layer norm
        use_cache (`bool`, *optional*, defaults to `True`):
            Whether or not the model should return the last key/values attentions (not used by all models). Only
            relevant if `config.is_decoder=True`.
        bos_token_id (`int`, *optional*, defaults to 50256):
            The id of the "beginning-of-sequence" token.
        eos_token_id (`int`, *optional*, defaults to 50256):
            The id of the "end-of-sequence" token.
        rope_theta (`float`, *optional*, defaults to 10000.0):
            The base period of the RoPE embeddings.
        sliding_window (`int`, *optional*):
            Sliding window attention window size. If not specified, will default to `None` (no sliding window).
        attention_dropout (`float`, *optional*, defaults to 0.0):
            The dropout ratio for the attention probabilities.
        residual_dropout (`float`, *optional*, defaults to 0.0):
            Residual connection dropout value.
        embedding_dropout (`float`, *optional*, defaults to 0.0):
            Embedding dropout.
        use_bias (`bool`, *optional*, defaults to `True`):
            Whether to use bias term on linear layers of the model.


    ```python
    >>> from transformers import Starcoder2Model, Starcoder2Config

    >>> # Initializing a Starcoder2 7B style configuration
    >>> configuration = Starcoder2Config()

    >>> # Initializing a model from the Starcoder2 7B style configuration
    >>> model = Starcoder2Model(configuration)

    >>> # Accessing the model configuration
    >>> configuration = model.config
    ```"""

    model_type = "starcoder2"
    keys_to_ignore_at_inference = ["past_key_values"]

    def __init__(
        self,
        vocab_size=49152,
        hidden_size=3072,
        intermediate_size=12288,
        num_hidden_layers=30,
        num_attention_heads=24,
        num_key_value_heads=2,
        hidden_act="gelu_pytorch_tanh",
        max_position_embeddings=4096,
        initializer_range=0.018042,
        norm_epsilon=1e-5,
        use_cache=True,
        bos_token_id=50256,
        eos_token_id=50256,
        rope_theta=10000.0,
        sliding_window=None,
        attention_dropout=0.0,
        residual_dropout=0.0,
        embedding_dropout=0.0,
        use_bias=True,
        **kwargs,
    ):
        self.vocab_size = vocab_size
        self.max_position_embeddings = max_position_embeddings
        self.hidden_size = hidden_size
        self.intermediate_size = intermediate_size
        self.num_hidden_layers = num_hidden_layers
        self.num_attention_heads = num_attention_heads
        self.sliding_window = sliding_window
        self.use_bias = use_bias
        self.num_key_value_heads = num_key_value_heads
        self.hidden_act = hidden_act
        self.initializer_range = initializer_range
        self.norm_epsilon = norm_epsilon
        self.use_cache = use_cache
        self.rope_theta = rope_theta
        self.attention_dropout = attention_dropout
        self.residual_dropout = residual_dropout
        self.embedding_dropout = embedding_dropout

        super().__init__(
            bos_token_id=bos_token_id,
            eos_token_id=eos_token_id,
            **kwargs,
        )

__all__ = ['Starcoder2Config']
