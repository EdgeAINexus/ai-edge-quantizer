"""Performs naive min/max uniform quantization."""


from typing import Any, Optional
import numpy as np
from google3.third_party.odml.model_customization.quantization import typing as qtyping
from google3.third_party.odml.model_customization.quantization.algorithms.uniform_quantize import uniform_quantize_tensor
from google3.third_party.odml.model_customization.quantization.algorithms.utils import min_max_quantize_utils as utils
from google3.third_party.odml.model_customization.quantization.utils import tfl_flatbuffer_utils

ALGORITHM_KEY = "ptq"
_TFLOpName = qtyping.TFLOperationName
_QuantTransformation = qtyping.QuantTransformation
_OpQuantConstraint = utils.OpQuantConstraint


def materialize_batch_matmul(
    op_info: qtyping.OpInfo,
    graph_info: qtyping.GraphInfo,
    tensor_name_to_qsv: dict[str, Any],
) -> list[qtyping.TensorTransformationParams]:
  """Materialize tensors in tfl.reshape."""
  return utils.materialize_standard_op(
      op_info,
      graph_info,
      tensor_name_to_qsv,
  )


def materialize_reshape(
    op_info: qtyping.OpInfo,
    graph_info: qtyping.GraphInfo,
    tensor_name_to_qsv: dict[str, Any],
) -> list[qtyping.TensorTransformationParams]:
  """Materialize tensors in tfl.reshape."""
  return utils.materialize_standard_op(
      op_info,
      graph_info,
      tensor_name_to_qsv,
      constraint=_OpQuantConstraint.SAME_AS_INPUT_SCALE,
      inputs_to_ignore=[1],  # Shape tensor does not need to be quantized.
  )


def materialize_average_pool_2d(
    op_info: qtyping.OpInfo,
    graph_info: qtyping.GraphInfo,
    tensor_name_to_qsv: dict[str, Any],
) -> list[qtyping.TensorTransformationParams]:
  """Materialize tensors in tfl.average_pool_2d."""
  return utils.materialize_standard_op(
      op_info,
      graph_info,
      tensor_name_to_qsv,
      constraint=_OpQuantConstraint.SAME_AS_INPUT_SCALE,
  )


def materialize_fc_conv(
    op_info: qtyping.OpInfo,
    graph_info: qtyping.GraphInfo,
    tensor_name_to_qsv: dict[str, Any],
) -> list[qtyping.TensorTransformationParams]:
  """Materialize tensors in fully_connected, conv_2d and depthwise_conv_2d.

  Args:
    op_info: Aggregated information about the op (e.g., quantization config).
    graph_info: Graph information needed to perform quantization for the op.
    tensor_name_to_qsv: A map of tensor name to quantization parameters.

  Returns:
    Quantization configuration for the tensors associated with the op (e.g.,
    weights, bias).

  Raises:
    ValueError: if the op is not one of tfl.fully_connected, tfl.batch_matmul,
    tfl.conv_2d and tfl.depthwise_conv_2d.
  """
  op_tensor_params = utils.materialize_standard_op(
      op_info,
      graph_info,
      tensor_name_to_qsv,
      inputs_to_ignore=[2],  # ignore bias tensor.
  )
  _, _, bias_tensor, _ = tfl_flatbuffer_utils.parse_fc_bmm_conv_tensors(
      op_info.op, graph_info.subgraph_tensors
  )
  if bias_tensor is not None:
    bias_quant_params = None
    # Fused bias needs to be quantized for SRQ
    if op_info.op_quant_config.execution_mode == qtyping.OpExecutionMode.SRQ:
      bias_content = tfl_flatbuffer_utils.get_tensor_data(
          bias_tensor,
          graph_info.buffers,
          graph_info.whole_model_buffer,
      )
      bias_quant_params = (
          uniform_quantize_tensor.symmetric_quantize_bias_tensor(
              bias_content,
              op_tensor_params[0].consumers[0].parameters,  # input
              op_tensor_params[1].consumers[0].parameters,  # weight
          )
      )
    # We only quantize bias under SRQ. Setting is_constant=True for SRQ only
    # to avoid quantize bias for DRQ and weight-only cases.
    is_constant = (
        op_info.op_quant_config.execution_mode == qtyping.OpExecutionMode.SRQ
    )
    bias_params = utils.get_tensor_transformation_params(
        tfl_flatbuffer_utils.get_tensor_name(bias_tensor),
        op_info,
        is_inbounding_tensor=True,
        quant_params=bias_quant_params,
        is_constant=is_constant,
    )
    op_tensor_params.append(bias_params)

  return op_tensor_params


# TODO(b/333731147): use named tuple to store min/max.
def init_qsvs(
    op_info: qtyping.OpInfo,
    graph_info: qtyping.GraphInfo,
    inputs_to_ignore: Optional[list[int]] = None,
    outputs_to_ignore: Optional[list[int]] = None,
) -> qtyping.QSV:
  """Initialize the QSVs.

  Args:
    op_info: aggregated information about the op (e.g., quantization config).
    graph_info: graph information needed to perform quantization for the op.
    inputs_to_ignore: Input tensor indices to ignore.
    outputs_to_ignore: output tensor indices to ignore.

  Returns:
    QSVs.
  """

  # Set min/max to 0/6 to help stablize the calibration process
  # http://google3/third_party/py/mojax/operation_manager/algorithms/ptq_static_range.py?l=297
  init_min_val, init_max_val = 0.0, 6.0
  op_qsvs = {}

  inputs_to_ignore = inputs_to_ignore or []
  outputs_to_ignore = outputs_to_ignore or []
  for i, tensor_idx in enumerate(op_info.op.inputs):
    if tensor_idx != -1 and i not in inputs_to_ignore:
      tensor = graph_info.subgraph_tensors[tensor_idx]
      tensor_name = tfl_flatbuffer_utils.get_tensor_name(tensor)
      op_qsvs[tensor_name] = utils.init_tensor_min_max(
          tensor,
          graph_info,
          op_info,
          init_min_val,
          init_max_val,
      )
  for i, tensor_idx in enumerate(op_info.op.outputs):
    if tensor_idx != -1 and i not in outputs_to_ignore:
      tensor = graph_info.subgraph_tensors[tensor_idx]
      tensor_name = tfl_flatbuffer_utils.get_tensor_name(tensor)
      op_qsvs[tensor_name] = utils.init_tensor_min_max(
          tensor,
          graph_info,
          op_info,
          init_min_val,
          init_max_val,
      )
  return op_qsvs


def min_max_calibrate(
    tfl_op: Any,
    graph_info: qtyping.GraphInfo,
    tensor_content_map: dict[str, np.ndarray],
    inputs_to_ignore: Optional[list[int]] = None,
    outputs_to_ignore: Optional[list[int]] = None,
) -> dict[str, qtyping.QSV]:
  """Collect quantization statistics variable (QSV, e.g., scale/zero_point) for the op.

  Args:
    tfl_op: the tfl operation.
    graph_info: graph information needed to perform quantization for the op.
    tensor_content_map: a map of tensor name to tensor content.
    inputs_to_ignore: list of input tensor indices to ignore.
    outputs_to_ignore: list of output tensor indices to ignore.

  Returns:
    A dictionary with key as tensor name and value as the collected QSV.
  """
  op_qsvs = {}

  def _collect_activation_tensor_min_max(tensor_idx):
    tensor = graph_info.subgraph_tensors[tensor_idx]
    tensor_data = tfl_flatbuffer_utils.get_tensor_data(
        tensor, graph_info.buffers, graph_info.whole_model_buffer
    )
    # Skip constant tensors.
    if tensor_data is not None:
      return
    tensor_name = tfl_flatbuffer_utils.get_tensor_name(tensor)
    tensor_content = tensor_content_map[tensor_name]
    op_qsvs[tensor_name] = {
        "min": np.min(tensor_content, axis=None, keepdims=True),
        "max": np.max(tensor_content, axis=None, keepdims=True),
    }

  inputs_to_ignore = inputs_to_ignore or []
  outputs_to_ignore = outputs_to_ignore or []
  for i, tensor_idx in enumerate(tfl_op.inputs):
    if tensor_idx != -1 and i not in inputs_to_ignore:
      _collect_activation_tensor_min_max(tensor_idx)
  for i, tensor_idx in enumerate(tfl_op.outputs):
    if tensor_idx != -1 and i not in outputs_to_ignore:
      _collect_activation_tensor_min_max(tensor_idx)

  return op_qsvs
