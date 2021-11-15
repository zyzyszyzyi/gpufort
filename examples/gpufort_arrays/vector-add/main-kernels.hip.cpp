// This file was generated by gpufort
#ifndef __KERNELS_HIP_CPP__
#define __KERNELS_HIP_CPP__
#include "hip/hip_runtime.h"
#include "hip/hip_complex.h"
#include "gpufort.h"
#include "gpufort_arrays.h"


// BEGIN main_26_e28c45
/*
   HIP C++ implementation of the function/loop body of:

     !$cuf kernel do(1) <<<grid, tBlock>>>
     do i=1,size(y_d,1)
       y_d(i) = y_d(i) + a*xi
     end do

*/

__global__ void  vecadd_kernel(
    gpufort::array1<float> y_d,
    float a,
    gpufort::array1<float> x_d
) {
  int i = 1 + (1)*(threadIdx.x + blockIdx.x * blockDim.x);
  if (loop_cond(i,y_d.size(1),1)) {
    y_d(i)= y_d(i) + a*x_d(i);
  }
}

extern "C" void launch_vecadd_kernel_auto_(
    const int& sharedmem, 
    hipStream_t& stream,
    gpufort::array1<float>& y_d,
    float& a,
    gpufort::array1<float>& x_d
) {
  const int vecadd_kernel_blockX = 128;
  dim3 block(vecadd_kernel_blockX);
  const int vecadd_kernel_NX = (1 + ((y_d.size(1)) - (1)));
  const int vecadd_kernel_gridX = divideAndRoundUp( vecadd_kernel_NX, vecadd_kernel_blockX );
  dim3 grid(vecadd_kernel_gridX);
   
  // launch kernel
  hipLaunchKernelGGL((vecadd_kernel), grid, block, sharedmem, stream, y_d, a, x_d);
}
// END vecadd_kernel
#endif // __KERNELS_HIP_CPP__ 