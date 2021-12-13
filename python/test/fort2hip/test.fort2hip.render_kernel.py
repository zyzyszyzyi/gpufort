#!/usr/bin/env python3
import os
import json
import unittest
import cProfile,pstats,io,time
import addtoplevelpath
import indexer.indexerutils
import utils.logging
import fort2hip.model

LOG_FORMAT = "[%(levelname)s]\tgpufort:%(message)s"
utils.logging.VERBOSE    = False
utils.logging.init_logging("log.log",LOG_FORMAT,"warning")

PROFILING_ENABLE = False

# render_hip_kernel_comment_hip_cpp
# render_hip_kernel_hip_cpp
# render_hip_kernel_synchronization_hip_cpp
# render_hip_kernel_launcher_hip_cpp
# render_cpu_kernel_launcher_hip_cpp

declaration_list= \
"""
type basic
  real(8)            :: scalar_double
  integer(4),pointer :: array_integer(:,:)
end type basic

type nested
  type(basic)                            :: single_basic
  type(basic),allocatable,dimension(:,:) :: array_basic
  integer(4),pointer                     :: array_integer(:,:,:)
end type nested

real(8)            :: scalar_double
integer(4),pointer :: array_integer(:,:,:)
type(nested)       :: derived_type
!
real(8)        :: scalar_double_local
real(8),shared :: scalar_double_shared
"""

class TestRenderKernel(unittest.TestCase):
    def prepare(self,text):
        return text.strip().split("\n")
    def clean(self,text):
        return text.replace(" ","").replace("\t","").replace("\n","").replace("\r","")
    def setUp(self):
        global PROFILING_ENABLE
        if PROFILING_ENABLE:
            self._profiler = cProfile.Profile()
            self._profiler.enable()
        self._started_at = time.time()
        self._scope = indexer.indexerutils.create_scope_from_declaration_list(declaration_list)
    def tearDown(self):
        global PROFILING_ENABLE
        if PROFILING_ENABLE:
            self._profiler.disable() 
            s = io.StringIO()
            sortby = 'cumulative'
            stats = pstats.Stats(self._profiler, stream=s).sort_stats(sortby)
            stats.print_stats(10)
            print(s.getvalue())
        elapsed = time.time() - self._started_at
        print('{} ({}s)'.format(self.id(), round(elapsed, 6)))
    def create_kernel_context(self,kernel_name):
        local_vars          = [ivar for ivar in self._scope["variables"] if "_local" in ivar["name"]]
        shared_vars         = [ivar for ivar in self._scope["variables"] if "_shared" in ivar["name"]]
        global_vars         = [ivar for ivar in self._scope["variables"] if ivar not in local_vars and\
                              ivar not in shared_vars]
        global_reduced_vars = [] 
        #print([ivar["name"] for ivar in local_vars])
        #print([ivar["name"] for ivar in shared_vars])
        #print([ivar["name"] for ivar in global_vars])
        kernel = {}
        kernel["launch_bounds"]       = "__launch_bounds___(1024,1)"
        kernel["name"]                = kernel_name
        kernel["shared_vars"]         = shared_vars
        kernel["local_vars"]          = local_vars
        kernel["global_vars"]         = global_vars
        kernel["global_reduced_vars"] = global_reduced_vars
        kernel["c_body"]              = "// do nothing" 
        kernel["f_body"]              = "! do nothing"
        return kernel
    def create_gpu_kernel_launcher_context(self,
                                           kernel_name,kind="auto",
                                           debug_output=True):
        kernel_launcher = {}
        # for launcher interface
        kernel_launcher["kind"]         = "auto"
        if len(kind):
            kernel_launcher["name"]     = "_".join(["launch",kernel_name,kind])
        else:
            kernel_launcher["name"]     = "_".join(["launch",kernel_name])
        kernel_launcher["block"]        = [1024,1,1]
        kernel_launcher["grid"]         = [4,1,1] 
        kernel_launcher["problem_size"] = [4096,1,1] 
        kernel_launcher["debug_output"] = True
        return kernel_launcher
    def create_cpu_kernel_launcher_context(self,
                                           kernel_name,kind="auto"):
        # for launcher interface
        kernel_launcher = {}
        kernel_launcher["launcher_name"] = "_".join(["launch",kernel_name,"cpu"])
        kernel_launcher["debug_output"]  = True
        return kernel_launcher
    def test_1_render_kernel(self):
        print(fort2hip.model.render_hip_kernel_hip_cpp(self.create_kernel_context("mykernel")))
    def test_2_render_hip_kernel_launcher(self):
        print(fort2hip.model.render_hip_kernel_launcher_hip_cpp(self.create_kernel_context("mykernel"),
                                                                self.create_gpu_kernel_launcher_context("mykernel")))
    def test_3_render_cpu_kernel_launcher(self):
        print(fort2hip.model.render_cpu_kernel_launcher_hip_cpp(self.create_kernel_context("mykernel"),
                                                                self.create_cpu_kernel_launcher_context("mykernel")))
        

if __name__ == '__main__':
    unittest.main() 
