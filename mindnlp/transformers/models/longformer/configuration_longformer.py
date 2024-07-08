# coding=utf-8
# Copyright 2020 The Allen Institute for AI team and The HuggingFace Inc. team.
# Copyright 2023 Huawei Technologies Co., Ltd
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
""" Longformer configuration"""
from typing import List, Union

from mindnlp.utils import logging
from ...configuration_utils import PretrainedConfig


logger = logging.get_logger(__name__)

LONGFORMER_PRETRAINED_CONFIG_ARCHIVE_MAP = {
    "allenai/longformer-base-4096": "https://hf-mirror.com/allenai/longformer-base-4096/resolve/main/config.json",
    "allenai/longformer-large-4096": "https://hf-mirror.com/allenai/longformer-large-4096/resolve/main/config.json",
    "allenai/longformer-large-4096-finetuned-triviaqa": (
        "https://hf-mirror.com/allenai/longformer-large-4096-finetuned-triviaqa/resolve/main/config.json"
    ),
    "allenai/longformer-base-4096-extra.pos.embd.only": (
        "https://hf-mirror.com/allenai/longformer-base-4096-extra.pos.embd.only/resolve/main/config.json"
    ),
    "allenai/longformer-large-4096-extra.pos.embd.only": (
        "https://hf-mirror.com/allenai/longformer-large-4096-extra.pos.embd.only/resolve/main/config.json"
    ),
}


class LongformerConfig(PretrainedConfig):
    r"""
    This is the configuration class to store the configuration of a [`LongformerModel`] or a [`TFLongformerModel`]. It
    is used to instantiate a Longformer model according to the specified arguments, defining the model architecture.

    This is the configuration class to store the configuration of a [`LongformerModel`]. It is used to instantiate an
    Longformer model according to the specified arguments, defining the model architecture. Instantiating a
    configuration with the defaults will yield a similar configuration to that of the LongFormer
    [allenai/longformer-base-4096](https://hf-mirror.com/allenai/longformer-base-4096) architecture with a sequence
    length 4,096.

    Configuration objects inherit from [`PretrainedConfig`] and can be used to control the model outputs. Read the
    documentation from [`PretrainedConfig`] for more information.

    Args:
        vocab_size (`int`, *optional*, defaults to 30522):
            Vocabulary size of the Longformer model. Defines the number of different tokens that can be represented by
            the `inputs_ids` passed when calling [`LongformerModel`] or [`TFLongformerModel`].
        hidden_size (`int`, *optional*, defaults to 768):
            Dimensionality of the encoder layers and the pooler layer.
        num_hidden_layers (`int`, *optional*, defaults to 12):
            Number of hidden layers in the Transformer encoder.
        num_attention_heads (`int`, *optional*, defaults to 12):
            Number of attention heads for each attention layer in the Transformer encoder.
        intermediate_size (`int`, *optional*, defaults to 3072):
            Dimensionality of the "intermediate" (often named feed-forward) layer in the Transformer encoder.
        hidden_act (`str` or `Callable`, *optional*, defaults to `"gelu"`):
            The non-linear activation function (function or string) in the encoder and pooler. If string, `"gelu"`,
            `"relu"`, `"silu"` and `"gelu_new"` are supported.
        hidden_dropout_prob (`float`, *optional*, defaults to 0.1):
            The dropout probability for all fully connected layers in the embeddings, encoder, and pooler.
        attention_probs_dropout_prob (`float`, *optional*, defaults to 0.1):
            The dropout ratio for the attention probabilities.
        max_position_embeddings (`int`, *optional*, defaults to 512):
            The maximum sequence length that this model might ever be used with. Typically set this to something large
            just in case (e.g., 512 or 1024 or 2048).
        type_vocab_size (`int`, *optional*, defaults to 2):
            The vocabulary size of the `token_type_ids` passed when calling [`LongformerModel`] or
            [`TFLongformerModel`].
        initializer_range (`float`, *optional*, defaults to 0.02):
            The standard deviation of the truncated_normal_initializer for initializing all weight matrices.
        layer_norm_eps (`float`, *optional*, defaults to 1e-12):
            The epsilon used by the layer normalization layers.
        attention_window (`int` or `List[int]`, *optional*, defaults to 512):
            Size of an attention window around each token. If an `int`, use the same size for all layers. To specify a
            different window size for each layer, use a `List[int]` where `len(attention_window) == num_hidden_layers`.

    Example:
        ```python
        >>> from transformers import LongformerConfig, LongformerModel
        ...
        >>> # Initializing a Longformer configuration
        >>> configuration = LongformerConfig()
        ...
        >>> # Initializing a model from the configuration
        >>> model = LongformerModel(configuration)
        ...
        >>> # Accessing the model configuration
        >>> configuration = model.config
        ```
    """
    model_type = "longformer"

    def __init__(
        self,
        attention_window: Union[List[int], int] = 512,
        sep_token_id: int = 2,
        pad_token_id: int = 1,
        bos_token_id: int = 0,
        eos_token_id: int = 2,
        vocab_size: int = 30522,
        hidden_size: int = 768,
        num_hidden_layers: int = 12,
        num_attention_heads: int = 12,
        intermediate_size: int = 3072,
        hidden_act: str = "gelu",
        hidden_dropout_prob: float = 0.1,
        attention_probs_dropout_prob: float = 0.1,
        max_position_embeddings: int = 512,
        type_vocab_size: int = 2,
        initializer_range: float = 0.02,
        layer_norm_eps: float = 1e-12,
        onnx_export: bool = False,
        **kwargs,
    ):
        """Constructs LongformerConfig."""
        super().__init__(pad_token_id=pad_token_id, **kwargs)

        self.attention_window = attention_window
        self.sep_token_id = sep_token_id
        self.bos_token_id = bos_token_id
        self.eos_token_id = eos_token_id
        self.vocab_size = vocab_size
        self.hidden_size = hidden_size
        self.num_hidden_layers = num_hidden_layers
        self.num_attention_heads = num_attention_heads
        self.hidden_act = hidden_act
        self.intermediate_size = intermediate_size
        self.hidden_dropout_prob = hidden_dropout_prob
        self.attention_probs_dropout_prob = attention_probs_dropout_prob
        self.max_position_embeddings = max_position_embeddings
        self.type_vocab_size = type_vocab_size
        self.initializer_range = initializer_range
        self.layer_norm_eps = layer_norm_eps
        self.onnx_export = onnx_export

__all__ = ['LongformerConfig']
