# Copyright 2021 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import functools
import operator

import jaxlib.mlir.ir as ir
import jaxlib.mlir.dialects.mhlo as mhlo

import numpy as np

from jaxlib import xla_client

try:
  from . import _hip_linalg
  for _name, _value in _hip_linalg.registrations().items():
    xla_client.register_custom_call_target(_name, _value, platform="ROCM")
except ImportError:
  pass

_prod = lambda xs: functools.reduce(operator.mul, xs, 1)


def lu_pivots_to_permutation_mhlo(pivots, *, permutation_size):
  """Kernel for the transformation of pivots to permutations on GPU."""
  typ = ir.RankedTensorType(pivots.type)
  dims = typ.shape
  i32_type = ir.IntegerType.get_signless(32)

  assert typ.element_type == i32_type, typ

  batch_size = _prod(dims[:-1])
  pivot_size = dims[-1]

  opaque = _hip_linalg.hip_lu_pivots_to_permutation_descriptor(
      batch_size, pivot_size, permutation_size)
  pivots_layout = ir.DenseIntElementsAttr.get(np.arange(len(dims) - 1, -1, -1),
                                              type=ir.IndexType.get())
  permutations_layout = pivots_layout
  permutations_dims = list(dims)
  permutations_dims[-1] = permutation_size
  permutations_type = ir.RankedTensorType.get(permutations_dims, i32_type)
  return mhlo.CustomCallOp(
      [permutations_type],
      [pivots],
      call_target_name = ir.StringAttr.get("hip_lu_pivots_to_permutation"),
      has_side_effect=ir.BoolAttr.get(False),
      backend_config=ir.StringAttr.get(opaque),
      api_version=ir.IntegerAttr.get(i32_type, 2),
      called_computations=ir.ArrayAttr.get([]),
      operand_layouts=ir.ArrayAttr.get([pivots_layout]),
      result_layouts=ir.ArrayAttr.get([permutations_layout])).result
