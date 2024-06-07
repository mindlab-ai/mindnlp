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
"""Fast Tokenization classes for Longformer."""
import json
from typing import List, Optional, Tuple

from tokenizers import pre_tokenizers, processors

from mindnlp.utils import logging
from ...tokenization_utils_base import AddedToken, BatchEncoding
from ...tokenization_utils_fast import PreTrainedTokenizerFast
from .tokenization_longformer import LongformerTokenizer


logger = logging.get_logger(__name__)

VOCAB_FILES_NAMES = {"vocab_file": "vocab.json", "merges_file": "merges.txt", "tokenizer_file": "tokenizer.json"}

PRETRAINED_VOCAB_FILES_MAP = {
    "vocab_file": {
        "allenai/longformer-base-4096": "https://hf-mirror.com/allenai/longformer-base-4096/resolve/main/vocab.json",
        "allenai/longformer-large-4096": (
            "https://hf-mirror.com/allenai/longformer-large-4096/resolve/main/vocab.json"
        ),
        "allenai/longformer-large-4096-finetuned-triviaqa": (
            "https://hf-mirror.com/allenai/longformer-large-4096-finetuned-triviaqa/resolve/main/vocab.json"
        ),
        "allenai/longformer-base-4096-extra.pos.embd.only": (
            "https://hf-mirror.com/allenai/longformer-base-4096-extra.pos.embd.only/resolve/main/vocab.json"
        ),
        "allenai/longformer-large-4096-extra.pos.embd.only": (
            "https://hf-mirror.com/allenai/longformer-large-4096-extra.pos.embd.only/resolve/main/vocab.json"
        ),
    },
    "merges_file": {
        "allenai/longformer-base-4096": "https://hf-mirror.com/allenai/longformer-base-4096/resolve/main/merges.txt",
        "allenai/longformer-large-4096": (
            "https://hf-mirror.com/allenai/longformer-large-4096/resolve/main/merges.txt"
        ),
        "allenai/longformer-large-4096-finetuned-triviaqa": (
            "https://hf-mirror.com/allenai/longformer-large-4096-finetuned-triviaqa/resolve/main/merges.txt"
        ),
        "allenai/longformer-base-4096-extra.pos.embd.only": (
            "https://hf-mirror.com/allenai/longformer-base-4096-extra.pos.embd.only/resolve/main/merges.txt"
        ),
        "allenai/longformer-large-4096-extra.pos.embd.only": (
            "https://hf-mirror.com/allenai/longformer-large-4096-extra.pos.embd.only/resolve/main/merges.txt"
        ),
    },
    "tokenizer_file": {
        "allenai/longformer-base-4096": (
            "https://hf-mirror.com/allenai/longformer-base-4096/resolve/main/tokenizer.json"
        ),
        "allenai/longformer-large-4096": (
            "https://hf-mirror.com/allenai/longformer-large-4096/resolve/main/tokenizer.json"
        ),
        "allenai/longformer-large-4096-finetuned-triviaqa": (
            "https://hf-mirror.com/allenai/longformer-large-4096-finetuned-triviaqa/resolve/main/tokenizer.json"
        ),
        "allenai/longformer-base-4096-extra.pos.embd.only": (
            "https://hf-mirror.com/allenai/longformer-base-4096-extra.pos.embd.only/resolve/main/tokenizer.json"
        ),
        "allenai/longformer-large-4096-extra.pos.embd.only": (
            "https://hf-mirror.com/allenai/longformer-large-4096-extra.pos.embd.only/resolve/main/tokenizer.json"
        ),
    },
}

PRETRAINED_POSITIONAL_EMBEDDINGS_SIZES = {
    "allenai/longformer-base-4096": 4096,
    "allenai/longformer-large-4096": 4096,
    "allenai/longformer-large-4096-finetuned-triviaqa": 4096,
    "allenai/longformer-base-4096-extra.pos.embd.only": 4096,
    "allenai/longformer-large-4096-extra.pos.embd.only": 4096,
}


# Copied from transformers.models.roberta.tokenization_roberta_fast.RobertaTokenizerFast with roberta-base->allenai/longformer-base-4096, RoBERTa->Longformer all-casing, Roberta->Longformer
class LongformerTokenizerFast(PreTrainedTokenizerFast):
    """
    Construct a "fast" Longformer tokenizer (backed by HuggingFace's *tokenizers* library), derived from the GPT-2
    tokenizer, using byte-level Byte-Pair-Encoding.

    This tokenizer has been trained to treat spaces like parts of the tokens (a bit like sentencepiece) so a word will
    be encoded differently whether it is at the beginning of the sentence (without space) or not:
        ```python
        >>> from transformers import LongformerTokenizerFast

        >>> tokenizer = LongformerTokenizerFast.from_pretrained("allenai/longformer-base-4096")
        >>> tokenizer("Hello world")["input_ids"]
        [0, 31414, 232, 2]

        >>> tokenizer(" Hello world")["input_ids"]
        [0, 20920, 232, 2]
        ```

    You can get around that behavior by passing `add_prefix_space=True` when instantiating this tokenizer or when you
    call it on some text, but since the model was not pretrained this way, it might yield a decrease in performance.

    <Tip>

    When used with `is_split_into_words=True`, this tokenizer needs to be instantiated with `add_prefix_space=True`.

    </Tip>

    This tokenizer inherits from [`PreTrainedTokenizerFast`] which contains most of the main methods. Users should
    refer to this superclass for more information regarding those methods.

    Args:
        vocab_file (`str`):
            Path to the vocabulary file.
        merges_file (`str`):
            Path to the merges file.
        errors (`str`, *optional*, defaults to `"replace"`):
            Paradigm to follow when decoding bytes to UTF-8. See
            [bytes.decode](https://docs.python.org/3/library/stdtypes.html#bytes.decode) for more information.
        bos_token (`str`, *optional*, defaults to `"<s>"`):
            The beginning of sequence token that was used during pretraining. Can be used a sequence classifier token.

            <Tip>

            When building a sequence using special tokens, this is not the token that is used for the beginning of
            sequence. The token used is the `cls_token`.

            </Tip>

        eos_token (`str`, *optional*, defaults to `"</s>"`):
            The end of sequence token.

            <Tip>

            When building a sequence using special tokens, this is not the token that is used for the end of sequence.
            The token used is the `sep_token`.

            </Tip>

        sep_token (`str`, *optional*, defaults to `"</s>"`):
            The separator token, which is used when building a sequence from multiple sequences, e.g. two sequences for
            sequence classification or for a text and a question for question answering. It is also used as the last
            token of a sequence built with special tokens.
        cls_token (`str`, *optional*, defaults to `"<s>"`):
            The classifier token which is used when doing sequence classification (classification of the whole sequence
            instead of per-token classification). It is the first token of the sequence when built with special tokens.
        unk_token (`str`, *optional*, defaults to `"<unk>"`):
            The unknown token. A token that is not in the vocabulary cannot be converted to an ID and is set to be this
            token instead.
        pad_token (`str`, *optional*, defaults to `"<pad>"`):
            The token used for padding, for example when batching sequences of different lengths.
        mask_token (`str`, *optional*, defaults to `"<mask>"`):
            The token used for masking values. This is the token used when training this model with masked language
            modeling. This is the token which the model will try to predict.
        add_prefix_space (`bool`, *optional*, defaults to `False`):
            Whether or not to add an initial space to the input. This allows to treat the leading word just as any
            other word. (Longformer tokenizer detect beginning of words by the preceding space).
        trim_offsets (`bool`, *optional*, defaults to `True`):
            Whether the post processing step should trim offsets to avoid including whitespaces.
    """
    vocab_files_names = VOCAB_FILES_NAMES
    pretrained_vocab_files_map = PRETRAINED_VOCAB_FILES_MAP
    max_model_input_sizes = PRETRAINED_POSITIONAL_EMBEDDINGS_SIZES
    model_input_names = ["input_ids", "attention_mask"]
    slow_tokenizer_class = LongformerTokenizer

    def __init__(
        self,
        vocab_file=None,
        merges_file=None,
        tokenizer_file=None,
        errors="replace",
        bos_token="<s>",
        eos_token="</s>",
        sep_token="</s>",
        cls_token="<s>",
        unk_token="<unk>",
        pad_token="<pad>",
        mask_token="<mask>",
        add_prefix_space=False,
        trim_offsets=True,
        **kwargs,
    ):
        """
        This method initializes an instance of the LongformerTokenizerFast class.

        Args:
            self: The instance of the class.
            vocab_file (str, optional): Path to the vocabulary file. Default is None.
            merges_file (str, optional): Path to the merges file. Default is None.
            tokenizer_file (str, optional): Path to the tokenizer file. Default is None.
            errors (str, optional): Specifies how to handle errors in decoding. Default is 'replace'.
            bos_token (str, optional): Beginning of sequence token. Default is '<s>'.
            eos_token (str, optional): End of sequence token. Default is '</s>'.
            sep_token (str, optional): Separator token. Default is '</s>'.
            cls_token (str, optional): Classification token. Default is '<s>'.
            unk_token (str, optional): Token for unknown words. Default is '<unk>'.
            pad_token (str, optional): Token for padding. Default is '<pad>'.
            mask_token (str, optional): Mask token. Default is '<mask>'.
            add_prefix_space (bool, optional): Whether to add prefix space. Default is False.
            trim_offsets (bool, optional): Whether to trim offsets. Default is True.

        Returns:
            None

        Raises:
            - TypeError: If the provided parameters are of incorrect types.
            - ValueError: If the values of parameters are invalid.
            - KeyError: If a required key is missing in the input data.
            - Exception: For any other unexpected errors.
        """
        mask_token = (
            AddedToken(mask_token, lstrip=True, rstrip=False, normalized=False)
            if isinstance(mask_token, str)
            else mask_token
        )
        super().__init__(
            vocab_file,
            merges_file,
            tokenizer_file=tokenizer_file,
            errors=errors,
            bos_token=bos_token,
            eos_token=eos_token,
            sep_token=sep_token,
            cls_token=cls_token,
            unk_token=unk_token,
            pad_token=pad_token,
            mask_token=mask_token,
            add_prefix_space=add_prefix_space,
            trim_offsets=trim_offsets,
            **kwargs,
        )

        pre_tok_state = json.loads(self.backend_tokenizer.pre_tokenizer.__getstate__())
        if pre_tok_state.get("add_prefix_space", add_prefix_space) != add_prefix_space:
            pre_tok_class = getattr(pre_tokenizers, pre_tok_state.pop("type"))
            pre_tok_state["add_prefix_space"] = add_prefix_space
            self.backend_tokenizer.pre_tokenizer = pre_tok_class(**pre_tok_state)

        self.add_prefix_space = add_prefix_space

        tokenizer_component = "post_processor"
        tokenizer_component_instance = getattr(self.backend_tokenizer, tokenizer_component, None)
        if tokenizer_component_instance:
            state = json.loads(tokenizer_component_instance.__getstate__())

            # The lists 'sep' and 'cls' must be cased in tuples for the object `post_processor_class`
            if "sep" in state:
                state["sep"] = tuple(state["sep"])
            if "cls" in state:
                state["cls"] = tuple(state["cls"])

            changes_to_apply = False

            if state.get("add_prefix_space", add_prefix_space) != add_prefix_space:
                state["add_prefix_space"] = add_prefix_space
                changes_to_apply = True

            if state.get("trim_offsets", trim_offsets) != trim_offsets:
                state["trim_offsets"] = trim_offsets
                changes_to_apply = True

            if changes_to_apply:
                component_class = getattr(processors, state.pop("type"))
                new_value = component_class(**state)
                setattr(self.backend_tokenizer, tokenizer_component, new_value)

    @property
    def mask_token(self) -> str:
        """
        `str`: Mask token, to use when training a model with masked-language modeling. Log an error if used while not
        having been set.

        Longformer tokenizer has a special mask token to be usable in the fill-mask pipeline. The mask token will greedily
        comprise the space before the *<mask>*.
        """
        if self._mask_token is None:
            if self.verbose:
                logger.error("Using mask_token, but it is not set yet.")
            return None
        return str(self._mask_token)

    @mask_token.setter
    def mask_token(self, value):
        """
        Overriding the default behavior of the mask token to have it eat the space before it.

        This is needed to preserve backward compatibility with all the previously used models based on Longformer.
        """
        # Mask token behave like a normal word, i.e. include the space before it
        # So we set lstrip to True
        value = AddedToken(value, lstrip=True, rstrip=False) if isinstance(value, str) else value
        self._mask_token = value

    def _batch_encode_plus(self, *args, **kwargs) -> BatchEncoding:
        """
        This method is a private function within the class LongformerTokenizerFast that batch encodes input sequences and returns the encoded representations.

        Args:
            self: An instance of the LongformerTokenizerFast class.

        Returns:
            A BatchEncoding object containing the batch encoded representations of the input sequences.

        Raises:
            AssertionError: Raised if the 'add_prefix_space' attribute is False and the 'is_split_into_words' argument is True. In this case, the method requires the LongformerTokenizerFast instance to be
            instantiated with 'add_prefix_space=True'.
        """
        is_split_into_words = kwargs.get("is_split_into_words", False)
        assert self.add_prefix_space or not is_split_into_words, (
            f"You need to instantiate {self.__class__.__name__} with add_prefix_space=True "
            "to use it with pretokenized inputs."
        )

        return super()._batch_encode_plus(*args, **kwargs)

    def _encode_plus(self, *args, **kwargs) -> BatchEncoding:
        """
        This method encodes input sequences into a BatchEncoding object. It is intended for use within the LongformerTokenizerFast class.

        Args:
            self: An instance of the LongformerTokenizerFast class. It is used to access the properties and methods of the class.

            *args: Variable positional arguments that may be passed to the method.

            **kwargs: Variable keyword arguments that may be passed to the method. The following kwargs are supported:
                - is_split_into_words (bool, optional): Specifies whether the input is already split into words. Default is False.

        Returns:
            BatchEncoding: A BatchEncoding object containing the encoded input sequences. The encoding includes tokenization and optional additional processing based on input arguments.

        Raises:
            AssertionError: Raised when the 'add_prefix_space' property is False and 'is_split_into_words' is True. In this case, it is required to instantiate the LongformerTokenizerFast class with
            add_prefix_space=True to use pretokenized inputs.
        """
        is_split_into_words = kwargs.get("is_split_into_words", False)

        assert self.add_prefix_space or not is_split_into_words, (
            f"You need to instantiate {self.__class__.__name__} with add_prefix_space=True "
            "to use it with pretokenized inputs."
        )

        return super()._encode_plus(*args, **kwargs)

    def save_vocabulary(self, save_directory: str, filename_prefix: Optional[str] = None) -> Tuple[str]:
        """
        Save the vocabulary.

        Args:
            self (LongformerTokenizerFast): An instance of the LongformerTokenizerFast class.
            save_directory (str): The directory where the vocabulary files will be saved.
            filename_prefix (Optional[str], optional): The prefix to use for the filename of the saved vocabulary files. Defaults to None.

        Returns:
            Tuple[str]: A tuple containing the file paths of the saved vocabulary files.

        Raises:
            None.

        This method saves the vocabulary of the tokenizer to the specified directory. The vocabulary files are saved with the given filename prefix, if provided. The saved vocabulary files can later be loaded
        using the 'load_vocabulary' method.
        """
        files = self._tokenizer.model.save(save_directory, name=filename_prefix)
        return tuple(files)

    def build_inputs_with_special_tokens(self, token_ids_0, token_ids_1=None):
        """
        Builds a list of token IDs with special tokens for the LongformerTokenizerFast class.
        
        Args:
            self (LongformerTokenizerFast): An instance of the LongformerTokenizerFast class.
            token_ids_0 (list[int]): A list of token IDs representing the first sequence.
            token_ids_1 (list[int], optional): A list of token IDs representing the second sequence. 
                Defaults to None.
        
        Returns:
            list[int] or None: The list of token IDs with special tokens. If token_ids_1 is None, 
                the output list will be [bos_token_id] + token_ids_0 + [eos_token_id]. 
                If token_ids_1 is provided, the output list will be [bos_token_id] + token_ids_0 + [eos_token_id]
                + [eos_token_id] + token_ids_1 + [eos_token_id].
        
        Raises:
            None.
        """
        output = [self.bos_token_id] + token_ids_0 + [self.eos_token_id]
        if token_ids_1 is None:
            return output

        return output + [self.eos_token_id] + token_ids_1 + [self.eos_token_id]

    def create_token_type_ids_from_sequences(
        self, token_ids_0: List[int], token_ids_1: Optional[List[int]] = None
    ) -> List[int]:
        """
        Create a mask from the two sequences passed to be used in a sequence-pair classification task. Longformer does not
        make use of token type ids, therefore a list of zeros is returned.

        Args:
            token_ids_0 (`List[int]`):
                List of IDs.
            token_ids_1 (`List[int]`, *optional*):
                Optional second list of IDs for sequence pairs.

        Returns:
            `List[int]`: List of zeros.
        """
        sep = [self.sep_token_id]
        cls = [self.cls_token_id]

        if token_ids_1 is None:
            return len(cls + token_ids_0 + sep) * [0]
        return len(cls + token_ids_0 + sep + sep + token_ids_1 + sep) * [0]

__all__ = ['LongformerTokenizerFast']
