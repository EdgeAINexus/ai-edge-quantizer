load("//devtools/python/blaze:pytype.bzl", "pytype_strict_contrib_test", "pytype_strict_library")
load("//devtools/python/blaze:strict.bzl", "py_strict_test")

package(
    default_applicable_licenses = ["//third_party/odml:license"],
    default_visibility = ["//visibility:public"],
)

pytype_strict_library(
    name = "quantization_toolkit",
    srcs = ["quantization_toolkit.py"],
    srcs_version = "PY3",
    deps = [
        ":algorithm_manager",
        ":model_modifier",
        ":model_validator",
        ":params_generator",
        ":recipe_manager",
        ":typing",
        "//testing/pybase",
        "//third_party/odml/model_customization/quantization/utils:test_utils",
        "//third_party/odml/model_customization/quantization/utils:validation_utils",
        "//third_party/tensorflow/python/platform:gfile",
    ],
)

py_strict_test(
    name = "quantization_toolkit_test",
    srcs = ["quantization_toolkit_test.py"],
    data = [
        "//third_party/odml/model_customization/quantization/test_models:test_recipes",
        "//third_party/odml/model_customization/quantization/test_models:test_tfl_models",
    ],
    deps = [
        ":quantization_toolkit",
        ":typing",
        "//testing/pybase",
        "//third_party/odml/model_customization/quantization/utils:test_utils",
    ],
)

pytype_strict_library(
    name = "recipe_manager",
    srcs = ["recipe_manager.py"],
    srcs_version = "PY3",
    deps = [
        ":algorithm_manager",
        ":typing",
        "//third_party/py/absl/logging",
    ],
)

pytype_strict_contrib_test(
    name = "recipe_manager_test",
    srcs = ["recipe_manager_test.py"],
    deps = [
        ":algorithm_manager",
        ":recipe_manager",
        ":typing",
        "//testing/pybase",
        "//third_party/py/absl/testing:parameterized",
    ],
)

pytype_strict_library(
    name = "params_generator",
    srcs = ["params_generator.py"],
    srcs_version = "PY3",
    deps = [
        ":algorithm_manager",
        ":recipe_manager",
        ":typing",
        "//third_party/odml/model_customization/quantization/utils:tfl_flatbuffer_utils",
        "//third_party/py/absl/logging",
        "//third_party/tensorflow/lite/tools:flatbuffer_utils",
    ],
)

py_strict_test(
    name = "params_generator_test",
    srcs = ["params_generator_test.py"],
    data = [
        "//third_party/odml/model_customization/quantization/test_models:test_tfl_models",
    ],
    deps = [
        ":calibrator",
        ":params_generator",
        ":recipe_manager",
        ":typing",
        "//testing/pybase",
        "//third_party/odml/model_customization/quantization/utils:test_utils",
        "//third_party/odml/model_customization/quantization/utils:tfl_flatbuffer_utils",
        "//third_party/py/absl/testing:parameterized",
        "//third_party/py/numpy",
    ],
)

pytype_strict_library(
    name = "typing",
    srcs = ["typing.py"],
    srcs_version = "PY3",
    # Need for type annotation only
    deps = ["//third_party/py/numpy"],
)

pytype_strict_library(
    name = "algorithm_manager_api",
    srcs = ["algorithm_manager_api.py"],
    srcs_version = "PY3",
    deps = [
        "//third_party/odml/model_customization/quantization:typing",
        "//third_party/py/absl/logging",
        "//third_party/py/immutabledict",
    ],
)

pytype_strict_contrib_test(
    name = "algorithm_manager_api_test",
    srcs = ["algorithm_manager_api_test.py"],
    deps = [
        ":algorithm_manager_api",
        "//testing/pybase",
        "//third_party/odml/model_customization/quantization:typing",
        "//third_party/py/absl/testing:parameterized",
        "//third_party/py/jax",
    ],
)

pytype_strict_library(
    name = "algorithm_manager",
    srcs = ["algorithm_manager.py"],
    srcs_version = "PY3",
    deps = [
        ":algorithm_manager_api",
        "//third_party/odml/model_customization/quantization:typing",
        "//third_party/odml/model_customization/quantization/algorithms/uniform_quantize:naive_min_max_quantize",
        "//third_party/odml/model_customization/quantization/algorithms/uniform_quantize:uniform_quantize_tensor",
    ],
)

pytype_strict_library(
    name = "calibrator",
    srcs = ["calibrator.py"],
    srcs_version = "PY3",
    deps = [
        ":algorithm_manager",
        ":recipe_manager",
        ":typing",
        "//third_party/odml/model_customization/quantization/utils:tfl_flatbuffer_utils",
        "//third_party/odml/model_customization/quantization/utils:tfl_interpreter_utils",
        "//third_party/py/absl/logging",
    ],
)

pytype_strict_contrib_test(
    name = "calibrator_test",
    srcs = ["calibrator_test.py"],
    data = [
        "//third_party/odml/model_customization/quantization/test_models:test_tfl_models",
    ],
    deps = [
        ":calibrator",
        ":recipe_manager",
        ":typing",
        "//testing/pybase",
        "//third_party/odml/model_customization/quantization/utils:test_utils",
        "//third_party/odml/model_customization/quantization/utils:tfl_interpreter_utils",
        "//third_party/py/numpy",
    ],
)

pytype_strict_library(
    name = "transformation_instruction_generator",
    srcs = ["transformation_instruction_generator.py"],
    deps = [
        ":typing",
        "//third_party/odml/model_customization/quantization/utils:tfl_flatbuffer_utils",
        "//third_party/tensorflow/lite/python:schema_py",
    ],
)

pytype_strict_contrib_test(
    name = "transformation_instruction_generator_test",
    srcs = ["transformation_instruction_generator_test.py"],
    data = [
        "//third_party/odml/model_customization/quantization/test_models:test_tfl_models",
    ],
    deps = [
        ":transformation_instruction_generator",
        ":typing",
        "//testing/pybase",
        "//testing/pybase:parameterized",
        "//third_party/odml/model_customization/quantization/utils:test_utils",
        "//third_party/py/numpy",
    ],
)

pytype_strict_library(
    name = "transformation_performer",
    srcs = ["transformation_performer.py"],
    deps = [
        ":typing",
        "//third_party/odml/model_customization/quantization/transformations:dequant_insert",
        "//third_party/odml/model_customization/quantization/transformations:quantize_tensor",
        "//third_party/py/numpy",
        "//third_party/tensorflow/lite/python:schema_py",
    ],
)

pytype_strict_contrib_test(
    name = "transformation_performer_test",
    srcs = ["transformation_performer_test.py"],
    data = ["//third_party/odml/model_customization/quantization/test_models:test_tfl_models"],
    deps = [
        ":transformation_performer",
        ":typing",
        "//testing/pybase",
        "//testing/pybase:parameterized",
        "//third_party/odml/model_customization/quantization/utils:test_utils",
        "//third_party/odml/model_customization/quantization/utils:tfl_flatbuffer_utils",
        "//third_party/py/numpy",
    ],
)

pytype_strict_library(
    name = "model_modifier",
    srcs = ["model_modifier.py"],
    deps = [
        ":transformation_instruction_generator",
        ":transformation_performer",
        ":typing",
        "//third_party/odml/model_customization/quantization/utils:tfl_flatbuffer_utils",
        "//third_party/py/numpy",
        "//third_party/tensorflow/lite/python:schema_py",
        "//third_party/tensorflow/lite/tools:flatbuffer_utils",
    ],
)

pytype_strict_contrib_test(
    name = "model_modifier_test",
    srcs = ["model_modifier_test.py"],
    data = ["//third_party/odml/model_customization/quantization/test_models:test_tfl_models"],
    deps = [
        ":model_modifier",
        ":params_generator",
        ":recipe_manager",
        ":typing",
        "//testing/pybase",
        "//testing/pybase:parameterized",
        "//third_party/odml/model_customization/quantization/utils:test_utils",
        "//third_party/odml/model_customization/quantization/utils:tfl_flatbuffer_utils",
        "//third_party/tensorflow/lite/tools:flatbuffer_utils",
    ],
)

pytype_strict_library(
    name = "model_validator",
    srcs = ["model_validator.py"],
    deps = [
        "//third_party/odml/model_customization/quantization/utils:tfl_interpreter_utils",
        "//third_party/py/numpy",
    ],
)

pytype_strict_contrib_test(
    name = "model_validator_test",
    srcs = ["model_validator_test.py"],
    data = ["//third_party/odml/model_customization/quantization/test_models:test_tfl_models"],
    deps = [
        ":model_validator",
        "//testing/pybase",
        "//third_party/odml/model_customization/quantization/utils:test_utils",
        "//third_party/odml/model_customization/quantization/utils:tfl_interpreter_utils",
        "//third_party/odml/model_customization/quantization/utils:validation_utils",
    ],
)

py_strict_test(
    name = "end_to_end_test",
    srcs = ["end_to_end_test.py"],
    data = ["//third_party/odml/model_customization/quantization/test_models:test_tfl_models"],
    deps = [
        ":quantization_toolkit",
        ":typing",
        "//testing/pybase",
        "//third_party/odml/model_customization/quantization/utils:test_utils",
        "//third_party/py/absl/testing:parameterized",
    ],
)
