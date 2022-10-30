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
"""
Test RTE
"""
import os
import unittest
import pytest
import mindspore as ms
from mindnlp.dataset import RTE, RTE_Process
from mindnlp.dataset import load, process
from mindnlp.dataset.transforms import BasicTokenizer


class TestRTE(unittest.TestCase):
    r"""
    Test RTE
    """

    def setUp(self):
        self.input = None

    @pytest.mark.dataset
    def test_rte(self):
        """Test rte"""
        num_lines = {
            "train": 2490,
            "dev": 277,
            "test": 3000,
        }
        root = os.path.join(os.path.expanduser("~"), ".mindnlp")
        dataset_train, dataset_dev, dataset_test = RTE(
            root=root, split=("train", "dev", "test")
        )
        assert dataset_train.get_dataset_size() == num_lines["train"]
        assert dataset_dev.get_dataset_size() == num_lines["dev"]
        assert dataset_test.get_dataset_size() == num_lines["test"]

        dataset_train = RTE(root=root, split="train")
        dataset_dev = RTE(root=root, split="dev")
        dataset_test = RTE(root=root, split="test")
        assert dataset_train.get_dataset_size() == num_lines["train"]
        assert dataset_dev.get_dataset_size() == num_lines["dev"]
        assert dataset_test.get_dataset_size() == num_lines["test"]

    @pytest.mark.dataset
    def test_rte_by_register(self):
        """test rte by register"""
        root = os.path.join(os.path.expanduser("~"), ".mindnlp")
        _ = load(
            "RTE",
            root=root,
            split=("train", "dev", "test"),
        )

class TestRTEProcess(unittest.TestCase):
    r"""
    Test RTE_Process
    """

    def setUp(self):
        self.input = None

    @pytest.mark.dataset
    def test_rte_process(self):
        r"""
        Test RTE_Process
        """

        train_dataset, _, _ = RTE()
        train_dataset, vocab = RTE_Process(train_dataset)

        train_dataset = train_dataset.create_tuple_iterator()
        assert (next(train_dataset)[1]).dtype == ms.int32
        assert (next(train_dataset)[2]).dtype == ms.int32

        for _, value in vocab.vocab().items():
            assert isinstance(value, int)
            break

    @pytest.mark.dataset
    def test_rte_process_by_register(self):
        """test rte process by register"""
        train_dataset, _, _ = RTE()
        train_dataset, vocab = process('RTE',
                                dataset=train_dataset,
                                column=("sentence1", "sentence2"),
                                tokenizer=BasicTokenizer(),
                                vocab=None
                                )

        train_dataset = train_dataset.create_tuple_iterator()
        assert (next(train_dataset)[1]).dtype == ms.int32
        assert (next(train_dataset)[2]).dtype == ms.int32

        for _, value in vocab.vocab().items():
            assert isinstance(value, int)
            break
