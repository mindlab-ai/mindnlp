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
"""Testing suite for the MindSpore XCLIP model."""

import inspect
import os
import tempfile
import unittest

import numpy as np
from huggingface_hub import hf_hub_download

from mindspore import ops

from mindnlp.transformers import XCLIPConfig, XCLIPTextConfig, XCLIPVisionConfig
from mindnlp.utils.testing_utils import require_mindspore, require_vision, slow
from mindnlp.utils import is_mindspore_available, is_vision_available
from mindnlp.core.serialization import safe_load_file, safe_save_file

from ...test_configuration_common import ConfigTester
from ...test_modeling_common import ModelTesterMixin, _config_zero_init, floats_tensor, ids_tensor, random_attention_mask
# from ...test_pipeline_mixin import PipelineTesterMixin


if is_mindspore_available():
    import mindspore as ms
    from mindnlp.core import nn

    from mindnlp.transformers import XCLIPModel, XCLIPTextModel, XCLIPVisionModel


if is_vision_available():
    from mindnlp.transformers import XCLIPProcessor


class XCLIPVisionModelTester:
    def __init__(
        self,
        parent,
        batch_size=8,
        image_size=30,
        patch_size=2,
        num_channels=3,
        num_frames=8,  # important; the batch size * time must be divisible by the number of frames
        is_training=True,
        hidden_size=32,
        num_hidden_layers=2,
        num_attention_heads=4,
        intermediate_size=37,
        mit_hidden_size=64,
        dropout=0.1,
        attention_dropout=0.1,
        initializer_range=0.02,
        scope=None,
    ):
        self.parent = parent
        self.batch_size = batch_size
        self.image_size = image_size
        self.patch_size = patch_size
        self.num_channels = num_channels
        self.num_frames = num_frames
        self.is_training = is_training
        self.hidden_size = hidden_size
        self.num_hidden_layers = num_hidden_layers
        self.num_attention_heads = num_attention_heads
        self.intermediate_size = intermediate_size
        self.mit_hidden_size = mit_hidden_size
        self.dropout = dropout
        self.attention_dropout = attention_dropout
        self.initializer_range = initializer_range
        self.scope = scope

        # in ViT, the seq length equals the number of patches + 1 (we add 1 for the [CLS] token)
        num_patches = (image_size // patch_size) ** 2
        self.seq_length = num_patches + 1

    def prepare_config_and_inputs(self):
        pixel_values = floats_tensor(
            [self.batch_size * self.num_frames, self.num_channels,
                self.image_size, self.image_size]
        )
        config = self.get_config()

        return config, pixel_values

    def get_config(self):
        return XCLIPVisionConfig(
            image_size=self.image_size,
            patch_size=self.patch_size,
            num_channels=self.num_channels,
            num_frames=self.num_frames,
            hidden_size=self.hidden_size,
            num_hidden_layers=self.num_hidden_layers,
            num_attention_heads=self.num_attention_heads,
            intermediate_size=self.intermediate_size,
            mit_hidden_size=self.mit_hidden_size,
            dropout=self.dropout,
            attention_dropout=self.attention_dropout,
            initializer_range=self.initializer_range,
        )

    def create_and_check_model(self, config, pixel_values):
        model = XCLIPVisionModel(config=config)
        model.set_train(False)
        result = model(pixel_values)
        # expected sequence length = num_patches + 1 (we add 1 for the [CLS] token)
        image_size = (self.image_size, self.image_size)
        patch_size = (self.patch_size, self.patch_size)
        num_patches = (image_size[1] // patch_size[1]) * \
            (image_size[0] // patch_size[0])
        self.parent.assertEqual(
            result.last_hidden_state.shape, (self.batch_size *
                                             self.num_frames, num_patches + 1, self.hidden_size)
        )
        self.parent.assertEqual(
            result.pooler_output.shape, (self.batch_size * self.num_frames, self.hidden_size))

    def prepare_config_and_inputs_for_common(self):
        config_and_inputs = self.prepare_config_and_inputs()
        config, pixel_values = config_and_inputs
        inputs_dict = {"pixel_values": pixel_values}
        return config, inputs_dict


@require_mindspore
class XCLIPVisionModelTest(ModelTesterMixin, unittest.TestCase):
    """
    Here we also overwrite some of the tests of test_modeling_common.py, as X-CLIP does not use input_ids, inputs_embeds,
    attention_mask and seq_length.
    """

    all_model_classes = (XCLIPVisionModel,) if is_mindspore_available() else ()
    fx_compatible = False
    test_pruning = False
    test_resize_embeddings = False
    test_head_masking = False

    def setUp(self):
        self.model_tester = XCLIPVisionModelTester(self)
        self.config_tester = ConfigTester(
            self, config_class=XCLIPVisionConfig, has_text_modality=False, hidden_size=37
        )

    def test_config(self):
        self.config_tester.run_common_tests()

    @unittest.skip(reason="X-CLIP does not use inputs_embeds")
    def test_inputs_embeds(self):
        pass

    def test_model_get_set_embeddings(self):
        config, _ = self.model_tester.prepare_config_and_inputs_for_common()

        for model_class in self.all_model_classes:
            model = model_class(config)
            self.assertIsInstance(model.get_input_embeddings(), (nn.Module))
            x = model.get_output_embeddings()
            self.assertTrue(x is None or isinstance(x, nn.Linear))

    def test_forward_signature(self):
        config, _ = self.model_tester.prepare_config_and_inputs_for_common()

        for model_class in self.all_model_classes:
            model = model_class(config)
            signature = inspect.signature(model.forward)
            # signature.parameters is an OrderedDict => so arg_names order is deterministic
            arg_names = [*signature.parameters.keys()]

            expected_arg_names = ["pixel_values"]
            self.assertListEqual(arg_names[:1], expected_arg_names)

    def test_model(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_model(*config_and_inputs)

    def test_training(self):
        pass

    def test_training_gradient_checkpointing(self):
        pass

    @unittest.skip(
        reason="This architecure seem to not compute gradients properly when using GC, check: https://github.com/huggingface/transformers/pull/27124"
    )
    def test_training_gradient_checkpointing_use_reentrant(self):
        pass

    @unittest.skip(
        reason="This architecure seem to not compute gradients properly when using GC, check: https://github.com/huggingface/transformers/pull/27124"
    )
    def test_training_gradient_checkpointing_use_reentrant_false(self):
        pass

    @unittest.skip(reason="XCLIPVisionModel has no base class and is not available in MODEL_MAPPING")
    def test_save_load_fast_init_from_base(self):
        pass

    @unittest.skip(reason="XCLIPVisionModel has no base class and is not available in MODEL_MAPPING")
    def test_save_load_fast_init_to_base(self):
        pass

    @slow
    def test_model_from_pretrained(self):
        model_name = "microsoft/xclip-base-patch32"
        model = XCLIPVisionModel.from_pretrained(model_name)
        self.assertIsNotNone(model)

    def test_gradient_checkpointing_backward_compatibility(self):
        config, inputs_dict = self.model_tester.prepare_config_and_inputs_for_common()

        for model_class in self.all_model_classes:
            if not model_class.supports_gradient_checkpointing:
                continue
            config.gradient_checkpointing = True
            model = model_class(config)
            self.assertTrue(model.is_gradient_checkpointing)

    def test_attention_outputs(self):
        config, inputs_dict = self.model_tester.prepare_config_and_inputs_for_common()
        config.return_dict = True

        # we add 1 here due to the special message token in X-CLIP's vision encoder
        seq_len = getattr(self.model_tester, "seq_length", None) + 1
        encoder_seq_length = getattr(
            self.model_tester, "encoder_seq_length", seq_len)

        for model_class in self.all_model_classes:
            inputs_dict["output_attentions"] = True
            inputs_dict["output_hidden_states"] = False
            config.return_dict = True
            model = model_class(config)
            model.set_train(False)
            outputs = model(
                **self._prepare_for_class(inputs_dict, model_class))
            self.assertEqual(len(outputs.attentions),
                             self.model_tester.num_hidden_layers)

            # check that output_attentions also work using config
            del inputs_dict["output_attentions"]
            config.output_attentions = True
            model = model_class(config)
            model.set_train(False)
            outputs = model(
                **self._prepare_for_class(inputs_dict, model_class))
            self.assertEqual(len(outputs.attentions),
                             self.model_tester.num_hidden_layers)

            self.assertListEqual(
                list(outputs.attentions[0].shape[-3:]),
                [self.model_tester.num_attention_heads,
                    encoder_seq_length, encoder_seq_length],
            )
            out_len = len(outputs)

            # Check attention is always last and order is fine
            inputs_dict["output_attentions"] = True
            inputs_dict["output_hidden_states"] = True
            model = model_class(config)
            model.set_train(False)
            outputs = model(
                **self._prepare_for_class(inputs_dict, model_class))

            self.assertEqual(out_len + 1, len(outputs))

            self_attentions = outputs.attentions

            self.assertEqual(len(self_attentions),
                             self.model_tester.num_hidden_layers)
            self.assertListEqual(
                list(self_attentions[0].shape[-3:]),
                [self.model_tester.num_attention_heads,
                    encoder_seq_length, encoder_seq_length],
            )

    @unittest.skip('MindSpore need mpirun to launch multi-process for data_parallel')
    def test_multi_gpu_data_parallel_forward(self):
        pass


class XCLIPTextModelTester:
    def __init__(
        self,
        parent,
        batch_size=8,
        seq_length=7,
        is_training=True,
        use_input_mask=True,
        use_labels=True,
        vocab_size=99,
        hidden_size=32,
        num_hidden_layers=2,
        num_attention_heads=4,
        intermediate_size=37,
        dropout=0.1,
        attention_dropout=0.1,
        max_position_embeddings=512,
        initializer_range=0.02,
        scope=None,
    ):
        self.parent = parent
        self.batch_size = batch_size
        self.seq_length = seq_length
        self.is_training = is_training
        self.use_input_mask = use_input_mask
        self.use_labels = use_labels
        self.vocab_size = vocab_size
        self.hidden_size = hidden_size
        self.num_hidden_layers = num_hidden_layers
        self.num_attention_heads = num_attention_heads
        self.intermediate_size = intermediate_size
        self.dropout = dropout
        self.attention_dropout = attention_dropout
        self.max_position_embeddings = max_position_embeddings
        self.initializer_range = initializer_range
        self.scope = scope

    def prepare_config_and_inputs(self):
        input_ids = ids_tensor(
            [self.batch_size, self.seq_length], self.vocab_size)

        input_mask = None
        if self.use_input_mask:
            input_mask = random_attention_mask(
                [self.batch_size, self.seq_length])

        if input_mask is not None:
            batch_size, seq_length = input_mask.shape
            rnd_start_indices = np.random.randint(
                1, seq_length - 1, size=(batch_size,))
            for batch_idx, start_index in enumerate(rnd_start_indices):
                input_mask[int(batch_idx), :int(start_index)] = 1
                input_mask[int(batch_idx), int(start_index):] = 0

        config = self.get_config()

        return config, input_ids, input_mask

    def get_config(self):
        return XCLIPTextConfig(
            vocab_size=self.vocab_size,
            hidden_size=self.hidden_size,
            num_hidden_layers=self.num_hidden_layers,
            num_attention_heads=self.num_attention_heads,
            intermediate_size=self.intermediate_size,
            dropout=self.dropout,
            attention_dropout=self.attention_dropout,
            max_position_embeddings=self.max_position_embeddings,
            initializer_range=self.initializer_range,
        )

    def create_and_check_model(self, config, input_ids, input_mask):
        model = XCLIPTextModel(config=config)
        model.set_train(False)
        result = model(input_ids, attention_mask=input_mask)
        result = model(input_ids)
        self.parent.assertEqual(result.last_hidden_state.shape,
                                (self.batch_size, self.seq_length, self.hidden_size))
        self.parent.assertEqual(
            result.pooler_output.shape, (self.batch_size, self.hidden_size))

    def prepare_config_and_inputs_for_common(self):
        config_and_inputs = self.prepare_config_and_inputs()
        config, input_ids, input_mask = config_and_inputs
        inputs_dict = {"input_ids": input_ids, "attention_mask": input_mask}
        return config, inputs_dict


@require_mindspore
class XCLIPTextModelTest(ModelTesterMixin, unittest.TestCase):
    all_model_classes = (XCLIPTextModel,) if is_mindspore_available() else ()
    fx_compatible = False
    test_pruning = False
    test_head_masking = False

    def setUp(self):
        self.model_tester = XCLIPTextModelTester(self)
        self.config_tester = ConfigTester(
            self, config_class=XCLIPTextConfig, hidden_size=37)

    def test_config(self):
        self.config_tester.run_common_tests()

    def test_model(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_model(*config_and_inputs)

    def test_training(self):
        pass

    def test_training_gradient_checkpointing(self):
        pass

    @unittest.skip(
        reason="This architecure seem to not compute gradients properly when using GC, check: https://github.com/huggingface/transformers/pull/27124"
    )
    def test_training_gradient_checkpointing_use_reentrant(self):
        pass

    @unittest.skip(
        reason="This architecure seem to not compute gradients properly when using GC, check: https://github.com/huggingface/transformers/pull/27124"
    )
    def test_training_gradient_checkpointing_use_reentrant_false(self):
        pass

    @unittest.skip(reason="X-CLIP does not use inputs_embeds")
    def test_inputs_embeds(self):
        pass

    @unittest.skip(reason="XCLIPTextModel has no base class and is not available in MODEL_MAPPING")
    def test_save_load_fast_init_from_base(self):
        pass

    @unittest.skip(reason="XCLIPTextModel has no base class and is not available in MODEL_MAPPING")
    def test_save_load_fast_init_to_base(self):
        pass

    @slow
    def test_model_from_pretrained(self):
        model_name = "microsoft/xclip-base-patch32"
        model = XCLIPTextModel.from_pretrained(model_name)
        self.assertIsNotNone(model)


class XCLIPModelTester:
    def __init__(
        self,
        parent,
        text_kwargs=None,
        vision_kwargs=None,
        projection_dim=64,
        mit_hidden_size=64,
        is_training=True,
    ):
        if text_kwargs is None:
            text_kwargs = {}
        if vision_kwargs is None:
            vision_kwargs = {}

        self.parent = parent
        self.projection_dim = projection_dim
        self.mit_hidden_size = mit_hidden_size
        self.text_model_tester = XCLIPTextModelTester(parent, **text_kwargs)
        self.vision_model_tester = XCLIPVisionModelTester(
            parent, **vision_kwargs)
        # need bs for batching_equivalence test
        self.batch_size = self.text_model_tester.batch_size
        self.is_training = is_training

    def prepare_config_and_inputs(self):
        text_config, input_ids, attention_mask = self.text_model_tester.prepare_config_and_inputs()
        vision_config, _ = self.vision_model_tester.prepare_config_and_inputs()
        pixel_values = floats_tensor(
            [
                self.vision_model_tester.batch_size,
                self.vision_model_tester.num_frames,
                self.vision_model_tester.num_channels,
                self.vision_model_tester.image_size,
                self.vision_model_tester.image_size,
            ]
        )

        config = self.get_config()

        return config, input_ids, attention_mask, pixel_values

    def get_config(self):
        return XCLIPConfig.from_text_vision_configs(
            self.text_model_tester.get_config(),
            self.vision_model_tester.get_config(),
            projection_dim=self.projection_dim,
        )

    def create_and_check_model(self, config, input_ids, attention_mask, pixel_values):
        model = XCLIPModel(config).set_train(False)
        result = model(input_ids, pixel_values, attention_mask)
        self.parent.assertEqual(
            result.logits_per_video.shape,
            (self.vision_model_tester.batch_size,
             self.text_model_tester.batch_size),
        )
        self.parent.assertEqual(
            result.logits_per_text.shape,
            (self.text_model_tester.batch_size,
             self.vision_model_tester.batch_size),
        )

    def prepare_config_and_inputs_for_common(self):
        config_and_inputs = self.prepare_config_and_inputs()
        config, input_ids, attention_mask, pixel_values = config_and_inputs
        inputs_dict = {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "pixel_values": pixel_values,
            "return_loss": True,
        }
        return config, inputs_dict


@require_mindspore
class XCLIPModelTest(ModelTesterMixin, unittest.TestCase):
    all_model_classes = (XCLIPModel,) if is_mindspore_available() else ()
    pipeline_model_mapping = {
        "feature-extraction": XCLIPModel} if is_mindspore_available() else {}
    fx_compatible = False
    test_head_masking = False
    test_pruning = False
    test_resize_embeddings = False
    test_attention_outputs = False
    test_torchscript = False
    maxdiff = None

    def setUp(self):
        self.model_tester = XCLIPModelTester(self)

    def test_model(self):
        config_and_inputs = self.model_tester.prepare_config_and_inputs()
        self.model_tester.create_and_check_model(*config_and_inputs)

    @unittest.skip(reason="Hidden_states is tested in individual model tests")
    def test_hidden_states_output(self):
        pass

    @unittest.skip(reason="Inputs_embeds is tested in individual model tests")
    def test_inputs_embeds(self):
        pass

    @unittest.skip(reason="Retain_grad is tested in individual model tests")
    def test_retain_grad_hidden_states_attentions(self):
        pass

    @unittest.skip(reason="XCLIPModel does not have input/output embeddings")
    def test_model_get_set_embeddings(self):
        pass

    @unittest.skip(reason="XCLIPModel does not support feedforward chunking")
    def test_feed_forward_chunking(self):
        pass

    # override as the `logit_scale`, `prompts_generator.alpha` parameters require special treatment
    def test_initialization(self):
        config, inputs_dict = self.model_tester.prepare_config_and_inputs_for_common()

        configs_no_init = _config_zero_init(config)
        for model_class in self.all_model_classes:
            model = model_class(config=configs_no_init)
            for name, param in model.parameters_and_names():
                if param.requires_grad:
                    # check if `logit_scale` is initilized as per the original implementation
                    if name == "logit_scale":
                        self.assertAlmostEqual(
                            param.data.item(),
                            np.log(1 / 0.07),
                            delta=1e-3,
                            msg=f"Parameter {name} of model {model_class} seems not properly initialized",
                        )
                    elif name == "prompts_generator.alpha":
                        self.assertAlmostEqual(
                            param.data.mean().item(), model.config.prompt_alpha)
                    else:
                        self.assertIn(
                            ((param.data.mean() * 1e9).round() / 1e9).item(),
                            [0.0, 1.0],
                            msg=f"Parameter {name} of model {model_class} seems not properly initialized",
                        )

    def _create_and_check_torchscript(self, config, inputs_dict):
        if not self.test_torchscript:
            return

        configs_no_init = _config_zero_init(
            config)  # To be sure we have no Nan
        configs_no_init.torchscript = True
        configs_no_init.return_dict = False
        for model_class in self.all_model_classes:
            model = model_class(config=configs_no_init)
            model.set_train(False)

            try:
                input_ids = inputs_dict["input_ids"]
                # X-CLIP needs pixel_values
                pixel_values = inputs_dict["pixel_values"]
                traced_model = ops.trace(model, (input_ids, pixel_values))
            except RuntimeError:
                self.fail("Couldn't trace module.")

            with tempfile.TemporaryDirectory() as tmp_dir_name:
                pt_file_name = os.path.join(
                    tmp_dir_name, "traced_model.safetensors")

                try:
                    safe_save_file(traced_model, pt_file_name)
                except Exception:
                    self.fail("Couldn't save module.")

                try:
                    loaded_model = safe_load_file(pt_file_name)
                except Exception:
                    self.fail("Couldn't load module.")

            model.set_train(False)

            loaded_model.set_train(False)

            model_state_dict = model.state_dict()
            loaded_model_state_dict = loaded_model.state_dict()

            non_persistent_buffers = {}
            for key in loaded_model_state_dict.keys():
                if key not in model_state_dict.keys():
                    non_persistent_buffers[key] = loaded_model_state_dict[key]

            loaded_model_state_dict = {
                key: value for key, value in loaded_model_state_dict.items() if key not in non_persistent_buffers
            }

            self.assertEqual(set(model_state_dict.keys()),
                             set(loaded_model_state_dict.keys()))

            model_buffers = list(model.buffers())
            for non_persistent_buffer in non_persistent_buffers.values():
                found_buffer = False
                for i, model_buffer in enumerate(model_buffers):
                    if ops.equal(non_persistent_buffer, model_buffer):
                        found_buffer = True
                        break

                self.assertTrue(found_buffer)
                model_buffers.pop(i)

            models_equal = True
            for layer_name, p1 in model_state_dict.items():
                p2 = loaded_model_state_dict[layer_name]
                if p1.data.ne(p2.data).sum() > 0:
                    models_equal = False

            self.assertTrue(models_equal)

    def test_load_vision_text_config(self):
        config, inputs_dict = self.model_tester.prepare_config_and_inputs_for_common()

        # Save XCLIPConfig and check if we can load XCLIPVisionConfig from it
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            config.save_pretrained(tmp_dir_name)
            vision_config = XCLIPVisionConfig.from_pretrained(tmp_dir_name)
            self.assertDictEqual(
                config.vision_config.to_dict(), vision_config.to_dict())

        # Save XCLIPConfig and check if we can load XCLIPTextConfig from it
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            config.save_pretrained(tmp_dir_name)
            text_config = XCLIPTextConfig.from_pretrained(tmp_dir_name)
            self.assertDictEqual(
                config.text_config.to_dict(), text_config.to_dict())

    @slow
    def test_model_from_pretrained(self):
        model_name = "microsoft/xclip-base-patch32"
        model = XCLIPModel.from_pretrained(model_name)
        self.assertIsNotNone(model)


# We will verify our results on a spaghetti video
def prepare_video():
    file = hf_hub_download(
        repo_id="hf-internal-testing/spaghetti-video", filename="eating_spaghetti_8_frames.npy", repo_type="dataset"
    )
    video = np.load(file)
    return list(video)


@require_vision
@require_mindspore
class XCLIPModelIntegrationTest(unittest.TestCase):
    @slow
    def test_inference(self):
        model_name = "microsoft/xclip-base-patch32"
        model = XCLIPModel.from_pretrained(model_name)
        processor = XCLIPProcessor.from_pretrained(model_name)

        video = prepare_video()
        inputs = processor(
            text=["playing sports", "eating spaghetti", "go shopping"], videos=video, return_tensors="ms", padding=True
        )

        # forward pass
        outputs = model(**inputs)

        # verify the logits
        self.assertEqual(
            outputs.logits_per_video.shape,
            (inputs.pixel_values.shape[0], inputs.input_ids.shape[0]),
        )
        self.assertEqual(
            outputs.logits_per_text.shape,
            (inputs.input_ids.shape[0], inputs.pixel_values.shape[0]),
        )

        expected_logits = ms.Tensor([[14.0181, 20.2771, 14.4776]])

        self.assertTrue(np.allclose(
            outputs.logits_per_video.asnumpy(), expected_logits.asnumpy(), atol=1e-3))
