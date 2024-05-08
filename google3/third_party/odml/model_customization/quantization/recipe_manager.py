"""Manages model quantization recipe (configuration) for the Toolkit."""

import collections
import dataclasses
import re
from typing import Any, Optional
from absl import logging
from google3.third_party.odml.model_customization.quantization import algorithm_manager
from google3.third_party.odml.model_customization.quantization import typing as qtyping

# A collection of quantization configuration.
# Key: scope regex.
# Value: list of OpQuantizationRecipe in dictionary format.
ModelQuantizationRecipe = list[dict[str, Any]]
_TFLOpName = qtyping.TFLOperationName
_OpQuantizationConfig = qtyping.OpQuantizationConfig
_TensorQuantizationConfig = qtyping.TensorQuantizationConfig


@dataclasses.dataclass
class OpQuantizationRecipe:
  """Dataclass for quantization configuration under a scope."""

  # Regular expression for scope name matching.
  regex: str

  # Target TFL operation. * for any supported TFL operation.
  operation: _TFLOpName

  # Algorithm key to be applied.
  algorithm_key: str

  # Quantization configuration to be applied for the op.
  op_config: _OpQuantizationConfig = dataclasses.field(
      default_factory=_OpQuantizationConfig
  )

  # Flag to check if this rule overrides the previous matched rule with
  # different algorithm key. Used when the algorithm keys of previous matched
  # config and the current config are different. When set to true, the
  # previously matched config is ignored; otherwise, the current matched config
  # is ignored.
  # When the algorithm keys of both configs are the same, then this flag does
  # not have any effect; the op_config of previously matched config is updated
  # using the op_config of this one.
  override_algorithm: bool = True


class RecipeManager:
  """Sets the quantization recipe for target model.

  Very similar design as mojax/flax_quantizer/configurator.py
  """

  def __init__(self):
    """Scope name config.

    Key: scope regex. ".*" for all scopes.
    Value: list of operator quantization settings under the scope.
    The priority between rules are determined by the order they entered: later
    one has higher priority.
    """
    self._scope_configs: collections.OrderedDict[
        str, list[OpQuantizationRecipe]
    ] = collections.OrderedDict()

  # TODO: b/335254997 - Check if an op quantization config is supported.
  def add_quantization_config(
      self,
      regex: str,
      operation_name: _TFLOpName,
      op_config: Optional[_OpQuantizationConfig] = None,
      algorithm_key: str = algorithm_manager.PTQ,
      override_algorithm: bool = True,
  ) -> None:
    """Adds a quantization configuration.

    Conflict arises when we are trying to set an operation under a certain regex
    which is already existed in the config dictionary. Under such circumstance,
    the new config is used to replace the previous one.

    We also have special treatment for _TFLOperationKey.ALL. If the new config
    is on _TFLOperationKey.ALL and there are existing op configs inside the same
    scope, we clear the previous configs and use _TFLOperationKey.ALL.

    Args:
      regex: Regular expression for layer name matching.
      operation_name: Target TFLite operation. * for all supported TFLite
        operation.
      op_config: Quantization configuration which will be used to update the
        default configuration. None or empty dict means the default
        configuration will be used.
      algorithm_key: Algorithm key to be applied.
      override_algorithm: Flag to check if this rule overrides the previously
        matched rule with different algorithm key.
    """
    if op_config is None:
      op_config = _OpQuantizationConfig()

    config = OpQuantizationRecipe(
        regex, operation_name, algorithm_key, op_config, override_algorithm
    )
    # Special care if trying to set all ops to some config.
    if config.operation == _TFLOpName.ALL:
      logging.warning(
          'Reset all op configs under scope_regex %s with %s.',
          regex,
          config,
      )
      self._scope_configs[regex] = [config]
      return

    if (
        algorithm_key != algorithm_manager.NO_QUANT
        and not algorithm_manager.is_op_registered(
            algorithm_key, operation_name
        )
    ):
      raise ValueError(
          f'Unsupported operation {operation_name} for algorithm'
          f' {algorithm_key}. Please check and update algorithm manager.'
      )

    if regex not in self._scope_configs:
      self._scope_configs[regex] = [config]
    else:
      # Reiterate configs to avoid duplication on op settings.
      configs = []
      is_new_op = True
      for existing_config in self._scope_configs[regex]:
        if existing_config.operation == config.operation:
          is_new_op = False
          op_config = config
          logging.warning(
              'Overwrite operation %s config under scope_regex %s with %s.',
              existing_config.operation,
              regex,
              config,
          )
        else:
          op_config = existing_config
        configs.append(op_config)
      if is_new_op:
        configs.append(config)
      self._scope_configs[regex] = configs

  def get_quantization_configs(
      self,
      target_op_name: _TFLOpName,
      scope_name: str,
  ) -> tuple[str, _OpQuantizationConfig]:
    """Gets the algorithm key and quantization configuration for an op.

    The configuration matching rules are tested in the order they are put. In
    case there are two or more matching rules, if the same quantization
    algorithms are assigned for both rules, then the later quantization config
    will be used. If the  assigned algorithms are different,
    override_algorithm flag is used to see which algorithm will be used. If the
    flag is True, the latter is used. If the flag is False, the latter is
    ignored.


    Args:
      target_op_name: Target TFLite operation. * for all supported TFLite
        operation.
      scope_name: Name of the target scope.

    Returns:
       A tuple of quantization algorithm, and quantization configuration.
    """
    result_key, result_config = (
        algorithm_manager.NO_QUANT,
        _OpQuantizationConfig(),
    )
    for scope_regex, recipes in self._scope_configs.items():
      if re.search(scope_regex, scope_name):
        for recipe in recipes:
          if (
              recipe.operation != _TFLOpName.ALL
              and recipe.operation != target_op_name
          ):
            continue
          if result_key != recipe.algorithm_key:
            if recipe.override_algorithm:
              # Algorithm overridden: reinitialize config.
              result_key = recipe.algorithm_key
            else:
              # Ignore the current rule.
              continue
          result_config = recipe.op_config

    return result_key, result_config

  def get_quantization_recipe(self) -> ModelQuantizationRecipe:
    """Gets the full quantization recipe from the manager.

    Returns:
      A list of quantization configs in the recipe.
    """
    ret = []
    for _, scope_config in self._scope_configs.items():
      for quant_config in scope_config:
        config = dict()
        config['regex'] = quant_config.regex
        config['operation'] = quant_config.operation
        config['algorithm_key'] = quant_config.algorithm_key
        config['op_config'] = quant_config.op_config.to_dict()
        config['override_algorithm'] = quant_config.override_algorithm
        ret.append(config)
    return ret

  def load_quantization_recipe(
      self, quantization_recipe: ModelQuantizationRecipe
  ) -> None:
    """Loads the quantization recipe to the manager.

    Args:
      quantization_recipe: A configuration dictionary which is generated by
        get_full_config.
    """
    self._scope_configs = collections.OrderedDict()
    for config in quantization_recipe:
      self.add_quantization_config(
          config['regex'],
          config['operation'],
          _OpQuantizationConfig.from_dict(config['op_config']),
          config['algorithm_key'],
          config['override_algorithm'],
      )
