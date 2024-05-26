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
"""
Cache utils.
"""
from typing import Any, Dict, List, Optional, Tuple

import mindspore
from mindspore import ops
from .configuration_utils import PretrainedConfig

class Cache:
    """
    Base, abstract class for all caches. The actual data structure is specific to each subclass.
    """

    def update(
        self,
        key_states: mindspore.Tensor,
        value_states: mindspore.Tensor,
        layer_idx: int,
        cache_kwargs: Optional[Dict[str, Any]] = None,
    ) -> Tuple[mindspore.Tensor, mindspore.Tensor]:
        """
        Updates the cache with the new `key_states` and `value_states` for the layer `layer_idx`.

        Parameters:
            key_states (`mindspore.Tensor`):
                The new key states to cache.
            value_states (`mindspore.Tensor`):
                The new value states to cache.
            layer_idx (`int`):
                The index of the layer to cache the states for.
            cache_kwargs (`Dict[str, Any]`, `optional`):
                Additional arguments for the cache subclass. These are specific to each subclass and allow new types of
                cache to be created.

        Return:
            A tuple containing the updated key and value states.
        """
        raise NotImplementedError("Make sure to implement `update` in a subclass.")

    def get_seq_length(self, layer_idx: Optional[int] = 0) -> int:
        """Returns the sequence length of the cached states. A layer index can be optionally passed."""
        raise NotImplementedError("Make sure to implement `get_seq_length` in a subclass.")

    def get_max_length(self) -> Optional[int]:
        """Returns the maximum sequence length of the cached states, if there is any."""
        raise NotImplementedError("Make sure to implement `get_max_length` in a subclass.")

    def get_usable_length(self, new_seq_length: int, layer_idx: Optional[int] = 0) -> int:
        """Given the sequence length of the new inputs, returns the usable length of the cache."""
        # Cache without size limit -> all cache is usable
        # Cache with size limit -> if the length cache plus the length of the new inputs is larger the maximum cache
        #   length, we will need to evict part of the cache (and thus not all cache is usable)
        max_length = self.get_max_length()
        previous_seq_length = self.get_seq_length(layer_idx)
        if max_length is not None and previous_seq_length + new_seq_length > max_length:
            return max_length - new_seq_length
        return previous_seq_length


class DynamicCache(Cache):
    """
    A cache that grows dynamically as more tokens are generated. This is the default for generative models.

    It stores the Key and Value states as a list of tensors, one for each layer. The expected shape for each tensor is
    `[batch_size, num_heads, seq_len, head_dim]`.
    """

    def __init__(self) -> None:

        r"""
        Initializes an instance of the 'DynamicCache' class.
        
        Args:
            self: The instance of the 'DynamicCache' class.
        
        Returns:
            None. This method does not return any value.
        
        Raises:
            None.
        
        Description:
        This method initializes the 'DynamicCache' instance by setting up the key and value caches, as well as initializing the number of seen tokens.
        
        - The 'key_cache' is a list of mindspore.Tensor objects that stores the keys.
        - The 'value_cache' is a list of mindspore.Tensor objects that stores the corresponding values.
        - The 'seen_tokens' is an integer that represents the number of tokens that have been seen.
        
        The 'key_cache' and 'value_cache' lists are initially empty, while the 'seen_tokens' is set to 0.
        
        Example:
            cache = DynamicCache()
            # Initializes a new instance of 'DynamicCache' with empty key and value caches,
            # and the number of seen tokens set to 0.
        """
        self.key_cache: List[mindspore.Tensor] = []
        self.value_cache: List[mindspore.Tensor] = []
        self.seen_tokens = 0  # Used in `generate` to keep tally of how many tokens the cache has seen

    def __getitem__(self, layer_idx: int) -> List[Tuple[mindspore.Tensor]]:
        """
        Support for backwards-compatible `past_key_value` indexing, e.g. `past_key_value[0][0].shape[2]` to get the
        sequence length.
        """
        if layer_idx < len(self):
            return (self.key_cache[layer_idx], self.value_cache[layer_idx])
        raise KeyError(f"Cache only has {len(self)} layers, attempted to access layer with index {layer_idx}")

    def __iter__(self):
        """
        Support for backwards-compatible `past_key_value` iteration, e.g. `for x in past_key_value:` to iterate over
        keys and values
        """
        for layer_idx in range(len(self)):
            yield (self.key_cache[layer_idx], self.value_cache[layer_idx])

    def __len__(self):
        """
        Support for backwards-compatible `past_key_value` length, e.g. `len(past_key_value)`. This value corresponds
        to the number of layers in the model.
        """
        return len(self.key_cache)

    def update(
        self,
        key_states: mindspore.Tensor,
        value_states: mindspore.Tensor,
        layer_idx: int,
        cache_kwargs: Optional[Dict[str, Any]] = None,
    ) -> Tuple[mindspore.Tensor, mindspore.Tensor]:
        """
        Updates the cache with the new `key_states` and `value_states` for the layer `layer_idx`.

        Parameters:
            key_states (`mindspore.Tensor`):
                The new key states to cache.
            value_states (`mindspore.Tensor`):
                The new value states to cache.
            layer_idx (`int`):
                The index of the layer to cache the states for.
            cache_kwargs (`Dict[str, Any]`, `optional`):
                Additional arguments for the cache subclass. No additional arguments are used in `DynamicCache`.

        Return:
            A tuple containing the updated key and value states.
        """
        # Update the number of seen tokens
        if layer_idx == 0:
            self.seen_tokens += key_states.shape[-2]

        # Update the cache
        if len(self.key_cache) <= layer_idx:
            self.key_cache.append(key_states)
            self.value_cache.append(value_states)
        else:
            self.key_cache[layer_idx] = ops.cat([self.key_cache[layer_idx], key_states], axis=-2)
            self.value_cache[layer_idx] = ops.cat([self.value_cache[layer_idx], value_states], axis=-2)

        return self.key_cache[layer_idx], self.value_cache[layer_idx]

    def get_seq_length(self, layer_idx: Optional[int] = 0) -> int:
        """Returns the sequence length of the cached states. A layer index can be optionally passed."""
        if len(self.key_cache) <= layer_idx:
            return 0
        return self.key_cache[layer_idx].shape[-2]

    def get_max_length(self) -> Optional[int]:
        """Returns the maximum sequence length of the cached states. DynamicCache does not have a maximum length."""
        return None

    def reorder_cache(self, beam_idx: mindspore.Tensor):
        """Reorders the cache for beam search, given the selected beam indices."""
        for layer_idx in range(len(self.key_cache)):
            self.key_cache[layer_idx] = self.key_cache[layer_idx].index_select(0, beam_idx)
            self.value_cache[layer_idx] = self.value_cache[layer_idx].index_select(0, beam_idx)

    def to_legacy_cache(self) -> Tuple[Tuple[mindspore.Tensor], Tuple[mindspore.Tensor]]:
        """Converts the `DynamicCache` instance into the its equivalent in the legacy cache format."""
        legacy_cache = ()
        for layer_idx in range(len(self)):
            legacy_cache += ((self.key_cache[layer_idx], self.value_cache[layer_idx]),)
        return legacy_cache

    @classmethod
    def from_legacy_cache(cls, past_key_values: Optional[Tuple[Tuple[mindspore.Tensor]]] = None) -> "DynamicCache":
        """Converts a cache in the legacy cache format into an equivalent `DynamicCache`."""
        cache = cls()
        if past_key_values is not None:
            for layer_idx in range(len(past_key_values)):
                key_states, value_states = past_key_values[layer_idx]
                cache.update(key_states, value_states, layer_idx)
        return cache


class SinkCache(Cache):
    """
    A cache that as described in the [Attention Sinks paper](https://arxiv.org/abs/2309.17453). It allows the model to
    generate beyond the length of its context window, without losing fluency in the conversation. As it discards past
    tokens, the model will lose the ability to generate tokens that depend on the context that was discarded.

    It stores the Key and Value states as a list of tensors, one for each layer. The expected shape for each tensor is
    `[batch_size, num_heads, seq_len, head_dim]`.

    Parameters:
        window_length (`int`):
            The length of the context window.
        num_sink_tokens (`int`):
            The number of sink tokens. See the original paper for more information.
    """

    def __init__(self, window_length: int, num_sink_tokens: int) -> None:

        r"""
        Initializes an instance of the SinkCache class.
        
        Args:
            self (SinkCache): The SinkCache instance.
            window_length (int): The length of the window used for caching.
            num_sink_tokens (int): The number of sink tokens.
        
        Returns:
            None
        
        Raises:
            None
        '''
        
        The `__init__` method is used to initialize a new instance of the `SinkCache` class. It takes three parameters: `self`, `window_length`, and `num_sink_tokens`. 
        
        - `self` (SinkCache): The `self` parameter refers to the instance of the `SinkCache` class that is being initialized.
        
        - `window_length` (int): The `window_length` parameter specifies the length of the window used for caching. This value determines the size of the cache and affects the number of tokens that can be stored.
        
        - `num_sink_tokens` (int): The `num_sink_tokens` parameter represents the number of sink tokens. Sink tokens are special tokens used in the caching mechanism.
        
        The method does not return any value (`None`).
        
        This method does not raise any exceptions.
        """
        self.key_cache: List[mindspore.Tensor] = []
        self.value_cache: List[mindspore.Tensor] = []
        self.window_length = window_length
        self.num_sink_tokens = num_sink_tokens
        self.cos_sin_cache = {}
        self.seen_tokens = 0  # Used in `generate` to keep tally of how many tokens the cache has seen

    @staticmethod
    def _rotate_half(x):

        r"""
        Rotate the input tensor 'x' by half of its length along the last dimension.
        
        Args:
            x (tensor): The input tensor to be rotated. It should have at least one dimension.
            
        Returns:
            None. The method modifies the input tensor in place.
        
        Raises:
            ValueError: If the input tensor 'x' does not have at least one dimension.
            IndexError: If the input tensor 'x' does not have a valid shape for rotation.
        """
        x1 = x[..., : x.shape[-1] // 2]
        x2 = x[..., x.shape[-1] // 2 :]
        return ops.cat((-x2, x1), axis=-1)

    def _apply_key_rotary_pos_emb(
        self, key_states: mindspore.Tensor, cos: mindspore.Tensor, sin: mindspore.Tensor
    ) -> mindspore.Tensor:

        r"""
        Applies key rotary positional embedding to the given key states.
        
        Args:
            self (SinkCache): The instance of the SinkCache class.
            key_states (mindspore.Tensor): The key states to which the rotational embedding is applied.
            cos (mindspore.Tensor): The cosine values used for rotational embedding.
            sin (mindspore.Tensor): The sine values used for rotational embedding.
        
        Returns:
            mindspore.Tensor: The key states after applying the rotary positional embedding.
        
        Raises:
            None
        
        This method applies the rotary positional embedding to the key states using the provided cosine and sine values. The embedding is applied by element-wise multiplication of the key states with the cosine values, and element-wise multiplication of the half-rotated key states with the sine values. The resulting rotated key states are then returned.
        """
        rotated_key_states = (key_states * cos) + (self._rotate_half(key_states) * sin)
        return rotated_key_states

    def _get_rerotation_cos_sin(
        self, key_states: mindspore.Tensor, cos: mindspore.Tensor, sin: mindspore.Tensor
    ) -> Tuple[mindspore.Tensor, mindspore.Tensor]:

        r"""
        This method calculates the rerotation cosine and sine values based on the provided key states, cosine, and sine tensors.
        
        Args:
            self: The instance of the SinkCache class.
            key_states (mindspore.Tensor): The key states tensor representing the current state of the keys.
            cos (mindspore.Tensor): The cosine tensor.
            sin (mindspore.Tensor): The sine tensor.
            
        Returns:
            Tuple[mindspore.Tensor, mindspore.Tensor]: A tuple containing the rerotation cosine and sine tensors of type mindspore.Tensor. 
            The rerotation cosine and sine values are calculated based on the input key_states, cos, and sin tensors.
        
        Raises:
            N/A
        """
        if key_states.shape[-2] not in self.cos_sin_cache:
            # Upcast to float32 temporarily for better accuracy
            cos = cos.to(mindspore.float32)
            sin = sin.to(mindspore.float32)

            # Compute the cos and sin required for back- and forward-rotating to one position earlier in the sequence
            original_cos = cos[self.num_sink_tokens + key_states.shape[-2] :]
            shifted_cos = cos[self.num_sink_tokens : -key_states.shape[-2]]
            original_sin = sin[self.num_sink_tokens + key_states.shape[-2] :]
            shifted_sin = sin[self.num_sink_tokens : -key_states.shape[-2]]
            rerotation_cos = original_cos * shifted_cos + original_sin * shifted_sin
            rerotation_sin = -original_sin * shifted_cos + original_cos * shifted_sin

            self.cos_sin_cache[key_states.shape[-2]] = (
                rerotation_cos.to(key_states.dtype).unsqueeze(0),
                rerotation_sin.to(key_states.dtype).unsqueeze(0),
            )
        return self.cos_sin_cache[key_states.shape[-2]]

    def get_seq_length(self, layer_idx: Optional[int] = 0) -> int:
        """Returns the sequence length of the cached states. A layer index can be optionally passed."""
        # Workaround to make 'key_states.shape[-2] + past_key_value.get_seq_length(self.layer_idx)' <= window_length
        if len(self.key_cache) <= layer_idx:
            return 0
        return self.key_cache[layer_idx].shape[-2]

    def get_max_length(self) -> Optional[int]:
        """Returns the maximum sequence length of the cached states."""
        return self.window_length

    def update(
        self,
        key_states: mindspore.Tensor,
        value_states: mindspore.Tensor,
        layer_idx: int,
        cache_kwargs: Optional[Dict[str, Any]] = None,
    ) -> Tuple[mindspore.Tensor, mindspore.Tensor]:
        """
        Updates the cache with the new `key_states` and `value_states` for the layer `layer_idx`.

        Parameters:
            key_states (`mindspore.Tensor`):
                The new key states to cache.
            value_states (`mindspore.Tensor`):
                The new value states to cache.
            layer_idx (`int`):
                The index of the layer to cache the states for.
            cache_kwargs (`Dict[str, Any]`, `optional`):
                Additional arguments for the cache subclass. The following arguments can be used in `SinkCache`: `sin`,
                `cos` and `partial_rotation_size`. These arguments are used with models using RoPE, to recompute the
                rotation as the tokens are shifted.

        Return:
            A tuple containing the updated key and value states.
        """
        # Optional kwargs for `SinkCache` -- needed on models using RoPE. `partial_rotation_size` is used on models
        # with partially rotated position embeddings, like Phi or Persimmon.
        sin = cache_kwargs.get("sin")
        cos = cache_kwargs.get("cos")
        partial_rotation_size = cache_kwargs.get("partial_rotation_size")
        using_rope = cos is not None and sin is not None

        # Update the number of seen tokens
        if layer_idx == 0:
            self.seen_tokens += key_states.shape[-2]

        # [bsz, num_heads, seq_len, head_dim]
        if len(self.key_cache) <= layer_idx:
            # Empty cache
            self.key_cache.append(key_states)
            self.value_cache.append(value_states)

        elif key_states.shape[-2] + self.get_seq_length(layer_idx) < self.window_length:
            # Growing cache
            self.key_cache[layer_idx] = ops.cat([self.key_cache[layer_idx], key_states], axis=-2)
            self.value_cache[layer_idx] = ops.cat([self.value_cache[layer_idx], value_states], axis=-2)

        else:
            # Shifting cache
            keys_to_keep = self.key_cache[layer_idx][
                :, :, -self.window_length + self.num_sink_tokens + key_states.shape[-2] :
            ]

            # On RoPE models, we need to recompute the Key rotation as the tokens are shifted
            if using_rope:
                rerotation_cos, rerotation_sin = self._get_rerotation_cos_sin(
                    key_states, cos[: self.window_length], sin[: self.window_length]
                )
                if partial_rotation_size is not None:
                    keys_to_keep, keys_pass = (
                        keys_to_keep[..., :partial_rotation_size],
                        keys_to_keep[..., partial_rotation_size:],
                    )
                keys_to_keep = self._apply_key_rotary_pos_emb(keys_to_keep, rerotation_cos, rerotation_sin)
                if partial_rotation_size is not None:
                    keys_to_keep = ops.cat((keys_to_keep, keys_pass), axis=-1)

            # Concatenate sink tokens, shifted & rotated tokens (if needed), and new tokens
            sink_keys = self.key_cache[layer_idx][:, :, : self.num_sink_tokens]
            self.key_cache[layer_idx] = ops.cat([sink_keys, keys_to_keep, key_states], axis=-2)

            sink_values = self.value_cache[layer_idx][:, :, : self.num_sink_tokens]
            values_to_keep = self.value_cache[layer_idx][
                :, :, -self.window_length + self.num_sink_tokens + value_states.shape[-2] :
            ]
            self.value_cache[layer_idx] = ops.cat([sink_values, values_to_keep, value_states], axis=-2)

        return self.key_cache[layer_idx], self.value_cache[layer_idx]

    def reorder_cache(self, beam_idx: mindspore.Tensor):
        """Reorders the cache for beam search, given the selected beam indices."""
        for layer_idx in range(len(self.key_cache)):
            self.key_cache[layer_idx] = self.key_cache[layer_idx].index_select(0, beam_idx)
            self.value_cache[layer_idx] = self.value_cache[layer_idx].index_select(0, beam_idx)

class StaticCache(Cache):
    """
    Static Cache class to be used with `torch.compile(model)`.

    Parameters:
        config (`PretrainedConfig):
            The configuration file defining the `max_position_embeddings`, `hidden_size` and `num_attention_heads`
            required to initialize the static cache.
        max_batch_size (`int`):
            The maximum batch size with which the model will be used.
        max_cache_len (`int`):
            The maximum sequence length with which the model will be used.
        device (`torch.device`):
            The device on which the cache should be initialized. Should be the same as the layer.
        dtype (*optional*, defaults to `torch.float32`):
            The default `dtype` to use when initializing the layer.
    """

    def __init__(self, config: PretrainedConfig, max_batch_size: int, max_cache_len: int, dtype=None) -> None:

        r"""
        Initializes a StaticCache object.
        
        Args:
            self (StaticCache): The instance of the StaticCache class.
            config (PretrainedConfig): The pre-trained configuration object containing model parameters.
            max_batch_size (int): The maximum batch size for caching.
            max_cache_len (int): The maximum length of the cache. Defaults to the maximum position embeddings in the config.
            dtype (optional): The data type of the cache. Defaults to mindspore.float32.
        
        Returns:
            None. This method initializes the StaticCache object with the provided parameters.
        
        Raises:
            TypeError: If the provided config is not of type PretrainedConfig.
            ValueError: If max_batch_size or max_cache_len is less than or equal to zero.
            AttributeError: If the provided config does not contain necessary attributes.
        """
        super().__init__()
        self.max_batch_size = max_batch_size
        self.max_cache_len = config.max_position_embeddings if max_cache_len is None else max_cache_len
        # Some model define a custom `head_dim` != config.hidden_size // config.num_attention_heads
        self.head_dim = (
            config.head_dim if hasattr(config, "head_dim") else config.hidden_size // config.num_attention_heads
        )

        self.dtype = dtype if dtype is not None else mindspore.float32
        self.num_key_value_heads = (
            config.num_attention_heads if config.num_key_value_heads is None else config.num_key_value_heads
        )

        cache_shape = (max_batch_size, self.num_key_value_heads, self.max_cache_len, self.head_dim)
        self.key_cache: mindspore.Tensor = ops.zeros(cache_shape, dtype=self.dtype)
        self.value_cache: mindspore.Tensor = ops.zeros(cache_shape, dtype=self.dtype)

    def update(
        self,
        key_states: mindspore.Tensor,
        value_states: mindspore.Tensor,
        layer_idx: int,
        cache_kwargs: Optional[Dict[str, Any]] = None,
    ) -> Tuple[mindspore.Tensor, mindspore.Tensor]:
        """
        Updates the cache with the new `key_states` and `value_states` for the layer `layer_idx`.
        It is VERY important to index using a tensor, otherwise you introduce a copy to the device.

        Parameters:
            key_states (`mindspore.Tensor`):
                The new key states to cache.
            value_states (`mindspore.Tensor`):
                The new value states to cache.
            layer_idx (`int`):
                The index of the layer to cache the states for. Kept for backward compatibility
            cache_kwargs (`Dict[str, Any]`, `optional`):
                Additional arguments for the cache subclass. The `StaticCache` just needs the `q_len`
                to know how much of the cache it should overwrite.

        Return:
            A tuple containing the updated key and value states.
        """
        new_cache_positions = cache_kwargs.get("cache_position")
        k_out = self.key_cache
        v_out = self.value_cache

        k_out[:, :, new_cache_positions] = key_states
        v_out[:, :, new_cache_positions] = value_states

        return k_out, v_out

    def get_seq_length(self, layer_idx: Optional[int] = 0) -> int:
        """Returns the sequence length of the cached states that were seen by the model. `layer_idx` kept for BC"""
        # TODO: Fix once the stateful `int` bug in PyTorch is fixed.
        raise ValueError(
            "get_seq_length is not implemented for StaticCache. Please refer to https://github.com/huggingface/transformers/pull/29114."
        )

    def get_usable_length(self, new_sequence_length=None, layer_idx: Optional[int] = 0) -> int:

        r"""
        Returns the usable length of a sequence in the StaticCache layer.
        
        Args:
            self (StaticCache): An instance of the StaticCache class.
            new_sequence_length (Optional[int]): The new length of the sequence. Defaults to None.
            layer_idx (int): Index of the layer. Defaults to 0.
        
        Returns:
            int: The usable length of the sequence.
        
        Raises:
            ValueError: If the method 'get_seq_length' is not implemented for the StaticCache layer.
        
        Note:
            This method calculates the usable length of a sequence in the StaticCache layer. It takes into account any changes in the sequence length and the layer index. If 'new_sequence_length' is not provided, the method assumes the sequence length remains unchanged. If 'layer_idx' is not provided, the method defaults to the first layer (index 0).
        
        Example:
            >>> cache = StaticCache()
            >>> cache.get_usable_length(new_sequence_length=100, layer_idx=2)
            100
        
            For more information, please refer to https://github.com/huggingface/transformers/pull/29114.
        """
        raise ValueError(
            "get_seq_length is not implemented for StaticCache. Please refer to https://github.com/huggingface/transformers/pull/29114."
        )

    def get_max_length(self) -> Optional[int]:
        """Returns the maximum sequence length of the cached states. DynamicCache does not have a maximum length."""
        return self.max_cache_len

    def reorder_cache(self, beam_idx: mindspore.Tensor):
        """Reorders the cache for beam search, given the selected beam indices."""
        self.key_cache = self.key_cache.index_select(0, beam_idx)
        self.value_cache = self.value_cache.index_select(0, beam_idx)

    def to_legacy_cache(self):
        """Dummy function for BC. We have to keep it because otherwise the call in the forward of models will break it"""
        return None
