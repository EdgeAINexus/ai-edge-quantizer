import os

from absl.testing import parameterized
import numpy as np

from tensorflow.python.platform import googletest
from ai_edge_quantizer import qtyping
from ai_edge_quantizer.algorithms.uniform_quantize import naive_min_max_quantize
from ai_edge_quantizer.algorithms.uniform_quantize.naive_min_max_quantize_op_tests import test_utils as naive_min_max_test_utils
from ai_edge_quantizer.utils import test_utils
from ai_edge_quantizer.utils import tfl_flatbuffer_utils

_TFLOpName = qtyping.TFLOperationName
_OpExecutionMode = qtyping.OpExecutionMode
_TensorQuantConfig = qtyping.TensorQuantizationConfig
_QuantTransformation = qtyping.QuantTransformation
_OpTestInfo = naive_min_max_test_utils.OpTestInfo

_TEST_DATA_PREFIX_PATH = test_utils.get_path_to_datafile("../../../test_models")
_DEFAULT_ACTIVATION_QUANT_SETTING = (
    naive_min_max_test_utils.DEFAULT_ACTIVATION_QUANT_SETTING
)
_DEFAULT_WEIGHT_QUANT_SETTING = (
    naive_min_max_test_utils.DEFAULT_WEIGHT_QUANT_SETTING
)


class ReshapeTest(naive_min_max_test_utils.NaiveMinMaxQuantizeTest):

  def setUp(self):
    super().setUp()
    np.random.seed(666)
    self._test_model_path = os.path.join(
        _TEST_DATA_PREFIX_PATH, "conv_fc_mnist.tflite"
    )
    self._op_test_info = _OpTestInfo(
        test_model=tfl_flatbuffer_utils.read_model(self._test_model_path),
        model_buffer=tfl_flatbuffer_utils.get_model_buffer(
            self._test_model_path
        ),
        op_tensor_names={},
        input_range=(np.array([[-10]]), np.array([[8]])),
        output_range=(np.array([[0]]), np.array([[1]])),
    )
    # The test model has one subgraph for now.
    self._graph_info = qtyping.GraphInfo(
        subgraph_tensors=self._op_test_info.test_model.subgraphs[0].tensors,
        buffers=self._op_test_info.test_model.buffers,
        whole_model_buffer=self._op_test_info.model_buffer,
    )

  @parameterized.parameters(
      (_DEFAULT_ACTIVATION_QUANT_SETTING),
      (
          _TensorQuantConfig(
              num_bits=16,
              symmetric=True,
              channel_wise=False,
          )
      ),
  )
  def test_materialize_softmax_succeeds(self, activation_tensor_config):
    op_quant_config = qtyping.OpQuantizationConfig(
        activation_tensor_config=activation_tensor_config,
        weight_tensor_config=_DEFAULT_WEIGHT_QUANT_SETTING,
        execution_mode=_OpExecutionMode.SRQ,
    )
    # Read from Model Explorer.
    subgraph0 = self._op_test_info.test_model.subgraphs[0]
    subgraph_op_id = 5
    op = subgraph0.operators[subgraph_op_id]
    op_info = qtyping.OpInfo(
        op=op,
        op_name=qtyping.TFLOperationName.SOFTMAX,
        subgraph_op_index=subgraph_op_id,
        op_quant_config=op_quant_config,
    )

    # Test settings.
    op_tensor_names = {}
    op_tensor_names["input"] = "sequential/dense_1/MatMul"
    op_tensor_names["output"] = "StatefulPartitionedCall:0"
    self._op_test_info.op_tensor_names = op_tensor_names
    self._test_single_input_output_ops(
        op_info,
        self._graph_info,
        self._op_test_info,
        naive_min_max_quantize.materialize_softmax,
    )


if __name__ == "__main__":
  googletest.main()