# Copyright 2022 Huawei Technologies Co., Ltd
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
"""Test OPT"""
import gc
import os
import unittest
import pytest
import numpy as np
import mindspore
from mindspore.ops import functional
from mindspore import Tensor
from mindnlp.models.opt import OPTModel, OPTForCausalLM
from mindnlp.transforms.tokenizers import OPTTokenizer


class OPTModelIntegrationTests(unittest.TestCase):

    def test_inference_no_head(self):
        model = OPTModel.from_pretrained('facebook/opt-350m', from_pt=True, return_dict=True)
        input_ids = Tensor([[0, 31414, 232, 328, 740, 1140, 12695, 69, 46078, 1588, 2]], dtype=mindspore.int64)

        mindspore.set_context(device_target="GPU")

        functional.stop_gradient(model)
        output = model(input_ids=input_ids).last_hidden_state

        expected_shape = (1, 11, 512)
        assert (np.asarray(output.shape) == np.asarray(expected_shape)).all()
        # expected value works for CPU, as well as GPU (with TF32 disabled)
        expected_slice = Tensor(
            [
                [-0.28726277, -1.9241608, -0.3058734],
                [-1.2737825, -0.13332152, -0.18766522],
                [0.41159445, 0.1191957, -1.3107123],
            ]
        )
        assert np.allclose(output[0, :3, :3].numpy(), expected_slice.numpy(), atol=5e-4)


class OPTEmbeddingsTest(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.path_model = "facebook/opt-350m"

    def test_load_model(self):
        try:
            _ = OPTForCausalLM.from_pretrained(self.path_model, from_pt=True)
        except BaseException:
            self.fail("Failed loading model")

    def test_logits(self):
        model = OPTForCausalLM.from_pretrained(self.path_model, from_pt=True)
        model = model.set_train(False)
        tokenizer = OPTTokenizer.from_pretrained(self.path_model)

        prompts = np.asarray([
            "Today is a beautiful day and I want to",
            "In the city of",
            "Paris is the capital of France and",
            "Computers and mobile phones have taken",
        ])

        inputs = tokenizer(prompts)

        logits = model(Tensor(inputs['input_ids']), attention_mask=Tensor(inputs['attention_mask']))[0].mean(axis=-1)
        logits_meta = np.array(
            [
                [1.3851, -13.8923, -10.5229, -10.7533, -0.2309, -10.2384, -0.5365, -9.0947, -5.1670],
                [-4.7073, -10.6276, -3.9415, -21.5242, -0.2822, -0.2822, -0.2822, -0.2822, -0.2822],
                [0.6247, -3.4229, -8.9179, -1.4297, -14.1650, 1.4146, -9.0218, -0.2703, -0.2703],
                [6.4783, -1.9913, -10.7926, -2.3336, 1.5092, -0.9974, -6.8213, 1.3477, 1.3477],
            ]
        )
        assert np.allclose(logits.numpy(), logits_meta, atol=1e-4)


# TODO: Do generation test
class OPTGenerationTest(unittest.TestCase):
    @property
    def prompts(self):
        return [
            "Today is a beautiful day and I want",
            "In the city of",
            "Paris is the capital of France and",
            "Computers and mobile phones have taken",
        ]

    def test_generation_pre_attn_layer_norm(self):
        model_id = "facebook/opt-350m"

        EXPECTED_OUTPUTS = [
            "Today is a beautiful day and I want to",
            "In the city of San Francisco, the city",
            "Paris is the capital of France and the capital",
            "Computers and mobile phones have taken over the",
        ]

        predicted_outputs = []
        tokenizer = OPTTokenizer.from_pretrained(model_id)
        model = OPTForCausalLM.from_pretrained(model_id, from_pt=True)

        for prompt in self.prompts:
            input_ids = tokenizer(prompt)['input_ids']

            generated_ids = model.generate(inputs=np.asarray([input_ids], dtype=int), max_length=9)

            generated_string = tokenizer.batch_decode([generated_ids], skip_special_tokens=True)
            predicted_outputs += generated_string
        self.assertListEqual(predicted_outputs, EXPECTED_OUTPUTS)

    def test_batch_generation(self):
        model_id = "facebook/opt-350m"

        tokenizer = OPTTokenizer.from_pretrained(model_id)
        model = OPTForCausalLM.from_pretrained(model_id)

        tokenizer.padding_side = "left"

        # use different length sentences to test batching
        sentences = [
            "Hello, my dog is a little",
            "Today, I",
        ]

        inputs = tokenizer(sentences, return_tensors="pt", padding=True)
        input_ids = inputs["input_ids"]

        outputs = model.generate(
            input_ids=input_ids,
            attention_mask=inputs["attention_mask"],
        )

        inputs_non_padded = tokenizer(sentences[0], return_tensors="pt").input_ids
        output_non_padded = model.generate(input_ids=inputs_non_padded)

        num_paddings = inputs_non_padded.shape[-1] - inputs["attention_mask"][-1].long().sum().cpu().item()
        inputs_padded = tokenizer(sentences[1], return_tensors="pt").input_ids
        output_padded = model.generate(input_ids=inputs_padded, max_length=model.config.max_length - num_paddings)

        batch_out_sentence = tokenizer.batch_decode(outputs, skip_special_tokens=True)
        non_padded_sentence = tokenizer.decode(output_non_padded[0], skip_special_tokens=True)
        padded_sentence = tokenizer.decode(output_padded[0], skip_special_tokens=True)

        expected_output_sentence = [
            "Hello, my dog is a little bit of a dork.\nI'm a little bit",
            "Today, I was in the middle of a conversation with a friend about the",
        ]
        self.assertListEqual(expected_output_sentence, batch_out_sentence)
        self.assertListEqual(batch_out_sentence, [non_padded_sentence, padded_sentence])

    def test_generation_post_attn_layer_norm(self):
        model_id = "facebook/opt-350m"

        EXPECTED_OUTPUTS = [
            "Today is a beautiful day and I want to",
            "In the city of San Francisco, the city",
            "Paris is the capital of France and the capital",
            "Computers and mobile phones have taken over the",
        ]

        predicted_outputs = []
        tokenizer = OPTTokenizer.from_pretrained(model_id)
        model = OPTForCausalLM.from_pretrained(model_id)

        for prompt in self.prompts:
            input_ids = tokenizer(prompt, return_tensors="pt").input_ids

            generated_ids = model.generate(input_ids, max_length=10)

            generated_string = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)
            predicted_outputs += generated_string

        self.assertListEqual(predicted_outputs, EXPECTED_OUTPUTS)