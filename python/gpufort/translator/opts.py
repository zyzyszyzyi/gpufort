# SPDX-License-Identifier: MIT
# Copyright (c) 2020-2022 Advanced Micro Devices, Inc. All rights reserved.
# general options
log_prefix = "translator"
comment = r"(!|^\s*[\*cCdD])[^\$].+"
fortran_style_tensor_access = True
        # For a Fortran tensor access, emit `a(i,j,k,...)`
        # instead of the C style `a[_idx_a(i,j,k)]`.
        # This assumes that the generated kernel code makes use
        # of C++ classes such as those of the gpufort::array type
        # that are equipped with an overloaded () operator.
keyword_case = "lower" # one of ["lower","upper","camel"]
single_level_indent="  "
        # Default indent.
character_format = "{type}({len})"
        # Format to use when generating Fortran character datatype
derived_type_format = "{type}({kind})"
        # Format to use when generating datatype part of Fortran derived type variable
basic_type_format = "{type}({kind})"
        # Format to use when generating Fortran basic datatype such as integer/real/... types.
gpufort_cpp_symbols = {
    "threadidx.x": "(1+threadIdx.x)",
    "threadidx.y": "(1+threadIdx.y)",
    "threadidx.z": "(1+threadIdx.z)",
    "blockidx.x": "(1+blockIdx.x)",
    "blockidx.y": "(1+blockIdx.y)",
    "blockidx.z": "(1+blockIdx.z)",
    "blockdim.x": "blockDim.x",
    "blockdim.y": "blockDim.y",
    "blockdim.z": "blockDim.z",
    "griddim.x": "gridDim.x",
    "griddim.y": "gridDim.y",
    "griddim.z": "gridDim.z",
    "warpsize": "warpSize",
    "syncthreads": "__syncthreads",
    "atomicadd": "atomicAdd",
    "atomicsub": "atomicSub",
    "atomicmax": "atomicMax",
    "atomicmin": "atomicMin",
    "atomicand": "atomicAnd",
    "atomicor": "atomicOr",
    "atomicxor": "atomicXor",
    "atomicexch": "atomicExch",
    "atomicinc": "atomicInc",
    "atomicdec": "atomicDec",
    "atomiccas": "atomicCas",
    "sign": "copysign",
    # symbols generated by GPUFORT
    "__pow": "pow",
}
        # lower case C-like symbols generated from Fortran code and their translation to HIP C++ (device) symbols
max_directive_line_width = 80
unconverted = "TODO(gpufort) UNCONVERTED - Please adjust yourself!"
depend_todo = "TODO(gpufort) - specify depend inputs"
fortran_2_c_type_map = {
    "character": {
        "": "char",
        "c_char": "char",
    },
    "complex": {
        "": "hipFloatComplex",
        "16": None,
        "8": "hipDoubleComplex",
        "4": "hipFloatComplex",
        "2": None,
        "1": None,
        "c_float_complex": "hipFloatComplex",
        "c_double_complex": "hipDoubleComplex",
        "c_long_double_complex": "long double _complex",
    },
    "doubleprecision": {
        "": "double",
    },
    "real": {
        "": "float",
        "16": "long double",
        "8": "double",
        "4": "float",
        "2": "_Float16",
        "1": None,
        "c_float": "float",
        "c_double": "double",
        "c_long_double": "long double",
        "c_float128": "__float128",
        "c_float128_complex": "__float128 _complex",
    },
    "integer": {
        "": "int",
        "8": "long",
        "4": "int",
        "2": "short",
        "1": "char",
        "c_char": "char",
        "c_int": "int",
        "c_short": "short int",
        "c_long": "long int",
        "c_long_long": "long long int",
        "c_signed_char": "signed char",
        "c_size_t": "size_t",
        "c_int8_t": "int8_t",
        "c_int16_t": "int16_t",
        "c_int32_t": "int32_t",
        "c_int64_t": "int64_t",
        "c_int128_t": "int128_t",
        "c_int_least8_t": "int_least8_t",
        "c_int_least16_t": "int_least16_t",
        "c_int_least32_t": "int_least32_t",
        "c_int_least64_t": "int_least64_t",
        "c_int_least128_t": "int_least128_t",
        "c_int_fast8_t": "int_fast8_t",
        "c_int_fast16_t": "int_fast16_t",
        "c_int_fast32_t": "int_fast32_t",
        "c_int_fast64_t": "int_fast64_t",
        "c_int_fast128_t": "int_fast128_t",
        "c_intmax_t": "intmax_t",
        "c_intptr_t": "intptr_t",
        "c_ptrdiff_t": "ptrdiff_t",
    },
    "logical": {
        "": "int",
        "c_bool": "bool",
    },
    "type": {
      "dim3" : "dim3",
    },
}

fortran_type_2_bytes_map = { # x86_64
    "character": {
        "": "1",
        "c_char": "1"
    },
    "complex": {
        "": "2*4",
        "16": "2*16",
        "8": "2*8",
        "4": "2*4",
        "2": "2*2",
        "1": "2*1",
        "c_float_complex": "2*4",
        "c_double_complex": "2*8",
        "c_long_double_complex": "2*16"
    },
    "doubleprecision": {
        "": "8"
    },
    "real": {
        "": "4",
        "16": "16",
        "8": "8",
        "4": "4",
        "2": "2",
        "1": "1",
        "c_float": "4",
        "c_double": "8",
        "c_long_double": "16",
        "c_float128": "16",
        "c_float128_complex": "16"
    },
    "integer": {
        "": "4",
        "8": "8",
        "4": "4",
        "2": "2",
        "1": "1",
        "c_int": "4",
        "c_short": "2",
        "c_long": "8",
        "c_long_long": "16",
        "c_signed_char": "1",
        "c_size_t": "8",
        "c_int8_t": "1",
        "c_int16_t": "2",
        "c_int32_t": "4",
        "c_int64_t": "8",
        "c_int128_t": "16",
        "c_int_least8_t": "1",
        "c_int_least16_t": "2",
        "c_int_least32_t": "4",
        "c_int_least64_t": "8",
        "c_int_least128_t": "16",
        "c_int_fast8_t": "1",
        "c_int_fast16_t": "8",
        "c_int_fast32_t": "8",
        "c_int_fast64_t": "8",
        "c_int_fast128_t": "16",
        "c_intmax_t": "8",
        "c_intptr_t": "8",
        "c_ptrdiff_t": "8"
    },
    "logical": {
        "": "4",
        "c_bool": "1"
    }
}
#loop_versioning = False
#        # Emit different loop variants if the step size is not known
map_to_flat_arrays = True
        # Map allocatable or pointer array members of derived types to flat arrays.
map_to_flat_scalars = True
        # Map scalar members of derived types to flat scalars.
# options for CUF
cublas_version = 1
        # Assume cublas version 1, i.e. CUBLAS routines do not expect a handle
modern_fortran = True
