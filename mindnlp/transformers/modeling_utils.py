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
# pylint: disable=E1128
# pylint: disable=C0103
# pylint: disable=C0412
# pylint: disable=W0642
# pylint: disable=W0212
# pylint: disable=W0201
# pylint: disable=C0413
# pylint: disable=R0916
# pylint: disable=W1203
# pylint: disable=W0613
"""
Abstract class for Pretrained models.
"""
import os
import gc
import re
import json
from typing import Union, Optional, Tuple, OrderedDict, Callable, Dict, List
from tqdm.autonotebook import tqdm
import numpy as np

import mindspore
from mindspore import nn, ops, Tensor, Parameter
from mindspore.train.serialization import save_checkpoint

from mindnlp.configs import HF_MODEL_URL_BASE, DEFAULT_ROOT
from mindnlp.utils.download import cached_path, get_checkpoint_shard_files
from mindnlp.utils import less_min_pynative_first, convert_file_size_to_int, logging
from mindnlp._legacy.functional import arange

if less_min_pynative_first:
    from mindspore import load_checkpoint
else:
    from mindnlp._legacy.utils import load_checkpoint

from .generation import GenerationMixin
from .configuration_utils import PretrainedConfig
from .generation.configuration_utils import GenerationConfig

logger = logging.get_logger(__name__)

WEIGHTS_NAME = "mindspore.ckpt"
WEIGHTS_INDEX_NAME = "mindspore.ckpt.index.json"
HF_WEIGHTS_INDEX_NAME = "pytorch_model.bin.index.json"
_init_weights = True

class CellUtilMixin:
    """
    A few utilities to be used as a mixin.
    """

    @property
    def dtype(self) -> mindspore.dtype:
        """
        `mindspore.dtype`: The dtype of the module (assuming that all the module parameters have the same dtype).
        """
        return mindspore.float32

    @staticmethod
    def create_extended_attention_mask_for_decoder(input_shape, attention_mask):
        """create_extended_attention_mask_for_decoder"""
        batch_size, seq_length = input_shape
        seq_ids = arange(seq_length)
        causal_mask = ops.tile((seq_ids[None, None, :]).astype(mindspore.int32),\
         (batch_size, seq_length, 1)) <= seq_ids[None, :, None] # mindspore 2.0
        # causal_mask = Tensor(np.tile(seq_ids[None, None, :].asnumpy(), (batch_size, seq_length, 1))) \
        #     <= seq_ids[None, :, None]
        # in case past_key_values are used we need to add a prefix ones mask to the causal mask
        causal_mask = causal_mask.astype(attention_mask.dtype)

        if causal_mask.shape[1] < attention_mask.shape[1]:
            prefix_seq_len = attention_mask.shape[1] - causal_mask.shape[1]
            causal_mask = ops.concat(
                [
                    ops.ones((batch_size, seq_length, prefix_seq_len), causal_mask.dtype),
                    causal_mask,
                ],
                axis=-1,
            )

        extended_attention_mask = causal_mask[:, None, :, :] * attention_mask[:, None, None, :]
        return extended_attention_mask

    def invert_attention_mask(self, encoder_attention_mask: Tensor) -> Tensor:
        """
        Invert an attention mask (e.g., switches 0. and 1.).

        Args:
            encoder_attention_mask (`mindspore.Tensor`): An attention mask.

        Returns:
            `mindspore.Tensor`: The inverted attention mask.
        """
        if encoder_attention_mask.ndim == 3:
            encoder_extended_attention_mask = encoder_attention_mask[:, None, :, :]
        if encoder_attention_mask.ndim == 2:
            encoder_extended_attention_mask = encoder_attention_mask[:, None, None, :]
        else:
            encoder_extended_attention_mask = encoder_attention_mask
        # T5 has a mask that can compare sequence ids, we can simulate this here with this transposition
        # Cf. https://github.com/tensorflow/mesh/blob/8d2465e9bc93129b913b5ccc6a59aa97abd96ec6/mesh_tensorflow
        # /transformer/transformer_layers.py#L270
        # encoder_extended_attention_mask = (encoder_extended_attention_mask ==
        # encoder_extended_attention_mask.transpose(-1, -2))
        encoder_extended_attention_mask = encoder_extended_attention_mask.astype(dtype=self.dtype)  # fp16 compatibility
        encoder_extended_attention_mask = (1.0 - encoder_extended_attention_mask) \
            * Tensor(np.finfo(mindspore.dtype_to_nptype(self.dtype)).min)

        return encoder_extended_attention_mask

    def get_extended_attention_mask(
        self, attention_mask: Tensor, input_shape: Tuple[int],dtype = None
    ) -> Tensor:
        """
        Makes broadcastable attention and causal masks so that future and masked tokens are ignored.

        Arguments:
            attention_mask (`torch.Tensor`):
                Mask with ones indicating tokens to attend to, zeros for tokens to ignore.
            input_shape (`Tuple[int]`):
                The shape of the input to the model.

        Returns:
            `torch.Tensor` The extended attention mask, with a the same dtype as `attention_mask.dtype`.
        """
        if dtype is None:
            dtype = self.dtype

        # We can provide a self-attention mask of dimensions [batch_size, from_seq_length, to_seq_length]
        # ourselves in which case we just need to make it broadcastable to all heads.
        if attention_mask.ndim == 3:
            extended_attention_mask = attention_mask[:, None, :, :]
        elif attention_mask.ndim == 2:
            # Provided a padding mask of dimensions [batch_size, seq_length]
            # - if the model is a decoder, apply a causal mask in addition to the padding mask
            # - if the model is an encoder, make the mask broadcastable
            #   to [batch_size, num_heads, seq_length, seq_length]
            if self.config.is_decoder:
                extended_attention_mask = CellUtilMixin.create_extended_attention_mask_for_decoder(
                    input_shape, attention_mask
                )
            else:
                extended_attention_mask = attention_mask[:, None, None, :]
        else:
            raise ValueError(
                f"Wrong shape for input_ids (shape {input_shape}) or attention_mask (shape {attention_mask.shape})"
            )

        # Since attention_mask is 1.0 for positions we want to attend and 0.0 for
        # masked positions, this operation will create a tensor which is 0.0 for
        # positions we want to attend and the dtype's smallest value for masked positions.
        # Since we are adding it to the raw scores before the softmax, this is
        # effectively the same as removing these entirely.
        extended_attention_mask = extended_attention_mask.astype(dtype=dtype)  # fp16 compatibility
        extended_attention_mask = (1.0 - extended_attention_mask) \
            * Tensor(np.finfo(mindspore.dtype_to_nptype(dtype)).min)
        return extended_attention_mask

    def get_head_mask(
        self, head_mask: Optional[Tensor], num_hidden_layers: int, is_attention_chunked: bool = False
    ) -> Tensor:
        """
        Prepare the head mask if needed.

        Args:
            head_mask (`mindspore.Tensor` with shape `[num_heads]` or `[num_hidden_layers x num_heads]`, *optional*):
                The mask indicating if we should keep the heads or not (1.0 for keep, 0.0 for discard).
            num_hidden_layers (`int`):
                The number of hidden layers in the model.
            is_attention_chunked: (`bool`, *optional*, defaults to `False`):
                Whether or not the attentions scores are computed by chunks or not.

        Returns:
            `mindspore.Tensor` with shape `[num_hidden_layers x batch x
            num_heads x seq_length x seq_length]` or list with
            `[None]` for each layer.
        """
        if head_mask is not None:
            head_mask = self._convert_head_mask_to_5d(head_mask, num_hidden_layers)
            if is_attention_chunked is True:
                head_mask = head_mask.expand_dims(-1)
        else:
            head_mask = ()
            for _ in range(num_hidden_layers):
                head_mask += (None,)

        return head_mask

    def _convert_head_mask_to_5d(self, head_mask, num_hidden_layers):
        """-> [num_hidden_layers x batch x num_heads x seq_length x seq_length]"""
        if head_mask.dim() == 1:
            head_mask = head_mask.expand_dims(0).expand_dims(0).expand_dims(-1).expand_dims(-1)
            head_mask = head_mask.broadcast_to(num_hidden_layers, -1, -1, -1, -1)
        elif head_mask.dim() == 2:
            head_mask = head_mask.expand_dims(1).expand_dims(-1)\
                .expand_dims(-1)  # We can specify head_mask for each layer
        assert head_mask.dim() == 5, f"head_mask.dim != 5, instead {head_mask.dim()}"
        head_mask = head_mask.astype(dtype=self.dtype)  # switch to float if need + fp16 compatibility
        return head_mask


class PreTrainedModel(nn.Cell, CellUtilMixin, GenerationMixin):
    """
    Abstract class for Pretrained models
    """
    config_class = None
    pretrained_model_archive_map = {}
    base_model_prefix = ""
    main_input_name = "input_ids"

    # a list of `re` patterns of `state_dict` keys that should be removed from the list of missing
    # keys we find (keys inside the model but not in the checkpoint) and avoid unnecessary warnings.
    _keys_to_ignore_on_load_missing = None
    # a list of `re` patterns of `state_dict` keys that should be removed from the list of
    # unexpected keys we find (keys inside the checkpoint but not the model) and avoid unnecessary
    # warnings.
    _keys_to_ignore_on_load_unexpected = None
    _keys_to_ignore_on_save = None

    _tied_weights_keys = None

    _keep_in_fp32_modules = None

    def __init__(self, config):
        super().__init__(config)
        # Save config in model
        self.config = config
        self.name_or_path = config.name_or_path
        self.generation_config = GenerationConfig.from_model_config(config) if self.can_generate() else None

    def post_init(self):
        """
        A method executed at the end of each Transformer model initialization, to execute code that needs the model's
        modules properly initialized (such as weight initialization).

        """
        self.init_weights()

    def init_weights(self):
        """
        If needed prunes and maybe initializes weights. If using a custom `PreTrainedModel`, you need to implement any
        initialization logic in `_init_weights`.
        """
        # Prune heads if needed
        if self.config.pruned_heads:
            self.prune_heads(self.config.pruned_heads)

        if _init_weights:
            # Initialize weights
            if getattr(self, 'apply', None):
                self.apply(self._initialize_weights)
            else:
                for _, cell in self.name_cells().items():
                    self._initialize_weights(cell)

            # Tie weights should be skipped when not initializing all weights
            # since from_pretrained(...) calls tie weights anyways
            self.tie_weights()

    def prune_heads(self, heads_to_prune: Dict[int, List[int]]):
        """
        Prunes heads of the base model.

        Arguments:
            heads_to_prune (`Dict[int, List[int]]`):
                Dictionary with keys being selected layer indices (`int`) and associated values being the list of heads
                to prune in said layer (list of `int`). For instance {1: [0, 2], 2: [2, 3]} will prune heads 0 and 2 on
                layer 1 and heads 2 and 3 on layer 2.
        """
        # save new sets of pruned heads as union of previously stored pruned heads and newly pruned heads
        for layer, heads in heads_to_prune.items():
            union_heads = set(self.config.pruned_heads.get(layer, [])) | set(heads)
            self.config.pruned_heads[layer] = list(union_heads)  # Unfortunately we have to store it as list for JSON

        self.base_model._prune_heads(heads_to_prune)

    def _initialize_weights(self, module):
        """
        Initialize the weights if they are not already initialized.
        """
        self._init_weights(module)

    @property
    def base_model(self):
        """
        to get base_model
        """
        return getattr(self, self.base_model_prefix, self)

    def get_input_embeddings(self) -> "nn.Cell":
        """
        Returns the model's input embeddings.

        Returns:
            :obj:`nn.Cell`: A mindspore cell mapping vocabulary to hidden states.
        """
        base_model = getattr(self, self.base_model_prefix, self)
        if base_model is not self:
            return base_model.get_input_embeddings()
        raise NotImplementedError

    def set_input_embeddings(self, new_embeddings: nn.Cell):
        """
        Set model's input embeddings.

        Args:
            value (:obj:`nn.Cell`): A mindspore cell mapping vocabulary to hidden states.
        """
        base_model = getattr(self, self.base_model_prefix, self)
        if base_model is not self:
            return base_model.set_input_embeddings(new_embeddings)
        raise NotImplementedError

    def resize_position_embeddings(self, new_num_position_embeddings: int):
        """
        resize the model position embeddings if necessary
        """
        raise NotImplementedError(
            f"`resize_position_embeddings` is not implemented for {self.__class__}`. To implement it, you should "
            f"overwrite this method in the class {self.__class__}"
        )

    def get_output_embeddings(self):
        """ Get model's output embeddings
            Return None if the model doesn't have output embeddings
        """
        return None  # Overwrite for models with output embeddings

    def set_output_embeddings(self, new_embeddings: nn.Cell):
        """
        Set model's output embeddings.

        Args:
            value (:obj:`nn.Cell`): A mindspore cell mapping vocabulary to hidden states.
        """
        base_model = getattr(self, self.base_model_prefix, self)
        if base_model is not self:
            return base_model.set_output_embeddings(new_embeddings)
        raise NotImplementedError

    def get_position_embeddings(self):
        """
        get the model position embeddings if necessary
        """
        raise NotImplementedError(
            f"`get_position_embeddings` is not implemented for {self.__class__}`. To implement it, you should "
            f"overwrite this method in the class {self.__class__}"
        )

    def tie_weights(self):
        """
        Make sure we are sharing the input and output embeddings.
        If you need this feature,
        you need to get it yourself output Add the output you need to add to the embeddings function_ Embedding layer,
        otherwise you cannot
        """
        if getattr(self.config, "tie_word_embeddings", True):
            output_embeddings = self.get_output_embeddings()
            if output_embeddings is not None:
                self._tie_or_clone_weights(
                    output_embeddings, self.get_input_embeddings())

        if getattr(self.config, "is_encoder_decoder", False) and getattr(self.config, "tie_encoder_decoder", False):
            if hasattr(self, self.base_model_prefix):
                self = getattr(self, self.base_model_prefix)
            self._tie_encoder_decoder_weights(
                self.encoder, self.decoder, self.base_model_prefix)

        for cell in self.cells():
            if hasattr(cell, "_tie_weights"):
                cell._tie_weights()

    @staticmethod
    def _tie_encoder_decoder_weights(encoder: nn.Cell, decoder: nn.Cell, base_model_prefix: str):
        """tie encoder decoder weights"""

    def _tie_or_clone_weights(self, output_embeddings, input_embeddings):
        """ Tie or clone module weights depending of weither we are using or not
        """
        output_embeddings.weight = input_embeddings.embedding_table
        output_embeddings._params['weight'] = input_embeddings.embedding_table
        if getattr(output_embeddings, "bias", None) is not None:
            if output_embeddings.weight.shape[0] == output_embeddings.bias.shape[0]:
                pass
            else:
                # instantial a new Parameter since mindspore.Parameter do not support assign_value with different shape
                output_embeddings.bias = Parameter(ops.pad(
                    output_embeddings.bias.data,
                    (0, output_embeddings.weight.shape[0] -
                    output_embeddings.bias.shape[0]),
                    "constant",
                    0,
                ))
        if hasattr(output_embeddings, "out_channels") and hasattr(input_embeddings, "vocab_size"):
            output_embeddings.out_channels = input_embeddings.vocab_size

    def resize_token_embeddings(
        self, new_num_tokens: Optional[int] = None, pad_to_multiple_of: Optional[int] = None
    ) -> nn.Embedding:
        """
        Resizes input token embeddings matrix of the model if `new_num_tokens != config.vocab_size`.

        Takes care of tying weights embeddings afterwards if the model class has a `tie_weights()` method.

        Arguments:
            new_num_tokens (`int`, *optional*):
                The number of new tokens in the embedding matrix. Increasing the size will add newly initialized
                vectors at the end. Reducing the size will remove vectors from the end. If not provided or `None`, just
                returns a pointer to the input tokens `torch.nn.Embedding` module of the model without doing anything.

        Return:
            `torch.nn.Embedding`: Pointer to the input tokens Embeddings Module of the model.
        """
        model_embeds = self._resize_token_embeddings(new_num_tokens, pad_to_multiple_of)
        if new_num_tokens is None and pad_to_multiple_of is None:
            return model_embeds

        # Update base model and current model config
        self.config.vocab_size = model_embeds.embedding_table.shape[0]
        self.vocab_size = model_embeds.embedding_table.shape[0]

        # Tie weights again if needed
        self.tie_weights()

        return model_embeds

    def _resize_token_embeddings(self, new_num_tokens, pad_to_multiple_of=None):
        old_embeddings = self.get_input_embeddings()
        new_embeddings = self._get_resized_embeddings(old_embeddings, new_num_tokens, pad_to_multiple_of)
        self.set_input_embeddings(new_embeddings)

        # Update new_num_tokens with the actual size of new_embeddings
        if pad_to_multiple_of is not None:
            new_num_tokens = new_embeddings.embedding_table.shape[0]
        # if word embeddings are not tied, make sure that lm head is resized as well
        if self.get_output_embeddings() is not None and not self.config.tie_word_embeddings:
            old_lm_head = self.get_output_embeddings()
            new_lm_head = self._get_resized_lm_head(
                old_lm_head, new_num_tokens)
            self.set_output_embeddings(new_lm_head)

        return self.get_input_embeddings()

    def resize_tokenizer_embeddings(self, new_num_tokens):
        """
        Obtain a new embedding layer or use the original one without updating it.
        """
        old_embeddings = self.get_input_embeddings()
        new_embeddings = self._get_resized_embeddings(
            old_embeddings, new_num_tokens)
        self.set_input_embeddings(new_embeddings)
        return self.get_input_embeddings()

    def _get_resized_embeddings(
        self,
        old_embeddings: nn.Embedding,
        new_num_tokens: Optional[int] = None,
        pad_to_multiple_of: Optional[int] = None,
    ) -> nn.Embedding:
        """ Build a resized Embedding Module from a provided token Embedding Module.
            Increasing the size will add newly initialized vectors at the end
            Reducing the size will remove vectors from the end

        Args:
            new_num_tokens: (`optional`) int
                New number of tokens in the embedding matrix.
                Increasing the size will add newly initialized vectors at the end
                Reducing the size will remove vectors from the end
                If not provided or None: return the provided token Embedding Module.
        Return: ``mindspore.nn.Embeddings``
            Pointer to the resized Embedding Module or the old Embedding Module if new_num_tokens is None
        """
        if pad_to_multiple_of is not None:
            if not isinstance(pad_to_multiple_of, int):
                raise ValueError(
                    f"Asking to pad the embedding matrix to a multiple of `{pad_to_multiple_of}`, which is not and integer. Please make sure to pass an integer"
                )
            if new_num_tokens is None:
                new_num_tokens = old_embeddings.weight.shape[0]
            new_num_tokens = ((new_num_tokens + pad_to_multiple_of - 1) // pad_to_multiple_of) * pad_to_multiple_of
        else:
            logger.info(
                "You are resizing the embedding layer without providing a `pad_to_multiple_of` parameter. This means that the new embedding"
                f" dimension will be {new_num_tokens}. This might induce some performance reduction as *Tensor Cores* will not be available."
                " For more details about this, or help on choosing the correct value for resizing, refer to this guide:"
                " https://docs.nvidia.com/deeplearning/performance/dl-performance-matrix-multiplication/index.html#requirements-tc"
            )

        if new_num_tokens is None:
            return old_embeddings

        old_num_tokens, old_embedding_dim = old_embeddings.embedding_table.shape
        if old_num_tokens == new_num_tokens:
            return old_embeddings

        # Build new embeddings
        new_embeddings = nn.Embedding(new_num_tokens, old_embedding_dim)

        # initialize all new embeddings (in particular added tokens)
        self._init_weights(new_embeddings)

        # Copy word embeddings from the previous weights
        num_tokens_to_copy = min(old_num_tokens, new_num_tokens)
        new_embeddings.embedding_table.data[:num_tokens_to_copy, :] = old_embeddings.embedding_table.data[
                                                                      :num_tokens_to_copy, :]

        return new_embeddings

    def _get_resized_lm_head(
        self, old_lm_head: nn.Dense, new_num_tokens: Optional[int] = None, transposed: Optional[bool] = False
    ) -> nn.Dense:
        """
        Build a resized Linear Module from a provided old Linear Module. Increasing the size will add newly initialized
        vectors at the end. Reducing the size will remove vectors from the end

        Args:
            old_lm_head (`nn.Dense`):
                Old lm head liner layer to be resized.
            new_num_tokens (`int`, *optional*):
                New number of tokens in the linear matrix.

                Increasing the size will add newly initialized vectors at the end. Reducing the size will remove
                vectors from the end. If not provided or `None`, just returns a pointer to the input tokens
                `nn.Dense` module of the model without doing anything. transposed (`bool`, *optional*, defaults
                to `False`): Whether `old_lm_head` is transposed or not. If True `old_lm_head.size()` is `lm_head_dim,
                vocab_size` else `vocab_size, lm_head_dim`.

        Return:
            `nn.Dense`: Pointer to the resized Linear Module or the old Linear Module if `new_num_tokens` is
            `None`
        """
        if new_num_tokens is None:
            return old_lm_head

        old_num_tokens, old_lm_head_dim = (
            old_lm_head.weight.shape if not transposed else old_lm_head.weight.T.shape
        )

        if old_num_tokens == new_num_tokens:
            return old_lm_head

        if not isinstance(old_lm_head, nn.Dense):
            raise TypeError(
                f"Old language model head is of type {type(old_lm_head)}, which is not an instance of {nn.Dense}. You"
                " should either use a different resize function or make sure that `old_lm_head` are an instance of"
                f" {nn.Dense}."
            )

        # Build new lm head
        new_lm_head_shape = (old_lm_head_dim, new_num_tokens) if not transposed else (new_num_tokens, old_lm_head_dim)
        has_new_lm_head_bias = old_lm_head.bias is not None

        # When using DeepSpeed ZeRO-3, we shouldn't create new embeddings with DeepSpeed init
        # because the shape of the new embedding layer is used across various modeling files
        # as well as to update config vocab size. Shape will be 0 when using DeepSpeed init leading
        # to errors when training.
        new_lm_head = nn.Dense(
            *new_lm_head_shape,
            has_bias=has_new_lm_head_bias,
        )

        # initialize new lm head (in particular added tokens)
        self._init_weights(new_lm_head)

        num_tokens_to_copy = min(old_num_tokens, new_num_tokens)

        self._copy_lm_head_original_to_resized(
            new_lm_head, old_lm_head, num_tokens_to_copy, transposed, has_new_lm_head_bias
        )

        return new_lm_head

    def _copy_lm_head_original_to_resized(
        self, new_lm_head, old_lm_head, num_tokens_to_copy, transposed, has_new_lm_head_bias
    ):
        # Copy old lm head weights to new lm head
        if not transposed:
            new_lm_head.weight.data[:num_tokens_to_copy, :] = old_lm_head.weight.data[:num_tokens_to_copy, :]
        else:
            new_lm_head.weight.data[:, :num_tokens_to_copy] = old_lm_head.weight.data[:, :num_tokens_to_copy]

        # Copy bias weights to new lm head
        if has_new_lm_head_bias:
            new_lm_head.bias.data[:num_tokens_to_copy] = old_lm_head.bias.data[:num_tokens_to_copy]


    @classmethod
    def load(cls, pretrained_model_name_or_path: Optional[Union[str, os.PathLike]],
             *args, **kwargs):
        """
        Load a pre-trained checkpoint from a pre-trained model file or url,
        download and cache the pre-trained model file if model name in model list.

        Params:
            pretrained_model_name_or_path:
        """
        return cls.from_pretrained(pretrained_model_name_or_path, args, kwargs)

    @classmethod
    def from_pretrained(
        cls,
        pretrained_model_name_or_path: Optional[Union[str, os.PathLike]],
        *model_args,
        config: Optional[Union[PretrainedConfig, str, os.PathLike]] = None,
        cache_dir: Optional[Union[str, os.PathLike]] = None,
        ignore_mismatched_sizes: bool = False,
        force_download: bool = False,
        local_files_only: bool = False,
        **kwargs,
    ):
        """from_pretrained"""
        state_dict = kwargs.pop("state_dict", None)
        cache_dir = kwargs.pop("cache_dir", os.path.join(DEFAULT_ROOT, 'models'))
        from_pt = kwargs.pop("from_pt", False)
        force_download = kwargs.pop("force_download", False)
        resume_download = kwargs.pop("resume_download", False)
        proxies = kwargs.pop("proxies", None)
        local_files_only = kwargs.pop("local_files_only", False)
        _fast_init = kwargs.pop("_fast_init", True)
        output_loading_info = kwargs.pop("output_loading_info", False)

        is_sharded = False
        # Load config if we don't provide a configuration
        if not isinstance(config, PretrainedConfig):
            config_path = config if config is not None else pretrained_model_name_or_path
            config, model_kwargs = cls.config_class.from_pretrained(
                config_path,
                *model_args,
                from_pt=from_pt,
                cache_dir=cache_dir,
                return_unused_kwargs=True,
                force_download=force_download,
                resume_download=resume_download,
                proxies=proxies,
                local_files_only=local_files_only,
                **kwargs,
            )
        else:
            model_kwargs = kwargs

        # Load model
        if pretrained_model_name_or_path is not None:
            if pretrained_model_name_or_path in cls.pretrained_model_archive_map and not from_pt:
                archive_file = cls.pretrained_model_archive_map[pretrained_model_name_or_path]
                cache_dir = os.path.join(cache_dir, pretrained_model_name_or_path)
            elif os.path.isdir(pretrained_model_name_or_path):
                archive_file = os.path.join(pretrained_model_name_or_path, "mindspore.ckpt")
                cache_dir = pretrained_model_name_or_path
            elif os.path.isfile(pretrained_model_name_or_path):
                archive_file = pretrained_model_name_or_path
                cache_dir = None
            elif from_pt:
                archive_file = HF_MODEL_URL_BASE.format(pretrained_model_name_or_path)
                cache_dir = os.path.join(cache_dir, pretrained_model_name_or_path)
            else:
                raise ValueError(
                    f'not found model of {pretrained_model_name_or_path}.')

            # redirect to the cache, if necessary
            try:
                resolved_archive_file = cached_path(
                    archive_file,
                    cache_dir=cache_dir,
                    proxies=proxies)

                if resolved_archive_file is None:
                    base_url = '/'.join(archive_file.split('/')[:-1])
                    archive_file = base_url + '/' + HF_WEIGHTS_INDEX_NAME if from_pt else \
                        base_url + '/' + WEIGHTS_INDEX_NAME

                    resolved_archive_file = cached_path(
                        archive_file,
                        cache_dir=cache_dir,
                        proxies=proxies)

                    if resolved_archive_file is not None:
                        cache_dir = os.path.join(cache_dir, 'shard_ckpt')
                        cached_filenames, _ = get_checkpoint_shard_files(
                            index_filename=resolved_archive_file,
                            cache_dir=cache_dir,
                            url=base_url,
                            proxies=proxies
                        )
                        is_sharded = True
                    else:
                        raise EnvironmentError(
                            f"Couldn't reach server at '{archive_file}' to download pretrained weights.")

            except EnvironmentError as exc:
                raise exc

            if resolved_archive_file == archive_file:
                logger.info("loading weights file %s", archive_file)
            else:
                logger.info("loading weights file %s from cache at %s",
                            archive_file, resolved_archive_file)

        if pretrained_model_name_or_path is None and state_dict is None:
            raise ValueError("the argument 'pretrained_model_name_or_path' should be "
                             "a string of model name or checkpoint path, but got 'None'.")

        config.name_or_path = pretrained_model_name_or_path

        # Instantiate model.
        model = cls(config, *model_args, **model_kwargs)

        if from_pt:
            if is_sharded:
                converted_filenames = []
                for name in cached_filenames:
                    converted = cls.convert_torch_to_mindspore(
                        str(name))
                    converted_filenames.append(converted)
            else:
                resolved_archive_file = cls.convert_torch_to_mindspore(
                    str(resolved_archive_file))
        else:
            if is_sharded:
                converted_filenames = cached_filenames

        def load_ckpt(resolved_archive_file):
            try:
                state_dict = load_checkpoint(str(resolved_archive_file))
            except Exception as exc:
                raise OSError(
                    f"Unable to load weights from mindspore checkpoint file '{resolved_archive_file}'. "
                ) from exc
            return state_dict

        keys_missing = list(model.parameters_dict().keys())
        param_id_set = set()

        def load_param_into_net(model: nn.Cell, param_dict: dict, prefix: str):
            keys_unexpected = list(param_dict.keys())

            has_prefix_module = any(s.startswith(prefix) for s in keys_unexpected)
            expects_prefix_module = any(s.startswith(prefix) for s in keys_missing)

            for pname_in_net, param in model.parameters_and_names():
                if has_prefix_module and not expects_prefix_module:
                    param_name = prefix + '.' + param.name
                elif not has_prefix_module and expects_prefix_module:
                    param_name = param.name.replace(f'{prefix}.', '')
                else:
                    param_name = param.name
                if id(param) in param_id_set:
                    # for tied params
                    keys_missing.remove(pname_in_net)

                    if pname_in_net in keys_unexpected:
                        keys_unexpected.remove(pname_in_net)
                    continue
                new_param = param_dict.pop(param_name, None)
                if new_param is not None:
                    if new_param.shape != param.shape:
                        if not ignore_mismatched_sizes:
                            raise RuntimeError(f'The shape of parameter `{param.name} is {param.shape}, but got mismatch parameter'
                                            f' `{param_name} with shape {new_param.shape} in checkpoint, '
                                            f'\n\tYou may consider adding `ignore_mismatched_sizes=True` in the model `from_pretrained` method.')
                        logger.warning(f'The shape of parameter `{param.name} is {param.shape}, but got mismatch parameter'
                                        f' `{param_name} with shape {new_param.shape} in checkpoint, ')
                        param = Parameter(new_param, param.name)
                    else:
                        param.set_dtype(new_param.dtype)
                        param.assign_value(new_param)
                    keys_unexpected.remove(param_name)
                    keys_missing.remove(param.name)
                    param_id_set.add(id(param))

            return keys_unexpected, keys_missing

        all_keys_unexpected = None
        if state_dict is None:
            if is_sharded:
                all_keys_unexpected = []
                for name in tqdm(converted_filenames, desc="Loading checkpoint shards"):
                    state_dict = load_ckpt(name)
                    keys_unexpected, keys_missing = load_param_into_net(model, state_dict, cls.base_model_prefix)
                    all_keys_unexpected.extend(keys_unexpected)
                    del state_dict
                    gc.collect()
            else:
                state_dict = load_ckpt(resolved_archive_file)

        all_keys_unexpected, keys_missing = load_param_into_net(model, state_dict, cls.base_model_prefix)

        if cls._keys_to_ignore_on_load_missing is not None:
            for pat in cls._keys_to_ignore_on_load_missing:
                keys_missing = [k for k in keys_missing if re.search(pat, k) is None]

        if cls._keys_to_ignore_on_load_unexpected is not None:
            for pat in cls._keys_to_ignore_on_load_unexpected:
                all_keys_unexpected = [k for k in all_keys_unexpected if re.search(pat, k) is None]


        if output_loading_info:
            loading_info = {
                "missing_keys": keys_missing,
                "unexpected_keys": all_keys_unexpected,
            }
            return model, loading_info

        if all_keys_unexpected:
            logger.warning(f'The following parameters in checkpoint files are not loaded:\n'
                           f'{all_keys_unexpected}')
        if keys_missing:
            logger.warning(f'The following parameters in models are missing parameter:\n'
                           f'{keys_missing}')
        return model

    def save(self, save_dir):
        """ Save a model and its configuration file to a directory, so that
            it can be re-loaded using the `:func:`PreTrainedModel.from_pretrained`` class method.

            Arguments:
                save_dir: directory to which to save.
        """
        if os.path.isfile(save_dir):
            logger.error(f"Provided path ({save_dir}) should be a directory, not a file")
            return
        os.makedirs(save_dir, exist_ok=True)

        # Only save the model itself if we are using distributed training
        model_to_save = self.cell if hasattr(self, "cell") else self

        # Attach architecture to the config
        model_to_save.config.architectures = [model_to_save.__class__.__name__]

        # If we save using the predefined names, we can load using `from_pretrained`
        output_model_file = os.path.join(save_dir, WEIGHTS_NAME)
        save_checkpoint(model_to_save, output_model_file)

        logger.info(f"Model weights saved in {output_model_file}")

    def can_generate(self) -> bool:
        """
        Returns whether this model can generate sequences with `.generate()`.

        Returns:
            `bool`: Whether this model can generate sequences with `.generate()`.
        """
        # Detects whether `prepare_inputs_for_generation` has been overwritten, which is a requirement for generation
        if "GenerationMixin" in str(self.prepare_inputs_for_generation.__func__):
            return False
        return True

    def warn_if_padding_and_no_attention_mask(self, input_ids, attention_mask):
        """
        Shows a one-time warning if the input_ids appear to contain padding and no attention mask was given.
        """
        if (attention_mask is not None) or (self.config.pad_token_id is None):
            return

        # Check only the first and last input IDs to reduce overhead.
        if self.config.pad_token_id in input_ids[:, [-1, 0]].asnumpy():
            warn_string = (
                "We strongly recommend passing in an `attention_mask` since your input_ids may be padded."
            )

            # If the pad token is equal to either BOS, EOS, or SEP, we do not know whether the user should use an
            # attention_mask or not. In this case, we should still show a warning because this is a rare case.
            if (
                (self.config.bos_token_id is not None and self.config.bos_token_id == self.config.pad_token_id)
                or (self.config.eos_token_id is not None and self.config.eos_token_id == self.config.pad_token_id)
                or (self.config.sep_token_id is not None and self.config.sep_token_id == self.config.pad_token_id)
            ):
                warn_string += (
                    f"\nYou may ignore this warning if your `pad_token_id` ({self.config.pad_token_id}) is identical "
                    f"to the `bos_token_id` ({self.config.bos_token_id}), `eos_token_id` ({self.config.eos_token_id}), "
                    f"or the `sep_token_id` ({self.config.sep_token_id}), and your input is not padded."
                )

            logger.warning(warn_string)

    def parameters_and_names(self, name_prefix='', expand=True):
        """
        fix ignore tied weights
        """
        cells = []
        if expand:
            cells = self.cells_and_names(name_prefix=name_prefix)
        else:
            cells.append((name_prefix, self))

        for cell_name, cell in cells:
            params = cell._params.items()
            for par_name, par in params:
                if par is not None and par.inited_param is not None:
                    par = par.inited_param
                if par is not None:
                    par_new_name = par_name
                    if cell_name:
                        par_new_name = cell_name + '.' + par_new_name

                    yield par_new_name, par

    def parameters_dict(self, recurse=True):
        """
        fix ignore tied weights
        """
        param_dict = OrderedDict()
        for name, param in self.parameters_and_names(expand=recurse):
            param_dict[name] = param
        return param_dict

    def check_names_and_refresh_name(self):
        """
        fix ignore tied weights
        """
        if not hasattr(self, "_params"):
            return
        all_name = dict(self.parameters_and_names()).keys()

        if len(set(all_name)) < len(all_name):
            self.update_parameters_name()
            self.check_names()

    def save_pretrained(
        self,
        save_directory: Union[str, os.PathLike],
        is_main_process: bool = True,
        state_dict: Optional[dict] = None,
        save_function: Callable = mindspore.save_checkpoint,
        max_shard_size: Union[int, str] = "5GB",
        variant: Optional[str] = None,
        **kwargs,
    ):
        """
        Save a model and its configuration file to a directory, so that it can be re-loaded using the
        [`~PreTrainedModel.from_pretrained`] class method.

        Arguments:
            save_directory (`str` or `os.PathLike`):
                Directory to which to save. Will be created if it doesn't exist.
            is_main_process (`bool`, *optional*, defaults to `True`):
                Whether the process calling this is the main process or not. Useful when in distributed training like
                TPUs and need to call this function on all processes. In this case, set `is_main_process=True` only on
                the main process to avoid race conditions.
            state_dict (nested dictionary of `torch.Tensor`):
                The state dictionary of the model to save. Will default to `self.state_dict()`, but can be used to only
                save parts of the model or if special precautions need to be taken when recovering the state dictionary
                of a model (like when using model parallelism).
            save_function (`Callable`):
                The function to use to save the state dictionary. Useful on distributed training like TPUs when one
                need to replace `torch.save` by another method.
            max_shard_size (`int` or `str`, *optional*, defaults to `"5GB"`):
                The maximum size for a checkpoint before being sharded. Checkpoints shard will then be each of size
                lower than this size. If expressed as a string, needs to be digits followed by a unit (like `"5MB"`).
                We default it to 5GB in order for models to be able to run easily on free-tier google colab instances
                without CPU OOM issues.

                <Tip warning={true}>

                If a single weight of the model is bigger than `max_shard_size`, it will be in its own checkpoint shard
                which will be bigger than `max_shard_size`.

                </Tip>
            variant (`str`, *optional*):
                If specified, weights are saved in the format pytorch_model.<variant>.bin.
            save_peft_format (`bool`, *optional*, defaults to `True`):
                For backward compatibility with PEFT library, in case adapter weights are attached to the model, all
                keys of the state dict of adapters needs to be pre-pended with `base_model.model`. Advanced users can
                disable this behaviours by setting `save_peft_format` to `False`.
            kwargs (`Dict[str, Any]`, *optional*):
                Additional key word arguments passed along to the [`~utils.PushToHubMixin.push_to_hub`] method.
        """

        if os.path.isfile(save_directory):
            logger.error(f"Provided path ({save_directory}) should be a directory, not a file")
            return

        os.makedirs(save_directory, exist_ok=True)


        # Only save the model itself if we are using distributed training
        model_to_save = self

        # save the string version of dtype to the config, e.g. convert torch.float32 => "float32"
        # we currently don't use this setting automatically, but may start to use with v5
        dtype = get_parameter_dtype(model_to_save)
        model_to_save.config.ms_dtype = str(dtype).lower()

        # Attach architecture to the config
        model_to_save.config.architectures = [model_to_save.__class__.__name__]

        # Save the config
        if is_main_process:
            model_to_save.config.save_pretrained(save_directory)
            if self.can_generate():
                model_to_save.generation_config.save_pretrained(save_directory)


        # Save the model
        if state_dict is None:
            state_dict = model_to_save.parameters_dict()

        # Handle the case where some state_dict keys shouldn't be saved
        if self._keys_to_ignore_on_save is not None:
            for ignore_key in self._keys_to_ignore_on_save:
                if ignore_key in state_dict.keys():
                    del state_dict[ignore_key]

        # Shard the model if it is too big.
        weights_name = _add_variant(WEIGHTS_NAME, variant)

        shards, index = shard_checkpoint(state_dict, max_shard_size=max_shard_size, weights_name=weights_name)

        # Clean the folder from a previous save
        for filename in os.listdir(save_directory):
            full_filename = os.path.join(save_directory, filename)
            # If we have a shard file that is not going to be replaced, we delete it, but only from the main process
            # in distributed settings to avoid race conditions.
            weights_no_suffix = weights_name.replace(".bin", "").replace(".safetensors", "")

            # make sure that file to be deleted matches format of sharded file, e.g. pytorch_model-00001-of-00005
            filename_no_suffix = filename.replace(".bin", "").replace(".safetensors", "")
            reg = re.compile(r"(.*?)-\d{5}-of-\d{5}")

            if (
                filename.startswith(weights_no_suffix)
                and os.path.isfile(full_filename)
                and filename not in shards
                and is_main_process
                and reg.fullmatch(filename_no_suffix) is not None
            ):
                os.remove(full_filename)

        # Save the model
        for shard_file, shard in shards.items():
            save_function(shard, os.path.join(save_directory, shard_file))

        if index is None:
            path_to_weights = os.path.join(save_directory, _add_variant(WEIGHTS_NAME, variant))
            logger.info(f"Model weights saved in {path_to_weights}")
        else:
            save_index_file = WEIGHTS_INDEX_NAME
            save_index_file = os.path.join(save_directory, _add_variant(save_index_file, variant))
            # Save the index as well
            with open(save_index_file, "w", encoding="utf-8") as f:
                content = json.dumps(index, indent=2, sort_keys=True) + "\n"
                f.write(content)
            logger.info(
                f"The model is bigger than the maximum size per checkpoint ({max_shard_size}) and is going to be "
                f"split in {len(shards)} checkpoint shards. You can find where each parameters has been saved in the "
                f"index located at {save_index_file}."
            )


def get_parameter_dtype(parameter: Union[nn.Cell, GenerationMixin, "ModuleUtilsMixin"]):
    """
    Returns the first found floating dtype in parameters if there is one, otherwise returns the last dtype it found.
    """
    last_dtype = None
    for t in parameter.get_parameters():
        last_dtype = t.dtype
        if ops.is_floating_point(t):
            return t.dtype

    if last_dtype is not None:
        # if no floating dtype was found return whatever the first dtype is
        return last_dtype

    return last_dtype

def _add_variant(weights_name: str, variant: Optional[str] = None) -> str:
    if variant is not None:
        splits = weights_name.split(".")
        splits = splits[:-1] + [variant] + splits[-1:]
        weights_name = ".".join(splits)

    return weights_name

def shard_checkpoint(
    state_dict: Dict[str, mindspore.Tensor], max_shard_size: Union[int, str] = "10GB", weights_name: str = WEIGHTS_NAME
):
    """
    Splits a model state dictionary in sub-checkpoints so that the final size of each sub-checkpoint does not exceed a
    given size.

    The sub-checkpoints are determined by iterating through the `state_dict` in the order of its keys, so there is no
    optimization made to make each sub-checkpoint as close as possible to the maximum size passed. For example, if the
    limit is 10GB and we have weights of sizes [6GB, 6GB, 2GB, 6GB, 2GB, 2GB] they will get sharded as [6GB], [6+2GB],
    [6+2+2GB] and not [6+2+2GB], [6+2GB], [6GB].

    <Tip warning={true}>

    If one of the model's weight is bigger than `max_shard_size`, it will end up in its own sub-checkpoint which will
    have a size greater than `max_shard_size`.

    </Tip>

    Args:
        state_dict (`Dict[str, torch.Tensor]`): The state dictionary of a model to save.
        max_shard_size (`int` or `str`, *optional*, defaults to `"10GB"`):
            The maximum size of each sub-checkpoint. If expressed as a string, needs to be digits followed by a unit
            (like `"5MB"`).
        weights_name (`str`, *optional*, defaults to `"pytorch_model.bin"`):
            The name of the model save file.
    """
    max_shard_size = convert_file_size_to_int(max_shard_size)

    sharded_state_dicts = [{}]
    last_block_size = 0
    total_size = 0
    storage_id_to_block = {}

    for key, weight in state_dict.items():
        # when bnb serialization is used the weights in the state dict can be strings
        # check: https://github.com/huggingface/transformers/pull/24416 for more details
        if isinstance(weight, str):
            continue
        storage_id = id(weight)

        # If a `weight` shares the same underlying storage as another tensor, we put `weight` in the same `block`
        if storage_id in storage_id_to_block:
            block_id = storage_id_to_block[storage_id]
            sharded_state_dicts[block_id][key] = weight
            continue

        weight_size = weight.numel() * dtype_byte_size(weight.dtype)

        # If this weight is going to tip up over the maximal size, we split, but only if we have put at least one
        # weight in the current shard.
        if last_block_size + weight_size > max_shard_size and len(sharded_state_dicts[-1]) > 0:
            sharded_state_dicts.append({})
            last_block_size = 0

        sharded_state_dicts[-1][key] = weight
        last_block_size += weight_size
        total_size += weight_size
        storage_id_to_block[storage_id] = len(sharded_state_dicts) - 1

    # If we only have one shard, we return it
    if len(sharded_state_dicts) == 1:
        return {weights_name: sharded_state_dicts[0]}, None

    # Otherwise, let's build the index
    weight_map = {}
    shards = {}
    for idx, shard in enumerate(sharded_state_dicts):
        shard_file = weights_name.replace(".ckpt", f"-{idx+1:05d}-of-{len(sharded_state_dicts):05d}.ckpt")
        shards[shard_file] = shard
        for key in shard.keys():
            weight_map[key] = shard_file

    # Add the metadata
    metadata = {"total_size": total_size}
    index = {"metadata": metadata, "weight_map": weight_map}
    return shards, index

def dtype_byte_size(dtype):
    """
    Returns the size (in bytes) occupied by one parameter of type `dtype`.

    Example:

    ```py
    >>> dtype_byte_size(torch.float32)
    4
    ```
    """
    if dtype == mindspore.bool_:
        return 1 / 8
    bit_search = re.search(r"[^\d](\d+)$", str(dtype))
    if bit_search is None:
        raise ValueError(f"`dtype` is not a valid dtype: {dtype}.")
    bit_size = int(bit_search.groups()[0])
    return bit_size // 8
