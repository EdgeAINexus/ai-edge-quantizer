"""quantize a given tensor."""

from typing import cast
import numpy as np
from google3.third_party.odml.model_customization.quantization import typing as qtyping
from google3.third_party.tensorflow.lite.python import schema_py_generated  # pylint: disable=g-direct-tensorflow-import


# TODO(b/335014051): support distinguishing INT, FLOAT & UINT, BFLOAT
def quant_params_to_tflite_type(
    bitwidth: int,
) -> schema_py_generated.TensorType | None:
  """Given specifications from quant param return the corresponding tflite dtype.

  Args:
    bitwidth: bitwidth from UniformQuantParams

  Returns:
    the corresponding tflite tensortype
  """
  if bitwidth <= 8:
    return schema_py_generated.TensorType.INT8
  elif bitwidth == 16:
    return schema_py_generated.TensorType.INT16
  elif bitwidth == 32:
    return schema_py_generated.TensorType.INT32
  elif bitwidth == 64:
    return schema_py_generated.TensorType.INT64
  else:
    raise ValueError(f"Unsupported quant params: {bitwidth}")


def quant_params_to_np_type(
    bitwidth: int,
) -> type[np.int8 | np.int16 | np.int32 | np.int64] | None:
  """Given specifications from quant param return the corresponding numpy type.

  Args:
    bitwidth: bitwidth from UniformQuantParams

  Returns:
    the corresponding numpy type
  """
  if bitwidth <= 8:
    return np.int8
  elif bitwidth == 16:
    return np.int16
  elif bitwidth == 32:
    return np.int32
  elif bitwidth == 64:
    return np.int64
  else:
    raise ValueError(f"Unsupported quant params: {bitwidth}")


# TODO(b/333797939): add INT4 packing
def quantize_tensor(
    tensor_id: int,
    op_codes: list[schema_py_generated.OperatorCodeT],
    buffers: list[schema_py_generated.BufferT],
    subgraph: schema_py_generated.SubGraphT,
    producer: int,
    consumers: list[int],
    quant_params: qtyping.UniformQuantParams,
) -> qtyping.TransformationInfo:
  """Quantize the tensor at the tensor_id in the given subgraph.

  Args:
    tensor_id: the tensor index for tensor to be quantized
    op_codes: list of operatorCode in the model, not used in the function but is
      needed for api purpose
    buffers: list of buffer in the original TFlite model for buffer quantization
    subgraph: flatbuffer subgraph object which the tensor resides.
    producer: op id for the producer of the tensor.
    consumers: op ids for consumers of the tensor.
    quant_params: quantization parameters to be applied on the orignal tensor

  Returns:
    TransformationInfo:
      op_id: the producer index for tensor
      num_ops_added: the total number of ops inserted by this operation, which
        is 0
  """
  del op_codes, consumers, producer
  tensor = subgraph.tensors[tensor_id]
  # TODO(b/336385820): suppport quantize buffer directly when quantized_data
  # is not provided
  if tensor.buffer:
    if quant_params.quantized_data is not None:
      buffers[tensor.buffer].data = np.frombuffer(
          cast(np.ndarray, quant_params.quantized_data).tobytes(),
          dtype=np.uint8,
      ).flatten()
  flatbuffer_quantization = schema_py_generated.QuantizationParametersT()
  flatbuffer_quantization.scale = list(
      quant_params.scale.flatten().astype(np.float32)
  )  # flatbuffer requires scale as list[float]
  flatbuffer_quantization.zeroPoint = list(
      quant_params.zero_point.flatten().astype(np.int32)
  )  # flatbuffer requires zeroPoint as list[int]
  if quant_params.quantized_dimension is not None:
    flatbuffer_quantization.quantizedDimension = (
        quant_params.quantized_dimension
    )
  tensor.quantization = flatbuffer_quantization
  tensor.type = quant_params_to_tflite_type(quant_params.num_bits)

  return qtyping.TransformationInfo(
      0, num_ops_added=0, output_tensor_id=tensor_id
  )
