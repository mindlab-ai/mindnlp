# coding=utf-8
# Copyright 2021 The Facebook Inc. and The HuggingFace Inc. team. All rights reserved.
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
"""Tokenization class for Wav2Vec2."""

import json
import os
import sys
import warnings
from dataclasses import dataclass
from itertools import groupby
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
from mindspore import Tensor

from ...tokenization_utils import PreTrainedTokenizer
from ...tokenization_utils_base import AddedToken, BatchEncoding
from ....utils import (
    ModelOutput,
    PaddingStrategy,
    TensorType,
    logging,
    to_py_obj,
)

__all__ = [
    'Wav2Vec2CTCTokenizer',
    'Wav2Vec2Tokenizer',
]

logger = logging.get_logger(__name__)

VOCAB_FILES_NAMES = {
    "vocab_file": "vocab.json",
    "tokenizer_config_file": "tokenizer_config.json",
}

PRETRAINED_VOCAB_FILES_MAP = {
    "vocab_file": {
        "facebook/wav2vec2-base-960h": "https://hf-mirror.com/facebook/wav2vec2-base-960h/resolve/main/vocab.json",
    },
    "tokenizer_config_file": {
        "facebook/wav2vec2-base-960h": (
            "https://hf-mirror.com/facebook/wav2vec2-base-960h/resolve/main/tokenizer_config.json"
        ),
    },
}

# Wav2Vec2 has no max input length
PRETRAINED_POSITIONAL_EMBEDDINGS_SIZES = {"facebook/wav2vec2-base-960h": sys.maxsize}

ListOfDict = List[Dict[str, Union[int, str]]]


@dataclass
class Wav2Vec2CTCTokenizerOutput(ModelOutput):
    """
    Output type of [` Wav2Vec2CTCTokenizer`], with transcription.

    Args:
        text (list of `str` or `str`):
            Decoded logits in text from. Usually the speech transcription.
        char_offsets (list of `List[Dict[str, Union[int, str]]]` or `List[Dict[str, Union[int, str]]]`):
            Offsets of the decoded characters. In combination with sampling rate and model downsampling rate char
            offsets can be used to compute time stamps for each charater. Total logit score of the beam associated with
            produced text.
        word_offsets (list of `List[Dict[str, Union[int, str]]]` or `List[Dict[str, Union[int, str]]]`):
            Offsets of the decoded words. In combination with sampling rate and model downsampling rate word offsets
            can be used to compute time stamps for each word.
    """
    text: Union[List[str], str]
    char_offsets: Union[List[ListOfDict], ListOfDict] = None
    word_offsets: Union[List[ListOfDict], ListOfDict] = None


class Wav2Vec2CTCTokenizer(PreTrainedTokenizer):

    """
    Constructs a Wav2Vec2CTC tokenizer.

    This tokenizer inherits from [`PreTrainedTokenizer`] which contains some of the main methods. Users should refer to
    the superclass for more information regarding such methods.

    Args:
        vocab_file (`str`):
            File containing the vocabulary.
        bos_token (`str`, *optional*, defaults to `"<s>"`):
            The beginning of sentence token.
        eos_token (`str`, *optional*, defaults to `"</s>"`):
            The end of sentence token.
        unk_token (`str`, *optional*, defaults to `"<unk>"`):
            The unknown token. A token that is not in the vocabulary cannot be converted to an ID and is set to be this
            token instead.
        pad_token (`str`, *optional*, defaults to `"<pad>"`):
            The token used for padding, for example when batching sequences of different lengths.
        word_delimiter_token (`str`, *optional*, defaults to `"|"`):
            The token used for defining the end of a word.
        do_lower_case (`bool`, *optional*, defaults to `False`):
            Whether or not to accept lowercase input and lowercase the output when decoding.
        target_lang (`str`, *optional*):
            A target language the tokenizer should set by default. `target_lang` has to be defined for multi-lingual,
            nested vocabulary such as [facebook/mms-1b-all](https://hf-mirror.com/facebook/mms-1b-all).

        **kwargs
            Additional keyword arguments passed along to [`PreTrainedTokenizer`]
    """
    vocab_files_names = VOCAB_FILES_NAMES
    pretrained_vocab_files_map = PRETRAINED_VOCAB_FILES_MAP
    max_model_input_sizes = PRETRAINED_POSITIONAL_EMBEDDINGS_SIZES
    model_input_names = ["input_ids", "attention_mask"]

    def __init__(
        self,
        vocab_file,
        bos_token="<s>",
        eos_token="</s>",
        unk_token="<unk>",
        pad_token="<pad>",
        word_delimiter_token="|",
        replace_word_delimiter_char=" ",
        do_lower_case=False,
        target_lang=None,
        **kwargs,
    ):
        """
        Initializes a new instance of the Wav2Vec2CTCTokenizer class.
        
        Args:
            self (Wav2Vec2CTCTokenizer): The instance of the Wav2Vec2CTCTokenizer class.
            vocab_file (str): The path to the vocabulary file.
            bos_token (str, optional): The beginning of sentence token. Default is '<s>'.
            eos_token (str, optional): The end of sentence token. Default is '</s>'.
            unk_token (str, optional): The unknown token. Default is '<unk>'.
            pad_token (str, optional): The padding token. Default is '<pad>'.
            word_delimiter_token (str, optional): The word delimiter token. Default is '|'.
            replace_word_delimiter_char (str, optional): The character used to replace the word delimiter. Default is ' '.
            do_lower_case (bool, optional): Whether to convert all tokens to lowercase. Default is False.
            target_lang (str, optional): The target language for encoding. Default is None.
            **kwargs: Additional keyword arguments.
        
        Returns:
            None
        
        Raises:
            None
        """
        self._word_delimiter_token = word_delimiter_token

        self.do_lower_case = do_lower_case
        self.replace_word_delimiter_char = replace_word_delimiter_char
        self.target_lang = target_lang

        with open(vocab_file, encoding="utf-8") as vocab_handle:
            self.vocab = json.load(vocab_handle)

        # if target lang is defined vocab must be a nested dict
        # with each target lang being one vocabulary
        if target_lang is not None:
            self.encoder = self.vocab[target_lang]
        else:
            self.encoder = self.vocab

        self.decoder = {v: k for k, v in self.encoder.items()}

        super().__init__(
            unk_token=unk_token,
            bos_token=bos_token,
            eos_token=eos_token,
            pad_token=pad_token,
            do_lower_case=do_lower_case,
            word_delimiter_token=word_delimiter_token,
            replace_word_delimiter_char=replace_word_delimiter_char,
            target_lang=target_lang,
            **kwargs,
        )

        # make sure that tokens made of several
        # characters are not split at tokenization
        for token in self.encoder.keys():
            if len(token) > 1:
                self.add_tokens(AddedToken(token, rstrip=True, lstrip=True, normalized=False))

    def set_target_lang(self, target_lang: str):
        """
        Set the target language of a nested multi-lingual dictionary
        """
        if self.vocab == self.encoder:
            raise ValueError(f"{self.vocab} is not a multi-lingual, nested tokenizer. Cannot set target language.")

        if target_lang not in self.vocab:
            raise ValueError(f"{target_lang} does not exist. Choose one of {', '.join(self.vocab.keys())}.")

        self.target_lang = target_lang
        self.init_kwargs["target_lang"] = target_lang
        self.encoder = self.vocab[target_lang]
        self.decoder = {v: k for k, v in self.encoder.items()}

        # make sure that tokens made of several
        # characters are not split at tokenization
        for token in self.encoder.keys():
            if len(token) > 1:
                self.add_tokens(AddedToken(token, rstrip=True, lstrip=True, normalized=False))

    @property
    def word_delimiter_token(self) -> str:
        """
        `str`: Word delimiter token. Log an error if used while not having been set.
        """
        if self._word_delimiter_token is None and self.verbose:
            logger.error("Using word_delimiter_token, but it is not set yet.")
            return None
        return str(self._word_delimiter_token)

    @property
    def word_delimiter_token_id(self) -> Optional[int]:
        """
        `Optional[int]`: Id of the word_delimiter_token in the vocabulary. Returns `None` if the token has not been
        set.
        """
        if self._word_delimiter_token is None:
            return None
        return self.convert_tokens_to_ids(self.word_delimiter_token)

    @word_delimiter_token.setter
    def word_delimiter_token(self, value):
        """
        Sets the word delimiter token for the Wav2Vec2CTCTokenizer.
        
        Args:
            self (Wav2Vec2CTCTokenizer): The instance of the Wav2Vec2CTCTokenizer class.
            value (str): The word delimiter token to be set.
        
        Returns:
            None.
        
        Raises:
            None.
        """
        self._word_delimiter_token = value

    @word_delimiter_token_id.setter
    def word_delimiter_token_id(self, value):
        """
        Sets the word delimiter token ID for the Wav2Vec2CTCTokenizer.
        
        Args:
            self (Wav2Vec2CTCTokenizer): The Wav2Vec2CTCTokenizer instance.
            value (list[int]): A list of integers representing the token IDs for word delimiters.
        
        Returns:
            None.
        
        Raises:
            TypeError: If the provided value is not a list of integers.
            ValueError: If the provided value contains invalid token IDs.
        """
        self._word_delimiter_token = self.convert_tokens_to_ids(value)

    @property
    def vocab_size(self) -> int:
        """
        Returns the size of the vocabulary used by the Wav2Vec2CTCTokenizer.
        
        Args:
            self: An instance of the Wav2Vec2CTCTokenizer class.
        
        Returns:
            int: The size of the vocabulary, which represents the total number of unique tokens in the decoder.
        
        Raises:
            None.
            
        Example:
            ```python
            >>> tokenizer = Wav2Vec2CTCTokenizer()
            >>> tokenizer.vocab_size()
            50000
            ```
        """
        return len(self.decoder)

    def get_vocab(self) -> Dict:
        """
        Returns the vocabulary used by the Wav2Vec2CTCTokenizer.

        Args:
            self (Wav2Vec2CTCTokenizer): An instance of the Wav2Vec2CTCTokenizer class.

        Returns:
            Dict: A dictionary representing the vocabulary used by the tokenizer.
                The keys are integers representing the token IDs, and the values are the corresponding tokens.

        Raises:
            None.

        This method retrieves the vocabulary used by the Wav2Vec2CTCTokenizer instance. The vocabulary is a dictionary
        that combines the encoder and added_tokens_encoder dictionaries. The encoder dictionary maps tokens to unique
        integer IDs, while the added_tokens_encoder dictionary contains additional tokens added by the user.
        The resulting vocabulary dictionary is returned.
        """
        vocab = dict(self.encoder)
        vocab.update(self.added_tokens_encoder)
        return vocab

    def _add_tokens(self, new_tokens: Union[List[str], List[AddedToken]], special_tokens: bool = False) -> int:
        """
        Add tokens to the Wav2Vec2CTCTokenizer's vocabulary.

        Args:
            self (Wav2Vec2CTCTokenizer): The instance of the Wav2Vec2CTCTokenizer class.
            new_tokens (Union[List[str], List[AddedToken]]): A list of new tokens to be added to the vocabulary.
                Each token can be either a string or an instance of AddedToken.
            special_tokens (bool, optional): A flag indicating whether the new tokens are special tokens.
                Defaults to False.

        Returns:
            int: The number of tokens added to the vocabulary.

        Raises:
            None

        This method takes a list of new tokens and adds them to the vocabulary of the Wav2Vec2CTCTokenizer.
        The new tokens can be either strings or instances of AddedToken. If a token is a string, a default AddedToken
        object will be created with the token as its text and the following default values for its attributes:
        rstrip=False, lstrip=False, normalized=False. If a token is already an instance of AddedToken,
        it will be added as is. The method then calls the super()._add_tokens() method to add the tokens to the
        vocabulary. The special_tokens flag can be used to indicate whether the new tokens are special tokens.
        """
        # Overwritten to never strip!
        to_add = []
        for token in new_tokens:
            if isinstance(token, str):
                to_add.append(AddedToken(token, rstrip=False, lstrip=False, normalized=False))
            else:
                to_add.append(token)

        return super()._add_tokens(to_add, special_tokens)

    def _tokenize(self, text, **kwargs):
        """
        Converts a string into a sequence of tokens (string), using the tokenizer.
        """
        if self.do_lower_case:
            text = text.upper()

        return list(text.replace(" ", self.word_delimiter_token))

    def _convert_token_to_id(self, token: str) -> int:
        """Converts a token (str) in an index (integer) using the vocab."""
        return self.encoder.get(token, self.encoder.get(self.unk_token))

    def _convert_id_to_token(self, index: int) -> str:
        """Converts an index (integer) in a token (str) using the vocab."""
        result = self.decoder.get(index, self.unk_token)
        return result

    def convert_tokens_to_string(
        self,
        tokens: List[str],
        group_tokens: bool = True,
        spaces_between_special_tokens: bool = False,
        output_char_offsets: bool = False,
        output_word_offsets: bool = False,
    ) -> Dict[str, Union[str, float]]:
        """
        Converts a connectionist-temporal-classification (CTC) output tokens into a single string.
        """
        if len(tokens) == 0:
            return {"text": "", "char_offsets": [], "word_offsets": []}
        # group same tokens into non-repeating tokens in CTC style decoding
        if group_tokens:
            chars, char_repetitions = zip(*((token, len(list(group_iter))) for token, group_iter in groupby(tokens)))
        else:
            chars = tokens
            char_repetitions = len(tokens) * [1]

        # filter self.pad_token which is used as CTC-blank token
        processed_chars = list(filter(lambda char: char != self.pad_token, chars))

        # replace delimiter token
        processed_chars = [
            self.replace_word_delimiter_char if char == self.word_delimiter_token else char for char in processed_chars
        ]

        # retrieve offsets
        char_offsets = word_offsets = None
        if output_char_offsets or output_word_offsets:
            char_offsets = self._compute_offsets(char_repetitions, chars, self.pad_token)

            if len(char_offsets) != len(processed_chars):
                raise ValueError(
                    f"`char_offsets`: {char_offsets} and `processed_tokens`: {processed_chars}"
                    " have to be of the same length, but are: "
                    f"`len(offsets)`: {len(char_offsets)} and `len(processed_tokens)`:"
                    f" {len(processed_chars)}"
                )

            # set tokens to correct processed token
            for i, char in enumerate(processed_chars):
                char_offsets[i]["char"] = char

            # retrieve word offsets from character offsets
            word_offsets = None
            if output_word_offsets:
                word_offsets = self._get_word_offsets(char_offsets, self.replace_word_delimiter_char)

            # don't output chars if not set to True
            if not output_char_offsets:
                char_offsets = None

        # join to string
        join_char = " " if spaces_between_special_tokens else ""
        string = join_char.join(processed_chars).strip()

        if self.do_lower_case:
            string = string.lower()

        return {"text": string, "char_offsets": char_offsets, "word_offsets": word_offsets}

    @staticmethod
    def _compute_offsets(
        char_repetitions: List[int], chars: List[str], ctc_token: int
    ) -> List[Dict[str, Union[str, int]]]:
        """
        Compute offsets for characters based on char repetitions and tokens.

        Args:
            char_repetitions (List[int]): A list of integers representing the number of repetitions for each character.
            chars (List[str]): A list of characters.
            ctc_token (int): The CTC token to be filtered out from the offsets.

        Returns:
            List[Dict[str, Union[str, int]]]: A list of dictionaries where each dictionary contains the character,
                start offset, and end offset.

        Raises:
            None
        """
        end_indices = np.asarray(char_repetitions).cumsum()
        start_indices = np.concatenate(([0], end_indices[:-1]))

        offsets = [
            {"char": t, "start_offset": s, "end_offset": e} for t, s, e in zip(chars, start_indices, end_indices)
        ]

        # filter out CTC token
        offsets = list(filter(lambda offsets: offsets["char"] != ctc_token, offsets))
        return offsets

    @staticmethod
    def _get_word_offsets(
        offsets: Dict[str, Union[str, float]], word_delimiter_char: str = " "
    ) -> Dict[str, Union[str, float]]:
        """
        Method to extract word offsets from a given set of character offsets.

        Args:
            offsets (Dict[str, Union[str, float]]): A dictionary containing character offsets with keys 'char',
                'start_offset', and 'end_offset'. The 'char' key represents the character, 'start_offset' represents
                the start offset, and 'end_offset' represents the end offset.
            word_delimiter_char (str, optional): The character used as a word delimiter. Defaults to a space character.

        Returns:
            Dict[str, Union[str, float]]: A dictionary containing word offsets with keys 'word', 'start_offset',
                and 'end_offset'. The 'word' key represents the extracted word, 'start_offset' represents the start
                offset, and 'end_offset' represents the end offset.

        Raises:
            None
        """
        word_offsets = []

        last_state = "SPACE"
        word = ""
        start_offset = 0
        end_offset = 0
        for offset in offsets:
            char = offset["char"]
            state = "SPACE" if char == word_delimiter_char else "WORD"

            if state == last_state:
                # If we are in the same state as before, we simply repeat what we've done before
                end_offset = offset["end_offset"]
                word += char
            else:
                # Switching state
                if state == "SPACE":
                    # Finishing a word
                    word_offsets.append({"word": word, "start_offset": start_offset, "end_offset": end_offset})
                else:
                    # Starting a new word
                    start_offset = offset["start_offset"]
                    end_offset = offset["end_offset"]
                    word = char

            last_state = state
        if last_state == "WORD":
            word_offsets.append({"word": word, "start_offset": start_offset, "end_offset": end_offset})

        return word_offsets

    def prepare_for_tokenization(self, text, is_split_into_words=False, **kwargs):
        """
        Prepare the input text for tokenization.

        Args:
            self (Wav2Vec2CTCTokenizer): The instance of the Wav2Vec2CTCTokenizer class.
            text (str): The input text to be prepared for tokenization.
            is_split_into_words (bool): A flag indicating whether the input text is already split into words.
                If True, the input text is expected to be split into words;
                otherwise, the input text is treated as a continuous string.
                Defaults to False.

        Returns:
            tuple: A tuple containing the prepared text and optional keyword arguments.

        Raises:
            None
        """
        if is_split_into_words:
            text = " " + text
        return (text, kwargs)

    def _decode(
        self,
        token_ids: List[int],
        skip_special_tokens: bool = False,
        clean_up_tokenization_spaces: bool = None,
        group_tokens: bool = True,
        spaces_between_special_tokens: bool = False,
        output_word_offsets: Optional[bool] = False,
        output_char_offsets: Optional[bool] = False,
    ) -> str:
        """
        special _decode function is needed for Wav2Vec2Tokenizer because added tokens should be treated exactly the
        same as tokens of the base vocabulary and therefore the function `convert_tokens_to_string` has to be called on
        the whole token list and not individually on added tokens
        """
        filtered_tokens = self.convert_ids_to_tokens(token_ids, skip_special_tokens=skip_special_tokens)

        result = []
        for token in filtered_tokens:
            if skip_special_tokens and token in self.all_special_ids:
                continue
            result.append(token)

        string_output = self.convert_tokens_to_string(
            result,
            group_tokens=group_tokens,
            spaces_between_special_tokens=spaces_between_special_tokens,
            output_word_offsets=output_word_offsets,
            output_char_offsets=output_char_offsets,
        )

        text = string_output["text"]

        clean_up_tokenization_spaces = (
            clean_up_tokenization_spaces
            if clean_up_tokenization_spaces is not None
            else self.clean_up_tokenization_spaces
        )
        if clean_up_tokenization_spaces:
            text = self.clean_up_tokenization(text)

        if output_word_offsets or output_char_offsets:
            return Wav2Vec2CTCTokenizerOutput(
                text=text,
                char_offsets=string_output["char_offsets"],
                word_offsets=string_output["word_offsets"],
            )
        else:
            return text

    # overwritten from `tokenization_utils_base.py` because tokenizer can output
    # `ModelOutput` which should not be a list for batched output and
    # because we need docs for `output_char_offsets` here
    def batch_decode(
        self,
        sequences: Union[List[int], List[List[int]], "np.ndarray", "Tensor"],
        skip_special_tokens: bool = False,
        clean_up_tokenization_spaces: bool = None,
        output_char_offsets: bool = False,
        output_word_offsets: bool = False,
        **kwargs,
    ) -> List[str]:
        """
        Convert a list of lists of token ids into a list of strings by calling decode.

        Args:
            sequences (`Union[List[int], List[List[int]], np.ndarray, torch.Tensor, tf.Tensor]`):
                List of tokenized input ids. Can be obtained using the `__call__` method.
            skip_special_tokens (`bool`, *optional*, defaults to `False`):
                Whether or not to remove special tokens in the decoding.
            clean_up_tokenization_spaces (`bool`, *optional*):
                Whether or not to clean up the tokenization spaces.
            output_char_offsets (`bool`, *optional*, defaults to `False`):
                Whether or not to output character offsets. Character offsets can be used in combination with the
                sampling rate and model downsampling rate to compute the time-stamps of transcribed characters.

                <Tip>

                Please take a look at the Example of [`~Wav2Vec2CTCTokenizer.decode`] to better understand how to make
                use of `output_char_offsets`. [`~Wav2Vec2CTCTokenizer.batch_decode`] works the same way with batched
                output.

                </Tip>

            output_word_offsets (`bool`, *optional*, defaults to `False`):
                Whether or not to output word offsets. Word offsets can be used in combination with the sampling rate
                and model downsampling rate to compute the time-stamps of transcribed words.

                <Tip>

                Please take a look at the Example of [`~Wav2Vec2CTCTokenizer.decode`] to better understand how to make
                use of `output_word_offsets`. [`~Wav2Vec2CTCTokenizer.batch_decode`] works the same way with batched
                output.

                </Tip>

            kwargs (additional keyword arguments, *optional*):
                Will be passed to the underlying model specific decode method.

        Returns:
            `List[str]` or [`~models.wav2vec2.tokenization_wav2vec2.Wav2Vec2CTCTokenizerOutput`]: The list of decoded
                sentences. Will be a [`~models.wav2vec2.tokenization_wav2vec2.Wav2Vec2CTCTokenizerOutput`] when
                `output_char_offsets == True` or `output_word_offsets == True`.
        """
        batch_decoded = [
            self.decode(
                seq,
                skip_special_tokens=skip_special_tokens,
                clean_up_tokenization_spaces=clean_up_tokenization_spaces,
                output_char_offsets=output_char_offsets,
                output_word_offsets=output_word_offsets,
                **kwargs,
            )
            for seq in sequences
        ]
        if output_char_offsets or output_word_offsets:
            # transform list of dicts to dict of lists
            return Wav2Vec2CTCTokenizerOutput({k: [d[k] for d in batch_decoded] for k in batch_decoded[0]})

        return batch_decoded

    # overwritten from `tokenization_utils_base.py` because we need docs for `output_char_offsets`
    # and `output_word_offsets` here
    def decode(
        self,
        token_ids: Union[int, List[int], "np.ndarray", "Tensor"],
        skip_special_tokens: bool = False,
        clean_up_tokenization_spaces: bool = None,
        output_char_offsets: bool = False,
        output_word_offsets: bool = False,
        **kwargs,
    ) -> str:
        """
        Converts a sequence of ids in a string, using the tokenizer and vocabulary with options to remove special
        tokens and clean up tokenization spaces.

        Similar to doing `self.convert_tokens_to_string(self.convert_ids_to_tokens(token_ids))`.

        Args:
            token_ids (`Union[int, List[int], np.ndarray, torch.Tensor, tf.Tensor]`):
                List of tokenized input ids. Can be obtained using the `__call__` method.
            skip_special_tokens (`bool`, *optional*, defaults to `False`):
                Whether or not to remove special tokens in the decoding.
            clean_up_tokenization_spaces (`bool`, *optional*):
                Whether or not to clean up the tokenization spaces.
            output_char_offsets (`bool`, *optional*, defaults to `False`):
                Whether or not to output character offsets. Character offsets can be used in combination with the
                sampling rate and model downsampling rate to compute the time-stamps of transcribed characters.

                <Tip>

                Please take a look at the example below to better understand how to make use of `output_char_offsets`.

                </Tip>

            output_word_offsets (`bool`, *optional*, defaults to `False`):
                Whether or not to output word offsets. Word offsets can be used in combination with the sampling rate
                and model downsampling rate to compute the time-stamps of transcribed words.

                <Tip>

                Please take a look at the example below to better understand how to make use of `output_word_offsets`.

                </Tip>

            kwargs (additional keyword arguments, *optional*):
                Will be passed to the underlying model specific decode method.

        Returns:
            `str` or [`~models.wav2vec2.tokenization_wav2vec2.Wav2Vec2CTCTokenizerOutput`]: The list of decoded
                sentences. Will be a [`~models.wav2vec2.tokenization_wav2vec2.Wav2Vec2CTCTokenizerOutput`] when
                `output_char_offsets == True` or `output_word_offsets == True`.

        Example:
            ```python
            >>> # Let's see how to retrieve time steps for a model
            >>> from transformers import AutoTokenizer, AutoFeatureExtractor, AutoModelForCTC
            >>> from datasets import load_dataset
            >>> import datasets
            >>> import torch
            ...
            >>> # import model, feature extractor, tokenizer
            >>> model = AutoModelForCTC.from_pretrained("facebook/wav2vec2-base-960h")
            >>> tokenizer = AutoTokenizer.from_pretrained("facebook/wav2vec2-base-960h")
            >>> feature_extractor = AutoFeatureExtractor.from_pretrained("facebook/wav2vec2-base-960h")
            ...
            >>> # load first sample of English common_voice
            >>> dataset = load_dataset("mozilla-foundation/common_voice_11_0", "en", split="train", streaming=True)
            >>> dataset = dataset.cast_column("audio", datasets.Audio(sampling_rate=16_000))
            >>> dataset_iter = iter(dataset)
            >>> sample = next(dataset_iter)
            ...
            >>> # forward sample through model to get greedily predicted transcription ids
            >>> input_values = feature_extractor(sample["audio"]["array"], return_tensors="ms").input_values
            >>> logits = model(input_values).logits[0]
            >>> pred_ids = torch.argmax(logits, axis=-1)
            ...
            >>> # retrieve word stamps (analogous commands for `output_char_offsets`)
            >>> outputs = tokenizer.decode(pred_ids, output_word_offsets=True)
            >>> # compute `time_offset` in seconds as product of downsampling ratio and sampling_rate
            >>> time_offset = model.config.inputs_to_logits_ratio / feature_extractor.sampling_rate
            ...
            >>> word_offsets = [
            ...     {
            ...         "word": d["word"],
            ...         "start_time": round(d["start_offset"] * time_offset, 2),
            ...         "end_time": round(d["end_offset"] * time_offset, 2),
            ...     }
            ...     for d in outputs.word_offsets
            ... ]
            >>> # compare word offsets with audio `en_train_0/common_voice_en_19121553.mp3` online on the dataset viewer:
            >>> # https://hf-mirror.com/datasets/mozilla-foundation/common_voice_11_0/viewer/en
            >>> word_offsets[:3]
            [{'word': 'THE', 'start_time': 0.7, 'end_time': 0.78}, {'word': 'TRICK', 'start_time': 0.88, 'end_time': 1.08}, {'word': 'APPEARS', 'start_time': 1.2, 'end_time': 1.64}]
            ```
        """
        # Convert inputs to python lists
        token_ids = to_py_obj(token_ids)

        return self._decode(
            token_ids=token_ids,
            skip_special_tokens=skip_special_tokens,
            clean_up_tokenization_spaces=clean_up_tokenization_spaces,
            output_char_offsets=output_char_offsets,
            output_word_offsets=output_word_offsets,
            **kwargs,
        )

    def save_vocabulary(self, save_directory: str, filename_prefix: Optional[str] = None) -> Tuple[str]:
        """
        Save the vocabulary to a specified directory.
        
        Args:
            self: The instance of the Wav2Vec2CTCTokenizer class.
            save_directory (str): The directory where the vocabulary will be saved.
            filename_prefix (Optional[str]): An optional prefix to be added to the filename. Defaults to None.
        
        Returns:
            Tuple[str]: A tuple containing the file path of the saved vocabulary.
        
        Raises:
            OSError: If the save_directory is not a valid directory.
        """
        if not os.path.isdir(save_directory):
            logger.error(f"Vocabulary path ({save_directory}) should be a directory")
            return
        vocab_file = os.path.join(
            save_directory, (filename_prefix + "-" if filename_prefix else "") + VOCAB_FILES_NAMES["vocab_file"]
        )

        with open(vocab_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(self.vocab, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

        return (vocab_file,)


class Wav2Vec2Tokenizer(PreTrainedTokenizer):
    """
    Constructs a Wav2Vec2 tokenizer.

    This tokenizer inherits from [`PreTrainedTokenizer`] which contains some of the main methods. Users should refer to
    the superclass for more information regarding such methods.

    Args:
        vocab_file (`str`):
            File containing the vocabulary.
        bos_token (`str`, *optional*, defaults to `"<s>"`):
            The beginning of sentence token.
        eos_token (`str`, *optional*, defaults to `"</s>"`):
            The end of sentence token.
        unk_token (`str`, *optional*, defaults to `"<unk>"`):
            The unknown token. A token that is not in the vocabulary cannot be converted to an ID and is set to be this
            token instead.
        pad_token (`str`, *optional*, defaults to `"<pad>"`):
            The token used for padding, for example when batching sequences of different lengths.
        word_delimiter_token (`str`, *optional*, defaults to `"|"`):
            The token used for defining the end of a word.
        do_lower_case (`bool`, *optional*, defaults to `False`):
            Whether or not to lowercase the output when decoding.
        do_normalize (`bool`, *optional*, defaults to `False`):
            Whether or not to zero-mean unit-variance normalize the input. Normalizing can help to significantly
            improve the performance for some models, *e.g.*,
            [wav2vec2-lv60](https://hf-mirror.com/models?search=lv60).
        return_attention_mask (`bool`, *optional*, defaults to `False`):
            Whether or not [`~Wav2Vec2Tokenizer.__call__`] should return `attention_mask`.

            <Tip>

            Wav2Vec2 models that have set `config.feat_extract_norm == "group"`, such as
            [wav2vec2-base](https://hf-mirror.com/facebook/wav2vec2-base-960h), have **not** been trained using
            `attention_mask`. For such models, `input_values` should simply be padded with 0 and no `attention_mask`
            should be passed.

            For Wav2Vec2 models that have set `config.feat_extract_norm == "layer"`, such as
            [wav2vec2-lv60](https://hf-mirror.com/facebook/wav2vec2-large-960h-lv60-self), `attention_mask` should be
            passed for batched inference.

            </Tip>

        **kwargs
            Additional keyword arguments passed along to [`PreTrainedTokenizer`]
    """
    vocab_files_names = VOCAB_FILES_NAMES
    pretrained_vocab_files_map = {
        "vocab_file": {
            "facebook/wav2vec2-base-960h": "https://hf-mirror.com/facebook/wav2vec2-base-960h/resolve/main/vocab.json"
        },
        "tokenizer_config_file": {
            "facebook/wav2vec2-base-960h": (
                "https://hf-mirror.com/facebook/wav2vec2-base-960h/resolve/main/tokenizer.json"
            ),
        },
    }
    model_input_names = ["input_values", "attention_mask"]

    def __init__(
        self,
        vocab_file,
        bos_token="<s>",
        eos_token="</s>",
        unk_token="<unk>",
        pad_token="<pad>",
        word_delimiter_token="|",
        do_lower_case=False,
        do_normalize=False,
        return_attention_mask=False,
        **kwargs,
    ):
        """
        Initializes a new instance of the Wav2Vec2Tokenizer class.
        
        Args:
            self: The instance of the class.
            vocab_file (str): The path to the vocabulary file.
            bos_token (str, optional): The beginning of sentence token. Default is '<s>'.
            eos_token (str, optional): The end of sentence token. Default is '</s>'.
            unk_token (str, optional): The unknown token. Default is '<unk>'.
            pad_token (str, optional): The padding token. Default is '<pad>'.
            word_delimiter_token (str, optional): The word delimiter token. Default is '|'.
            do_lower_case (bool, optional): Whether to convert tokens to lowercase. Default is False.
            do_normalize (bool, optional): Whether to apply text normalization. Default is False.
            return_attention_mask (bool, optional): Whether to return the attention mask. Default is False.
        
        Returns:
            None
        
        Raises:
            FutureWarning: This class is deprecated.
                Please use Wav2Vec2Processor or Wav2Vec2CTCTokenizer instead.
        """
        warnings.warn(
            "The class `Wav2Vec2Tokenizer` is deprecated. Please use"
            " `Wav2Vec2Processor` or `Wav2Vec2CTCTokenizer` instead.",
            FutureWarning,
        )

        self._word_delimiter_token = word_delimiter_token

        self.do_lower_case = do_lower_case
        self.return_attention_mask = return_attention_mask
        self.do_normalize = do_normalize

        with open(vocab_file, encoding="utf-8") as vocab_handle:
            self.encoder = json.load(vocab_handle)

        self.decoder = {v: k for k, v in self.encoder.items()}

        super().__init__(
            unk_token=unk_token,
            bos_token=bos_token,
            eos_token=eos_token,
            pad_token=pad_token,
            do_lower_case=do_lower_case,
            do_normalize=do_normalize,
            return_attention_mask=return_attention_mask,
            word_delimiter_token=word_delimiter_token,
            **kwargs,
        )

    @property
    def word_delimiter_token(self) -> str:
        """
        `str`: Padding token. Log an error if used while not having been set.
        """
        if self._word_delimiter_token is None and self.verbose:
            logger.error("Using word_delimiter_token, but it is not set yet.")
            return None
        return str(self._word_delimiter_token)

    @property
    def word_delimiter_token_id(self) -> Optional[int]:
        """
        `Optional[int]`: Id of the word_delimiter_token in the vocabulary. Returns `None` if the token has not been
        set.
        """
        if self._word_delimiter_token is None:
            return None
        return self.convert_tokens_to_ids(self.word_delimiter_token)

    @word_delimiter_token.setter
    def word_delimiter_token(self, value):
        """
        word_delimiter_token
        
        Setter method for setting the word delimiter token in the Wav2Vec2Tokenizer class.
        
        Args:
            self (Wav2Vec2Tokenizer): The instance of the Wav2Vec2Tokenizer class.
            value (str): The value to be set as the word delimiter token. Should be a string
                representing the word delimiter token.
        
        Returns:
            None.
        
        Raises:
            None.
        """
        self._word_delimiter_token = value

    @word_delimiter_token_id.setter
    def word_delimiter_token_id(self, value):
        """
        Method to set the token ID for word delimiter in the Wav2Vec2Tokenizer class.
        
        Args:
            self (Wav2Vec2Tokenizer): The instance of the Wav2Vec2Tokenizer class.
                This parameter refers to the tokenizer object itself.
            value (Union[int, List[int]]): The new token ID or list of token IDs for word delimiter.
                The value should be an integer or a list of integers representing token IDs.
                If a list is provided, the tokens will be converted to their corresponding IDs.
        
        Returns:
            None: This method does not return any value. It sets the word delimiter token ID internally.
        
        Raises:
            ValueError: If the provided value is not a valid integer or list of integers.
            TypeError: If the provided value is not of type int or list.
        """
        self._word_delimiter_token = self.convert_tokens_to_ids(value)

    def __call__(           self,
        raw_speech: Union[np.ndarray, List[float], List[np.ndarray], List[List[float]]],
        padding: Union[bool, str, PaddingStrategy] = False,
        max_length: Optional[int] = None,
        pad_to_multiple_of: Optional[int] = None,
        return_tensors: Optional[Union[str, TensorType]] = None,
        verbose: bool = True,
        **kwargs,
    ) -> BatchEncoding:
        """
        Main method to tokenize and prepare for the model one or several sequence(s) or one or several pair(s) of
        sequences.

        Args:
            raw_speech (`np.ndarray`, `List[float]`, `List[np.ndarray]`, `List[List[float]]`):
                The sequence or batch of sequences to be padded. Each sequence can be a numpy array, a list of float
                values, a list of numpy array or a list of list of float values. Must be mono channel audio, not
                stereo, i.e. single float per timestep.
        """
        is_batched_numpy = isinstance(raw_speech, np.ndarray) and len(raw_speech.shape) > 1
        if is_batched_numpy and len(raw_speech.shape) > 2:
            raise ValueError(f"Only mono-channel audio is supported for input to {self}")
        is_batched = is_batched_numpy or (
            isinstance(raw_speech, (list, tuple)) and (isinstance(raw_speech[0], (np.ndarray, tuple, list)))
        )

        # make sure input is in list format
        if is_batched and not isinstance(raw_speech[0], np.ndarray):
            raw_speech = [np.asarray(speech) for speech in raw_speech]
        elif not is_batched and not isinstance(raw_speech, np.ndarray):
            raw_speech = np.asarray(raw_speech)

        # always return batch
        if not is_batched:
            raw_speech = [raw_speech]

        # zero-mean and unit-variance normalization
        if self.do_normalize:
            raw_speech = [(x - np.mean(x)) / np.sqrt(np.var(x) + 1e-5) for x in raw_speech]

        # convert into correct format for padding
        encoded_inputs = BatchEncoding({"input_values": raw_speech})

        padded_inputs = self.pad(
            encoded_inputs,
            padding=padding,
            max_length=max_length,
            pad_to_multiple_of=pad_to_multiple_of,
            return_attention_mask=self.return_attention_mask,
            return_tensors=return_tensors,
            verbose=verbose,
        )

        return padded_inputs

    @property
    def vocab_size(self) -> int:
        """
        Method to retrieve the vocabulary size of the Wav2Vec2Tokenizer instance.
        
        Args:
            self (Wav2Vec2Tokenizer): The instance of the Wav2Vec2Tokenizer class.
                This parameter refers to the current instance of the Wav2Vec2Tokenizer class.
                It is used to access the decoder attribute to calculate the vocabulary size.
        
        Returns:
            int: An integer representing the size of the vocabulary.
                The return value corresponds to the number of elements in the decoder attribute of the instance.
        
        Raises:
            None.
        """
        return len(self.decoder)

    def get_vocab(self) -> Dict:
        """
        This method returns a vocabulary dictionary containing the encoder and added tokens encoder.
        
        Args:
            self (Wav2Vec2Tokenizer): The instance of the Wav2Vec2Tokenizer class.
            
        Returns:
            Dict: A dictionary containing the combined encoder and added tokens encoder.
        
        Raises:
            None.
        """
        return dict(self.encoder, **self.added_tokens_encoder)

    def _convert_token_to_id(self, token: str) -> int:
        """Converts a token (str) in an index (integer) using the vocab."""
        return self.encoder.get(token, self.encoder.get(self.unk_token))

    def _convert_id_to_token(self, index: int) -> str:
        """Converts an index (integer) in a token (str) using the vocab."""
        result = self.decoder.get(index, self.unk_token)
        return result

    def convert_tokens_to_string(self, tokens: List[str]) -> str:
        """
        Converts a connectionist-temporal-classification (CTC) output tokens into a single string.
        """
        # group same tokens into non-repeating tokens in CTC style decoding
        grouped_tokens = [token_group[0] for token_group in groupby(tokens)]

        # filter self.pad_token which is used as CTC-blank token
        filtered_tokens = list(filter(lambda token: token != self.pad_token, grouped_tokens))

        # replace delimiter token
        string = "".join([" " if token == self.word_delimiter_token else token for token in filtered_tokens]).strip()

        if self.do_lower_case:
            string = string.lower()

        return string

    def _decode(
        self,
        token_ids: List[int],
        skip_special_tokens: bool = False,
        clean_up_tokenization_spaces: bool = None,
        **kwargs,
    ) -> str:
        """
        special _decode function is needed for Wav2Vec2Tokenizer because added tokens should be treated exactly the
        same as tokens of the base vocabulary and therefore the function `convert_tokens_to_string` has to be called on
        the whole token list and not individually on added tokens
        """
        filtered_tokens = self.convert_ids_to_tokens(token_ids, skip_special_tokens=skip_special_tokens)

        result = []
        for token in filtered_tokens:
            if skip_special_tokens and token in self.all_special_ids:
                continue
            result.append(token)

        text = self.convert_tokens_to_string(result)

        clean_up_tokenization_spaces = (
            clean_up_tokenization_spaces
            if clean_up_tokenization_spaces is not None
            else self.clean_up_tokenization_spaces
        )
        if clean_up_tokenization_spaces:
            clean_text = self.clean_up_tokenization(text)
            return clean_text
        else:
            return text

    def save_vocabulary(self, save_directory: str, filename_prefix: Optional[str] = None) -> Tuple[str]:
        """
        Saves the vocabulary of the Wav2Vec2Tokenizer to a file.
        
        Args:
            self (Wav2Vec2Tokenizer): An instance of the Wav2Vec2Tokenizer class.
            save_directory (str): The directory where the vocabulary file will be saved.
            filename_prefix (Optional[str], optional): A prefix to be added to the filename. Defaults to None.
        
        Returns:
            Tuple[str]: A tuple containing the path to the saved vocabulary file.
        
        Raises:
            FileNotFoundError: If the specified save_directory does not exist.
            IsADirectoryError: If save_directory is not a directory.
        """
        if not os.path.isdir(save_directory):
            logger.error(f"Vocabulary path ({save_directory}) should be a directory")
            return
        vocab_file = os.path.join(
            save_directory, (filename_prefix + "-" if filename_prefix else "") + VOCAB_FILES_NAMES["vocab_file"]
        )

        with open(vocab_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(self.encoder, indent=2, sort_keys=True, ensure_ascii=False) + "\n")

        return (vocab_file,)
