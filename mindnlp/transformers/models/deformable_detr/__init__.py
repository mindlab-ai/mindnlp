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

from typing import TYPE_CHECKING

from ....utils import OptionalDependencyNotAvailable, is_mindspore_available, is_vision_available

from .configuration_deformable_detr import *
from .feature_extraction_deformable_detr import *
from .image_processing_deformable_detr import *
from .modeling_deformable_detr import *

_import_structure = {
    "configuration_deformable_detr": ["DeformableDetrConfig"],
}

try:
    if not is_vision_available():
        raise OptionalDependencyNotAvailable()
except OptionalDependencyNotAvailable:
    pass
else:
    _import_structure["feature_extraction_deformable_detr"] = ["DeformableDetrFeatureExtractor"]
    _import_structure["image_processing_deformable_detr"] = ["DeformableDetrImageProcessor"]

try:
    if not is_mindspore_available():
        raise OptionalDependencyNotAvailable()
except OptionalDependencyNotAvailable:
    pass
else:
    _import_structure["modeling_deformable_detr"] = [
        "DeformableDetrForObjectDetection",
        "DeformableDetrModel",
        "DeformableDetrPreTrainedModel",
    ]


if TYPE_CHECKING:
    from .configuration_deformable_detr import DeformableDetrConfig

    try:
        if not is_vision_available():
            raise OptionalDependencyNotAvailable()
    except OptionalDependencyNotAvailable:
        pass
    else:
        from .feature_extraction_deformable_detr import DeformableDetrFeatureExtractor
        from .image_processing_deformable_detr import DeformableDetrImageProcessor

    try:
        if not is_mindspore_available():
            raise OptionalDependencyNotAvailable()
    except OptionalDependencyNotAvailable:
        pass
    else:
        from .modeling_deformable_detr import (
            DeformableDetrForObjectDetection,
            DeformableDetrModel,
            DeformableDetrPreTrainedModel,
        )

__all__ = []
__all__.extend(configuration_deformable_detr.__all__)
__all__.extend(feature_extraction_deformable_detr.__all__)
__all__.extend(image_processing_deformable_detr.__all__)
__all__.extend(modeling_deformable_detr.__all__)
