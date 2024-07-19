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

"""Utils for min/max based quantization."""

from collections.abc import Sequence
import enum
from typing import Any, Optional
import numpy as np
from ai_edge_quantizer import qtyping
from ai_edge_quantizer.algorithms.uniform_quantize import uniform_quantize_tensor
from ai_edge_quantizer.utils import tfl_flatbuffer_utils

_TFLOpName = qtyping.TFLOperationName
_QuantTransformation = qtyping.QuantTransformation

_SUPPORTED_WEIGHT_ONLY_OPS = frozenset([
    _TFLOpName.FULLY_CONNECTED,
    _TFLOpName.CONV_2D,
    _TFLOpName.BATCH_MATMUL,
    _TFLOpName.EMBEDDING_LOOKUP,
    _TFLOpName.DEPTHWISE_CONV_2D,
])

_SUPPORTED_DRQ_OPS = frozenset([
    _TFLOpName.FULLY_CONNECTED,
    _TFLOpName.CONV_2D,
    _TFLOpName.BATCH_MATMUL,
    _TFLOpName.EMBEDDING_LOOKUP,
    _TFLOpName.DEPTHWISE_CONV_2D,
])

_INT4_DRQ_SUPPORTED_OPS = frozenset([
    _TFLOpName.FULLY_CONNECTED,
    # TODO: b/353365054 - Uncomment after int4 DRQ is supported for
    # conv2d.
    # _TFLOpName.CONV_2D,
])

_SUPPORTED_SRQ_OPS = frozenset([
    _TFLOpName.FULLY_CONNECTED,
    _TFLOpName.CONV_2D,
    _TFLOpName.AVERAGE_POOL_2D,
    _TFLOpName.RESHAPE,
    _TFLOpName.SOFTMAX,
    _TFLOpName.DEPTHWISE_CONV_2D,
    _TFLOpName.TANH,
    _TFLOpName.TRANSPOSE,
    _TFLOpName.GELU,
    _TFLOpName.ADD,
    _TFLOpName.SUB,
    _TFLOpName.MUL,
    _TFLOpName.BATCH_MATMUL,
])

_INT4_SRQ_SUPPORTED_OPS = frozenset([
    _TFLOpName.FULLY_CONNECTED,
    _TFLOpName.CONV_2D,
    _TFLOpName.EMBEDDING_LOOKUP,
])


def check_weight_only_config(op_name: _TFLOpName) -> None:
  """Checks the op quantization config for weight-only quantization."""
  if op_name not in _SUPPORTED_WEIGHT_ONLY_OPS:
    raise ValueError(f"Unsupported op for weight-only quantization: {op_name}.")


def check_drq_config(
    op_name: _TFLOpName, op_quant_config: qtyping.OpQuantizationConfig
) -> None:
  """Checks the op quantization config for dynamic range quantization."""
  weight_config = op_quant_config.weight_tensor_config
  if op_name not in _SUPPORTED_DRQ_OPS:
    raise ValueError(
        f"Unsupported op for dynamic range quantization: {op_name} "
    )
  if weight_config.num_bits not in (4, 8) or not weight_config.symmetric:
    raise ValueError(
        f"Only int4/int8 symmetric DRQ is supported for op {op_name}"
    )
  if weight_config.num_bits == 4 and op_name not in _INT4_DRQ_SUPPORTED_OPS:
    raise ValueError(f"Int4 DRQ is not supported for op {op_name}.")


def check_srq_config(
    op_name: _TFLOpName, op_quant_config: qtyping.OpQuantizationConfig
) -> None:
  """Checks the op quantization config for static range quantization."""
  act_config = op_quant_config.activation_tensor_config
  weight_config = op_quant_config.weight_tensor_config
  if op_name not in _SUPPORTED_SRQ_OPS:
    raise ValueError(
        f"Unsupported op for static range quantization: {op_name}."
    )
  if act_config is None:
    raise ValueError("activation_tensor_config is required for SRQ.")
  if act_config.dtype != qtyping.TensorDataType.INT:
    raise ValueError("SRQ requires activation tensor to be int type.")
  if act_config.num_bits not in (8, 16):
    raise ValueError(
        f"Only int8/int16 activation SRQ is supported for op {op_name}."
    )
  if act_config.num_bits == 16 and not act_config.symmetric:
    raise ValueError(
        "Int16 activation SRQ requires symmetric activation quantization."
    )
  if weight_config.num_bits not in (4, 8) or not weight_config.symmetric:
    raise ValueError(
        "Currently only int4/int8 symmetric weight are supported for op"
        f" {op_name}."
    )
  if weight_config.num_bits == 4 and op_name not in _INT4_SRQ_SUPPORTED_OPS:
    raise ValueError(f"Int4 weight SRQ is not supported for op {op_name}.")


class OpQuantConstraint(enum.Enum):
  """Quantization constraint for an op."""

  NO_CONSTRAIN = 0
  # All tensors in the op have the same scale as the input tensor
  # e.g., transpose/reshape/split.
  SAME_AS_INPUT_SCALE = 1
  # All tensors in the op have the same scale as the output tensor.
  # e.g., concatenate
  SAME_AS_OUTPUT_SCALE = 2


def init_tensor_min_max(
    tensor: Any,
    graph_info: qtyping.GraphInfo,
    op_info: qtyping.OpInfo,
    init_min_val: float = 0.0,
    init_max_val: float = 6.0,
):
  """Initialize the min/max for a tensor."""
  tensor_data = tfl_flatbuffer_utils.get_tensor_data(tensor, graph_info.buffers)
  # Initial values for non-constant tensors.
  if tensor_data is None:
    # preserve tensor rank on min/max (e.g., keepdims=True).
    min_max_shape = [1] * len(tensor.shape)
    return {
        "min": np.broadcast_to(init_min_val, min_max_shape),
        "max": np.broadcast_to(init_max_val, min_max_shape),
    }
  # Real min/max for constant tensors.
  else:
    quantized_dim = None
    if op_info.op_quant_config.weight_tensor_config.channel_wise:
      if op_info.op_name == _TFLOpName.BATCH_MATMUL:
        quantized_dim = _get_bmm_weight_quantized_dim(
            tensor_data, adj_y=op_info.op.builtinOptions.adjY
        )
      else:
        quantized_dim = tfl_flatbuffer_utils.TFL_OP_TO_WEIGHT_QUANTIZED_DIM.get(
            op_info.op_name, None
        )
    reduce_dims = _get_reduce_dims(quantized_dim, tensor.shape)
    return {
        "min": np.min(tensor_data, axis=reduce_dims, keepdims=True),
        "max": np.max(tensor_data, axis=reduce_dims, keepdims=True),
    }


def _get_tensor_transformation_params_wrapper(
    tensor: Any,
    is_inbounding_tensor: bool,
    op_info: qtyping.OpInfo,
    graph_info: qtyping.GraphInfo,
    tensor_name_to_qsv: dict[str, Any],
    quant_params=None,
) -> qtyping.TensorTransformationParams:
  """Util to get tensor transformation params.

  Args:
    tensor: Tensor to be quantized.
    is_inbounding_tensor: Whether the tensor is an inbounding tensor for the op.
    op_info: Aggregated information about the op (e.g., quantization config).
    graph_info: Graph information needed to perform quantization for the op.
    tensor_name_to_qsv: A map of tensor name to quantization parameters.
    quant_params: Quantization parameters for the tensor.

  Returns:
    Transformation parameters for the tensor.

  Raises:
    ValueError: If the tensor is not found in tensor_name_to_qsv.
  """
  tensor_name = tfl_flatbuffer_utils.get_tensor_name(tensor)
  tensor_data = tfl_flatbuffer_utils.get_tensor_data(tensor, graph_info.buffers)
  tensor_quant_config = op_info.op_quant_config.activation_tensor_config
  is_constant = tensor_data is not None
  # Use weight configuration if it is supported.
  if is_constant and op_info.op_name in frozenset.union(
      _SUPPORTED_WEIGHT_ONLY_OPS, _SUPPORTED_DRQ_OPS
  ):
    tensor_quant_config = op_info.op_quant_config.weight_tensor_config
  # Get quant params.
  if quant_params is None and tensor_quant_config is not None:
    if tensor_name not in tensor_name_to_qsv:
      if is_constant:
        # We need min/max to calculate quantization parameters, which
        # should be collected during the calibration process. However,
        # weight-only and DRQ do not require calibration, thus it is
        # possible that this information is missing here. In that case we
        # collect min/max on the spot.
        tensor_min_max = init_tensor_min_max(
            tensor,
            graph_info,
            op_info,
        )
      else:
        raise ValueError(
            f"Tensor {tensor_name} not found in tensor_name_to_qsv. Check"
            " if the correct calibration results are passed into the"
            " ParamsGenerator."
        )
    else:
      tensor_min_max = tensor_name_to_qsv[tensor_name]
    quant_params = _get_tensor_quant_params(
        op_info,
        tensor_min_max,
        tensor_quant_config,
        tensor_content=tensor_data,
    )
  return get_tensor_transformation_params(
      tensor_name,
      op_info,
      is_inbounding_tensor,
      quant_params,
      is_constant,
  )


def _materialize_op_tensors(
    op_tensor_params: list[qtyping.TensorTransformationParams],
    op_tensors: Sequence[Any],
    is_inbounding_tensor: bool,
    op_info: qtyping.OpInfo,
    graph_info: qtyping.GraphInfo,
    tensor_name_to_qsv: dict[str, Any],
    quant_params=None,
) -> None:
  """Util to materialize op tensors. Appends the results to op_tensor_params.

  Args:
    op_tensor_params: Tensor transformation parameters for the op. Will be
      modified to include new tensor parameters.
    op_tensors: Tensors associated with the op.
    is_inbounding_tensor: Whether the tensor is an inbounding tensor for the op.
    op_info: Aggregated information about the op (e.g., quantization config).
    graph_info: Graph information needed to perform quantization for the op.
    tensor_name_to_qsv: A map of tensor name to quantization parameters.
    quant_params: Quantization parameters for the tensor.
  """
  for tensor in op_tensors:
    tensor_params = _get_tensor_transformation_params_wrapper(
        tensor,
        is_inbounding_tensor,
        op_info,
        graph_info,
        tensor_name_to_qsv,
        quant_params,
    )
    op_tensor_params.append(tensor_params)


def _get_single_tensor_params(
    tensors: Sequence[Any],
    is_inbounding_tensor: bool,
    op_info: qtyping.OpInfo,
    graph_info: qtyping.GraphInfo,
    tensor_name_to_qsv: dict[str, Any],
) -> qtyping.TensorTransformationParams:
  """Util to get single tensor params.

  Args:
    tensors: A list of a single tensor.
    is_inbounding_tensor: Whether the tensor is an inbounding tensor for the op.
    op_info: Aggregated information about the op (e.g., quantization config).
    graph_info: Graph information needed to perform quantization for the op.
    tensor_name_to_qsv: A map of tensor name to quantization parameters.

  Returns:
    Transformation parameters for the tensor.

  Raises:
    ValueError: If the tensor list is not of size 1.
  """
  if len(tensors) != 1:
    raise ValueError(
        "Trying to get a single tensor params with a list of multiple tensor"
        f" with size {len(tensors)}."
    )
  return _get_tensor_transformation_params_wrapper(
      tensors[0],
      is_inbounding_tensor,
      op_info,
      graph_info,
      tensor_name_to_qsv,
  )


def _materialize_standard_op_with_same_as_input_scale(
    input_tensors: Sequence[Any],
    output_tensors: Sequence[Any],
    op_info: qtyping.OpInfo,
    graph_info: qtyping.GraphInfo,
    tensor_name_to_qsv: dict[str, Any],
) -> list[qtyping.TensorTransformationParams]:
  """Materialize tensors in an op with same as input scale constraint.

  Args:
    input_tensors: Input tensors for the op.
    output_tensors: Output tensors for the op.
    op_info: Aggregated information about the op (e.g., quantization config).
    graph_info: Graph information needed to perform quantization for the op.
    tensor_name_to_qsv: A map of tensor name to quantization parameters.

  Returns:
    Quantization configuration for the tensors associated with the op (e.g.,
    weights, bias).
  """
  op_tensor_params = []
  # Must be a single input to avoid ambiguity.
  input_tensor_params = _get_single_tensor_params(
      input_tensors,
      is_inbounding_tensor=True,
      op_info=op_info,
      graph_info=graph_info,
      tensor_name_to_qsv=tensor_name_to_qsv,
  )
  op_tensor_params.append(input_tensor_params)
  # Use input quantization params for all output tensors.
  _materialize_op_tensors(
      op_tensor_params,
      output_tensors,
      is_inbounding_tensor=False,
      op_info=op_info,
      graph_info=graph_info,
      tensor_name_to_qsv=tensor_name_to_qsv,
      quant_params=input_tensor_params.consumers[0].parameters,
  )
  # Change output qsv to be the same as input qsv. This is safe since TFL
  # subgraph is acyclic.
  input_tensor_qsv = tensor_name_to_qsv[input_tensor_params.tensor_name]
  for output_tensor in output_tensors:
    tensor_name_to_qsv[tfl_flatbuffer_utils.get_tensor_name(output_tensor)] = (
        input_tensor_qsv
    )

  return op_tensor_params


def _materialize_standard_op_with_same_as_output_scale(
    input_tensors: Sequence[Any],
    output_tensors: Sequence[Any],
    op_info: qtyping.OpInfo,
    graph_info: qtyping.GraphInfo,
    tensor_name_to_qsv: dict[str, Any],
) -> list[qtyping.TensorTransformationParams]:
  """Materialize tensors in an op with same as output scale constraint.

  Args:
    input_tensors: Input tensors for the op.
    output_tensors: Output tensors for the op.
    op_info: Aggregated information about the op (e.g., quantization config).
    graph_info: Graph information needed to perform quantization for the op.
    tensor_name_to_qsv: A map of tensor name to quantization parameters.

  Returns:
    Quantization configuration for the tensors associated with the op (e.g.,
    weights, bias).
  """
  op_tensor_params = []
  # Must be a single output to avoid ambiguity.
  output_tensor_params = _get_single_tensor_params(
      output_tensors,
      is_inbounding_tensor=False,
      op_info=op_info,
      graph_info=graph_info,
      tensor_name_to_qsv=tensor_name_to_qsv,
  )
  # Use output quantization params for all input tensors.
  if output_tensor_params.producer is None:
    quant_params = None
  else:
    quant_params = output_tensor_params.producer.parameters
  _materialize_op_tensors(
      op_tensor_params,
      input_tensors,
      is_inbounding_tensor=True,
      op_info=op_info,
      graph_info=graph_info,
      tensor_name_to_qsv=tensor_name_to_qsv,
      quant_params=quant_params,
  )
  op_tensor_params.append(output_tensor_params)

  return op_tensor_params


def _materialize_standard_op_no_constraint(
    input_tensors: Sequence[Any],
    output_tensors: Sequence[Any],
    op_info: qtyping.OpInfo,
    graph_info: qtyping.GraphInfo,
    tensor_name_to_qsv: dict[str, Any],
) -> list[qtyping.TensorTransformationParams]:
  """Materialize tensors in an op with no constraint.

  Args:
    input_tensors: Input tensors for the op.
    output_tensors: Output tensors for the op.
    op_info: Aggregated information about the op (e.g., quantization config).
    graph_info: Graph information needed to perform quantization for the op.
    tensor_name_to_qsv: A map of tensor name to quantization parameters.

  Returns:
    Quantization configuration for the tensors associated with the op (e.g.,
    weights, bias).
  """
  op_tensor_params = []
  _materialize_op_tensors(
      op_tensor_params,
      input_tensors,
      is_inbounding_tensor=True,
      op_info=op_info,
      graph_info=graph_info,
      tensor_name_to_qsv=tensor_name_to_qsv,
  )
  _materialize_op_tensors(
      op_tensor_params,
      output_tensors,
      is_inbounding_tensor=False,
      op_info=op_info,
      graph_info=graph_info,
      tensor_name_to_qsv=tensor_name_to_qsv,
  )

  return op_tensor_params


def materialize_standard_op(
    op_info: qtyping.OpInfo,
    graph_info: qtyping.GraphInfo,
    tensor_name_to_qsv: dict[str, Any],
    constraint: OpQuantConstraint = OpQuantConstraint.NO_CONSTRAIN,
    inputs_to_ignore: Optional[list[int]] = None,
    outputs_to_ignore: Optional[list[int]] = None,
) -> list[qtyping.TensorTransformationParams]:
  """Default materialization function for an op.

  Use materialize_fc_conv as the entry point to materialize FULLY_CONNECTED,
  CONV_2D, DEPTHWISE_CONV_2D as these ops may contain fused bias.

  Args:
    op_info: Aggregated information about the op (e.g., quantization config).
    graph_info: Graph information needed to perform quantization for the op.
    tensor_name_to_qsv: A map of tensor name to quantization parameters.
    constraint: The constraint for materializing the op.
    inputs_to_ignore: Input tensor indices to ignore.
    outputs_to_ignore: Output tensor indices to ignore.

  Returns:
    Quantization configuration for the tensors associated with the op (e.g.,
    weights, bias). The returned list has the structure:
    [input_tensor_0_params, ..., input_tensor_n_params,
    output_tensor_0_params, ..., output_tensor_m_params].
  """
  # Process op inputs and outputs.
  inputs_to_ignore = inputs_to_ignore or []
  outputs_to_ignore = outputs_to_ignore or []
  input_tensors, output_tensors = [], []
  for i, input_tensor_index in enumerate(op_info.op.inputs):
    if i not in inputs_to_ignore and input_tensor_index >= 0:
      input_tensors.append(graph_info.subgraph_tensors[input_tensor_index])
  for i, output_tensor_index in enumerate(op_info.op.outputs):
    if i not in outputs_to_ignore and output_tensor_index >= 0:
      output_tensors.append(graph_info.subgraph_tensors[output_tensor_index])

  # Materialize op tensors.
  if constraint == OpQuantConstraint.SAME_AS_INPUT_SCALE:
    return _materialize_standard_op_with_same_as_input_scale(
        input_tensors, output_tensors, op_info, graph_info, tensor_name_to_qsv
    )
  elif constraint == OpQuantConstraint.SAME_AS_OUTPUT_SCALE:
    return _materialize_standard_op_with_same_as_output_scale(
        input_tensors, output_tensors, op_info, graph_info, tensor_name_to_qsv
    )
  else:
    return _materialize_standard_op_no_constraint(
        input_tensors, output_tensors, op_info, graph_info, tensor_name_to_qsv
    )


def materialize_op_with_output_activation_constraint(
    op_info: qtyping.OpInfo,
    graph_info: qtyping.GraphInfo,
    tensor_name_to_qsv: dict[str, Any],
    output_activation_constraints: dict[int, qtyping.UniformQuantParams],
) -> list[qtyping.TensorTransformationParams]:
  """Materialize tensors in an op with output activation constraint.

  The output activation constraints are used to explicitly set
  quantization parameters for the output tensor when doing SRQ.

  Function assumes that there is only one output tensor.

  Args:
    op_info: Aggregated information about the op (e.g., quantization config).
    graph_info: Graph information needed to perform quantization for the op.
    tensor_name_to_qsv: A map of tensor name to quantization parameters.
    output_activation_constraints: A map of output activation num bits to
      quantization parameters.

  Returns:
    Quantization configuration for the tensors associated with the op (e.g.,
    weights, bias).

  Raises:
    ValueError: If the op has more than one output tensor, or if the output
      activation constraints dictionary does not contain an entry for the
      activation num bits specified in the op quantization config.
  """
  if len(op_info.op.outputs) != 1:
    raise ValueError(
        "Materialize op with output activation constraint only supports ops"
        " with a single output tensor."
    )

  tensor_params = materialize_standard_op(
      op_info,
      graph_info,
      tensor_name_to_qsv,
  )
  output_tensor_params = tensor_params[-1]

  # Explicitly set quantization parameters for the output tensor when doing SRQ.
  activation_tensor_config = op_info.op_quant_config.activation_tensor_config
  if (
      activation_tensor_config is not None
      and output_tensor_params.producer is not None
  ):
    activation_num_bits = activation_tensor_config.num_bits
    if activation_num_bits not in output_activation_constraints:
      raise ValueError(
          "Output activation constraints dictionary does not contain entity"
          f" for activation num bits {activation_num_bits}."
      )
    op_tensor_params = qtyping.OpToTensorParams(
        subgraph_op_id=output_tensor_params.producer.subgraph_op_id,
        transformations=output_tensor_params.producer.transformations,
        parameters=output_activation_constraints[activation_num_bits],
    )
    output_tensor_params.producer = op_tensor_params

  return tensor_params


def get_tensor_transformations(
    op_quant_config: qtyping.OpQuantizationConfig,
    is_inbounding_tensor: bool,
    is_constant: bool,
):
  """Get the transformations for the tensor.

  Args:
    op_quant_config: the quantization config for the op.
    is_inbounding_tensor: whether the tensor is an inbounding tensor for the op.
    is_constant: whether the tensor is a constant tensor.

  Returns:
    The transformations for the tensor.
  """
  transformations = []
  if op_quant_config.execution_mode == qtyping.OpExecutionMode.SRQ:
    if is_inbounding_tensor:
      transformations = [_QuantTransformation.ADD_QUANTIZE]
      if is_constant:
        # Quantize the constant tensor directly to simplify downstream
        # optimizations.
        transformations = [_QuantTransformation.QUANTIZE_TENSOR]
    else:
      transformations = [_QuantTransformation.ADD_DEQUANTIZE]
  elif op_quant_config.execution_mode == qtyping.OpExecutionMode.DRQ:
    if is_inbounding_tensor and is_constant:
      transformations = [_QuantTransformation.QUANTIZE_TENSOR]
    else:
      transformations = [_QuantTransformation.NO_QUANTIZE]
  elif op_quant_config.execution_mode == qtyping.OpExecutionMode.WEIGHT_ONLY:
    if is_inbounding_tensor and is_constant:
      # ADD_DEQUANTIZE is always accompanined with a quantization parameters.
      # Thus [ADD_DEQUANTIZE] is equivalent to [QUANTIZE_TENSOR, ADD_DEQUANTIZE]
      # downstream pattern: quantized_tensor -> dequantize op -> float_tensor.
      transformations = [_QuantTransformation.ADD_DEQUANTIZE]
    else:
      transformations = [_QuantTransformation.NO_QUANTIZE]

  return transformations


def get_tensor_transformation_params(
    tensor_name: str,
    op_info: qtyping.OpInfo,
    is_inbounding_tensor: bool,
    quant_params: Optional[qtyping.UniformQuantParams] = None,
    is_constant: bool = False,
) -> qtyping.TensorTransformationParams:
  """Transformation params for the op's tensor.

  Args:
    tensor_name: the name of the tensor.
    op_info: aggregated information about the op (e.g., quantization config).
    is_inbounding_tensor: whether the tensor is inbounding tensor to the op.
    quant_params: the quantization parameters for the tensor.
    is_constant: whether the tensor is a constant tensor.

  Returns:
    The transformation for the op's tensor.
  """
  transformations = get_tensor_transformations(
      op_info.op_quant_config, is_inbounding_tensor, is_constant
  )
  op2tensor_params = qtyping.OpToTensorParams(
      subgraph_op_id=op_info.subgraph_op_index,
      parameters=quant_params,
      transformations=transformations,
  )
  if is_inbounding_tensor:
    return qtyping.TensorTransformationParams(
        tensor_name=tensor_name,
        consumers=[op2tensor_params],
    )
  return qtyping.TensorTransformationParams(
      tensor_name=tensor_name,
      producer=op2tensor_params,
  )


def _get_tensor_quant_params(
    op_info: qtyping.OpInfo,
    tensor_min_max: dict[str, Any],
    tensor_quant_config: qtyping.TensorQuantizationConfig,
    tensor_content: Optional[np.ndarray] = None,
) -> qtyping.UniformQuantParams:
  """Get the quantization parameters for a tensor.

  Args:
    op_info: aggregated information about the op (e.g., quantization config).
    tensor_min_max: the min/max of the tensor.
    tensor_quant_config: the quantization config for the tensor.
    tensor_content: the content of the tensor.

  Returns:
    The quantization parameters for the tensor.
  """
  if "min" not in tensor_min_max or "max" not in tensor_min_max:
    raise ValueError(
        "min and max must be provided to produce tensor quantization"
        " parameters. Check if the correct calibration results are passed into"
        " the ParamsGenerator."
    )
  zp, scale = uniform_quantize_tensor.tensor_zp_scale_from_min_max(
      tensor_min_max["min"],
      tensor_min_max["max"],
      tensor_quant_config.num_bits,
      tensor_quant_config.symmetric,
  )
  quantized_dim = None
  if tensor_quant_config.channel_wise:
    if op_info.op_name == _TFLOpName.BATCH_MATMUL:
      quantized_dim = _get_bmm_weight_quantized_dim(
          tensor_content, adj_y=op_info.op.builtinOptions.adjY
      )
    else:
      quantized_dim = tfl_flatbuffer_utils.TFL_OP_TO_WEIGHT_QUANTIZED_DIM[
          op_info.op_name
      ]
  quant_params = qtyping.UniformQuantParams(
      scale=scale,
      zero_point=zp,
      num_bits=tensor_quant_config.num_bits,
      symmetric=tensor_quant_config.symmetric,
      quantized_dimension=quantized_dim,
  )
  if tensor_content is None:
    return quant_params
  quantized_vars = uniform_quantize_tensor.uniform_quantize(
      tensor_content, quant_params
  )
  # Update with quantized values.
  return qtyping.UniformQuantParams(
      scale=scale,
      zero_point=zp,
      num_bits=tensor_quant_config.num_bits,
      symmetric=tensor_quant_config.symmetric,
      quantized_dimension=quantized_dim,
      quantized_data=quantized_vars,
  )


def _get_reduce_dims(
    quantized_dim: Optional[int],
    tensor_shape: list[int],
) -> Optional[tuple[int, ...]]:
  """Get the reduce dims of a tensor for the given quantized dimension."""
  if quantized_dim is None:
    return None
  reduce_dims = []
  for rank_idx in range(len(tensor_shape)):
    if rank_idx != quantized_dim:
      reduce_dims.append(rank_idx)
  return tuple(reduce_dims)


def _get_bmm_weight_quantized_dim(
    weight_tensor_data: np.ndarray, adj_y: bool
) -> int:
  """Get the quantized dimension for batch matmul."""
  rank = len(weight_tensor_data.shape)
  # If adj_y is true, the weight tensor is transposed.
  if adj_y:
    return rank - 2
  return rank - 1
