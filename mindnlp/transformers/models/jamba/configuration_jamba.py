# coding=utf-8
# Copyright 2024 AI21 Labs Ltd. and the HuggingFace Inc. team. All rights reserved.
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
""" Jamba model configuration"""
import math

from ...configuration_utils import PretrainedConfig
from ....utils import logging


logger = logging.get_logger(__name__)


class JambaConfig(PretrainedConfig):
    r"""
    This is the configuration class to store the configuration of a [`JambaModel`]. It is used to instantiate a
    Jamba model according to the specified arguments, defining the model architecture. Instantiating a configuration
    with the defaults will yield a similar configuration to that of the jamba-small architecture.
    [ai21labs/jamba-small](https://huggingface.co/ai21labs/Jamba-v0.1)
    Configuration objects inherit from [`PretrainedConfig`] and can be used to control the model outputs. Read the
    documentation from [`PretrainedConfig`] for more information.

    Args:
        vocab_size (`int`, *optional*, defaults to 65536):
            Vocabulary size of the Jamba model. Defines the number of different tokens that can be represented by the
            `inputs_ids` passed when calling [`JambaModel`]
        tie_word_embeddings (`bool`, *optional*, defaults to `False`):
            Whether the model's input and output word embeddings should be tied. Note that this is only relevant if the
            model has a output word embedding layer.
        hidden_size (`int`, *optional*, defaults to 4096):
            Dimension of the hidden representations.
        intermediate_size (`int`, *optional*, defaults to 14336):
            Dimension of the MLP representations.
        num_hidden_layers (`int`, *optional*, defaults to 32):
            Number of hidden layers in the Transformer encoder.
        num_attention_heads (`int`, *optional*, defaults to 32):
            Number of attention heads for each attention layer in the Transformer encoder.
        num_key_value_heads (`int`, *optional*, defaults to 8):
            This is the number of key_value heads that should be used to implement Grouped Query Attention. If
            `num_key_value_heads=num_attention_heads`, the model will use Multi Head Attention (MHA), if
            `num_key_value_heads=1`, the model will use Multi Query Attention (MQA) otherwise GQA is used. When
            converting a multi-head checkpoint to a GQA checkpoint, each group key and value head should be forwarded
            by meanpooling all the original heads within that group. For more details checkout [this
            paper](https://arxiv.org/pdf/2305.13245.pdf). If it is not specified, will default to `8`.
        hidden_act (`str` or `function`, *optional*, defaults to `"silu"`):
            The non-linear activation function (function or string) in the decoder.
        initializer_range (`float`, *optional*, defaults to 0.02):
            The standard deviation of the truncated_normal_initializer for initializing all weight matrices.
        rms_norm_eps (`float`, *optional*, defaults to 1e-06):
            The epsilon used by the rms normalization layers.
        use_cache (`bool`, *optional*, defaults to `True`):
            Whether or not the model should return the last key/values attentions (not used by all models). Only
            relevant if `config.is_decoder=True`.
        calc_logits_for_entire_prompt (`bool`, *optional*, defaults to `False`):
            Whether or not to calculate logits for entire prompt during generation. If `False`, only the logits of the
            last prompt token will be calculated, which are the only logits needed for generation. For long sequences,
            the logits for the entire sequence may use a lot of memory so setting `calc_logits_for_entire_prompt=False`
            will reduce memory footprint significantly.
            Note: some generation features may not be available if this is set to `False`.
        output_router_logits (`bool`, *optional*, defaults to `False`):
            Whether or not the router logits should be returned by the model. Enabling this will also
            allow the model to output the auxiliary loss. See [here]() for more details
        router_aux_loss_coef (`float`, *optional*, defaults to 0.001):
            The aux loss factor for the total loss.
        pad_token_id (`int`, *optional*, defaults to 0):
            The id of the padding token.
        bos_token_id (`int`, *optional*, defaults to 1):
            The id of the "beginning-of-sequence" token.
        eos_token_id (`int`, *optional*, defaults to 2):
            The id of the "end-of-sequence" token.
        sliding_window (`int`, *optional*):
            Sliding window attention window size. If not specified, will default to `None`.
        n_ctx (`int`, *optional*, defaults to 262144):
            This value doesn't have any real effect. The maximum sequence length that this model is intended to be
            used with. It can be used with longer sequences, but performance may degrade.
        attention_dropout (`float`, *optional*, defaults to 0.0):
            The dropout ratio for the attention probabilities.
        num_experts_per_tok (`int`, *optional*, defaults to 2):
            The number of experts to root per-token, can be also interpreted as the `top-p` routing
            parameter
        num_experts (`int`, *optional*, defaults to 16):
            Number of experts per Sparse MLP layer.
        expert_layer_period (`int`, *optional*, defaults to 2):
            Once in this many layers, we will have an expert layer
        expert_layer_offset (`int`, *optional*, defaults to 1):
            The first layer index that contains an expert mlp layer
        attn_layer_period (`int`, *optional*, defaults to 8):
            Once in this many layers, we will have a vanilla attention layer
        attn_layer_offset (`int`, *optional*, defaults to 4):
            The first layer index that contains a vanilla attention mlp layer
        use_mamba_kernels (`bool`, *optional*, defaults to `True`):
            Flag indicating whether or not to use the fast mamba kernels. These are available only if `mamba-ssm` and
            `causal-conv1d` are installed, and the mamba modules are running on a CUDA device. Raises ValueError if
            `True` and kernels are not available
        mamba_d_state (`int`, *optional*, defaults to 16):
            The dimension the mamba state space latents
        mamba_d_conv (`int`, *optional*, defaults to 4):
            The size of the mamba convolution kernel
        mamba_expand (`int`, *optional*, defaults to 2):
            Expanding factor (relative to hidden_size) used to determine the mamba intermediate size
        mamba_dt_rank (`Union[int,str]`, *optional*, defaults to `"auto"`):
            Rank of the the mamba discretization projection matrix.
            `"auto"` means that it will default to `math.ceil(self.hidden_size / 16)`
        mamba_conv_bias (`bool`, *optional*, defaults to `True`):
            Flag indicating whether or not to use bias in the convolution layer of the mamba mixer block.
        mamba_proj_bias (`bool`, *optional*, defaults to `False`):
            Flag indicating whether or not to use bias in the input and output projections
            (["in_proj", "out_proj"]) of the mamba mixer block
        mamba_inner_layernorms (`bool`, *optional*, defaults to `True`):
            Flag indicating whether or not to apply layernorms to internal mamba activations
    """
    model_type = "jamba"
    keys_to_ignore_at_inference = ["past_key_values"]

    def __init__(
            self,
            vocab_size=65536,
            tie_word_embeddings=False,
            hidden_size=4096,
            intermediate_size=14336,
            num_hidden_layers=32,
            num_attention_heads=32,
            num_key_value_heads=8,
            hidden_act="silu",
            initializer_range=0.02,
            rms_norm_eps=1e-6,
            use_cache=True,
            calc_logits_for_entire_prompt=False,
            output_router_logits=False,
            router_aux_loss_coef=0.001,
            pad_token_id=0,
            bos_token_id=1,
            eos_token_id=2,
            sliding_window=None,
            n_ctx=262144,
            attention_dropout=0.0,
            num_experts_per_tok=2,
            num_experts=16,
            expert_layer_period=2,
            expert_layer_offset=1,
            attn_layer_period=8,
            attn_layer_offset=4,
            use_mamba_kernels=True,
            mamba_d_state=16,
            mamba_d_conv=4,
            mamba_expand=2,
            mamba_dt_rank="auto",
            mamba_conv_bias=True,
            mamba_proj_bias=False,
            mamba_inner_layernorms=True,
            **kwargs,
    ):
        """
        Initializes a new instance of the JambaConfig class.
        
        Args:
            self: The object instance.
            vocab_size (int, optional): The size of the vocabulary. Default is 65536.
            tie_word_embeddings (bool, optional): Whether to tie the word embeddings. Default is False.
            hidden_size (int, optional): The size of the hidden layers. Default is 4096.
            intermediate_size (int, optional): The size of the intermediate layers. Default is 14336.
            num_hidden_layers (int, optional): The number of hidden layers. Default is 32.
            num_attention_heads (int, optional): The number of attention heads. Default is 32.
            num_key_value_heads (int, optional): The number of key-value heads. Default is 8.
            hidden_act (str, optional): The activation function for the hidden layers. Default is 'silu'.
            initializer_range (float, optional): The range for weight initialization. Default is 0.02.
            rms_norm_eps (float, optional): The epsilon value for RMS normalization. Default is 1e-06.
            use_cache (bool, optional): Whether to use cache for attention layers. Default is True.
            calc_logits_for_entire_prompt (bool, optional): Whether to calculate logits for the entire prompt.
                Default is False.
            output_router_logits (bool, optional): Whether to output router logits. Default is False.
            router_aux_loss_coef (float, optional): The coefficient for the router auxiliary loss. Default is 0.001.
            pad_token_id (int, optional): The token ID for padding. Default is 0.
            bos_token_id (int, optional): The token ID for the beginning of sentence. Default is 1.
            eos_token_id (int, optional): The token ID for the end of sentence. Default is 2.
            sliding_window (None or int, optional): The size of the sliding window. Default is None.
            n_ctx (int, optional): The size of the context window. Default is 262144.
            attention_dropout (float, optional): The dropout rate for attention layers. Default is 0.0.
            num_experts_per_tok (int, optional): The number of experts per token. Default is 2.
            num_experts (int, optional): The total number of experts. Default is 16.
            expert_layer_period (int, optional): The period for expert layers. Default is 2.
            expert_layer_offset (int, optional): The offset for expert layers. Default is 1.
            attn_layer_period (int, optional): The period for attention layers. Default is 8.
            attn_layer_offset (int, optional): The offset for attention layers. Default is 4.
            use_mamba_kernels (bool, optional): Whether to use Mamba kernels. Default is True.
            mamba_d_state (int, optional): The state dimension for Mamba. Default is 16.
            mamba_d_conv (int, optional): The convolutional dimension for Mamba. Default is 4.
            mamba_expand (int, optional): The expansion factor for Mamba. Default is 2.
            mamba_dt_rank (int or 'auto', optional): The rank for Mamba's data tensors. Default is 'auto'.
            mamba_conv_bias (bool, optional): Whether to include biases in Mamba's convolution layers. Default is True.
            mamba_proj_bias (bool, optional): Whether to include biases in Mamba's projection layers. Default is False.
            mamba_inner_layernorms (bool, optional): Whether to use inner layer normalization in Mamba. Default is True.
        
        Returns:
            None
        
        Raises:
            None
        """
        self.vocab_size = vocab_size
        self.tie_word_embeddings = tie_word_embeddings
        self.hidden_size = hidden_size
        self.intermediate_size = intermediate_size
        self.num_hidden_layers = num_hidden_layers
        self.num_attention_heads = num_attention_heads
        self.sliding_window = sliding_window
        self.n_ctx = n_ctx
        self.attention_dropout = attention_dropout

        # for backward compatibility
        if num_key_value_heads is None:
            num_key_value_heads = num_attention_heads

        self.num_key_value_heads = num_key_value_heads
        self.hidden_act = hidden_act
        self.initializer_range = initializer_range
        self.rms_norm_eps = rms_norm_eps

        self.use_cache = use_cache
        self.calc_logits_for_entire_prompt = calc_logits_for_entire_prompt
        self.output_router_logits = output_router_logits
        self.router_aux_loss_coef = router_aux_loss_coef

        self.num_experts_per_tok = num_experts_per_tok
        self.num_experts = num_experts
        self.expert_layer_period = expert_layer_period
        self.expert_layer_offset = expert_layer_offset
        self.attn_layer_period = attn_layer_period
        self.attn_layer_offset = attn_layer_offset

        self.use_mamba_kernels = use_mamba_kernels
        self.mamba_d_state = mamba_d_state
        self.mamba_d_conv = mamba_d_conv
        self.mamba_expand = mamba_expand
        self.mamba_dt_rank = math.ceil(self.hidden_size / 16) if mamba_dt_rank == "auto" else mamba_dt_rank
        self.mamba_conv_bias = mamba_conv_bias
        self.mamba_proj_bias = mamba_proj_bias
        self.mamba_inner_layernorms = mamba_inner_layernorms

        super().__init__(
            pad_token_id=pad_token_id,
            bos_token_id=bos_token_id,
            eos_token_id=eos_token_id,
            tie_word_embeddings=tie_word_embeddings,
            **kwargs,
        )

__all__ = ['JambaConfig']
