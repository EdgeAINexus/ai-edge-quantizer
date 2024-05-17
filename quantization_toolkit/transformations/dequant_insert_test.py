"""Test for various transformations used by quantization toolkit."""

import os
import numpy as np
from tensorflow.python.platform import googletest
from quantization_toolkit import qtyping
from quantization_toolkit.transformations import dequant_insert
from quantization_toolkit.transformations import transformation_utils
from quantization_toolkit.utils import test_utils
from quantization_toolkit.utils import tfl_flatbuffer_utils
from tensorflow.lite.python import schema_py_generated  # pylint: disable=g-direct-tensorflow-import

TEST_DATA_PREFIX_PATH = test_utils.get_path_to_datafile("..")


class DequantInsertTest(googletest.TestCase):

  def setUp(self):
    super().setUp()
    self._orig_test_model_path = os.path.join(
        TEST_DATA_PREFIX_PATH, "test_models/insert_dequant_test.tflite"
    )
    self._model = tfl_flatbuffer_utils.read_model(self._orig_test_model_path)

  def test_dequant_insert_constant(self):
    """Test dequant insert lib on a constant tensor."""
    subgraph = self._model.subgraphs[0]
    model = self._model
    dequant_opcode = schema_py_generated.BuiltinOperator.DEQUANTIZE
    # insert dequant on the constant before the add node
    dequant_insert.insert_dequant(
        transformation_utils.TransformationInput(
            7,
            model.operatorCodes,
            model.buffers,
            subgraph,
            -1,
            [4],
            qtyping.UniformQuantParams(8, None, np.array([1]), np.array([0])),
        )
    )

    # check dequant op code is added to the model
    self.assertEqual(
        model.operatorCodes[len(model.operatorCodes) - 1].builtinCode,
        dequant_opcode,
    )

    # check new tensor is correct created
    self.assertIn(b"_dequant", subgraph.tensors[9].name)
    self.assertEqual(
        subgraph.tensors[9].type, schema_py_generated.TensorType.FLOAT32
    )
    self.assertEqual(
        subgraph.tensors[7].type, schema_py_generated.TensorType.INT8
    )
    # checking if consumer haves the correct input
    self.assertEqual(subgraph.operators[5].inputs[0], 6)
    self.assertEqual(subgraph.operators[5].inputs[1], 9)

    # checking the inserted node has the correct input/output
    self.assertEqual(subgraph.operators[4].outputs[0], 9)
    self.assertEqual(subgraph.operators[4].inputs[0], 7)
    # checking inserted node is the dequant node
    self.assertEqual(
        subgraph.operators[4].opcodeIndex, len(model.operatorCodes) - 1
    )

  def test_dequant_insert_activation(self):
    """Test dequant insert lib on activation tensors."""
    subgraph = self._model.subgraphs[0]
    model = self._model
    dequant_opcode = schema_py_generated.BuiltinOperator.DEQUANTIZE
    # insert dequant on the output of a conv node
    dequant_insert.insert_dequant(
        transformation_utils.TransformationInput(
            4,
            model.operatorCodes,
            model.buffers,
            subgraph,
            1,
            [3],
            qtyping.UniformQuantParams(8, None, np.array([1]), np.array([0])),
        )
    )

    # check dequant op code is added to the model
    self.assertEqual(
        model.operatorCodes[len(model.operatorCodes) - 1].builtinCode,
        dequant_opcode,
    )

    # check new tensor is correct created
    self.assertIn(b"_dequant", subgraph.tensors[9].name)
    self.assertEqual(
        subgraph.tensors[9].type, schema_py_generated.TensorType.FLOAT32
    )
    # check original source tensor is updated
    self.assertEqual(
        subgraph.tensors[4].type, schema_py_generated.TensorType.INT8
    )

    # checking if consumer haves the correct input
    self.assertEqual(subgraph.operators[4].inputs[0], 9)
    self.assertEqual(subgraph.operators[4].inputs[1], 5)

    # checking the inserted node has the correct input/output
    self.assertEqual(subgraph.operators[3].outputs[0], 9)
    self.assertEqual(subgraph.operators[3].inputs[0], 4)
    # checking inserted node is the dequant node
    self.assertEqual(
        subgraph.operators[3].opcodeIndex, len(model.operatorCodes) - 1
    )

  def test_dequant_insert_constant_multiple_consumers(self):
    """Test dequant insert lib on tensors with multiple consumers."""
    subgraph = self._model.subgraphs[0]
    model = self._model
    dequant_opcode = schema_py_generated.BuiltinOperator.DEQUANTIZE
    # insert dequant on the input of a conv node
    post_trans_info = dequant_insert.insert_dequant(
        transformation_utils.TransformationInput(
            2,
            model.operatorCodes,
            model.buffers,
            subgraph,
            -1,
            [1, 2],
            qtyping.UniformQuantParams(8, None, np.array([1]), np.array([0])),
        )
    )
    self.assertEqual(post_trans_info.op_id, 1)
    self.assertEqual(post_trans_info.num_ops_added, 1)

    # check dequant op code is added to the model
    self.assertEqual(
        model.operatorCodes[len(model.operatorCodes) - 1].builtinCode,
        dequant_opcode,
    )

    # check new tensor is correct created
    self.assertIn(b"_dequant", subgraph.tensors[9].name)
    self.assertEqual(
        subgraph.tensors[9].type, schema_py_generated.TensorType.FLOAT32
    )
    # check original source tensor has the correct type
    self.assertEqual(
        subgraph.tensors[2].type, schema_py_generated.TensorType.INT8
    )

    # checking the inserted node has the correct input/output
    self.assertEqual(subgraph.operators[1].outputs[0], 9)
    self.assertEqual(subgraph.operators[1].inputs[0], 2)
    # checking inserted node is the dequant node
    self.assertEqual(
        subgraph.operators[1].opcodeIndex, len(model.operatorCodes) - 1
    )

    # checking if consumer haves the correct input
    self.assertEqual(subgraph.operators[2].inputs[1], 9)
    self.assertEqual(subgraph.operators[3].inputs[1], 9)

  def test_dequant_insert_activation_multiple_consumers(self):
    """Test dequant insert lib on tensors with multiple consumers."""
    subgraph = self._model.subgraphs[0]
    model = self._model
    dequant_opcode = schema_py_generated.BuiltinOperator.DEQUANTIZE
    # insert dequant on the output of a conv node
    dequant_insert.insert_dequant(
        transformation_utils.TransformationInput(
            1,
            model.operatorCodes,
            model.buffers,
            subgraph,
            0,
            [1, 2],
            qtyping.UniformQuantParams(8, None, np.array([1]), np.array([0])),
        )
    )

    # check dequant op code is added to the model
    self.assertEqual(
        model.operatorCodes[len(model.operatorCodes) - 1].builtinCode,
        dequant_opcode,
    )

    # check new tensor is correct created
    self.assertIn(b"_dequant", subgraph.tensors[9].name)
    self.assertEqual(
        subgraph.tensors[9].type, schema_py_generated.TensorType.FLOAT32
    )
    # check original source tensor is updated
    self.assertEqual(
        subgraph.tensors[1].type, schema_py_generated.TensorType.INT8
    )

    # checking the inserted node has the correct input/output
    self.assertEqual(subgraph.operators[1].outputs[0], 9)
    self.assertEqual(subgraph.operators[1].inputs[0], 1)
    # checking inserted node is the dequant node
    self.assertEqual(
        subgraph.operators[1].opcodeIndex, len(model.operatorCodes) - 1
    )

    # checking if consumer haves the correct input
    self.assertEqual(subgraph.operators[2].inputs[0], 9)
    self.assertEqual(subgraph.operators[3].inputs[0], 9)

  def test_dequant_insert_activation_multiple_consumers_select(self):
    """Test dequant insert lib on tensors with multiple consumers but only insert for one of them."""
    subgraph = self._model.subgraphs[0]
    model = self._model
    dequant_opcode = schema_py_generated.BuiltinOperator.DEQUANTIZE
    # insert dequant on the output of a conv node
    dequant_insert.insert_dequant(
        transformation_utils.TransformationInput(
            1,
            model.operatorCodes,
            model.buffers,
            subgraph,
            0,
            [1],
            qtyping.UniformQuantParams(8, None, np.array([1]), np.array([0])),
        )
    )

    # check dequant op code is added to the model
    self.assertEqual(
        model.operatorCodes[len(model.operatorCodes) - 1].builtinCode,
        dequant_opcode,
    )

    # check new tensor is correct created
    self.assertIn(b"_dequant", subgraph.tensors[9].name)
    self.assertEqual(
        subgraph.tensors[9].type, schema_py_generated.TensorType.FLOAT32
    )
    # check original source tensor is updated
    self.assertEqual(
        subgraph.tensors[1].type, schema_py_generated.TensorType.INT8
    )

    # checking the inserted node has the correct input/output
    self.assertEqual(subgraph.operators[1].outputs[0], 9)
    self.assertEqual(subgraph.operators[1].inputs[0], 1)
    # checking inserted node is the dequant node
    self.assertEqual(
        subgraph.operators[1].opcodeIndex, len(model.operatorCodes) - 1
    )

    # checking if consumer haves the correct input
    self.assertEqual(subgraph.operators[2].inputs[0], 9)
    self.assertEqual(subgraph.operators[3].inputs[0], 1)


if __name__ == "__main__":
  googletest.main()
