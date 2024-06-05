# Copyright 2022 The HuggingFace Team. All rights reserved.
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
"""efficientformer init"""
from . import configuration_efficientformer, image_processing_efficientformer,modeling_efficientformer
from .configuration_efficientformer import *
from .image_processing_efficientformer import *
from .modeling_efficientformer import *


_import_structure = {"configuration_efficientformer": ["EfficientFormerConfig"]}

try:
    if not is_vision_available():
        raise OptionalDependencyNotAvailable()
except OptionalDependencyNotAvailable:
    pass
else:
    _import_structure["image_processing_efficientformer"] = ["EfficientFormerImageProcessor"]

try:
    if not is_torch_available():
        raise OptionalDependencyNotAvailable()
except OptionalDependencyNotAvailable:
    pass
else:
    _import_structure["modeling_efficientformer"] = [
        "EfficientFormerForImageClassification",
        "EfficientFormerForImageClassificationWithTeacher",
        "EfficientFormerModel",
        "EfficientFormerPreTrainedModel",
    ]

try:
    if not is_tf_available():
        raise OptionalDependencyNotAvailable()
except OptionalDependencyNotAvailable:
    pass
else:
    _import_structure["modeling_tf_efficientformer"] = [
        "TFEfficientFormerForImageClassification",
        "TFEfficientFormerForImageClassificationWithTeacher",
        "TFEfficientFormerModel",
        "TFEfficientFormerPreTrainedModel",
    ]

if TYPE_CHECKING:
    from .configuration_efficientformer import EfficientFormerConfig

    try:
        if not is_vision_available():
            raise OptionalDependencyNotAvailable()
    except OptionalDependencyNotAvailable:
        pass
    else:
        from .image_processing_efficientformer import EfficientFormerImageProcessor

    try:
        if not is_torch_available():
            raise OptionalDependencyNotAvailable()
    except OptionalDependencyNotAvailable:
        pass
    else:
        from .modeling_efficientformer import (
            EfficientFormerForImageClassification,
            EfficientFormerForImageClassificationWithTeacher,
            EfficientFormerModel,
            EfficientFormerPreTrainedModel,
        )
    try:
        if not is_tf_available():
            raise OptionalDependencyNotAvailable()
    except OptionalDependencyNotAvailable:
        pass
    else:
        from .modeling_tf_efficientformer import (
            TFEfficientFormerForImageClassification,
            TFEfficientFormerForImageClassificationWithTeacher,
            TFEfficientFormerModel,
            TFEfficientFormerPreTrainedModel,
        )

else:
    import sys

    sys.modules[__name__] = _LazyModule(__name__, globals()["__file__"], _import_structure, module_spec=__spec__)
