import os

from absl.testing import parameterized
import numpy as np

from tensorflow.python.platform import googletest
from ai_edge_quantizer import qtyping
from ai_edge_quantizer.algorithms.uniform_quantize import naive_min_max_quantize
from ai_edge_quantizer.algorithms.uniform_quantize.naive_min_max_quantize_op_tests import test_utils as naive_min_max_test_utils
from ai_edge_quantizer.utils import test_utils
from ai_edge_quantizer.utils import tfl_flatbuffer_utils

_TEST_DATA_PREFIX_PATH = test_utils.get_path_to_datafile("../../../test_models")

_TFLOpName = qtyping.TFLOperationName
_OpExecutionMode = qtyping.OpExecutionMode
_TensorQuantConfig = qtyping.TensorQuantizationConfig
_QuantTransformation = qtyping.QuantTransformation
_OpTestInfo = naive_min_max_test_utils.OpTestInfo


class EmbeddingLookupTest(naive_min_max_test_utils.NaiveMinMaxQuantizeTest):

  def setUp(self):
    super().setUp()
    np.random.seed(666)
    self._test_model_path = os.path.join(
        _TEST_DATA_PREFIX_PATH, "embedding_lookup.tflite"
    )
    self._op_test_info = _OpTestInfo(
        test_model=tfl_flatbuffer_utils.read_model(self._test_model_path),
        model_buffer=tfl_flatbuffer_utils.get_model_buffer(
            self._test_model_path
        ),
        op_tensor_names={},
        input_range=(np.array([[-10]]), np.array([[8]])),
        output_range=(np.array([[10]]), np.array([[88]])),
    )
    # The test model has one subgraph for now.
    self._graph_info = qtyping.GraphInfo(
        subgraph_tensors=self._op_test_info.test_model.subgraphs[0].tensors,
        buffers=self._op_test_info.test_model.buffers,
        whole_model_buffer=self._op_test_info.model_buffer,
    )

  @parameterized.product(
      num_bits_weight=(4, 8),
      symmetric_weight=(True, False),
      channel_wise_weight=(True, False),
      execution_mode=(
          _OpExecutionMode.DRQ,
          _OpExecutionMode.WEIGHT_ONLY,
      ),
  )
  def test_embedding_lookup_succeeds(
      self,
      num_bits_weight,
      symmetric_weight,
      channel_wise_weight,
      execution_mode,
  ):

    # Read from Model Explorer.
    subgraph0 = self._op_test_info.test_model.subgraphs[0]
    subgraph_op_id = 0
    op = subgraph0.operators[subgraph_op_id]
    op_tensor_names = {}
    op_tensor_names["weight"] = (
        "jax2tf_export_func_/...y_yz-_...z/pjit__einsum_/MatMul;jax2tf_export_func_/pjit__one_hot_/Equal;jax2tf_export_func_/pjit__one_hot_/Cast_1"
    )
    op_tensor_names["input"] = "inputs"
    op_tensor_names["output"] = "Identity_1"
    self._op_test_info.op_tensor_names = op_tensor_names
    self._op_test_info.quantized_dimension = 0

    op_info = qtyping.OpInfo(
        op=op,
        op_name=qtyping.TFLOperationName.EMBEDDING_LOOKUP,
        subgraph_op_index=subgraph_op_id,
        op_quant_config=qtyping.OpQuantizationConfig(
            weight_tensor_config=_TensorQuantConfig(
                num_bits=num_bits_weight,
                symmetric=symmetric_weight,
                channel_wise=channel_wise_weight,
            ),
            execution_mode=execution_mode,
        ),
    )
    # TODO: b/335913710 - Rename the test function.
    self._test_fc_bmm_conv(
        op_info,
        self._graph_info,
        self._op_test_info,
        naive_min_max_quantize.materialize_embedding_lookup,
    )


if __name__ == "__main__":
  googletest.main()