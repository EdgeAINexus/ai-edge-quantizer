# Copyright 2024 The AI Edge Quantizer Authors.
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
# ==============================================================================

"""E2E tests for the quantizer for model with mean."""

from absl.testing import parameterized
import numpy as np

from tensorflow.python.platform import googletest
from ai_edge_quantizer import qtyping
from ai_edge_quantizer import quantizer
from ai_edge_quantizer.utils import test_utils

_OpExecutionMode = qtyping.OpExecutionMode
_OpName = qtyping.TFLOperationName
_TensorQuantConfig = qtyping.TensorQuantizationConfig
_OpQuantConfig = qtyping.OpQuantizationConfig

_RNG = np.random.default_rng(66)


def _get_dummy_data(num_samples):
  data = []
  for _ in range(num_samples):
    data.append({'input_1': _RNG.uniform(size=(1, 32, 32)).astype(np.float32)})
  return data


def _get_calibration_data(num_samples: int = 128):
  return _get_dummy_data(num_samples)


def _get_test_data(num_samples: int = 8):
  return _get_dummy_data(num_samples)


class MeanTest(parameterized.TestCase):

  def setUp(self):
    super().setUp()
    self.float_model_path = test_utils.get_path_to_datafile(
        '../models/single_mean.tflite'
    )
    self._quantizer = quantizer.Quantizer(self.float_model_path)

  @parameterized.parameters(
      '../../recipes/default_a8w8_recipe.json',
      '../../recipes/default_a16w8_recipe.json',
  )
  def test_mean_model_full_integer(self, recipe_path):
    recipe_path = test_utils.get_path_to_datafile(recipe_path)
    self._quantizer.load_quantization_recipe(recipe_path)
    self.assertTrue(self._quantizer.need_calibration)
    calibration_result = self._quantizer.calibrate(_get_calibration_data())
    _ = self._quantizer.quantize(calibration_result)

    comparison_result = self._quantizer.compare(
        error_metrics='mse', signature_test_data=_get_test_data()
    )
    self._check_comparison_result(comparison_result, output_tolerance=1e-4)

  # TODO: b/345503484 - Check weight tensor type of the quantized model.
  def _check_comparison_result(self, comparison_result, output_tolerance):
    output_mse = comparison_result['PartitionedCall:0']
    self.assertLess(output_mse, output_tolerance)


if __name__ == '__main__':
  googletest.main()
