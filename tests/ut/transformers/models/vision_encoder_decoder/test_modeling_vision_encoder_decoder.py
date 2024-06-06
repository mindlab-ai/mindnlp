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

import tempfile
import unittest


from mindnlp.utils.testing_utils import (
    require_mindspore,
    require_vision,
    slow,
    to_2tuple,
    is_vision_available,
    is_mindspore_available,
)

from ...test_modeling_common import floats_tensor, ids_tensor, random_attention_mask
from ..bert.test_modeling_bert import BertModelTester
from ..vit.test_modeling_vit import ViTModelTester


if is_mindspore_available():
    import numpy as np
    import mindspore as ms

    from mindnlp.transformers import (
        AutoTokenizer,
        BertLMHeadModel,
        VisionEncoderDecoderConfig,
        VisionEncoderDecoderModel,
        ViTModel,
    )
    from mindnlp.transformers.modeling_outputs import BaseModelOutput


if is_vision_available():
    from PIL import Image

    from mindnlp.transformers import ViTImageProcessor


@require_mindspore
class EncoderDecoderMixin:
    def get_encoder_decoder_model(self, config, decoder_config):
        pass

    def prepare_config_and_inputs(self):
        pass

    def get_pretrained_model_and_inputs(self):
        pass

    def check_encoder_decoder_model_from_pretrained_configs(
        self, config, decoder_config, decoder_input_ids, decoder_attention_mask, pixel_values=None, **kwargs
    ):
        encoder_decoder_config = VisionEncoderDecoderConfig.from_encoder_decoder_configs(config, decoder_config)
        self.assertTrue(encoder_decoder_config.decoder.is_decoder)

        enc_dec_model = VisionEncoderDecoderModel(encoder_decoder_config)
        enc_dec_model.set_train(False)

        self.assertTrue(enc_dec_model.config.is_encoder_decoder)

        outputs_encoder_decoder = enc_dec_model(
            pixel_values=pixel_values,
            decoder_input_ids=decoder_input_ids,
            decoder_attention_mask=decoder_attention_mask,
        )

        self.assertEqual(
            outputs_encoder_decoder["logits"].shape, (decoder_input_ids.shape + (decoder_config.vocab_size,))
        )

    def check_encoder_decoder_model(
        self, config, decoder_config, decoder_input_ids, decoder_attention_mask, pixel_values=None, **kwargs
    ):
        encoder_model, decoder_model = self.get_encoder_decoder_model(config, decoder_config)
        enc_dec_model = VisionEncoderDecoderModel(encoder=encoder_model, decoder=decoder_model)
        self.assertTrue(enc_dec_model.config.decoder.is_decoder)
        self.assertTrue(enc_dec_model.config.decoder.add_cross_attention)
        self.assertTrue(enc_dec_model.config.is_encoder_decoder)
        outputs_encoder_decoder = enc_dec_model(
            pixel_values=pixel_values,
            decoder_input_ids=decoder_input_ids,
            decoder_attention_mask=decoder_attention_mask,
            output_hidden_states=True,
        )
        self.assertEqual(
            outputs_encoder_decoder["logits"].shape, (decoder_input_ids.shape + (decoder_config.vocab_size,))
        )
        encoder_outputs = BaseModelOutput(last_hidden_state=outputs_encoder_decoder.encoder_hidden_states[-1])
        outputs_encoder_decoder = enc_dec_model(
            encoder_outputs=encoder_outputs,
            decoder_input_ids=decoder_input_ids,
            decoder_attention_mask=decoder_attention_mask,
        )

        self.assertEqual(
            outputs_encoder_decoder["logits"].shape, (decoder_input_ids.shape + (decoder_config.vocab_size,))
        )

    def check_encoder_decoder_model_from_pretrained(
        self,
        config,
        decoder_config,
        decoder_input_ids,
        decoder_attention_mask,
        return_dict,
        pixel_values=None,
        **kwargs,
    ):
        encoder_model, decoder_model = self.get_encoder_decoder_model(config, decoder_config)
        kwargs = {"encoder_model": encoder_model, "decoder_model": decoder_model, "return_dict": return_dict}
        enc_dec_model = VisionEncoderDecoderModel.from_encoder_decoder_pretrained(**kwargs)
        outputs_encoder_decoder = enc_dec_model(
            pixel_values=pixel_values,
            decoder_input_ids=decoder_input_ids,
            decoder_attention_mask=decoder_attention_mask,
            output_hidden_states=True,
            return_dict=True,
        )

        self.assertEqual(
            outputs_encoder_decoder["logits"].shape, (decoder_input_ids.shape + (decoder_config.vocab_size,))
        )

    def check_save_and_load(
        self, config, decoder_config, decoder_input_ids, decoder_attention_mask, pixel_values=None, **kwargs
    ):
        encoder_model, decoder_model = self.get_encoder_decoder_model(config, decoder_config)
        enc_dec_model = VisionEncoderDecoderModel(encoder=encoder_model, decoder=decoder_model)
        enc_dec_model.set_train(False)
        outputs = enc_dec_model(
            pixel_values=pixel_values,
            decoder_input_ids=decoder_input_ids,
            decoder_attention_mask=decoder_attention_mask,
        )
        out_2 = outputs[0].numpy()
        out_2[np.isnan(out_2)] = 0

        with tempfile.TemporaryDirectory() as tmpdirname:
            enc_dec_model.save_pretrained(tmpdirname)
            enc_dec_model = VisionEncoderDecoderModel.from_pretrained(tmpdirname)

            after_outputs = enc_dec_model(
                pixel_values=pixel_values,
                decoder_input_ids=decoder_input_ids,
                decoder_attention_mask=decoder_attention_mask,
            )
            out_1 = after_outputs[0].numpy()
            out_1[np.isnan(out_1)] = 0
            max_diff = np.amax(np.abs(out_1 - out_2))
            self.assertLessEqual(max_diff, 1e-5)

    def check_save_and_load_encoder_decoder_model(
        self, config, decoder_config, decoder_input_ids, decoder_attention_mask, pixel_values=None, **kwargs
    ):
        encoder_model, decoder_model = self.get_encoder_decoder_model(config, decoder_config)
        enc_dec_model = VisionEncoderDecoderModel(encoder=encoder_model, decoder=decoder_model)
        enc_dec_model.set_train(False)
        outputs = enc_dec_model(
            pixel_values=pixel_values,
            decoder_input_ids=decoder_input_ids,
            decoder_attention_mask=decoder_attention_mask,
        )
        out_2 = outputs[0].numpy()
        out_2[np.isnan(out_2)] = 0

        with tempfile.TemporaryDirectory() as encoder_tmp_dirname, tempfile.TemporaryDirectory() as decoder_tmp_dirname:
            enc_dec_model.encoder.save_pretrained(encoder_tmp_dirname)
            enc_dec_model.decoder.save_pretrained(decoder_tmp_dirname)
            VisionEncoderDecoderModel.from_encoder_decoder_pretrained(
                encoder_pretrained_model_name_or_path=encoder_tmp_dirname,
                decoder_pretrained_model_name_or_path=decoder_tmp_dirname,
            )

            after_outputs = enc_dec_model(
                pixel_values=pixel_values,
                decoder_input_ids=decoder_input_ids,
                decoder_attention_mask=decoder_attention_mask,
            )
            out_1 = after_outputs[0].numpy()
            out_1[np.isnan(out_1)] = 0
            max_diff = np.amax(np.abs(out_1 - out_2))
            self.assertLessEqual(max_diff, 1e-5)

    def check_encoder_decoder_model_output_attentions(
        self,
        config,
        decoder_config,
        decoder_input_ids,
        decoder_attention_mask,
        labels=None,
        pixel_values=None,
        **kwargs,
    ):
        # make the decoder inputs a different shape from the encoder inputs to harden the test
        decoder_input_ids = decoder_input_ids[:, :-1]
        decoder_attention_mask = decoder_attention_mask[:, :-1]
        encoder_model, decoder_model = self.get_encoder_decoder_model(config, decoder_config)
        enc_dec_model = VisionEncoderDecoderModel(encoder=encoder_model, decoder=decoder_model)
        outputs_encoder_decoder = enc_dec_model(
            pixel_values=pixel_values,
            decoder_input_ids=decoder_input_ids,
            decoder_attention_mask=decoder_attention_mask,
            output_attentions=True,
        )

        encoder_attentions = outputs_encoder_decoder["encoder_attentions"]
        self.assertEqual(len(encoder_attentions), config.num_hidden_layers)

        # in ViT, the seq_len equals the number of patches + 1 (we add 1 for the [CLS] token)
        image_size = to_2tuple(encoder_model.config.image_size)
        patch_size = to_2tuple(encoder_model.config.patch_size)
        num_patches = (image_size[1] // patch_size[1]) * (image_size[0] // patch_size[0])
        seq_len = num_patches + 1
        self.assertEqual(encoder_attentions[0].shape[-3:], (config.num_attention_heads, seq_len, seq_len))

        decoder_attentions = outputs_encoder_decoder["decoder_attentions"]
        num_decoder_layers = (
            decoder_config.num_decoder_layers
            if hasattr(decoder_config, "num_decoder_layers")
            else decoder_config.num_hidden_layers
        )
        self.assertEqual(len(decoder_attentions), num_decoder_layers)

        self.assertEqual(
            decoder_attentions[0].shape[-3:],
            (decoder_config.num_attention_heads, decoder_input_ids.shape[-1], decoder_input_ids.shape[-1]),
        )

        cross_attentions = outputs_encoder_decoder["cross_attentions"]
        self.assertEqual(len(cross_attentions), num_decoder_layers)

        cross_attention_input_seq_len = decoder_input_ids.shape[-1]
        self.assertEqual(
            cross_attentions[0].shape[-3:],
            (decoder_config.num_attention_heads, cross_attention_input_seq_len, seq_len),
        )

    def check_encoder_decoder_model_generate(self, config, decoder_config, pixel_values=None, **kwargs):
        encoder_model, decoder_model = self.get_encoder_decoder_model(config, decoder_config)
        enc_dec_model = VisionEncoderDecoderModel(encoder=encoder_model, decoder=decoder_model)

        # Generate until max length
        if hasattr(enc_dec_model.config, "eos_token_id"):
            enc_dec_model.config.eos_token_id = None
        if hasattr(enc_dec_model.config, "decoder") and hasattr(enc_dec_model.config.decoder, "eos_token_id"):
            enc_dec_model.config.decoder.eos_token_id = None
        if hasattr(enc_dec_model.generation_config, "eos_token_id"):
            enc_dec_model.generation_config.eos_token_id = None

        inputs = pixel_values

        # Bert does not have a bos token id, so use pad_token_id instead
        generated_output = enc_dec_model.generate(
            inputs, decoder_start_token_id=enc_dec_model.config.decoder.pad_token_id
        )
        self.assertEqual(generated_output.shape, (inputs.shape[0],) + (decoder_config.max_length,))

    def test_encoder_decoder_model(self):
        input_ids_dict = self.prepare_config_and_inputs()
        self.check_encoder_decoder_model(**input_ids_dict)

    def test_encoder_decoder_model_from_pretrained_configs(self):
        input_ids_dict = self.prepare_config_and_inputs()
        self.check_encoder_decoder_model_from_pretrained_configs(**input_ids_dict)

    def test_encoder_decoder_model_from_pretrained(self):
        input_ids_dict = self.prepare_config_and_inputs()
        self.check_encoder_decoder_model_from_pretrained(**input_ids_dict, return_dict=False)

    def test_encoder_decoder_model_from_pretrained_return_dict(self):
        input_ids_dict = self.prepare_config_and_inputs()
        self.check_encoder_decoder_model_from_pretrained(**input_ids_dict, return_dict=True)

    def test_save_and_load_from_pretrained(self):
        input_ids_dict = self.prepare_config_and_inputs()
        self.check_save_and_load(**input_ids_dict)

    def test_save_and_load_from_encoder_decoder_pretrained(self):
        input_ids_dict = self.prepare_config_and_inputs()
        self.check_save_and_load_encoder_decoder_model(**input_ids_dict)

    def test_encoder_decoder_model_output_attentions(self):
        input_ids_dict = self.prepare_config_and_inputs()
        self.check_encoder_decoder_model_output_attentions(**input_ids_dict)

    def test_encoder_decoder_model_generate(self):
        input_ids_dict = self.prepare_config_and_inputs()
        self.check_encoder_decoder_model_generate(**input_ids_dict)

    @slow
    def test_real_model_save_load_from_pretrained(self):
        model_2, inputs = self.get_pretrained_model_and_inputs()

        outputs = model_2(**inputs)
        out_2 = outputs[0].numpy()
        out_2[np.isnan(out_2)] = 0

        with tempfile.TemporaryDirectory() as tmp_dirname:
            model_2.save_pretrained(tmp_dirname)
            model_1 = VisionEncoderDecoderModel.from_pretrained(tmp_dirname)

            after_outputs = model_1(**inputs)
            out_1 = after_outputs[0].numpy()
            out_1[np.isnan(out_1)] = 0
            max_diff = np.amax(np.abs(out_1 - out_2))
            self.assertLessEqual(max_diff, 1e-5)


@require_mindspore
class ViT2BertModelTest(EncoderDecoderMixin, unittest.TestCase):
    def get_pretrained_model_and_inputs(self):
        model = VisionEncoderDecoderModel.from_encoder_decoder_pretrained(
            encoder_pretrained_model_name_or_path="hf-internal-testing/tiny-random-vit",
            decoder_pretrained_model_name_or_path="hf-internal-testing/tiny-bert"
        )
        batch_size = 13
        pixel_values = floats_tensor(
            [
                batch_size,
                model.encoder.config.num_channels,
                model.encoder.config.image_size,
                model.encoder.config.image_size,
            ]
        )
        # for ViT, the sequence length is equal to the number of patches + 1 (for the [CLS] token)
        decoder_input_ids = ids_tensor([batch_size, 4], model.decoder.config.vocab_size)
        decoder_attention_mask = random_attention_mask([batch_size, 4])
        inputs = {
            "pixel_values": pixel_values,
            "decoder_input_ids": decoder_input_ids,
            "decoder_attention_mask": decoder_attention_mask,
        }

        return model, inputs

    def get_encoder_decoder_model(self, config, decoder_config):
        encoder_model = ViTModel(config).set_train(False)
        decoder_model = BertLMHeadModel(decoder_config).set_train(False)
        return encoder_model, decoder_model

    def prepare_config_and_inputs(self):
        vit_model_tester = ViTModelTester(self)
        bert_model_tester = BertModelTester(self)
        encoder_config_and_inputs = vit_model_tester.prepare_config_and_inputs()
        decoder_config_and_inputs = bert_model_tester.prepare_config_and_inputs_for_decoder()

        config, pixel_values, _ = encoder_config_and_inputs

        (
            decoder_config,
            decoder_input_ids,
            decoder_token_type_ids,
            decoder_input_mask,
            decoder_sequence_labels,
            decoder_token_labels,
            decoder_choice_labels,
            encoder_attention_mask,
            _,
        ) = decoder_config_and_inputs

        # make sure that cross attention layers are added
        decoder_config.add_cross_attention = True
        return {
            "config": config,
            "pixel_values": pixel_values,
            "decoder_config": decoder_config,
            "decoder_input_ids": decoder_input_ids,
            "decoder_token_type_ids": decoder_token_type_ids,
            "decoder_attention_mask": decoder_input_mask,
            "decoder_sequence_labels": decoder_sequence_labels,
            "decoder_token_labels": decoder_token_labels,
            "decoder_choice_labels": decoder_choice_labels,
            "labels": decoder_token_labels,
        }


@require_vision
@require_mindspore
class ViT2GPT2ModelIntegrationTest(unittest.TestCase):
    @slow
    def test_inference_coco_en(self):
        loc = "ydshieh/vit-gpt2-coco-en"

        image_processor = ViTImageProcessor.from_pretrained(loc)
        tokenizer = AutoTokenizer.from_pretrained(loc)
        model = VisionEncoderDecoderModel.from_pretrained(loc)
        model.set_train(False)

        # We will verify our results on an image of cute cats
        img = Image.open("./tests/fixtures/tests_samples/COCO/000000039769.png")
        pixel_values = image_processor(images=img, return_tensors="ms").pixel_values

        decoder_input_ids = ms.tensor([[model.config.decoder_start_token_id]])

        logits = model(pixel_values, decoder_input_ids)[0].detach().numpy()

        # verify the logits
        expected_shape = (1, 1, model.config.decoder.vocab_size)
        self.assertEqual(logits.shape, expected_shape)

        EXPECTED_LOGIT_SLICE = np.array(
            [
                -38.705807,
                -30.639929,
                -31.41903,
                -39.012012,
                -38.38696,
                -34.887207,
                -33.290855,
                -35.68447,
                -38.508484,
                -36.124645,
            ]
        )
        max_diff = np.amax(np.abs(logits[0, 0, :10] - EXPECTED_LOGIT_SLICE))
        self.assertLessEqual(max_diff, 1e-4)

        def generate_step(pixel_values):
            outputs = model.generate(
                pixel_values, max_length=16, num_beams=4, return_dict_in_generate=True, output_scores=True
            )
            output_ids = outputs.sequences
            preds = tokenizer.batch_decode(output_ids, skip_special_tokens=True)
            preds = [pred.strip() for pred in preds]

            return preds, outputs.sequences_scores.detach().numpy()

        preds, scores = generate_step(pixel_values)

        EXPECTED_SCORES = np.array([-0.5956343])
        max_diff = np.amax(np.abs(scores - EXPECTED_SCORES))
        self.assertLessEqual(max_diff, 1e-4)

        # should produce
        # ["a cat laying on top of a couch next to another cat"]
        self.assertEqual(preds, ["a cat laying on top of a couch next to another cat"])
