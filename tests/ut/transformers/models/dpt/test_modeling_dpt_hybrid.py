# coding=utf-8
# Copyright 2024 Huawei Technologies Co., Ltd
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
"""Testing suite for the MindSpore DPT model."""

import unittest
import numpy as np

from mindnlp.transformers import DPTConfig
from mindnlp.utils import is_mindspore_available, is_vision_available
from mindnlp.utils.testing_utils import is_flaky, require_mindspore, require_vision, slow

from ...test_configuration_common import ConfigTester
from ...test_modeling_common import ModelTesterMixin, _config_zero_init, floats_tensor, ids_tensor

if is_mindspore_available():
    import mindspore
    from mindspore import nn, ops

    from mindnlp.transformers import DPTForDepthEstimation, DPTForSemanticSegmentation, DPTModel
    from mindnlp.transformers.models.auto.modeling_auto import MODEL_MAPPING_NAMES

if is_vision_available():
    from PIL import Image

    from mindnlp.transformers import DPTImageProcessor


class DPTModelTester:
    def __init__(
            self,
            parent,
            batch_size=2,
            image_size=32,
            patch_size=16,
            num_channels=3,
            is_training=True,
            use_labels=True,
            hidden_size=32,
            num_hidden_layers=4,
            backbone_out_indices=None,
            num_attention_heads=4,
            intermediate_size=37,
            hidden_act="gelu",
            hidden_dropout_prob=0.1,
            attention_probs_dropout_prob=0.1,
            initializer_range=0.02,
            num_labels=3,
            backbone_featmap_shape=None,
            neck_hidden_sizes=None,
            is_hybrid=True,
            scope=None,
    ):
        if neck_hidden_sizes is None:
            neck_hidden_sizes = [16, 16, 32, 32]
        if backbone_featmap_shape is None:
            backbone_featmap_shape = [1, 32, 24, 24]
        if backbone_out_indices is None:
            backbone_out_indices = [0, 1, 2, 3]
        self.parent = parent
        self.batch_size = batch_size
        self.image_size = image_size
        self.patch_size = patch_size
        self.num_channels = num_channels
        self.is_training = is_training
        self.use_labels = use_labels
        self.hidden_size = hidden_size
        self.num_hidden_layers = num_hidden_layers
        self.backbone_out_indices = backbone_out_indices
        self.num_attention_heads = num_attention_heads
        self.intermediate_size = intermediate_size
        self.hidden_act = hidden_act
        self.hidden_dropout_prob = hidden_dropout_prob
        self.attention_probs_dropout_prob = attention_probs_dropout_prob
        self.initializer_range = initializer_range
        self.num_labels = num_labels
        self.backbone_featmap_shape = backbone_featmap_shape
        self.scope = scope
        self.is_hybrid = is_hybrid
        self.neck_hidden_sizes = neck_hidden_sizes
        # sequence length of DPT = num_patches + 1 (we add 1 for the [CLS] token)
        num_patches = (image_size // patch_size) ** 2
        self.seq_length = num_patches + 1

    def prepare_config_and_inputs(self):
        pixel_values = floats_tensor([self.batch_size, self.num_channels, self.image_size, self.image_size])

        labels = None
        if self.use_labels:
            labels = ids_tensor([self.batch_size, self.image_size, self.image_size], self.num_labels)

        config = self.get_config()

        return config, pixel_values, labels

    def get_config(self):
        backbone_config = {
            "global_padding": "same",
            "layer_type": "bottleneck",
            "depths": [3, 4, 9],
            "out_features": ["stage1", "stage2", "stage3"],
            "embedding_dynamic_padding": True,
            "hidden_sizes": [16, 16, 32, 32],
            "num_groups": 2,
        }

        return DPTConfig(
            image_size=self.image_size,
            patch_size=self.patch_size,
            num_channels=self.num_channels,
            hidden_size=self.hidden_size,
            fusion_hidden_size=self.hidden_size,
            num_hidden_layers=self.num_hidden_layers,
            backbone_out_indices=self.backbone_out_indices,
            num_attention_heads=self.num_attention_heads,
            intermediate_size=self.intermediate_size,
            hidden_act=self.hidden_act,
            hidden_dropout_prob=self.hidden_dropout_prob,
            attention_probs_dropout_prob=self.attention_probs_dropout_prob,
            is_decoder=False,
            initializer_range=self.initializer_range,
            is_hybrid=self.is_hybrid,
            backbone_config=backbone_config,
            backbone=None,
            backbone_featmap_shape=self.backbone_featmap_shape,
            neck_hidden_sizes=self.neck_hidden_sizes,
        )

    def create_and_check_model(self, config, pixel_values, labels):
        model = DPTModel(config=config)
        model.set_train(False)
        result = model(pixel_values)
        self.parent.assertEqual(result.last_hidden_state.shape, (self.batch_size, self.seq_length, self.hidden_size))

    def create_and_check_for_depth_estimation(self, config, pixel_values, labels):
        config.num_labels = self.num_labels
        model = DPTForDepthEstimation(config)
        model.set_train(False)
        result = model(pixel_values)
        self.parent.assertEqual(result.predicted_depth.shape, (self.batch_size, self.image_size, self.image_size))

    def create_and_check_for_semantic_segmentation(self, config, pixel_values, labels):
        config.num_labels = self.num_labels
        model = DPTForSemanticSegmentation(config)
        model.set_train(False)
        result = model(pixel_values, labels=labels)
        self.parent.assertEqual(
            result.logits.shape, (self.batch_size, self.num_labels, self.image_size, self.image_size)
        )

    def prepare_config_and_inputs_for_common(self):
        config_and_inputs = self.prepare_config_and_inputs()
        config, pixel_values, labels = config_and_inputs
        inputs_dict = {"pixel_values": pixel_values}
        return config, inputs_dict


@require_mindspore
class DPTModelTest(ModelTesterMixin, unittest.TestCase):
    """
    Here we also overwrite some of the tests of test_modeling_common.py, as DPT does not use input_ids, inputs_embeds,
    attention_mask and seq_length.
    """

    all_model_classes = (
        DPTModel, DPTForDepthEstimation, DPTForSemanticSegmentation) if is_mindspore_available() else ()
    pipeline_model_mapping = (
        {
            "depth-estimation": DPTForDepthEstimation,
            "feature-extraction": DPTModel,
            "image-segmentation": DPTForSemanticSegmentation,
        }
        if is_mindspore_available()
        else {}
    )

    test_pruning = False
    test_resize_embeddings = False
    test_head_masking = False

    def setUp(self):
        self.model_tester = DPTModelTester(self)
        self.config_tester = ConfigTester(self, config_class=DPTConfig, has_text_modality=False, hidden_size=37)

    def test_config(self):
        self.config_tester.run_common_tests()

    @unittest.skip(reason="DPT does not use inputs_embeds")
    def test_inputs_embeds(self):
        pass

    @unittest.skip(reason="DPT does not use the nn.Embedding")
    def test_model_common_attributes(self):
        pass

    def test_model_get_set_embeddings(self):
        config, _ = self.model_tester.prepare_config_and_inputs_for_common()

        for model_class in self.all_model_classes:
            model = model_class(config)
            self.assertIsInstance(model.get_input_embeddings(), (nn.Module))
            x = model.get_output_embeddings()
            self.assertTrue(x is None or isinstance(x, nn.Dense))

    def test_model(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_model(*config_and_inputs)

    def test_for_depth_estimation(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_for_depth_estimation(*config_and_inputs)

    def test_for_semantic_segmentation(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_for_semantic_segmentation(*config_and_inputs)

    def test_training(self):
        for model_class in self.all_model_classes:
            if model_class.__name__ == "DPTForDepthEstimation":
                continue

            config, inputs_dict = self.model_tester.prepare_config_and_inputs_for_common()
            config.return_dict = True

            if model_class.__name__ in MODEL_MAPPING_NAMES.values():
                continue

            model = model_class(config)
            model.set_train()
            inputs = self._prepare_for_class(inputs_dict, model_class, return_labels=True)
            loss = model(**inputs).loss
            # loss.backward()

    def test_training_gradient_checkpointing(self):
        pass

    @unittest.skip(
        reason="This architecure seem to not compute gradients properly when using GC, "
               "check: https://github.com/huggingface/transformers/pull/27124"
    )
    def test_training_gradient_checkpointing_use_reentrant(self):
        pass

    @unittest.skip(
        reason="This architecure seem to not compute gradients properly when using GC, "
               "check: https://github.com/huggingface/transformers/pull/27124"
    )
    def test_training_gradient_checkpointing_use_reentrant_false(self):
        pass

    def test_initialization(self):
        config, inputs_dict = self.model_tester.prepare_config_and_inputs_for_common()

        configs_no_init = _config_zero_init(config)
        for model_class in self.all_model_classes:
            model = model_class(config=configs_no_init)
            # Skip the check for the backbone
            backbone_params = []
            for name, module in model.cells_and_names():
                if module.__class__.__name__ == "DPTViTHybridEmbeddings":
                    backbone_params = [f"{key.name}" for key in module.get_parameters()]
                    break

            for name, param in model.parameters_and_names():
                if param.requires_grad:
                    if name in backbone_params:
                        continue
                    self.assertIn(
                        ((param.data.mean() * 1e9).round() / 1e9).item(),
                        [0.0, 1.0],
                        msg=f"Parameter {name} of model {model_class} seems not properly initialized",
                    )

    @slow
    def test_model_from_pretrained(self):
        model_name = "Intel/dpt-hybrid-midas"
        model = DPTModel.from_pretrained(model_name)
        self.assertIsNotNone(model)

    def test_raise_readout_type(self):
        # We do this test only for DPTForDepthEstimation since it is the only model that uses readout_type
        config, _ = self.model_tester.prepare_config_and_inputs_for_common()
        config.readout_type = "add"
        with self.assertRaises(ValueError):
            _ = DPTForDepthEstimation(config)

    @is_flaky(description="is_flaky https://github.com/huggingface/transformers/issues/29516")
    def test_batching_equivalence(self):
        def get_tensor_equivalence_function(batched_input):
            # models operating on continuous spaces have higher abs difference than LMs
            # instead, we can rely on cos distance for image/speech models, similar to `diffusers`
            if "input_ids" not in batched_input:
                return lambda tensor1, tensor2: (
                        1.0 - ops.cosine_similarity(tensor1.float().flatten(), tensor2.float().flatten(), dim=0,
                                                    eps=1e-38)
                )
            return lambda tensor1, tensor2: ops.max(ops.abs(tensor1 - tensor2))

        def recursive_check(batched_object, single_row_object, model_name, key):
            if isinstance(batched_object, (list, tuple)):
                for batched_object_value, single_row_object_value in zip(batched_object, single_row_object):
                    recursive_check(batched_object_value, single_row_object_value, model_name, key)
            elif isinstance(batched_object, dict):
                for batched_object_value, single_row_object_value in zip(
                        batched_object.values(), single_row_object.values()
                ):
                    recursive_check(batched_object_value, single_row_object_value, model_name, key)
            # do not compare returned loss (0-dim tensor) / codebook ids (int) / caching objects
            elif batched_object is None or not isinstance(batched_object, mindspore.Tensor):
                return
            elif batched_object.dim() == 0:
                return
            else:
                # indexing the first element does not always work
                # e.g. models that output similarity scores of size (N, M) would need to index [0, 0]
                slice_ids = [slice(0, index) for index in single_row_object.shape]
                batched_row = batched_object[slice_ids]
                self.assertFalse(
                    ops.isnan(batched_row).any(), f"Batched output has `nan` in {model_name} for key={key}"
                )
                self.assertFalse(
                    ops.isinf(batched_row).any(), f"Batched output has `inf` in {model_name} for key={key}"
                )
                self.assertFalse(
                    ops.isnan(single_row_object).any(), f"Single row output has `nan` in {model_name} for key={key}"
                )
                self.assertFalse(
                    ops.isinf(single_row_object).any(), f"Single row output has `inf` in {model_name} for key={key}"
                )
                self.assertTrue(
                    (equivalence(batched_row, single_row_object)) <= 1e-03,
                    msg=(
                        f"Batched and Single row outputs are not equal in {model_name} for key={key}. "
                        f"Difference={equivalence(batched_row, single_row_object)}."
                    ),
                )

        config, batched_input = self.model_tester.prepare_config_and_inputs_for_common()
        equivalence = get_tensor_equivalence_function(batched_input)

        for model_class in self.all_model_classes:
            config.output_hidden_states = True

            model_name = model_class.__name__
            if hasattr(self.model_tester, "prepare_config_and_inputs_for_model_class"):
                config, batched_input = self.model_tester.prepare_config_and_inputs_for_model_class(model_class)
            batched_input_prepared = self._prepare_for_class(batched_input, model_class)
            model = model_class(config).set_train(False)

            batch_size = self.model_tester.batch_size
            single_row_input = {}
            for key, value in batched_input_prepared.items():
                if isinstance(value, mindspore.Tensor) and value.shape[0] % batch_size == 0:
                    # e.g. musicgen has inputs of size (bs*codebooks). in most cases value.shape[0] == batch_size
                    single_batch_shape = value.shape[0] // batch_size
                    single_row_input[key] = value[:single_batch_shape]
                else:
                    single_row_input[key] = value

            model_batched_output = model(**batched_input_prepared)
            model_row_output = model(**single_row_input)

            if isinstance(model_batched_output, mindspore.Tensor):
                model_batched_output = {"model_output": model_batched_output}
                model_row_output = {"model_output": model_row_output}

            for key in model_batched_output:
                # DETR starts from zero-init queries to decoder, leading to cos_similarity = `nan`
                if hasattr(self, "zero_init_hidden_state") and "decoder_hidden_states" in key:
                    model_batched_output[key] = model_batched_output[key][1:]
                    model_row_output[key] = model_row_output[key][1:]
                recursive_check(model_batched_output[key], model_row_output[key], model_name, key)


# We will verify our results on an image of cute cats
def prepare_img():
    image = Image.open("./tests/fixtures/tests_samples/COCO/000000039769.png")
    return image


@require_mindspore
@require_vision
@slow
class DPTModelIntegrationTest(unittest.TestCase):
    def test_inference_depth_estimation(self):
        image_processor = DPTImageProcessor.from_pretrained("Intel/dpt-hybrid-midas")
        model = DPTForDepthEstimation.from_pretrained("Intel/dpt-hybrid-midas")

        image = prepare_img()
        inputs = image_processor(images=image, return_tensors="ms")

        # forward pass
        outputs = model(**inputs)
        predicted_depth = outputs.predicted_depth

        # verify the predicted depth
        expected_shape = (1, 384, 384)
        self.assertEqual(predicted_depth.shape, expected_shape)

        expected_slice = mindspore.Tensor(
            [[[5.6437, 5.6146, 5.6511], [5.4371, 5.5649, 5.5958], [5.5215, 5.5184, 5.5293]]]
        )

        self.assertTrue(
            np.allclose((outputs.predicted_depth[:3, :3, :3] / 100).asnumpy(), expected_slice.asnumpy(), atol=1e-4))
