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
# ============================================================================
import inspect
import unittest
from typing import List
import numpy as np
from mindspore import ops

from mindnlp.transformers import SuperPointConfig
from mindnlp.utils.testing_utils import slow, require_vision, require_mindspore, is_mindspore_available, is_vision_available
from mindnlp.utils import cached_property
from ...test_configuration_common import ConfigTester
from ...test_modeling_common import ModelTesterMixin, floats_tensor

if is_mindspore_available():
    import mindspore
    from mindnlp.core import nn

    from mindnlp.transformers import (
        SuperPointForKeypointDetection,
    )
mindspore.set_context(pynative_synchronize=True)

if is_vision_available():
    from PIL import Image

    from mindnlp.transformers import AutoImageProcessor


class SuperPointModelTester:
    def __init__(
        self,
        parent,
        batch_size=3,
        image_width=80,
        image_height=60,
        encoder_hidden_sizes: List[int] = [32, 32, 64, 64],
        decoder_hidden_size: int = 128,
        keypoint_decoder_dim: int = 65,
        descriptor_decoder_dim: int = 128,
        keypoint_threshold: float = 0.005,
        max_keypoints: int = -1,
        nms_radius: int = 4,
        border_removal_distance: int = 4,
    ):
        self.parent = parent
        self.batch_size = batch_size
        self.image_width = image_width
        self.image_height = image_height

        self.encoder_hidden_sizes = encoder_hidden_sizes
        self.decoder_hidden_size = decoder_hidden_size
        self.keypoint_decoder_dim = keypoint_decoder_dim
        self.descriptor_decoder_dim = descriptor_decoder_dim
        self.keypoint_threshold = keypoint_threshold
        self.max_keypoints = max_keypoints
        self.nms_radius = nms_radius
        self.border_removal_distance = border_removal_distance

    def prepare_config_and_inputs(self):
        # SuperPoint expects a grayscale image as input
        pixel_values = floats_tensor([self.batch_size, 3, self.image_height, self.image_width])
        config = self.get_config()
        return config, pixel_values

    def get_config(self):
        return SuperPointConfig(
            encoder_hidden_sizes=self.encoder_hidden_sizes,
            decoder_hidden_size=self.decoder_hidden_size,
            keypoint_decoder_dim=self.keypoint_decoder_dim,
            descriptor_decoder_dim=self.descriptor_decoder_dim,
            keypoint_threshold=self.keypoint_threshold,
            max_keypoints=self.max_keypoints,
            nms_radius=self.nms_radius,
            border_removal_distance=self.border_removal_distance,
        )

    def create_and_check_keypoint_detection(self, config, pixel_values):
        model = SuperPointForKeypointDetection(config=config)
        model.set_train(False)
        result = model(pixel_values)
        self.parent.assertEqual(result.keypoints.shape[0], self.batch_size)
        self.parent.assertEqual(result.keypoints.shape[-1], 2)

        result = model(pixel_values, output_hidden_states=True)
        self.parent.assertEqual(
            result.hidden_states[-1].shape,
            (
                self.batch_size,
                self.encoder_hidden_sizes[-1],
                self.image_height // 8,
                self.image_width // 8,
            ),
        )

    def prepare_config_and_inputs_for_common(self):
        config_and_inputs = self.prepare_config_and_inputs()
        config, pixel_values = config_and_inputs
        inputs_dict = {"pixel_values": pixel_values}
        return config, inputs_dict


@require_mindspore
class SuperPointModelTest(ModelTesterMixin, unittest.TestCase):
    all_model_classes = (SuperPointForKeypointDetection,) if is_mindspore_available() else ()
    all_generative_model_classes = () if is_mindspore_available() else ()

    fx_compatible = False
    test_pruning = False
    test_resize_embeddings = False
    test_head_masking = False
    has_attentions = False
    from_pretrained_id = "magic-leap-community/superpoint"

    def setUp(self):
        self.model_tester = SuperPointModelTester(self)
        self.config_tester = ConfigTester(
            self,
            config_class=SuperPointConfig,
            has_text_modality=False,
            hidden_size=37,
            common_properties=["encoder_hidden_sizes", "decoder_hidden_size"],
        )

    def test_config(self):
        self.config_tester.run_common_tests()

    @unittest.skip(reason="SuperPointForKeypointDetection does not use inputs_embeds")
    def test_inputs_embeds(self):
        pass

    @unittest.skip(reason="NotImplemented")
    def test_model_common_attributes(self):
        pass

    @unittest.skip(reason="SuperPointForKeypointDetection does not support input and output embeddings")
    def test_model_get_set_embeddings(self):
        pass

    @unittest.skip(reason="SuperPointForKeypointDetection does not use feedforward chunking")
    def test_feed_forward_chunking(self):
        pass

    @unittest.skip(reason="SuperPointForKeypointDetection does not support training")
    def test_training(self):
        pass

    @unittest.skip(reason="SuperPointForKeypointDetection does not support training")
    def test_training_gradient_checkpointing(self):
        pass

    @unittest.skip(reason="SuperPointForKeypointDetection does not support training")
    def test_training_gradient_checkpointing_use_reentrant(self):
        pass

    @unittest.skip(reason="SuperPointForKeypointDetection does not support training")
    def test_training_gradient_checkpointing_use_reentrant_false(self):
        pass

    @unittest.skip(reason="SuperPoint does not output any loss term in the forward pass")
    def test_retain_grad_hidden_states_attentions(self):
        pass

    def test_keypoint_detection(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_keypoint_detection(*config_and_inputs)

    def test_forward_signature(self):
        config, _ = self.model_tester.prepare_config_and_inputs()
        for model_class in self.all_model_classes:
            model = model_class(config)
            signature = inspect.signature(model.forward)
            # signature.parameters is an OrderedDict => so arg_names order is deterministic
            arg_names = [*signature.parameters.keys()]

            expected_arg_names = ["pixel_values"]
            self.assertListEqual(arg_names[:1], expected_arg_names)

    def test_hidden_states_output(self):
        def check_hidden_states_output(inputs_dict, config, model_class):
            model = model_class(config)
            model.set_train(False)

            with mindspore._no_grad():
                outputs = model(**self._prepare_for_class(inputs_dict, model_class))

            hidden_states = outputs.hidden_states

            # SuperPoint's feature maps are of shape (batch_size, num_channels, width, height)
            for i, conv_layer_size in enumerate(self.model_tester.encoder_hidden_sizes[:-1]):
                self.assertListEqual(
                    list(hidden_states[i].shape[-3:]),
                    [
                        conv_layer_size,
                        self.model_tester.image_height // (2 ** (i + 1)),
                        self.model_tester.image_width // (2 ** (i + 1)),
                    ],
                )

        config, inputs_dict = self.model_tester.prepare_config_and_inputs_for_common()

        for model_class in self.all_model_classes:
            inputs_dict["output_hidden_states"] = True
            check_hidden_states_output(inputs_dict, config, model_class)

            # check that output_hidden_states also work using config
            del inputs_dict["output_hidden_states"]
            config.output_hidden_states = True

            check_hidden_states_output(inputs_dict, config, model_class)

    def test_model_from_pretrained(self):
        model = SuperPointForKeypointDetection.from_pretrained(self.from_pretrained_id,from_pt = True)
        self.assertIsNotNone(model)

    def test_forward_labels_should_be_none(self):
        config, inputs_dict = self.model_tester.prepare_config_and_inputs_for_common()
        for model_class in self.all_model_classes:
            model = model_class(config)
            model.set_train(False)

            with mindspore._no_grad():
                model_inputs = self._prepare_for_class(inputs_dict, model_class)
                # Provide an arbitrary sized Tensor as labels to model inputs
                model_inputs["labels"] = ops.rand((128, 128))

                with self.assertRaises(ValueError) as cm:
                    model(**model_inputs)
                self.assertEqual(ValueError, cm.exception.__class__)


def prepare_imgs():
    image1 = Image.open("./tests/fixtures/tests_samples/COCO/000000039769.png")
    image2 = Image.open("./tests/fixtures/tests_samples/COCO/000000004016.png")
    return [image1,image2]


@require_mindspore
@require_vision
class SuperPointModelIntegrationTest(unittest.TestCase):
    @cached_property
    def default_image_processor(self):
        return AutoImageProcessor.from_pretrained("magic-leap-community/superpoint") if is_vision_available() else None

    def test_inference(self):
        model = SuperPointForKeypointDetection.from_pretrained("magic-leap-community/superpoint")
        preprocessor = self.default_image_processor
        images = prepare_imgs()
        inputs = preprocessor(images=images, return_tensors="ms")     #return_tensors="pt"  to  return_tensors="ms"
        with mindspore._no_grad():
            outputs = model(**inputs)
        expected_number_keypoints_image0 = 567
        expected_number_keypoints_image1 = 830
        expected_max_number_keypoints = max(expected_number_keypoints_image0, expected_number_keypoints_image1)
        expected_keypoints_shape = (len(images), expected_max_number_keypoints,2)
        expected_scores_shape =(
                len(images),
                expected_max_number_keypoints,
            )
        expected_descriptors_shape = (len(images), expected_max_number_keypoints, 256)
        self.assertEqual(outputs.keypoints.shape, expected_keypoints_shape)
        self.assertEqual(outputs.scores.shape, expected_scores_shape)
        self.assertEqual(outputs.descriptors.shape, expected_descriptors_shape)
        expected_keypoints_image0_values = mindspore.tensor([[480.0, 9.0], [494.0, 9.0], [489.0, 16.0]])
        expected_scores_image0_values = mindspore.tensor(
            [0.0064, 0.0137, 0.0589, 0.0723, 0.5166, 0.0174, 0.1515, 0.2054, 0.0334]
        )
        expected_descriptors_image0_value = mindspore.tensor(-0.1096)
        predicted_keypoints_image0_values = outputs.keypoints[0, :3]
        predicted_scores_image0_values = outputs.scores[0, :9]
        predicted_descriptors_image0_value = outputs.descriptors[0, 0, 0]
        # Check output values
        self.assertTrue(
            np.allclose(
                predicted_keypoints_image0_values.asnumpy(),
                expected_keypoints_image0_values.asnumpy(),
                atol=1e-3,
            )
        )
        self.assertTrue(np.allclose(predicted_scores_image0_values.asnumpy(), expected_scores_image0_values.asnumpy(), atol=1e-3))
        self.assertTrue(
            np.allclose(
                predicted_descriptors_image0_value.asnumpy(),
                expected_descriptors_image0_value.asnumpy(),
                atol=1e-3,
            )
        )
        # Check mask values
        self.assertTrue(outputs.mask[0, expected_number_keypoints_image0].item() == 1)
        self.assertTrue(outputs.mask[0, expected_number_keypoints_image0+1].item() == 0)
        self.assertTrue(ops.all(outputs.mask[0, : expected_number_keypoints_image0 - 1]))
        self.assertTrue(ops.all(ops.logical_not(outputs.mask[0, expected_number_keypoints_image0+1:])))
        self.assertTrue(ops.all(outputs.mask[1]))
