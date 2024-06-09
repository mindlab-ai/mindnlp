# coding=utf-8
# Copyright 2022 WeChatAI The HuggingFace Inc. team. All rights reserved.
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
"""MindSpore RoCBert model."""

import math
from typing import List, Optional, Tuple, Union

import mindspore
import numpy as np
from mindspore import nn, ops
from mindspore.common.initializer import Normal, initializer

from mindnlp.utils import logging

from ...activations import ACT2FN
from ...modeling_outputs import (
    BaseModelOutputWithPastAndCrossAttentions,
    BaseModelOutputWithPoolingAndCrossAttentions,
    CausalLMOutputWithCrossAttentions,
    MaskedLMOutput,
    MultipleChoiceModelOutput,
    QuestionAnsweringModelOutput,
    SequenceClassifierOutput,
    TokenClassifierOutput,
)
from ...modeling_utils import PreTrainedModel
from ...ms_utils import (
    apply_chunking_to_forward,
    find_pruneable_heads_and_indices,
    prune_linear_layer,
)
from .configuration_roc_bert import RoCBertConfig

logger = logging.get_logger(__name__)

_CHECKPOINT_FOR_DOC = "weiweishi/roc-bert-base-zh"
_CONFIG_FOR_DOC = "RoCBertConfig"

# Base model docstring
_EXPECTED_OUTPUT_SHAPE = [1, 8, 768]

# Token Classification output
_CHECKPOINT_FOR_TOKEN_CLASSIFICATION = "ArthurZ/dummy-rocbert-ner"
_TOKEN_CLASS_EXPECTED_OUTPUT = ["S-EVENT", "S-FAC", "I-ORDINAL", "I-ORDINAL", "E-ORG", "E-LANGUAGE", "E-ORG", "E-ORG", "E-ORG", "E-ORG",
                                "I-EVENT", "S-TIME", "S-TIME", "E-LANGUAGE", "S-TIME", "E-DATE", "I-ORDINAL", "E-QUANTITY", "E-LANGUAGE",
                                "S-TIME", "B-ORDINAL", "S-PRODUCT", "E-LANGUAGE", "E-LANGUAGE", "E-ORG", "E-LOC", "S-TIME", "I-ORDINAL",
                                "S-FAC", "O", "S-GPE", "I-EVENT", "S-GPE", "E-LANGUAGE", "E-ORG", "S-EVENT", "S-FAC", "S-FAC", "S-FAC",
                                "E-ORG", "S-FAC", "E-ORG", "S-GPE"]  # fmt: skip
_TOKEN_CLASS_EXPECTED_LOSS = 3.62

# SequenceClassification docstring
_CHECKPOINT_FOR_SEQUENCE_CLASSIFICATION = "ArthurZ/dummy-rocbert-seq"
_SEQ_CLASS_EXPECTED_OUTPUT = "'financial news'"
_SEQ_CLASS_EXPECTED_LOSS = 2.31

# QuestionAsnwering docstring
_CHECKPOINT_FOR_QA = "ArthurZ/dummy-rocbert-qa"
_QA_EXPECTED_OUTPUT = "''"
_QA_EXPECTED_LOSS = 3.75
_QA_TARGET_START_INDEX = 14
_QA_TARGET_END_INDEX = 15

# Maske language modeling


class RoCBertEmbeddings(nn.Cell):
    """Construct the embeddings from word, position, shape, pronunciation and token_type embeddings."""

    def __init__(self, config):
        super().__init__()
        self.word_embeddings = nn.Embedding(
            config.vocab_size, config.hidden_size, padding_idx=config.pad_token_id
        )
        self.pronunciation_embed = nn.Embedding(
            config.pronunciation_vocab_size,
            config.pronunciation_embed_dim,
            padding_idx=config.pad_token_id,
        )
        self.shape_embed = nn.Embedding(
            config.shape_vocab_size,
            config.shape_embed_dim,
            padding_idx=config.pad_token_id,
        )
        self.position_embeddings = nn.Embedding(
            config.max_position_embeddings, config.hidden_size
        )
        self.token_type_embeddings = nn.Embedding(
            config.type_vocab_size, config.hidden_size
        )

        self.enable_pronunciation = config.enable_pronunciation
        self.enable_shape = config.enable_shape

        if config.concat_input:
            input_dim = config.hidden_size
            if self.enable_pronunciation:
                pronunciation_dim = config.pronunciation_embed_dim
                input_dim += pronunciation_dim
            if self.enable_shape:
                shape_dim = config.shape_embed_dim
                input_dim += shape_dim
            self.map_inputs_layer = nn.Dense(input_dim, config.hidden_size)
        else:
            self.map_inputs_layer = None

        # self.LayerNorm is not snake-cased to stick with TensorFlow model variable name and be able to load
        # any TensorFlow checkpoint file
        self.LayerNorm = nn.LayerNorm(
            [config.hidden_size], epsilon=config.layer_norm_eps
        )
        self.dropout = nn.Dropout(p=config.hidden_dropout_prob)

        # position_ids (1, len position emb) is contiguous in memory and exported when serialized
        self.position_ids = ops.arange(config.max_position_embeddings).broadcast_to(
            (1, -1)
        )
        self.position_embedding_type = getattr(
            config, "position_embedding_type", "absolute"
        )
        self.token_type_ids = ops.zeros(self.position_ids.shape, dtype=mindspore.int64)

    def construct(
        self,
        input_ids=None,
        input_shape_ids=None,
        input_pronunciation_ids=None,
        token_type_ids=None,
        position_ids=None,
        inputs_embeds=None,
        past_key_values_length=0,
    ):
        if input_ids is not None:
            input_shape = input_ids.shape
        else:
            input_shape = inputs_embeds.shape[:-1]

        seq_length = input_shape[1]

        if position_ids is None:
            position_ids = self.position_ids[
                :, past_key_values_length : seq_length + past_key_values_length
            ]

        # Setting the token_type_ids to the registered buffer in constructor where it is all zeros, which usually occurs
        # when its auto-generated, registered buffer helps users when tracing the model without passing token_type_ids, solves
        # issue #5664
        if token_type_ids is None:
            if hasattr(self, "token_type_ids"):
                buffered_token_type_ids = self.token_type_ids[:, :seq_length]
                buffered_token_type_ids_expanded = buffered_token_type_ids.broadcast_to(
                    (input_shape[0], seq_length)
                )
                token_type_ids = buffered_token_type_ids_expanded
            else:
                token_type_ids = ops.zeros(input_shape, dtype=mindspore.int64)

        if self.map_inputs_layer is None:
            if inputs_embeds is None:
                inputs_embeds = self.word_embeddings(input_ids)
            token_type_embeddings = self.token_type_embeddings(token_type_ids)
            embeddings = inputs_embeds + token_type_embeddings
            if self.position_embedding_type == "absolute":
                position_embeddings = self.position_embeddings(position_ids)
                embeddings += position_embeddings
            embeddings = self.LayerNorm(embeddings)
            embeddings = self.dropout(embeddings)

            denominator = 1
            embedding_in = embeddings
            if self.enable_shape and input_shape_ids is not None:
                embedding_shape = self.shape_embed(input_shape_ids)
                embedding_in += embedding_shape
                denominator += 1
            if self.enable_pronunciation and input_pronunciation_ids is not None:
                embedding_pronunciation = self.pronunciation_embed(
                    input_pronunciation_ids
                )
                embedding_in += embedding_pronunciation
                denominator += 1

            embedding_in /= denominator
            return embedding_in
        else:
            if inputs_embeds is None:
                inputs_embeds = self.word_embeddings(input_ids)  # embedding_word

            embedding_in = inputs_embeds
            if self.enable_shape:
                if input_shape_ids is None:
                    input_shape_ids = ops.zeros(input_shape, dtype=mindspore.int64)
                embedding_shape = self.shape_embed(input_shape_ids)
                embedding_in = ops.cat((embedding_in, embedding_shape), -1)
            if self.enable_pronunciation:
                if input_pronunciation_ids is None:
                    input_pronunciation_ids = ops.zeros(
                        input_shape, dtype=mindspore.int64
                    )
                embedding_pronunciation = self.pronunciation_embed(
                    input_pronunciation_ids
                )
                embedding_in = ops.cat((embedding_in, embedding_pronunciation), -1)

            embedding_in = self.map_inputs_layer(
                embedding_in
            )  # batch_size * seq_len * hidden_dim

            token_type_embeddings = self.token_type_embeddings(token_type_ids)
            embedding_in += token_type_embeddings
            if self.position_embedding_type == "absolute":
                position_embeddings = self.position_embeddings(position_ids)
                embedding_in += position_embeddings

            embedding_in = self.LayerNorm(embedding_in)
            embedding_in = self.dropout(embedding_in)
            return embedding_in


# Copied from transformers.models.bert.modeling_bert.BertSelfAttention with Bert->RoCBert
class RoCBertSelfAttention(nn.Cell):
    def __init__(self, config, position_embedding_type=None):
        super().__init__()
        if config.hidden_size % config.num_attention_heads != 0 and not hasattr(
            config, "embedding_size"
        ):
            raise ValueError(
                f"The hidden size ({config.hidden_size}) is not a multiple of the number of attention "
                f"heads ({config.num_attention_heads})"
            )

        self.num_attention_heads = config.num_attention_heads
        self.attention_head_size = int(config.hidden_size / config.num_attention_heads)
        self.all_head_size = self.num_attention_heads * self.attention_head_size

        self.query = nn.Dense(config.hidden_size, self.all_head_size)
        self.key = nn.Dense(config.hidden_size, self.all_head_size)
        self.value = nn.Dense(config.hidden_size, self.all_head_size)

        self.dropout = nn.Dropout(p=config.attention_probs_dropout_prob)
        self.position_embedding_type = position_embedding_type or getattr(
            config, "position_embedding_type", "absolute"
        )
        if self.position_embedding_type in ("relative_key", "relative_key_query"):
            self.max_position_embeddings = config.max_position_embeddings
            self.distance_embedding = nn.Embedding(
                2 * config.max_position_embeddings - 1, self.attention_head_size
            )

        self.is_decoder = config.is_decoder

    def transpose_for_scores(self, x: mindspore.Tensor) -> mindspore.Tensor:
        new_x_shape = x.shape[:-1] + (
            self.num_attention_heads,
            self.attention_head_size,
        )
        x = x.view(new_x_shape)
        return x.permute(0, 2, 1, 3)

    def construct(
        self,
        hidden_states: mindspore.Tensor,
        attention_mask: Optional[mindspore.Tensor] = None,
        head_mask: Optional[mindspore.Tensor] = None,
        encoder_hidden_states: Optional[mindspore.Tensor] = None,
        encoder_attention_mask: Optional[mindspore.Tensor] = None,
        past_key_value: Optional[Tuple[Tuple[mindspore.Tensor]]] = None,
        output_attentions: Optional[bool] = False,
    ) -> Tuple[mindspore.Tensor]:
        mixed_query_layer = self.query(hidden_states)

        # If this is instantiated as a cross-attention module, the keys
        # and values come from an encoder; the attention mask needs to be
        # such that the encoder's padding tokens are not attended to.
        is_cross_attention = encoder_hidden_states is not None

        if is_cross_attention and past_key_value is not None:
            # reuse k,v, cross_attentions
            key_layer = past_key_value[0]
            value_layer = past_key_value[1]
            attention_mask = encoder_attention_mask
        elif is_cross_attention:
            key_layer = self.transpose_for_scores(self.key(encoder_hidden_states))
            value_layer = self.transpose_for_scores(self.value(encoder_hidden_states))
            attention_mask = encoder_attention_mask
        elif past_key_value is not None:
            key_layer = self.transpose_for_scores(self.key(hidden_states))
            value_layer = self.transpose_for_scores(self.value(hidden_states))
            key_layer = ops.cat([past_key_value[0], key_layer], axis=2)
            value_layer = ops.cat([past_key_value[1], value_layer], axis=2)
        else:
            key_layer = self.transpose_for_scores(self.key(hidden_states))
            value_layer = self.transpose_for_scores(self.value(hidden_states))

        query_layer = self.transpose_for_scores(mixed_query_layer)

        use_cache = past_key_value is not None
        if self.is_decoder:
            # if cross_attention save Tuple(mindspore.Tensor, mindspore.Tensor) of all cross attention key/value_states.
            # Further calls to cross_attention layer can then reuse all cross-attention
            # key/value_states (first "if" case)
            # if uni-directional self-attention (decoder) save Tuple(mindspore.Tensor, mindspore.Tensor) of
            # all previous decoder key/value_states. Further calls to uni-directional self-attention
            # can concat previous decoder key/value_states to current projected key/value_states (third "elif" case)
            # if encoder bi-directional self-attention `past_key_value` is always `None`
            past_key_value = (key_layer, value_layer)

        # Take the dot product between "query" and "key" to get the raw attention scores.
        attention_scores = ops.matmul(query_layer, key_layer.swapaxes(-1, -2))

        if self.position_embedding_type in ("relative_key", "relative_key_query"):
            query_length, key_length = query_layer.shape[2], key_layer.shape[2]
            if use_cache:
                position_ids_l = mindspore.tensor(
                    key_length - 1, dtype=mindspore.int64
                ).view(-1, 1)
            else:
                position_ids_l = ops.arange(query_length, dtype=mindspore.int64).view(
                    -1, 1
                )
            position_ids_r = ops.arange(key_length, dtype=mindspore.int64).view(1, -1)
            distance = position_ids_l - position_ids_r

            positional_embedding = self.distance_embedding(
                distance + self.max_position_embeddings - 1
            )
            positional_embedding = positional_embedding.to(
                dtype=query_layer.dtype
            )  # fp16 compatibility

            if self.position_embedding_type == "relative_key":
                relative_position_scores = ops.einsum(
                    "bhld,lrd->bhlr", query_layer, positional_embedding
                )
                attention_scores = attention_scores + relative_position_scores
            elif self.position_embedding_type == "relative_key_query":
                relative_position_scores_query = ops.einsum(
                    "bhld,lrd->bhlr", query_layer, positional_embedding
                )
                relative_position_scores_key = ops.einsum(
                    "bhrd,lrd->bhlr", key_layer, positional_embedding
                )
                attention_scores = (
                    attention_scores
                    + relative_position_scores_query
                    + relative_position_scores_key
                )

        attention_scores = attention_scores / math.sqrt(self.attention_head_size)
        if attention_mask is not None:
            # Apply the attention mask is (precomputed for all layers in RoCBertModel forward() function)
            attention_scores = attention_scores + attention_mask

        # Normalize the attention scores to probabilities.
        attention_probs = ops.softmax(attention_scores, axis=-1)

        # This is actually dropping out entire tokens to attend to, which might
        # seem a bit unusual, but is taken from the original Transformer paper.
        attention_probs = self.dropout(attention_probs)

        # Mask heads if we want to
        if head_mask is not None:
            attention_probs = attention_probs * head_mask

        context_layer = ops.matmul(attention_probs, value_layer)

        context_layer = context_layer.permute(0, 2, 1, 3)
        new_context_layer_shape = context_layer.shape[:-2] + (self.all_head_size,)
        context_layer = context_layer.view(new_context_layer_shape)

        outputs = (
            (context_layer, attention_probs) if output_attentions else (context_layer,)
        )

        if self.is_decoder:
            outputs = outputs + (past_key_value,)
        return outputs


# Copied from transformers.models.bert.modeling_bert.BertSelfOutput with Bert->RoCBert
class RoCBertSelfOutput(nn.Cell):
    def __init__(self, config):
        super().__init__()
        self.dense = nn.Dense(config.hidden_size, config.hidden_size)
        self.LayerNorm = nn.LayerNorm(
            [config.hidden_size], epsilon=config.layer_norm_eps
        )
        self.dropout = nn.Dropout(p=config.hidden_dropout_prob)

    def construct(
        self, hidden_states: mindspore.Tensor, input_tensor: mindspore.Tensor
    ) -> mindspore.Tensor:
        hidden_states = self.dense(hidden_states)
        hidden_states = self.dropout(hidden_states)
        hidden_states = self.LayerNorm(hidden_states + input_tensor)
        return hidden_states


ROC_BERT_SELF_ATTENTION_CLASSES = {
    "eager": RoCBertSelfAttention,
}


# Copied from transformers.models.bert.modeling_bert.BertAttention with Bert->RoCBert,BERT->ROC_BERT
class RoCBertAttention(nn.Cell):
    def __init__(self, config, position_embedding_type=None):
        super().__init__()
        self.self = ROC_BERT_SELF_ATTENTION_CLASSES[config._attn_implementation](
            config, position_embedding_type=position_embedding_type
        )
        self.output = RoCBertSelfOutput(config)
        self.pruned_heads = set()

    def prune_heads(self, heads):
        if len(heads) == 0:
            return
        heads, index = find_pruneable_heads_and_indices(
            heads,
            self.self.num_attention_heads,
            self.self.attention_head_size,
            self.pruned_heads,
        )

        # Prune linear layers
        self.self.query = prune_linear_layer(self.self.query, index)
        self.self.key = prune_linear_layer(self.self.key, index)
        self.self.value = prune_linear_layer(self.self.value, index)
        self.output.dense = prune_linear_layer(self.output.dense, index, axis=1)

        # Update hyper params and store pruned heads
        self.self.num_attention_heads = self.self.num_attention_heads - len(heads)
        self.self.all_head_size = (
            self.self.attention_head_size * self.self.num_attention_heads
        )
        self.pruned_heads = self.pruned_heads.union(heads)

    def construct(
        self,
        hidden_states: mindspore.Tensor,
        attention_mask: Optional[mindspore.Tensor] = None,
        head_mask: Optional[mindspore.Tensor] = None,
        encoder_hidden_states: Optional[mindspore.Tensor] = None,
        encoder_attention_mask: Optional[mindspore.Tensor] = None,
        past_key_value: Optional[Tuple[Tuple[mindspore.Tensor]]] = None,
        output_attentions: Optional[bool] = False,
    ) -> Tuple[mindspore.Tensor]:
        self_outputs = self.self(
            hidden_states,
            attention_mask,
            head_mask,
            encoder_hidden_states,
            encoder_attention_mask,
            past_key_value,
            output_attentions,
        )
        attention_output = self.output(self_outputs[0], hidden_states)
        outputs = (attention_output,) + self_outputs[
            1:
        ]  # add attentions if we output them
        return outputs


# Copied from transformers.models.bert.modeling_bert.BertIntermediate with Bert->RoCBert
class RoCBertIntermediate(nn.Cell):
    def __init__(self, config):
        super().__init__()
        self.dense = nn.Dense(config.hidden_size, config.intermediate_size)
        if isinstance(config.hidden_act, str):
            self.intermediate_act_fn = ACT2FN[config.hidden_act]
        else:
            self.intermediate_act_fn = config.hidden_act

    def construct(self, hidden_states: mindspore.Tensor) -> mindspore.Tensor:
        hidden_states = self.dense(hidden_states)
        hidden_states = self.intermediate_act_fn(hidden_states)
        return hidden_states


# Copied from transformers.models.bert.modeling_bert.BertOutput with Bert->RoCBert
class RoCBertOutput(nn.Cell):
    def __init__(self, config):
        super().__init__()
        self.dense = nn.Dense(config.intermediate_size, config.hidden_size)
        self.LayerNorm = nn.LayerNorm(
            [config.hidden_size], epsilon=config.layer_norm_eps
        )
        self.dropout = nn.Dropout(p=config.hidden_dropout_prob)

    def construct(
        self, hidden_states: mindspore.Tensor, input_tensor: mindspore.Tensor
    ) -> mindspore.Tensor:
        hidden_states = self.dense(hidden_states)
        hidden_states = self.dropout(hidden_states)
        hidden_states = self.LayerNorm(hidden_states + input_tensor)
        return hidden_states


# Copied from transformers.models.bert.modeling_bert.BertLayer with Bert->RoCBert
class RoCBertLayer(nn.Cell):
    def __init__(self, config):
        super().__init__()
        self.chunk_size_feed_forward = config.chunk_size_feed_forward
        self.seq_len_dim = 1
        self.attention = RoCBertAttention(config)
        self.is_decoder = config.is_decoder
        self.add_cross_attention = config.add_cross_attention
        if self.add_cross_attention:
            if not self.is_decoder:
                raise ValueError(
                    f"{self} should be used as a decoder model if cross attention is added"
                )
            self.crossattention = RoCBertAttention(
                config, position_embedding_type="absolute"
            )
        self.intermediate = RoCBertIntermediate(config)
        self.output = RoCBertOutput(config)

    def construct(
        self,
        hidden_states: mindspore.Tensor,
        attention_mask: Optional[mindspore.Tensor] = None,
        head_mask: Optional[mindspore.Tensor] = None,
        encoder_hidden_states: Optional[mindspore.Tensor] = None,
        encoder_attention_mask: Optional[mindspore.Tensor] = None,
        past_key_value: Optional[Tuple[Tuple[mindspore.Tensor]]] = None,
        output_attentions: Optional[bool] = False,
    ) -> Tuple[mindspore.Tensor]:
        # decoder uni-directional self-attention cached key/values tuple is at positions 1,2
        self_attn_past_key_value = (
            past_key_value[:2] if past_key_value is not None else None
        )
        self_attention_outputs = self.attention(
            hidden_states,
            attention_mask,
            head_mask,
            output_attentions=output_attentions,
            past_key_value=self_attn_past_key_value,
        )
        attention_output = self_attention_outputs[0]

        # if decoder, the last output is tuple of self-attn cache
        if self.is_decoder:
            outputs = self_attention_outputs[1:-1]
            present_key_value = self_attention_outputs[-1]
        else:
            outputs = self_attention_outputs[
                1:
            ]  # add self attentions if we output attention weights

        cross_attn_present_key_value = None
        if self.is_decoder and encoder_hidden_states is not None:
            if not hasattr(self, "crossattention"):
                raise ValueError(
                    f"If `encoder_hidden_states` are passed, {self} has to be instantiated with cross-attention layers"
                    " by setting `config.add_cross_attention=True`"
                )

            # cross_attn cached key/values tuple is at positions 3,4 of past_key_value tuple
            cross_attn_past_key_value = (
                past_key_value[-2:] if past_key_value is not None else None
            )
            cross_attention_outputs = self.crossattention(
                attention_output,
                attention_mask,
                head_mask,
                encoder_hidden_states,
                encoder_attention_mask,
                cross_attn_past_key_value,
                output_attentions,
            )
            attention_output = cross_attention_outputs[0]
            outputs = (
                outputs + cross_attention_outputs[1:-1]
            )  # add cross attentions if we output attention weights

            # add cross-attn cache to positions 3,4 of present_key_value tuple
            cross_attn_present_key_value = cross_attention_outputs[-1]
            present_key_value = present_key_value + cross_attn_present_key_value

        layer_output = apply_chunking_to_forward(
            self.feed_forward_chunk,
            self.chunk_size_feed_forward,
            self.seq_len_dim,
            attention_output,
        )
        outputs = (layer_output,) + outputs

        # if decoder, return the attn key/values as the last output
        if self.is_decoder:
            outputs = outputs + (present_key_value,)

        return outputs

    def feed_forward_chunk(self, attention_output):
        intermediate_output = self.intermediate(attention_output)
        layer_output = self.output(intermediate_output, attention_output)
        return layer_output


# Copied from transformers.models.bert.modeling_bert.BertEncoder with Bert->RoCBert
class RoCBertEncoder(nn.Cell):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.layer = nn.CellList(
            [RoCBertLayer(config) for _ in range(config.num_hidden_layers)]
        )
        self.gradient_checkpointing = False

    def construct(
        self,
        hidden_states: mindspore.Tensor,
        attention_mask: Optional[mindspore.Tensor] = None,
        head_mask: Optional[mindspore.Tensor] = None,
        encoder_hidden_states: Optional[mindspore.Tensor] = None,
        encoder_attention_mask: Optional[mindspore.Tensor] = None,
        past_key_values: Optional[Tuple[Tuple[mindspore.Tensor]]] = None,
        use_cache: Optional[bool] = None,
        output_attentions: Optional[bool] = False,
        output_hidden_states: Optional[bool] = False,
        return_dict: Optional[bool] = True,
    ) -> Union[Tuple[mindspore.Tensor], BaseModelOutputWithPastAndCrossAttentions]:
        all_hidden_states = () if output_hidden_states else None
        all_self_attentions = () if output_attentions else None
        all_cross_attentions = (
            () if output_attentions and self.config.add_cross_attention else None
        )

        if self.gradient_checkpointing and self.training:
            if use_cache:
                logger.warning_once(
                    "`use_cache=True` is incompatible with gradient checkpointing. Setting `use_cache=False`..."
                )
                use_cache = False

        next_decoder_cache = () if use_cache else None
        for i, layer_module in enumerate(self.layer):
            if output_hidden_states:
                all_hidden_states = all_hidden_states + (hidden_states,)

            layer_head_mask = head_mask[i] if head_mask is not None else None
            past_key_value = past_key_values[i] if past_key_values is not None else None

            if self.gradient_checkpointing and self.training:
                layer_outputs = self._gradient_checkpointing_func(
                    layer_module.__call__,
                    hidden_states,
                    attention_mask,
                    layer_head_mask,
                    encoder_hidden_states,
                    encoder_attention_mask,
                    past_key_value,
                    output_attentions,
                )
            else:
                layer_outputs = layer_module(
                    hidden_states,
                    attention_mask,
                    layer_head_mask,
                    encoder_hidden_states,
                    encoder_attention_mask,
                    past_key_value,
                    output_attentions,
                )

            hidden_states = layer_outputs[0]
            if use_cache:
                next_decoder_cache += (layer_outputs[-1],)
            if output_attentions:
                all_self_attentions = all_self_attentions + (layer_outputs[1],)
                if self.config.add_cross_attention:
                    all_cross_attentions = all_cross_attentions + (layer_outputs[2],)

        if output_hidden_states:
            all_hidden_states = all_hidden_states + (hidden_states,)

        if not return_dict:
            return tuple(
                v
                for v in [
                    hidden_states,
                    next_decoder_cache,
                    all_hidden_states,
                    all_self_attentions,
                    all_cross_attentions,
                ]
                if v is not None
            )
        return BaseModelOutputWithPastAndCrossAttentions(
            last_hidden_state=hidden_states,
            past_key_values=next_decoder_cache,
            hidden_states=all_hidden_states,
            attentions=all_self_attentions,
            cross_attentions=all_cross_attentions,
        )


# Copied from transformers.models.bert.modeling_bert.BertPooler with Bert->RoCBert
class RoCBertPooler(nn.Cell):
    def __init__(self, config):
        super().__init__()
        self.dense = nn.Dense(config.hidden_size, config.hidden_size)
        self.activation = nn.Tanh()

    def construct(self, hidden_states: mindspore.Tensor) -> mindspore.Tensor:
        # We "pool" the model by simply taking the hidden state corresponding
        # to the first token.
        first_token_tensor = hidden_states[:, 0]
        pooled_output = self.dense(first_token_tensor)
        pooled_output = self.activation(pooled_output)
        return pooled_output


# Copied from transformers.models.bert.modeling_bert.BertPredictionHeadTransform with Bert->RoCBert
class RoCBertPredictionHeadTransform(nn.Cell):
    def __init__(self, config):
        super().__init__()
        self.dense = nn.Dense(config.hidden_size, config.hidden_size)
        if isinstance(config.hidden_act, str):
            self.transform_act_fn = ACT2FN[config.hidden_act]
        else:
            self.transform_act_fn = config.hidden_act
        self.LayerNorm = nn.LayerNorm(
            [config.hidden_size], epsilon=config.layer_norm_eps
        )

    def construct(self, hidden_states: mindspore.Tensor) -> mindspore.Tensor:
        hidden_states = self.dense(hidden_states)
        hidden_states = self.transform_act_fn(hidden_states)
        hidden_states = self.LayerNorm(hidden_states)
        return hidden_states


# Copied from transformers.models.bert.modeling_bert.BertLMPredictionHead with Bert->RoCBert
class RoCBertLMPredictionHead(nn.Cell):
    def __init__(self, config):
        super().__init__()
        self.transform = RoCBertPredictionHeadTransform(config)

        # The output weights are the same as the input embeddings, but there is
        # an output-only bias for each token.
        self.decoder = nn.Dense(config.hidden_size, config.vocab_size, has_bias=False)

        self.bias = mindspore.Parameter(ops.zeros(config.vocab_size))

        # Need a link between the two variables so that the bias is correctly resized with `resize_token_embeddings`
        self.decoder.bias = self.bias

    def _tie_weights(self):
        self.decoder.bias = self.bias

    def construct(self, hidden_states):
        hidden_states = self.transform(hidden_states)
        hidden_states = self.decoder(hidden_states)
        return hidden_states


# Copied from transformers.models.bert.modeling_bert.BertOnlyMLMHead with Bert->RoCBert
class RoCBertOnlyMLMHead(nn.Cell):
    def __init__(self, config):
        super().__init__()
        self.predictions = RoCBertLMPredictionHead(config)

    def construct(self, sequence_output: mindspore.Tensor) -> mindspore.Tensor:
        prediction_scores = self.predictions(sequence_output)
        return prediction_scores


class RoCBertPreTrainedModel(PreTrainedModel):
    """
    An abstract class to handle weights initialization and a simple interface for downloading and loading pretrained
    models.
    """

    config_class = RoCBertConfig
    base_model_prefix = "roc_bert"
    supports_gradient_checkpointing = True

    def _init_weights(self, cell):
        """Initialize the weights"""
        if isinstance(cell, nn.Dense):
            # Slightly different from the TF version which uses truncated_normal for initialization
            # cf https://github.com/pytorch/pytorch/pull/5617
            cell.weight.set_data(
                initializer(
                    Normal(self.config.initializer_range),
                    cell.weight.shape,
                    cell.weight.dtype,
                )
            )
            if cell.has_bias:
                cell.bias.set_data(
                    initializer("zeros", cell.bias.shape, cell.bias.dtype)
                )
        elif isinstance(cell, nn.Embedding):
            weight = np.random.normal(
                0.0, self.config.initializer_range, cell.weight.shape
            )
            if cell.padding_idx:
                weight[cell.padding_idx] = 0

            cell.weight.set_data(mindspore.Tensor(weight, cell.weight.dtype))
        elif isinstance(cell, nn.LayerNorm):
            cell.bias.set_data(initializer("zeros", cell.bias.shape, cell.bias.dtype))
            cell.weight.set_data(
                initializer("ones", cell.weight.shape, cell.weight.dtype)
            )


class RoCBertModel(RoCBertPreTrainedModel):
    """

    The model can behave as an encoder (with only self-attention) as well as a decoder, in which case a layer of
    cross-attention is added between the self-attention layers, following the architecture described in [Attention is
    all you need](https://arxiv.org/abs/1706.03762) by Ashish Vaswani, Noam Shazeer, Niki Parmar, Jakob Uszkoreit,
    Llion Jones, Aidan N. Gomez, Lukasz Kaiser and Illia Polosukhin.

    To behave as an decoder the model needs to be initialized with the `is_decoder` argument of the configuration set
    to `True`. To be used in a Seq2Seq model, the model needs to be initialized with both `is_decoder` argument and
    `add_cross_attention` set to `True`; an `encoder_hidden_states` is then expected as an input to the forward pass.
    """

    # Copied from transformers.models.clap.modeling_clap.ClapTextModel.__init__ with ClapText->RoCBert
    def __init__(self, config, add_pooling_layer=True):
        super().__init__(config)
        self.config = config

        self.embeddings = RoCBertEmbeddings(config)
        self.encoder = RoCBertEncoder(config)

        self.pooler = RoCBertPooler(config) if add_pooling_layer else None

        # Initialize weights and apply final processing
        self.post_init()

    # Copied from transformers.models.bert.modeling_bert.BertModel.get_input_embeddings
    def get_input_embeddings(self):
        return self.embeddings.word_embeddings

    # Copied from transformers.models.bert.modeling_bert.BertModel.set_input_embeddings
    def set_input_embeddings(self, value):
        self.embeddings.word_embeddings = value

    def get_pronunciation_embeddings(self):
        return self.embeddings.pronunciation_embed

    def set_pronunciation_embeddings(self, value):
        self.embeddings.pronunciation_embed = value

    def get_shape_embeddings(self):
        return self.embeddings.shape_embed

    def set_shape_embeddings(self, value):
        self.embeddings.shape_embed = value

    # Copied from transformers.models.bert.modeling_bert.BertModel._prune_heads
    def _prune_heads(self, heads_to_prune):
        """
        Prunes heads of the model. heads_to_prune: dict of {layer_num: list of heads to prune in this layer} See base
        class PreTrainedModel
        """
        for layer, heads in heads_to_prune.items():
            self.encoder.layer[layer].attention.prune_heads(heads)

    def construct(
        self,
        input_ids: Optional[mindspore.Tensor] = None,
        input_shape_ids: Optional[mindspore.Tensor] = None,
        input_pronunciation_ids: Optional[mindspore.Tensor] = None,
        attention_mask: Optional[mindspore.Tensor] = None,
        token_type_ids: Optional[mindspore.Tensor] = None,
        position_ids: Optional[mindspore.Tensor] = None,
        head_mask: Optional[mindspore.Tensor] = None,
        inputs_embeds: Optional[mindspore.Tensor] = None,
        encoder_hidden_states: Optional[mindspore.Tensor] = None,
        encoder_attention_mask: Optional[mindspore.Tensor] = None,
        past_key_values: Optional[List[mindspore.Tensor]] = None,
        use_cache: Optional[bool] = None,
        output_attentions: Optional[bool] = None,
        output_hidden_states: Optional[bool] = None,
        return_dict: Optional[bool] = None,
    ) -> Union[Tuple[mindspore.Tensor], BaseModelOutputWithPoolingAndCrossAttentions]:
        r"""
        encoder_hidden_states  (`torch.FloatTensor` of shape `(batch_size, sequence_length, hidden_size)`, *optional*):
            Sequence of hidden-states at the output of the last layer of the encoder. Used in the cross-attention if
            the model is configured as a decoder.
        encoder_attention_mask (`torch.FloatTensor` of shape `(batch_size, sequence_length)`, *optional*):
            >- Mask to avoid performing attention on the padding token indices of the encoder input. This mask is used in
                the cross-attention if the model is configured as a decoder. Mask values selected in `[0, 1]`:
            >   - 1 for tokens that are **not masked**,
            >   - 0 for tokens that are **masked**.
        past_key_values (`tuple(tuple(torch.FloatTensor))` of length `config.n_layers` with each tuple having 4 tensors of shape `(batch_size, num_heads, sequence_length - 1, embed_size_per_head)`):
            Contains precomputed key and value hidden states of the attention blocks. Can be used to speed up decoding.
            If `past_key_values` are used, the user can optionally input only the last `decoder_input_ids` (those that
            don't have their past key value states given to this model) of shape `(batch_size, 1)` instead of all
            `decoder_input_ids` of shape `(batch_size, sequence_length)`.
        use_cache (`bool`, *optional*):
            If set to `True`, `past_key_values` key value states are returned and can be used to speed up decoding (see
            `past_key_values`).
        """
        output_attentions = (
            output_attentions
            if output_attentions is not None
            else self.config.output_attentions
        )
        output_hidden_states = (
            output_hidden_states
            if output_hidden_states is not None
            else self.config.output_hidden_states
        )
        return_dict = (
            return_dict if return_dict is not None else self.config.use_return_dict
        )

        if self.config.is_decoder:
            use_cache = use_cache if use_cache is not None else self.config.use_cache
        else:
            use_cache = False

        if input_ids is not None and inputs_embeds is not None:
            raise ValueError(
                "You cannot specify both input_ids and inputs_embeds at the same time"
            )
        elif input_ids is not None:
            self.warn_if_padding_and_no_attention_mask(input_ids, attention_mask)
            input_shape = input_ids.shape
        elif inputs_embeds is not None:
            input_shape = inputs_embeds.shape[:-1]
        else:
            raise ValueError("You have to specify either input_ids or inputs_embeds")

        batch_size, seq_length = input_shape

        # past_key_values_length
        past_key_values_length = (
            past_key_values[0][0].shape[2] if past_key_values is not None else 0
        )

        if attention_mask is None:
            attention_mask = ops.ones((batch_size, seq_length + past_key_values_length))

        if token_type_ids is None:
            if hasattr(self.embeddings, "token_type_ids"):
                buffered_token_type_ids = self.embeddings.token_type_ids[:, :seq_length]
                buffered_token_type_ids_expanded = buffered_token_type_ids.broadcast_to(
                    (batch_size, seq_length)
                )
                token_type_ids = buffered_token_type_ids_expanded
            else:
                token_type_ids = ops.zeros(input_shape, dtype=mindspore.int64)

        # We can provide a self-attention mask of dimensions [batch_size, from_seq_length, to_seq_length]
        # ourselves in which case we just need to make it broadcastable to all heads.
        extended_attention_mask: mindspore.Tensor = self.get_extended_attention_mask(
            attention_mask, input_shape
        )

        # If a 2D or 3D attention mask is provided for the cross-attention
        # we need to make broadcastable to [batch_size, num_heads, seq_length, seq_length]
        if self.config.is_decoder and encoder_hidden_states is not None:
            encoder_batch_size, encoder_sequence_length, _ = encoder_hidden_states.shape
            encoder_hidden_shape = (encoder_batch_size, encoder_sequence_length)
            if encoder_attention_mask is None:
                encoder_attention_mask = ops.ones(encoder_hidden_shape)
            encoder_extended_attention_mask = self.invert_attention_mask(
                encoder_attention_mask
            )
        else:
            encoder_extended_attention_mask = None

        # Prepare head mask if needed
        # 1.0 in head_mask indicate we keep the head
        # attention_probs has shape bsz x n_heads x N x N
        # input head_mask has shape [num_heads] or [num_hidden_layers x num_heads]
        # and head_mask is converted to shape [num_hidden_layers x batch x num_heads x seq_length x seq_length]
        head_mask = self.get_head_mask(head_mask, self.config.num_hidden_layers)

        embedding_output = self.embeddings(
            input_ids=input_ids,
            input_shape_ids=input_shape_ids,
            input_pronunciation_ids=input_pronunciation_ids,
            position_ids=position_ids,
            token_type_ids=token_type_ids,
            inputs_embeds=inputs_embeds,
            past_key_values_length=past_key_values_length,
        )
        encoder_outputs = self.encoder(
            embedding_output,
            attention_mask=extended_attention_mask,
            head_mask=head_mask,
            encoder_hidden_states=encoder_hidden_states,
            encoder_attention_mask=encoder_extended_attention_mask,
            past_key_values=past_key_values,
            use_cache=use_cache,
            output_attentions=output_attentions,
            output_hidden_states=output_hidden_states,
            return_dict=return_dict,
        )
        sequence_output = encoder_outputs[0]
        pooled_output = (
            self.pooler(sequence_output) if self.pooler is not None else None
        )

        if not return_dict:
            return (sequence_output, pooled_output) + encoder_outputs[1:]

        return BaseModelOutputWithPoolingAndCrossAttentions(
            last_hidden_state=sequence_output,
            pooler_output=pooled_output,
            past_key_values=encoder_outputs.past_key_values,
            hidden_states=encoder_outputs.hidden_states,
            attentions=encoder_outputs.attentions,
            cross_attentions=encoder_outputs.cross_attentions,
        )


class RoCBertForPreTraining(RoCBertPreTrainedModel):
    _tied_weights_keys = [
        "cls.predictions.decoder.weight",
        "cls.predictions.decoder.bias",
    ]

    def __init__(self, config):
        super().__init__(config)

        self.roc_bert = RoCBertModel(config)
        self.cls = RoCBertOnlyMLMHead(config)

        # Initialize weights and apply final processing
        self.post_init()

    # Copied from transformers.models.bert.modeling_bert.BertForPreTraining.get_output_embeddings
    def get_output_embeddings(self):
        return self.cls.predictions.decoder

    # Copied from transformers.models.bert.modeling_bert.BertForPreTraining.set_output_embeddings
    def set_output_embeddings(self, new_embeddings):
        self.cls.predictions.decoder = new_embeddings
        self.cls.predictions.bias = new_embeddings.bias

    def construct(
        self,
        input_ids: Optional[mindspore.Tensor] = None,
        input_shape_ids: Optional[mindspore.Tensor] = None,
        input_pronunciation_ids: Optional[mindspore.Tensor] = None,
        attention_mask: Optional[mindspore.Tensor] = None,
        token_type_ids: Optional[mindspore.Tensor] = None,
        attack_input_ids: Optional[mindspore.Tensor] = None,
        attack_input_shape_ids: Optional[mindspore.Tensor] = None,
        attack_input_pronunciation_ids: Optional[mindspore.Tensor] = None,
        attack_attention_mask: Optional[mindspore.Tensor] = None,
        attack_token_type_ids: Optional[mindspore.Tensor] = None,
        position_ids: Optional[mindspore.Tensor] = None,
        head_mask: Optional[mindspore.Tensor] = None,
        inputs_embeds: Optional[mindspore.Tensor] = None,
        labels_input_ids: Optional[mindspore.Tensor] = None,
        labels_input_shape_ids: Optional[mindspore.Tensor] = None,
        labels_input_pronunciation_ids: Optional[mindspore.Tensor] = None,
        labels_attention_mask: Optional[mindspore.Tensor] = None,
        labels_token_type_ids: Optional[mindspore.Tensor] = None,
        output_attentions: Optional[bool] = None,
        output_hidden_states: Optional[bool] = None,
        return_dict: Optional[bool] = None,
        **kwargs,
    ) -> Union[Tuple[mindspore.Tensor], MaskedLMOutput]:
        r"""
        Args:
            attack_input_ids (`torch.LongTensor` of shape `(batch_size, sequence_length)`, *optional*):
                attack sample ids for computing the contrastive loss. Indices should be in `[-100, 0, ...,
                config.vocab_size]` (see `input_ids` docstring) Tokens with indices set to `-100` are ignored (masked),
                the loss is only computed for the tokens with labels in `[0, ..., config.vocab_size]`
            attack_input_shape_ids (`torch.LongTensor` of shape `(batch_size, sequence_length)`, *optional*):
                attack sample shape ids for computing the contrastive loss. Indices should be in `[-100, 0, ...,
                config.vocab_size]` (see `input_ids` docstring) Tokens with indices set to `-100` are ignored (masked),
                the loss is only computed for the tokens with labels in `[0, ..., config.vocab_size]`
            attack_input_pronunciation_ids (`torch.LongTensor` of shape `(batch_size, sequence_length)`, *optional*):
                attack sample pronunciation ids for computing the contrastive loss. Indices should be in `[-100, 0,
                ..., config.vocab_size]` (see `input_ids` docstring) Tokens with indices set to `-100` are ignored
                (masked), the loss is only computed for the tokens with labels in `[0, ..., config.vocab_size]`
            labels_input_ids (`torch.LongTensor` of shape `(batch_size, sequence_length)`, *optional*):
                target ids for computing the contrastive loss and masked_lm_loss . Indices should be in `[-100, 0, ...,
                config.vocab_size]` (see `input_ids` docstring) Tokens with indices set to `-100` are ignored (masked),
                the loss is only computed for the tokens with labels in `[0, ..., config.vocab_size]`
            labels_input_shape_ids (`torch.LongTensor` of shape `(batch_size, sequence_length)`, *optional*):
                target shape ids for computing the contrastive loss and masked_lm_loss . Indices should be in `[-100,
                0, ..., config.vocab_size]` (see `input_ids` docstring) Tokens with indices set to `-100` are ignored
                (masked), the loss is only computed for the tokens with labels in `[0, ..., config.vocab_size]`
            labels_input_pronunciation_ids (`torch.LongTensor` of shape `(batch_size, sequence_length)`, *optional*):
                target pronunciation ids for computing the contrastive loss and masked_lm_loss . Indices should be in
                `[-100, 0, ..., config.vocab_size]` (see `input_ids` docstring) Tokens with indices set to `-100` are
                 ignored (masked), the loss is only computed for the tokens with labels in `[0, ...,
                 config.vocab_size]`

            kwargs (`Dict[str, any]`, optional, defaults to *{}*):
                Used to hide legacy arguments that have been deprecated.

        Returns:
            `Union[Tuple[mindspore.Tensor], MaskedLMOutput]`

        Example:
            ```python
            >>> from transformers import AutoTokenizer, RoCBertForPreTraining
            >>> import torch

            >>> tokenizer = AutoTokenizer.from_pretrained("weiweishi/roc-bert-base-zh")
            >>> model = RoCBertForPreTraining.from_pretrained("weiweishi/roc-bert-base-zh")

            >>> inputs = tokenizer("你好，很高兴认识你", return_tensors="pt")
            >>> attack_inputs = {}
            >>> for key in list(inputs.keys()):
            ...     attack_inputs[f"attack_{key}"] = inputs[key]
            >>> label_inputs = {}
            >>> for key in list(inputs.keys()):
            ...     label_inputs[f"labels_{key}"] = inputs[key]

            >>> inputs.update(label_inputs)
            >>> inputs.update(attack_inputs)
            >>> outputs = model(**inputs)

            >>> logits = outputs.logits
            >>> logits.shape
            torch.Size([1, 11, 21128])
            ```
        """
        return_dict = (
            return_dict if return_dict is not None else self.config.use_return_dict
        )

        outputs = self.roc_bert(
            input_ids,
            input_shape_ids=input_shape_ids,
            input_pronunciation_ids=input_pronunciation_ids,
            attention_mask=attention_mask,
            token_type_ids=token_type_ids,
            position_ids=position_ids,
            head_mask=head_mask,
            inputs_embeds=inputs_embeds,
            output_attentions=output_attentions,
            output_hidden_states=output_hidden_states,
            return_dict=return_dict,
        )

        sequence_output, pooled_output = outputs[:2]
        prediction_scores = self.cls(sequence_output)

        loss = None
        if labels_input_ids is not None:
            # -100 index = padding token
            masked_lm_loss = ops.cross_entropy(
                prediction_scores.view(-1, self.config.vocab_size),
                labels_input_ids.view(-1),
            )

            if attack_input_ids is not None:
                batch_size, _ = labels_input_ids.shape

                target_inputs = labels_input_ids
                target_inputs[target_inputs == -100] = self.config.pad_token_id

                labels_output = self.roc_bert(
                    target_inputs,
                    input_shape_ids=labels_input_shape_ids,
                    input_pronunciation_ids=labels_input_pronunciation_ids,
                    attention_mask=labels_attention_mask,
                    token_type_ids=labels_token_type_ids,
                    return_dict=return_dict,
                )
                attack_output = self.roc_bert(
                    attack_input_ids,
                    input_shape_ids=attack_input_shape_ids,
                    input_pronunciation_ids=attack_input_pronunciation_ids,
                    attention_mask=attack_attention_mask,
                    token_type_ids=attack_token_type_ids,
                    return_dict=return_dict,
                )

                labels_pooled_output = labels_output[1]
                attack_pooled_output = attack_output[1]

                pooled_output_norm = ops.norm(pooled_output, dim=-1, keepdim=True)
                labels_pooled_output_norm = ops.norm(
                    labels_pooled_output, dim=-1, keepdim=True
                )
                attack_pooled_output_norm = ops.norm(
                    attack_pooled_output, dim=-1, keepdim=True
                )

                sim_matrix = ops.matmul(
                    pooled_output_norm, attack_pooled_output_norm.T
                )  # batch_size * hidden_dim
                sim_matrix_target = ops.matmul(
                    labels_pooled_output_norm, attack_pooled_output_norm.T
                )
                batch_labels = mindspore.Tensor(list(range(batch_size)))
                contrastive_loss = (
                    ops.cross_entropy(
                        100 * sim_matrix.view(batch_size, -1),
                        batch_labels.reshape(-1, 1),
                    )
                    + ops.cross_entropy(
                        100 * sim_matrix_target.view(batch_size, -1),
                        batch_labels.reshape(-1, 1),
                    )
                ) / 2

                loss = contrastive_loss + masked_lm_loss
            else:
                loss = masked_lm_loss

        if not return_dict:
            output = (prediction_scores,) + outputs[2:]
            return ((loss,) + output) if loss is not None else output

        return MaskedLMOutput(
            loss=loss,
            logits=prediction_scores,
            hidden_states=outputs.hidden_states,
            attentions=outputs.attentions,
        )


class RoCBertForMaskedLM(RoCBertPreTrainedModel):
    _tied_weights_keys = [
        "cls.predictions.decoder.weight",
        "cls.predictions.decoder.bias",
    ]

    # Copied from transformers.models.bert.modeling_bert.BertForMaskedLM.__init__ with Bert->RoCBert,bert->roc_bert
    def __init__(self, config):
        super().__init__(config)

        if config.is_decoder:
            logger.warning(
                "If you want to use `RoCBertForMaskedLM` make sure `config.is_decoder=False` for "
                "bi-directional self-attention."
            )

        self.roc_bert = RoCBertModel(config, add_pooling_layer=False)
        self.cls = RoCBertOnlyMLMHead(config)

        # Initialize weights and apply final processing
        self.post_init()

    # Copied from transformers.models.bert.modeling_bert.BertForMaskedLM.get_output_embeddings
    def get_output_embeddings(self):
        return self.cls.predictions.decoder

    # Copied from transformers.models.bert.modeling_bert.BertForMaskedLM.set_output_embeddings
    def set_output_embeddings(self, new_embeddings):
        self.cls.predictions.decoder = new_embeddings
        self.cls.predictions.bias = new_embeddings.bias

    def construct(
        self,
        input_ids: Optional[mindspore.Tensor] = None,
        input_shape_ids: Optional[mindspore.Tensor] = None,
        input_pronunciation_ids: Optional[mindspore.Tensor] = None,
        attention_mask: Optional[mindspore.Tensor] = None,
        token_type_ids: Optional[mindspore.Tensor] = None,
        position_ids: Optional[mindspore.Tensor] = None,
        head_mask: Optional[mindspore.Tensor] = None,
        inputs_embeds: Optional[mindspore.Tensor] = None,
        encoder_hidden_states: Optional[mindspore.Tensor] = None,
        encoder_attention_mask: Optional[mindspore.Tensor] = None,
        labels: Optional[mindspore.Tensor] = None,
        output_attentions: Optional[bool] = None,
        output_hidden_states: Optional[bool] = None,
        return_dict: Optional[bool] = None,
    ) -> Union[Tuple[mindspore.Tensor], MaskedLMOutput]:
        r"""
        Args:
            labels (`torch.LongTensor` of shape `(batch_size, sequence_length)`, *optional*):
                Labels for computing the masked language modeling loss. Indices should be in `[-100, 0, ...,
                config.vocab_size]` (see `input_ids` docstring) Tokens with indices set to `-100` are ignored (masked), the
                loss is only computed for the tokens with labels in `[0, ..., config.vocab_size]`.

        Example:
            ```python
            >>> from transformers import AutoTokenizer, RoCBertForMaskedLM
            >>> import torch

            >>> tokenizer = AutoTokenizer.from_pretrained("weiweishi/roc-bert-base-zh")
            >>> model = RoCBertForMaskedLM.from_pretrained("weiweishi/roc-bert-base-zh")

            >>> inputs = tokenizer("法国是首都[MASK].", return_tensors="pt")

            >>> with torch.no_grad():
            ...     logits = model(**inputs).logits

            >>> # retrieve index of {mask}
            >>> mask_token_index = (inputs.input_ids == tokenizer.mask_token_id)[0].nonzero(as_tuple=True)[0]

            >>> predicted_token_id = logits[0, mask_token_index].argmax(axis=-1)
            >>> tokenizer.decode(predicted_token_id)
            '.'
            ```
        """
        return_dict = (
            return_dict if return_dict is not None else self.config.use_return_dict
        )

        outputs = self.roc_bert(
            input_ids,
            input_shape_ids=input_shape_ids,
            input_pronunciation_ids=input_pronunciation_ids,
            attention_mask=attention_mask,
            token_type_ids=token_type_ids,
            position_ids=position_ids,
            head_mask=head_mask,
            inputs_embeds=inputs_embeds,
            encoder_hidden_states=encoder_hidden_states,
            encoder_attention_mask=encoder_attention_mask,
            output_attentions=output_attentions,
            output_hidden_states=output_hidden_states,
            return_dict=return_dict,
        )

        sequence_output = outputs[0]
        prediction_scores = self.cls(sequence_output)

        masked_lm_loss = None
        if labels is not None:
            masked_lm_loss = ops.cross_entropy(
                prediction_scores.view(-1, self.config.vocab_size), labels.view(-1)
            )

        if not return_dict:
            output = (prediction_scores,) + outputs[2:]
            return (
                ((masked_lm_loss,) + output) if masked_lm_loss is not None else output
            )

        return MaskedLMOutput(
            loss=masked_lm_loss,
            logits=prediction_scores,
            hidden_states=outputs.hidden_states,
            attentions=outputs.attentions,
        )

    def prepare_inputs_for_generation(
        self,
        input_ids,
        input_shape_ids=None,
        input_pronunciation_ids=None,
        attention_mask=None,
        **model_kwargs,
    ):
        input_shape = input_ids.shape
        effective_batch_size = input_shape[0]

        #  add a dummy token
        if self.config.pad_token_id is None:
            raise ValueError("The PAD token should be defined for generation")

        attention_mask = ops.cat(
            [attention_mask, attention_mask.new_zeros(attention_mask.shape[0], 1)],
            axis=-1,
        )
        dummy_token = ops.full(
            (effective_batch_size, 1), self.config.pad_token_id, dtype=mindspore.int64
        )
        input_ids = ops.cat([input_ids, dummy_token], axis=1)
        if input_shape_ids is not None:
            input_shape_ids = ops.cat([input_shape_ids, dummy_token], axis=1)
        if input_pronunciation_ids is not None:
            input_pronunciation_ids = ops.cat(
                [input_pronunciation_ids, dummy_token], axis=1
            )

        return {
            "input_ids": input_ids,
            "input_shape_ids": input_shape_ids,
            "input_pronunciation_ids": input_pronunciation_ids,
            "attention_mask": attention_mask,
        }


class RoCBertForCausalLM(RoCBertPreTrainedModel):
    _tied_weights_keys = [
        "cls.predictions.decoder.weight",
        "cls.predictions.decoder.bias",
    ]

    # Copied from transformers.models.bert.modeling_bert.BertLMHeadModel.__init__ with BertLMHeadModel->RoCBertForCausalLM,Bert->RoCBert,bert->roc_bert
    def __init__(self, config):
        super().__init__(config)

        if not config.is_decoder:
            logger.warning(
                "If you want to use `RoCRoCBertForCausalLM` as a standalone, add `is_decoder=True.`"
            )

        self.roc_bert = RoCBertModel(config, add_pooling_layer=False)
        self.cls = RoCBertOnlyMLMHead(config)

        # Initialize weights and apply final processing
        self.post_init()

    # Copied from transformers.models.bert.modeling_bert.BertLMHeadModel.get_output_embeddings
    def get_output_embeddings(self):
        return self.cls.predictions.decoder

    # Copied from transformers.models.bert.modeling_bert.BertLMHeadModel.set_output_embeddings
    def set_output_embeddings(self, new_embeddings):
        self.cls.predictions.decoder = new_embeddings
        self.cls.predictions.bias = new_embeddings.bias

    def construct(
        self,
        input_ids: Optional[mindspore.Tensor] = None,
        input_shape_ids: Optional[mindspore.Tensor] = None,
        input_pronunciation_ids: Optional[mindspore.Tensor] = None,
        attention_mask: Optional[mindspore.Tensor] = None,
        token_type_ids: Optional[mindspore.Tensor] = None,
        position_ids: Optional[mindspore.Tensor] = None,
        inputs_embeds: Optional[mindspore.Tensor] = None,
        encoder_hidden_states: Optional[mindspore.Tensor] = None,
        encoder_attention_mask: Optional[mindspore.Tensor] = None,
        head_mask: Optional[mindspore.Tensor] = None,
        past_key_values: Optional[List[mindspore.Tensor]] = None,
        labels: Optional[mindspore.Tensor] = None,
        use_cache: Optional[bool] = None,
        output_attentions: Optional[bool] = None,
        output_hidden_states: Optional[bool] = None,
        return_dict: Optional[bool] = None,
    ) -> Union[Tuple[mindspore.Tensor], CausalLMOutputWithCrossAttentions]:
        r"""
        Args:
            encoder_hidden_states  (`torch.FloatTensor` of shape `(batch_size, sequence_length, hidden_size)`, *optional*):
                Sequence of hidden-states at the output of the last layer of the encoder. Used in the cross-attention if
                the model is configured as a decoder.
            encoder_attention_mask (`torch.FloatTensor` of shape `(batch_size, sequence_length)`, *optional*):
                >- Mask to avoid performing attention on the padding token indices of the encoder input. This mask is used in
                    the cross-attention if the model is configured as a decoder. Mask values selected in `[0, 1]`:
                >   - 1 for tokens that are **not masked**,
                >   - 0 for tokens that are **masked**.
            past_key_values (`tuple(tuple(torch.FloatTensor))`, *optional*, returned when `use_cache=True` is passed or when `config.use_cache=True`):
                Tuple of `tuple(torch.FloatTensor)` of length `config.n_layers`, with each tuple having 2 tensors of shape
                `(batch_size, num_heads, sequence_length, embed_size_per_head)`) and 2 additional tensors of shape
                `(batch_size, num_heads, encoder_sequence_length, embed_size_per_head)`. The two additional tensors are
                only required when the model is used as a decoder in a Sequence to Sequence model.

                Contains pre-computed hidden-states (key and values in the self-attention blocks and in the cross-attention
                blocks) that can be used (see `past_key_values` input) to speed up sequential decoding.

                If `past_key_values` are used, the user can optionally input only the last `decoder_input_ids` (those that
                don't have their past key value states given to this model) of shape `(batch_size, 1)` instead of all
                `decoder_input_ids` of shape `(batch_size, sequence_length)`.
            labels (`torch.LongTensor` of shape `(batch_size, sequence_length)`, *optional*):
                Labels for computing the left-to-right language modeling loss (next word prediction). Indices should be in
                `[-100, 0, ..., config.vocab_size]` (see `input_ids` docstring) Tokens with indices set to `-100` are
                ignored (masked), the loss is only computed for the tokens with labels n `[0, ..., config.vocab_size]`.
            use_cache (`bool`, *optional*):
                If set to `True`, `past_key_values` key value states are returned and can be used to speed up decoding (see
                `past_key_values`).

        Returns:
            `Union[Tuple[mindspore.Tensor], CausalLMOutputWithCrossAttentions]`

        Example:
            ```python
            >>> from transformers import AutoTokenizer, RoCBertForCausalLM, RoCBertConfig
            >>> import torch

            >>> tokenizer = AutoTokenizer.from_pretrained("weiweishi/roc-bert-base-zh")
            >>> config = RoCBertConfig.from_pretrained("weiweishi/roc-bert-base-zh")
            >>> config.is_decoder = True
            >>> model = RoCBertForCausalLM.from_pretrained("weiweishi/roc-bert-base-zh", config=config)

            >>> inputs = tokenizer("你好，很高兴认识你", return_tensors="pt")
            >>> outputs = model(**inputs)

            >>> prediction_logits = outputs.logits
            ```
        """
        return_dict = (
            return_dict if return_dict is not None else self.config.use_return_dict
        )

        outputs = self.roc_bert(
            input_ids,
            input_shape_ids=input_shape_ids,
            input_pronunciation_ids=input_pronunciation_ids,
            attention_mask=attention_mask,
            token_type_ids=token_type_ids,
            position_ids=position_ids,
            head_mask=head_mask,
            inputs_embeds=inputs_embeds,
            encoder_hidden_states=encoder_hidden_states,
            encoder_attention_mask=encoder_attention_mask,
            past_key_values=past_key_values,
            use_cache=use_cache,
            output_attentions=output_attentions,
            output_hidden_states=output_hidden_states,
            return_dict=return_dict,
        )

        sequence_output = outputs[0]
        prediction_scores = self.cls(sequence_output)

        lm_loss = None
        if labels is not None:
            # we are doing next-token prediction; shift prediction scores and input ids by one
            shifted_prediction_scores = prediction_scores[:, :-1, :]
            labels = labels[:, 1:]
            lm_loss = ops.cross_entropy(
                shifted_prediction_scores.view(-1, self.config.vocab_size),
                labels.view(-1),
            )

        if not return_dict:
            output = (prediction_scores,) + outputs[2:]
            return ((lm_loss,) + output) if lm_loss is not None else output

        return CausalLMOutputWithCrossAttentions(
            loss=lm_loss,
            logits=prediction_scores,
            past_key_values=outputs.past_key_values,
            hidden_states=outputs.hidden_states,
            attentions=outputs.attentions,
            cross_attentions=outputs.cross_attentions,
        )

    def prepare_inputs_for_generation(
        self,
        input_ids,
        input_shape_ids=None,
        input_pronunciation_ids=None,
        past_key_values=None,
        attention_mask=None,
        **model_kwargs,
    ):
        input_shape = input_ids.shape

        # if model is used as a decoder in encoder-decoder model, the decoder attention mask is created on the fly
        if attention_mask is None:
            attention_mask = input_ids.new_ones(input_shape)

        # cut decoder_input_ids if past_key_values is used
        if past_key_values is not None:
            past_length = past_key_values[0][0].shape[2]

            # Some generation methods already pass only the last input ID
            if input_ids.shape[1] > past_length:
                remove_prefix_length = past_length
            else:
                # Default to old behavior: keep only final ID
                remove_prefix_length = input_ids.shape[1] - 1

            input_ids = input_ids[:, remove_prefix_length:]
            if input_shape_ids is not None:
                input_shape_ids = input_shape_ids[:, -1:]
            if input_pronunciation_ids is not None:
                input_pronunciation_ids = input_pronunciation_ids[:, -1:]

        return {
            "input_ids": input_ids,
            "input_shape_ids": input_shape_ids,
            "input_pronunciation_ids": input_pronunciation_ids,
            "attention_mask": attention_mask,
            "past_key_values": past_key_values,
        }

    # Copied from transformers.models.bert.modeling_bert.BertLMHeadModel._reorder_cache
    def _reorder_cache(self, past_key_values, beam_idx):
        reordered_past = ()
        for layer_past in past_key_values:
            reordered_past += (
                tuple(
                    past_state.index_select(0, beam_idx) for past_state in layer_past
                ),
            )
        return reordered_past


class RoCBertForSequenceClassification(RoCBertPreTrainedModel):
    # Copied from transformers.models.bert.modeling_bert.BertForSequenceClassification.__init__ with Bert->RoCBert,bert->roc_bert
    def __init__(self, config):
        super().__init__(config)
        self.num_labels = config.num_labels
        self.config = config

        self.roc_bert = RoCBertModel(config)
        classifier_dropout = (
            config.classifier_dropout
            if config.classifier_dropout is not None
            else config.hidden_dropout_prob
        )
        self.dropout = nn.Dropout(classifier_dropout)
        self.classifier = nn.Dense(config.hidden_size, config.num_labels)

        # Initialize weights and apply final processing
        self.post_init()

    def construct(
        self,
        input_ids: Optional[mindspore.Tensor] = None,
        input_shape_ids: Optional[mindspore.Tensor] = None,
        input_pronunciation_ids: Optional[mindspore.Tensor] = None,
        attention_mask: Optional[mindspore.Tensor] = None,
        token_type_ids: Optional[mindspore.Tensor] = None,
        position_ids: Optional[mindspore.Tensor] = None,
        head_mask: Optional[mindspore.Tensor] = None,
        inputs_embeds: Optional[mindspore.Tensor] = None,
        labels: Optional[mindspore.Tensor] = None,
        output_attentions: Optional[bool] = None,
        output_hidden_states: Optional[bool] = None,
        return_dict: Optional[bool] = None,
    ) -> Union[Tuple[mindspore.Tensor], SequenceClassifierOutput]:
        r"""
        Args:
            labels (`torch.LongTensor` of shape `(batch_size,)`, *optional*):
                Labels for computing the sequence classification/regression loss. Indices should be in `[0, ...,
                config.num_labels - 1]`. If `config.num_labels == 1` a regression loss is computed (Mean-Square loss), If
                `config.num_labels > 1` a classification loss is computed (Cross-Entropy).
        """
        return_dict = (
            return_dict if return_dict is not None else self.config.use_return_dict
        )

        outputs = self.roc_bert(
            input_ids,
            input_shape_ids=input_shape_ids,
            input_pronunciation_ids=input_pronunciation_ids,
            attention_mask=attention_mask,
            token_type_ids=token_type_ids,
            position_ids=position_ids,
            head_mask=head_mask,
            inputs_embeds=inputs_embeds,
            output_attentions=output_attentions,
            output_hidden_states=output_hidden_states,
            return_dict=return_dict,
        )

        pooled_output = outputs[1]

        pooled_output = self.dropout(pooled_output)
        logits = self.classifier(pooled_output)

        loss = None
        if labels is not None:
            if self.config.problem_type is None:
                if self.num_labels == 1:
                    self.config.problem_type = "regression"
                elif self.num_labels > 1 and labels.dtype in (
                    mindspore.int32,
                    mindspore.int64,
                ):
                    self.config.problem_type = "single_label_classification"
                else:
                    self.config.problem_type = "multi_label_classification"

            if self.config.problem_type == "regression":
                if self.num_labels == 1:
                    loss = ops.mse_loss(logits.squeeze(), labels.squeeze())
                else:
                    loss = ops.mse_loss(logits, labels)
            elif self.config.problem_type == "single_label_classification":
                loss = ops.cross_entropy(
                    logits.view(-1, self.num_labels), labels.view(-1)
                )
            elif self.config.problem_type == "multi_label_classification":
                loss = ops.binary_cross_entropy_with_logits(logits, labels)
        if not return_dict:
            output = (logits,) + outputs[2:]
            return ((loss,) + output) if loss is not None else output

        return SequenceClassifierOutput(
            loss=loss,
            logits=logits,
            hidden_states=outputs.hidden_states,
            attentions=outputs.attentions,
        )


class RoCBertForMultipleChoice(RoCBertPreTrainedModel):
    # Copied from transformers.models.bert.modeling_bert.BertForMultipleChoice.__init__ with Bert->RoCBert,bert->roc_bert
    def __init__(self, config):
        super().__init__(config)

        self.roc_bert = RoCBertModel(config)
        classifier_dropout = (
            config.classifier_dropout
            if config.classifier_dropout is not None
            else config.hidden_dropout_prob
        )
        self.dropout = nn.Dropout(p=classifier_dropout)
        self.classifier = nn.Dense(config.hidden_size, 1)

        # Initialize weights and apply final processing
        self.post_init()

    def construct(
        self,
        input_ids: Optional[mindspore.Tensor] = None,
        input_shape_ids: Optional[mindspore.Tensor] = None,
        input_pronunciation_ids: Optional[mindspore.Tensor] = None,
        attention_mask: Optional[mindspore.Tensor] = None,
        token_type_ids: Optional[mindspore.Tensor] = None,
        position_ids: Optional[mindspore.Tensor] = None,
        head_mask: Optional[mindspore.Tensor] = None,
        inputs_embeds: Optional[mindspore.Tensor] = None,
        labels: Optional[mindspore.Tensor] = None,
        output_attentions: Optional[bool] = None,
        output_hidden_states: Optional[bool] = None,
        return_dict: Optional[bool] = None,
    ) -> Union[Tuple[mindspore.Tensor], MultipleChoiceModelOutput]:
        r"""
        Args:
            labels (`torch.LongTensor` of shape `(batch_size,)`, *optional*):
                Labels for computing the multiple choice classification loss. Indices should be in `[0, ...,
                num_choices-1]` where `num_choices` is the size of the second dimension of the input tensors. (See
                `input_ids` above)
        """
        return_dict = (
            return_dict if return_dict is not None else self.config.use_return_dict
        )
        num_choices = (
            input_ids.shape[1] if input_ids is not None else inputs_embeds.shape[1]
        )

        input_ids = (
            input_ids.view(-1, input_ids.shape[-1]) if input_ids is not None else None
        )
        input_shape_ids = (
            input_shape_ids.view(-1, input_shape_ids.shape[-1])
            if input_shape_ids is not None
            else None
        )
        input_pronunciation_ids = (
            input_pronunciation_ids.view(-1, input_pronunciation_ids.shape[-1])
            if input_pronunciation_ids is not None
            else None
        )
        attention_mask = (
            attention_mask.view(-1, attention_mask.shape[-1])
            if attention_mask is not None
            else None
        )
        token_type_ids = (
            token_type_ids.view(-1, token_type_ids.shape[-1])
            if token_type_ids is not None
            else None
        )
        position_ids = (
            position_ids.view(-1, position_ids.shape[-1])
            if position_ids is not None
            else None
        )
        inputs_embeds = (
            inputs_embeds.view(-1, inputs_embeds.shape[-2], inputs_embeds.shape[-1])
            if inputs_embeds is not None
            else None
        )

        outputs = self.roc_bert(
            input_ids,
            input_shape_ids=input_shape_ids,
            input_pronunciation_ids=input_pronunciation_ids,
            attention_mask=attention_mask,
            token_type_ids=token_type_ids,
            position_ids=position_ids,
            head_mask=head_mask,
            inputs_embeds=inputs_embeds,
            output_attentions=output_attentions,
            output_hidden_states=output_hidden_states,
            return_dict=return_dict,
        )

        pooled_output = outputs[1]

        pooled_output = self.dropout(pooled_output)
        logits = self.classifier(pooled_output)
        reshaped_logits = logits.view(-1, num_choices)

        loss = None
        if labels is not None:
            loss = ops.cross_entropy(reshaped_logits, labels)

        if not return_dict:
            output = (reshaped_logits,) + outputs[2:]
            return ((loss,) + output) if loss is not None else output

        return MultipleChoiceModelOutput(
            loss=loss,
            logits=reshaped_logits,
            hidden_states=outputs.hidden_states,
            attentions=outputs.attentions,
        )


class RoCBertForTokenClassification(RoCBertPreTrainedModel):
    # Copied from transformers.models.bert.modeling_bert.BertForTokenClassification.__init__ with Bert->RoCBert,bert->roc_bert
    def __init__(self, config):
        super().__init__(config)
        self.num_labels = config.num_labels

        self.roc_bert = RoCBertModel(config, add_pooling_layer=False)
        classifier_dropout = (
            config.classifier_dropout
            if config.classifier_dropout is not None
            else config.hidden_dropout_prob
        )
        self.dropout = nn.Dropout(p=classifier_dropout)
        self.classifier = nn.Dense(config.hidden_size, config.num_labels)

        # Initialize weights and apply final processing
        self.post_init()

    def construct(
        self,
        input_ids: Optional[mindspore.Tensor] = None,
        input_shape_ids: Optional[mindspore.Tensor] = None,
        input_pronunciation_ids: Optional[mindspore.Tensor] = None,
        attention_mask: Optional[mindspore.Tensor] = None,
        token_type_ids: Optional[mindspore.Tensor] = None,
        position_ids: Optional[mindspore.Tensor] = None,
        head_mask: Optional[mindspore.Tensor] = None,
        inputs_embeds: Optional[mindspore.Tensor] = None,
        labels: Optional[mindspore.Tensor] = None,
        output_attentions: Optional[bool] = None,
        output_hidden_states: Optional[bool] = None,
        return_dict: Optional[bool] = None,
    ) -> Union[Tuple, TokenClassifierOutput]:
        r"""
        Args:
            labels (`torch.LongTensor` of shape `(batch_size, sequence_length)`, *optional*):
                Labels for computing the token classification loss. Indices should be in `[0, ..., config.num_labels - 1]`.
        """
        return_dict = (
            return_dict if return_dict is not None else self.config.use_return_dict
        )

        outputs = self.roc_bert(
            input_ids,
            input_shape_ids=input_shape_ids,
            input_pronunciation_ids=input_pronunciation_ids,
            attention_mask=attention_mask,
            token_type_ids=token_type_ids,
            position_ids=position_ids,
            head_mask=head_mask,
            inputs_embeds=inputs_embeds,
            output_attentions=output_attentions,
            output_hidden_states=output_hidden_states,
            return_dict=return_dict,
        )

        sequence_output = outputs[0]

        sequence_output = self.dropout(sequence_output)
        logits = self.classifier(sequence_output)

        loss = None
        if labels is not None:
            loss = ops.cross_entropy(logits.view(-1, self.num_labels), labels.view(-1))

        if not return_dict:
            output = (logits,) + outputs[2:]
            return ((loss,) + output) if loss is not None else output

        return TokenClassifierOutput(
            loss=loss,
            logits=logits,
            hidden_states=outputs.hidden_states,
            attentions=outputs.attentions,
        )


class RoCBertForQuestionAnswering(RoCBertPreTrainedModel):
    # Copied from transformers.models.bert.modeling_bert.BertForQuestionAnswering.__init__ with Bert->RoCBert,bert->roc_bert
    def __init__(self, config):
        super().__init__(config)
        self.num_labels = config.num_labels

        self.roc_bert = RoCBertModel(config, add_pooling_layer=False)
        self.qa_outputs = nn.Dense(config.hidden_size, config.num_labels)

        # Initialize weights and apply final processing
        self.post_init()

    def construct(
        self,
        input_ids: Optional[mindspore.Tensor] = None,
        input_shape_ids: Optional[mindspore.Tensor] = None,
        input_pronunciation_ids: Optional[mindspore.Tensor] = None,
        attention_mask: Optional[mindspore.Tensor] = None,
        token_type_ids: Optional[mindspore.Tensor] = None,
        position_ids: Optional[mindspore.Tensor] = None,
        head_mask: Optional[mindspore.Tensor] = None,
        inputs_embeds: Optional[mindspore.Tensor] = None,
        start_positions: Optional[mindspore.Tensor] = None,
        end_positions: Optional[mindspore.Tensor] = None,
        output_attentions: Optional[bool] = None,
        output_hidden_states: Optional[bool] = None,
        return_dict: Optional[bool] = None,
    ) -> Union[Tuple[mindspore.Tensor], QuestionAnsweringModelOutput]:
        r"""
        Args:
            start_positions (`torch.LongTensor` of shape `(batch_size,)`, *optional*):
                Labels for position (index) of the start of the labelled span for computing the token classification loss.
                Positions are clamped to the length of the sequence (`sequence_length`). Position outside of the sequence
                are not taken into account for computing the loss.
            end_positions (`torch.LongTensor` of shape `(batch_size,)`, *optional*):
                Labels for position (index) of the end of the labelled span for computing the token classification loss.
                Positions are clamped to the length of the sequence (`sequence_length`). Position outside of the sequence
                are not taken into account for computing the loss.
        """
        return_dict = (
            return_dict if return_dict is not None else self.config.use_return_dict
        )

        outputs = self.roc_bert(
            input_ids,
            input_shape_ids=input_shape_ids,
            input_pronunciation_ids=input_pronunciation_ids,
            attention_mask=attention_mask,
            token_type_ids=token_type_ids,
            position_ids=position_ids,
            head_mask=head_mask,
            inputs_embeds=inputs_embeds,
            output_attentions=output_attentions,
            output_hidden_states=output_hidden_states,
            return_dict=return_dict,
        )

        sequence_output = outputs[0]

        logits = self.qa_outputs(sequence_output)
        start_logits, end_logits = logits.split(1, axis=-1)
        start_logits = start_logits.squeeze(-1)
        end_logits = end_logits.squeeze(-1)

        total_loss = None
        if start_positions is not None and end_positions is not None:
            # If we are on multi-GPU, split add a dimension
            if len(start_positions.shape) > 1:
                start_positions = start_positions.squeeze(-1)
            if len(end_positions.shape) > 1:
                end_positions = end_positions.squeeze(-1)
            # sometimes the start/end positions are outside our model inputs, we ignore these terms
            ignored_index = start_logits.shape[1]
            start_positions = start_positions.clamp(0, ignored_index)
            end_positions = end_positions.clamp(0, ignored_index)

            start_loss = ops.cross_entropy(
                start_logits, start_positions, ignore_index=ignored_index
            )
            end_loss = ops.cross_entropy(
                end_logits, end_positions, ignore_index=ignored_index
            )
            total_loss = (start_loss + end_loss) / 2

        if not return_dict:
            output = (start_logits, end_logits) + outputs[2:]
            return ((total_loss,) + output) if total_loss is not None else output

        return QuestionAnsweringModelOutput(
            loss=total_loss,
            start_logits=start_logits,
            end_logits=end_logits,
            hidden_states=outputs.hidden_states,
            attentions=outputs.attentions,
        )


__all__ = [
    "RoCBertForCausalLM",
    "RoCBertForMaskedLM",
    "RoCBertForMultipleChoice",
    "RoCBertForPreTraining",
    "RoCBertForQuestionAnswering",
    "RoCBertForSequenceClassification",
    "RoCBertForTokenClassification",
    "RoCBertLayer",
    "RoCBertModel",
    "RoCBertPreTrainedModel",
]
