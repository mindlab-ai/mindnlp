# Copyright 2024 Huawei Technologies Co., Ltd
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
# ============================================
"""PyTorch VisionTextDualEncoder model."""

from typing import Optional, Tuple, Union

import mindspore as ms
from mindnlp.core import nn, ops
from mindspore import Tensor, Parameter

from ...modeling_utils import PreTrainedModel
from ....utils import logging
from ..auto.configuration_auto import AutoConfig
from ..auto.modeling_auto import AutoModel
from ..clip.modeling_clip import CLIPOutput, CLIPVisionConfig, CLIPVisionModel
from .configuration_vision_text_dual_encoder import VisionTextDualEncoderConfig


logger = logging.get_logger(__name__)

_CONFIG_FOR_DOC = "VisionTextDualEncoderConfig"


# Copied from transformers.models.clip.modeling_clip.contrastive_loss
def contrastive_loss(logits: ms.Tensor) -> ms.Tensor:
    return F.cross_entropy(logits, ops.arange(len(logits)))


# Copied from transformers.models.clip.modeling_clip.clip_loss
def clip_loss(similarity: ms.Tensor) -> ms.Tensor:
    caption_loss = contrastive_loss(similarity)
    image_loss = contrastive_loss(similarity.t())
    return (caption_loss + image_loss) / 2.0


class VisionTextDualEncoderModel(PreTrainedModel):
    config_class = VisionTextDualEncoderConfig
    base_model_prefix = "vision_text_dual_encoder"

    def __init__(
        self,
        config: Optional[VisionTextDualEncoderConfig] = None,
        vision_model: Optional[PreTrainedModel] = None,
        text_model: Optional[PreTrainedModel] = None,
    ):
        if config is None and (vision_model is None or text_model is None):
            raise ValueError("Either a configuration or an vision and a text model has to be provided")

        if config is None:
            config = VisionTextDualEncoderConfig.from_vision_text_configs(vision_model.config, text_model.config)
        else:
            if not isinstance(config, self.config_class):
                raise ValueError(f"config: {config} has to be of type {self.config_class}")

        # initialize with config
        super().__init__(config)

        if vision_model is None:
            if isinstance(config.vision_config, CLIPVisionConfig):
                vision_model = CLIPVisionModel(config.vision_config)
            else:
                vision_model = AutoModel.from_config(
                    config.vision_config
                )

        if text_model is None:
            text_model = AutoModel.from_config(config.text_config)

        self.vision_model = vision_model
        self.text_model = text_model

        # make sure that the individual model's config refers to the shared config
        # so that the updates to the config will be synced
        self.vision_model.config = self.config.vision_config
        self.text_model.config = self.config.text_config

        self.vision_embed_dim = config.vision_config.hidden_size
        self.text_embed_dim = config.text_config.hidden_size
        self.projection_dim = config.projection_dim

        self.visual_projection = nn.Linear(self.vision_embed_dim, self.projection_dim, bias=False)
        self.text_projection = nn.Linear(self.text_embed_dim, self.projection_dim, bias=False)
        self.logit_scale = Parameter(ms.tensor(self.config.logit_scale_init_value))

    def get_text_features(
        self,
        input_ids=None,
        attention_mask=None,
        position_ids=None,
        token_type_ids=None,
        output_attentions=None,
        output_hidden_states=None,
        return_dict=None,
    ):
        r"""
        Returns:
            text_features (`torch.FloatTensor` of shape `(batch_size, output_dim`): The text embeddings obtained by
                applying the projection layer to the pooled output of [`CLIPTextModel`].

        Example:
            ```python
            >>> from transformers import VisionTextDualEncoderModel, AutoTokenizer
            ...
            >>> model = VisionTextDualEncoderModel.from_pretrained("clip-italian/clip-italian")
            >>> tokenizer = AutoTokenizer.from_pretrained("clip-italian/clip-italian")
            ...
            >>> inputs = tokenizer(["una foto di un gatto", "una foto di un cane"], padding=True, return_tensors="pt")
            >>> text_features = model.get_text_features(**inputs)
            ```
        """
        text_outputs = self.text_model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            position_ids=position_ids,
            token_type_ids=token_type_ids,
            output_attentions=output_attentions,
            output_hidden_states=output_hidden_states,
            return_dict=return_dict,
        )

        pooled_output = text_outputs[1]
        text_features = self.text_projection(pooled_output)

        return text_features

    def get_image_features(
        self,
        pixel_values=None,
        output_attentions=None,
        output_hidden_states=None,
        return_dict=None,
    ):
        r"""

        Returns:
            image_features (`torch.FloatTensor` of shape `(batch_size, output_dim`): The image embeddings obtained by
                applying the projection layer to the pooled output of [`CLIPVisionModel`].

        Example:
            ```python
            >>> from PIL import Image
            >>> import requests
            >>> from transformers import VisionTextDualEncoderModel, AutoImageProcessor
            ...
            >>> model = VisionTextDualEncoderModel.from_pretrained("clip-italian/clip-italian")
            >>> image_processor = AutoImageProcessor.from_pretrained("google/vit-base-patch16-224")
            ...
            >>> url = "http://images.cocodataset.org/val2017/000000039769.jpg"
            >>> image = Image.open(requests.get(url, stream=True).raw)
            ...
            >>> inputs = image_processor(images=image, return_tensors="pt")
            ...
            >>> image_features = model.get_image_features(**inputs)
            ```
        """
        vision_outputs = self.vision_model(
            pixel_values=pixel_values,
            output_attentions=output_attentions,
            output_hidden_states=output_hidden_states,
            return_dict=return_dict,
        )

        pooled_output = vision_outputs[1]  # pooled_output
        image_features = self.visual_projection(pooled_output)

        return image_features

    def forward(
        self,
        input_ids: Optional[ms.Tensor] = None,
        pixel_values: Optional[ms.Tensor] = None,
        attention_mask: Optional[ms.Tensor] = None,
        position_ids: Optional[ms.Tensor] = None,
        return_loss: Optional[bool] = None,
        token_type_ids: Optional[ms.Tensor] = None,
        output_attentions: Optional[bool] = None,
        output_hidden_states: Optional[bool] = None,
        return_dict: Optional[bool] = None,
    ) -> Union[Tuple[ms.Tensor], CLIPOutput]:
        r"""
        Returns:
            Union[Tuple[ms.Tensor], CLIPOutput]

        Example:
            ```python
            >>> from PIL import Image
            >>> import requests
            >>> from transformers import (
            ...     VisionTextDualEncoderModel,
            ...     VisionTextDualEncoderProcessor,
            ...     AutoImageProcessor,
            ...     AutoTokenizer,
            ... )
            ...
            >>> tokenizer = AutoTokenizer.from_pretrained("google-bert/bert-base-uncased")
            >>> image_processor = AutoImageProcessor.from_pretrained("google/vit-base-patch16-224")
            >>> processor = VisionTextDualEncoderProcessor(image_processor, tokenizer)
            >>> model = VisionTextDualEncoderModel.from_vision_text_pretrained(
            ...     "google/vit-base-patch16-224", "google-bert/bert-base-uncased"
            ... )
            ...
            >>> # contrastive training
            >>> urls = [
            ...     "http://images.cocodataset.org/val2017/000000039769.jpg",
            ...     "https://farm3.staticflickr.com/2674/5850229113_4fe05d5265_z.jpg",
            ... ]
            >>> images = [Image.open(requests.get(url, stream=True).raw) for url in urls]
            >>> inputs = processor(
            ...     text=["a photo of a cat", "a photo of a dog"], images=images, return_tensors="pt", padding=True
            ... )
            >>> outputs = model(
            ...     input_ids=inputs.input_ids,
            ...     attention_mask=inputs.attention_mask,
            ...     pixel_values=inputs.pixel_values,
            ...     return_loss=True,
            ... )
            >>> loss, logits_per_image = outputs.loss, outputs.logits_per_image  # this is the image-text similarity score
            ...
            >>> # save and load from pretrained
            >>> model.save_pretrained("vit-bert")
            >>> model = VisionTextDualEncoderModel.from_pretrained("vit-bert")
            ...
            >>> # inference
            >>> outputs = model(**inputs)
            >>> logits_per_image = outputs.logits_per_image  # this is the image-text similarity score
            >>> probs = logits_per_image.softmax(dim=1)  # we can take the softmax to get the label probabilities
            ```
        """
        return_dict = return_dict if return_dict is not None else self.config.return_dict

        vision_outputs = self.vision_model(
            pixel_values=pixel_values,
            output_attentions=output_attentions,
            output_hidden_states=output_hidden_states,
            return_dict=return_dict,
        )

        text_outputs = self.text_model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            token_type_ids=token_type_ids,
            position_ids=position_ids,
            output_attentions=output_attentions,
            output_hidden_states=output_hidden_states,
            return_dict=return_dict,
        )

        image_embeds = vision_outputs[1]  # pooler_output
        image_embeds = self.visual_projection(image_embeds)

        text_embeds = text_outputs[1]  # pooler_output
        text_embeds = self.text_projection(text_embeds)

        # normalized features
        image_embeds = image_embeds / ops.norm(image_embeds, dim=-1, keepdim=True)
        text_embeds = text_embeds / ops.norm(text_embeds, dim=-1, keepdim=True)

        # cosine similarity as logits
        logit_scale = self.logit_scale.exp()
        logits_per_text = ops.matmul(text_embeds, image_embeds.t()) * logit_scale
        logits_per_image = ops.t(logits_per_text)

        loss = None
        if return_loss:
            loss = clip_loss(logits_per_text)

        if not return_dict:
            output = (logits_per_image, logits_per_text, text_embeds, image_embeds, text_outputs, vision_outputs)
            return ((loss,) + output) if loss is not None else output

        return CLIPOutput(
            loss=loss,
            logits_per_image=logits_per_image,
            logits_per_text=logits_per_text,
            text_embeds=text_embeds,
            image_embeds=image_embeds,
            text_model_output=text_outputs,
            vision_model_output=vision_outputs,
        )

    @classmethod
    def from_pretrained(cls, *args, **kwargs):
        # At the moment fast initialization is not supported
        # for composite models
        kwargs["_fast_init"] = False
        return super().from_pretrained(*args, **kwargs)

    @classmethod
    def from_vision_text_pretrained(
        cls,
        *model_args,
        vision_model_name_or_path: str = None,
        text_model_name_or_path: str = None,
        **kwargs,
    ) -> PreTrainedModel:
        """
        Params:
            vision_model_name_or_path (`str`, *optional*, defaults to `None`):
                Information necessary to initiate the vision model. Can be either:

                - A string, the *model id* of a pretrained model hosted inside a model repo on huggingface.co.
                - A path to a *directory* containing model weights saved using
                  [`~PreTrainedModel.save_pretrained`], e.g., `./my_model_directory/`.
                - A path or url to a *PyTorch checkpoint folder* (e.g, `./pt_model`). In this case, `from_pt`
                  should be set to `True` and a configuration object should be provided as `config` argument. This
                  loading path is slower than converting the PyTorch checkpoint in a Flax model using the provided
                  conversion scripts and loading the Flax model afterwards.

            text_model_name_or_path (`str`, *optional*):
                Information necessary to initiate the text model. Can be either:

                - A string, the *model id* of a pretrained model hosted inside a model repo on huggingface.co.
                - A path to a *directory* containing model weights saved using
                  [`~PreTrainedModel.save_pretrained`], e.g., `./my_model_directory/`.
                - A path or url to a *PyTorch checkpoint folder* (e.g, `./pt_model`). In this case, `from_pt`
                  should be set to `True` and a configuration object should be provided as `config` argument. This
                  loading path is slower than converting the PyTorch checkpoint in a Flax model using the provided
                  conversion scripts and loading the Flax model afterwards.

            model_args (remaining positional arguments, *optional*):
                All remaning positional arguments will be passed to the underlying model's `__init__` method.

            kwargs (remaining dictionary of keyword arguments, *optional*):
                Can be used to update the configuration object (after it being loaded) and initiate the model (e.g.,
                `output_attentions=True`).

                - To update the text configuration, use the prefix *text_* for each configuration parameter.
                - To update the vision configuration, use the prefix *vision_* for each configuration parameter.
                - To update the parent model configuration, do not use a prefix for each configuration parameter.

                Behaves differently depending on whether a `config` is provided or automatically loaded.

        Example:
            ```python
            >>> from transformers import VisionTextDualEncoderModel
            ...
            >>> # initialize a model from pretrained ViT and BERT models. Note that the projection layers will be randomly initialized.
            >>> model = VisionTextDualEncoderModel.from_vision_text_pretrained(
            ...     "google/vit-base-patch16-224", "google-bert/bert-base-uncased"
            ... )
            >>> # saving model after fine-tuning
            >>> model.save_pretrained("./vit-bert")
            >>> # load fine-tuned model
            >>> model = VisionTextDualEncoderModel.from_pretrained("./vit-bert")
            ```
        """
        kwargs_vision = {
            argument[len("vision_") :]: value for argument, value in kwargs.items() if argument.startswith("vision_")
        }

        kwargs_text = {
            argument[len("text_") :]: value for argument, value in kwargs.items() if argument.startswith("text_")
        }

        # remove vision, text kwargs from kwargs
        for key in kwargs_vision.keys():
            del kwargs["vision_" + key]
        for key in kwargs_text.keys():
            del kwargs["text_" + key]

        # Load and initialize the vision and text model
        vision_model = kwargs_vision.pop("model", None)
        if vision_model is None:
            if vision_model_name_or_path is None:
                raise ValueError(
                    "If `vision_model` is not defined as an argument, a `vision_model_name_or_path` has to be defined"
                )

            if "config" not in kwargs_vision:
                vision_config = AutoConfig.from_pretrained(vision_model_name_or_path)

            if vision_config.model_type == "clip":
                kwargs_vision["config"] = vision_config.vision_config
                vision_model = CLIPVisionModel.from_pretrained(vision_model_name_or_path, *model_args, **kwargs_vision)
                # TODO: Should we use the pre-trained projection as well ?
            else:
                kwargs_vision["config"] = vision_config
                vision_model = AutoModel.from_pretrained(vision_model_name_or_path, *model_args, **kwargs_vision)

        text_model = kwargs_text.pop("model", None)
        if text_model is None:
            if text_model_name_or_path is None:
                raise ValueError(
                    "If `text_model` is not defined as an argument, a `text_model_name_or_path` has to be defined"
                )

            if "config" not in kwargs_text:
                text_config = AutoConfig.from_pretrained(text_model_name_or_path)
                kwargs_text["config"] = text_config

            text_model = AutoModel.from_pretrained(text_model_name_or_path, *model_args, **kwargs_text)

        # instantiate config with corresponding kwargs
        config = VisionTextDualEncoderConfig.from_vision_text_configs(vision_model.config, text_model.config, **kwargs)

        # init model
        model = cls(config=config, vision_model=vision_model, text_model=text_model)

        # the projection layers are always newly initialized when loading the model
        # using pre-trained vision and text model.
        logger.warning(
            "The projection layer and logit scale weights `['visual_projection.weight', 'text_projection.weight',"
            " 'logit_scale']` are newly initialized. You should probably TRAIN this model on a down-stream task to be"
            " able to use it for predictions and inference."
        )

        return model


__all__ = [
    "VisionTextDualEncoderModel"
]
