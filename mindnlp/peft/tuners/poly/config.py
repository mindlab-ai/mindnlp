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
"""poly config"""
from dataclasses import dataclass, field
from typing import List, Literal, Optional, Union

from mindnlp.peft.config import PeftConfig
from mindnlp.peft.utils import PeftType


@dataclass
class PolyConfig(PeftConfig):
    """
    This is the configuration class to store the configuration of a [`PolyModel`].
        - [Polytropon (Poly)](https://arxiv.org/abs/2202.13914)
        - [Multi-Head Routing (MHR)](https://arxiv.org/abs/2211.03831)

    Args:
        r (`int`): Attention dimension of each Lora in Poly.
        target_cells (`Union[List[str],str]`): The names of the cells to apply Poly to.
        cells_to_save (`List[str]`): List of cells apart from Poly layers to be set as trainable
            and saved in the final checkpoint.
        init_weights (bool): Whether to perform initialization of Poly weights.
        poly_type (`Literal["poly"]`): The variant of the Poly cell to use. Currently, only "poly"
            is supported.
        n_tasks (`int`): The number of tasks in a multitasking scenario.
        n_skills (`int`): The number of skills (LoRA) in each Poly layer.
        n_splits (`int`): The number of splits within each LoRA of a Poly layer. A value greater
            than 1 indicates the use of Multi-Head Routing (MHR).
    """

    r: int = field(default=8, metadata={"help": "Lora attention dimension"})
    target_cells: Optional[Union[List[str], str]] = field(
        default=None,
        metadata={
            "help": "List of cell names or regex expression of the cell names to replace with Poly."
            "For example, ['q', 'v'] or '.*decoder.*(SelfAttention|EncDecAttention).*(q|v)$' "
        },
    )
    cells_to_save: Optional[List[str]] = field(
        default=None,
        metadata={
            "help": "List of cells apart from Poly layers to be set as trainable and saved in the final checkpoint. "
            "For example, in Sequence Classification or Token Classification tasks, "
            "the final layer `classifier/score` are randomly initialized and as such need to be trainable and saved."
        },
    )
    init_weights: bool = field(
        default=True,
        metadata={
            "help": (
                "Whether to initialize the weights of the Poly layers with their default initialization. Don't change "
                "this setting, except if you know exactly what you're doing."
            ),
        },
    )
    poly_type: Literal["poly"] = field(
        default="poly",
        metadata={
            "help": 'Type of Poly cells to be used. Currently only "poly" is supported.'
        },
    )
    n_tasks: int = field(
        default=1,
        metadata={"help": "Number of tasks in multitasking scenario."},
    )
    n_skills: int = field(
        default=4,
        metadata={"help": "Number of skills (LoRA) in each Poly layer."},
    )
    n_splits: int = field(
        default=1,
        metadata={"help": "Number of splits within each LoRA of a Poly layer."},
    )

    def __post_init__(self):
        self.peft_type = PeftType.POLY
        self.target_cells = (
            set(self.target_cells)
            if isinstance(self.target_cells, list)
            else self.target_cells
        )
