# Copyright 2020 The HuggingFace Team. All rights reserved.
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

from . import configuration_ctrl, modeling_ctrl, tokenization_ctrl

from .configuration_ctrl import *
from .modeling_ctrl import *
from .tokenization_ctrl import *


__all__ = []
__all__.extend(configuration_ctrl.__all__)
__all__.extend(tokenization_ctrl.__all__)
__all__.extend(modeling_ctrl.__all__)


# _import_structure = {
#     "configuration_ctrl": ["CTRLConfig"],
#     "tokenization_ctrl": ["CTRLTokenizer"],
# }

# try:
#     if not is_torch_available():
#         raise OptionalDependencyNotAvailable()
# except OptionalDependencyNotAvailable:
#     pass
# else:
#     _import_structure["modeling_ctrl"] = [
#         "CTRLForSequenceClassification",
#         "CTRLLMHeadModel",
#         "CTRLModel",
#         "CTRLPreTrainedModel",
#     ]

# try:
#     if not is_tf_available():
#         raise OptionalDependencyNotAvailable()
# except OptionalDependencyNotAvailable:
#     pass
# else:
#     _import_structure["modeling_tf_ctrl"] = [
#         "TFCTRLForSequenceClassification",
#         "TFCTRLLMHeadModel",
#         "TFCTRLModel",
#         "TFCTRLPreTrainedModel",
#     ]


# if TYPE_CHECKING:
#     from .configuration_ctrl import CTRLConfig
#     from .tokenization_ctrl import CTRLTokenizer

#     try:
#         if not is_torch_available():
#             raise OptionalDependencyNotAvailable()
#     except OptionalDependencyNotAvailable:
#         pass
#     else:
#         from .modeling_ctrl import (
#             CTRLForSequenceClassification,
#             CTRLLMHeadModel,
#             CTRLModel,
#             CTRLPreTrainedModel,
#         )

#     try:
#         if not is_tf_available():
#             raise OptionalDependencyNotAvailable()
#     except OptionalDependencyNotAvailable:
#         pass
#     else:
#         from .modeling_tf_ctrl import (
#             TFCTRLForSequenceClassification,
#             TFCTRLLMHeadModel,
#             TFCTRLModel,
#             TFCTRLPreTrainedModel,
#         )

# else:
#     import sys

#     sys.modules[__name__] = _LazyModule(__name__, globals()["__file__"], _import_structure, module_spec=__spec__)
