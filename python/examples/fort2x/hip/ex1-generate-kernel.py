#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2020-2022 Advanced Micro Devices, Inc. All rights reserved.
import os
import addtoplevelpath
from gpufort import util
from gpufort import fort2x
from gpufort import indexer

LOG_FORMAT = "[%(levelname)s]\tgpufort:%(message)s"
util.logging.opts.verbose = False
util.logging.init_logging("log.log", LOG_FORMAT, "debug")

def my_parameter_filter(*args):
    return True

fort2x.opts.namespace_per_scope_parameter_filter = my_parameter_filter

declaration_list = """\
integer, parameter :: N = 1000, M=2000, P = 10, amp = 2
integer :: i,j,k
integer(4) :: y(N,M,P), y_exact(N)
integer, dimension(-amp:amp) :: coeffs

type grid_t
  integer(4) :: alpha
  integer(4),allocatable :: x(:,:,:)
end type

type(grid_t) :: grid
"""

annotated_loop_nest = """\
!$acc parallel loop present(grid%x(:,:,5),y(:,:,7)) private(k,i,coeffs) collapse(2)
#ifndef single_loop
do j = 1, -(max(M,n)), min(m,n,2)
#endif
  do i = 1, N
    grid%x(i,j,5) = 1
    y(i,j,7) = 2

    do while ( k < 10 )
      y(i,j,7) = grid%alpha * grid%x(i,j,5) * k
      k = k + 1
    end do
    y(j,i:i+2,7) = grid%x(j,i:i+2,5); k &
                                        = 1

    if (i == 5.and.j > 2) then 
      k = 2*k
      go to 50
    else
      select case (i)
        case (1)
          k = 1*i
        case (2,3,-4)
          k = 2*i
        case default
          k = i
      end select
    endif
50 continue
  end do
#ifndef single_loop
end do
#endif
"""

#print(ttloopnest.cstr())
kernelgen = fort2x.hip.create_kernel_generator_from_loop_nest(
    declaration_list, annotated_loop_nest, kernel_name="mykernel")

nsgen = fort2x.namespacegen.NamespaceGenerator(indexer.scope.create_index_from_scope(kernelgen.scope),
                                               kernelgen.scope["tag"])
print("\n".join(nsgen.render_namespace_cpp()))

print("\n".join(kernelgen.render_gpu_kernel_cpp()))
launcher = kernelgen.create_launcher_context(kind="hip",
                                             debug_code=False,
                                             used_modules=[])
print("\n".join(kernelgen.render_gpu_launcher_cpp(launcher)))
launcher = kernelgen.create_launcher_context(kind="hip_ps",
                                             debug_code=False,
                                             used_modules=[])
print("\n".join(kernelgen.render_gpu_launcher_cpp(launcher)))