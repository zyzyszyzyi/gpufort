#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2021 Advanced Micro Devices, Inc. All rights reserved.
import os
import addtoplevelpath
import utils.logging
import fort2x.hip.fort2hiputils as fort2hiputils

LOG_FORMAT = "[%(levelname)s]\tgpufort:%(message)s"
utils.logging.VERBOSE    = False
utils.logging.init_logging("log.log",LOG_FORMAT,"warning")

PROFILING_ENABLE = False

declaration_list= """\
integer, parameter :: N = 1000, M=2000
integer :: i,j
integer(4) :: x(N), y(N), y_exact(N)
"""

annotated_loop_nest = """\
!$acc parallel loop present(x,y)
do i = 1, N
do j = 1, M
  x(i,j) = 1
  y(i,j) = 2
end do
end do
"""  

#print(ttloopnest.c_str())
kernelgen = fort2hiputils.create_kernel_generator_from_loop_nest(declaration_list,
                                                                 annotated_loop_nest,
                                                                 kernel_name="mykernel")

print("\n".join(kernelgen.render_gpu_kernel_cpp()))
launcher = kernelgen.create_launcher_context(kind="hip",
                                             debug_output=False,
                                             used_modules=[])
print("\n".join(kernelgen.render_gpu_launcher_cpp(launcher)))
launcher = kernelgen.create_launcher_context(kind="hip_ps",
                                             debug_output=False,
                                             used_modules=[])
print("\n".join(kernelgen.render_gpu_launcher_cpp(launcher)))
