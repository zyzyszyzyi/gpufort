#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2020-2022 Advanced Micro Devices, Inc. All rights reserved.
# SPDX-License-Identifier: MIT
# Copyright (c) 2020-2022 Advanced Micro Devices, Inc. All rights reserved.
import test
import gpufort.translator

testdata ="""
a0(1,2)
a0(1)
""".strip(" ").strip("\n").splitlines()

test.run(
   expression     = translator.func_call,
   testdata       = testdata,
   tag            = "func_call",
   raiseException = True
)

for v in testdata:
    print(translator.func_call.parseString(v)[0].c_str())