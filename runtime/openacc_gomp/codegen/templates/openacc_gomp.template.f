{# SPDX-License-Identifier: MIT #}
{# Copyright (c) 2020-2022 Advanced Micro Devices, Inc. All rights reserved. #}
! SPDX-License-Identifier: MIT 
! Copyright (c) 2020-2022 Advanced Micro Devices, Inc. All rights reserved. 

!
! autogenerated routines for different inputs
!

module openacc_gomp
  use iso_c_binding
  use openacc
  use openacc_gomp_base
  
{% set routine = "acc_deviceptr" %}
  interface {{routine}}
    function {{routine}}_b(hostptr) result(deviceptr) bind(c,name="acc_deviceptr")
      use iso_c_binding
      implicit none
      !
      type(c_ptr),value,intent(in) :: hostptr
      !
      type(c_ptr)                  :: deviceptr
    end function

    module procedure {% for tuple in datatypes -%}
{%- for dims in dimensions -%}
{%- set name = routine + "_" + tuple[0] + "_" + dims|string -%}                                                              
{{name}}{{ "," if not loop.last }}
{%- endfor %}
{{ "," if not loop.last }}
{%- endfor %} 
  end interface

{% for mapping in mappings -%}
{%- set routine = "map_" + mapping[0] %}
  interface {{routine}}
    module procedure {{routine}}_b
{%- for tuple in datatypes -%}
{%- for dims in dimensions -%}
{%- set name = routine + "_" + tuple[0] + "_" + dims|string -%}                                                              
,{{name}} 
{%- endfor -%}
{%- endfor %} 
  end interface

{% endfor %} 
  contains 

{% set routine = "acc_deviceptr" %}
    ! {{routine}}
{% for tuple in datatypes -%}
{%- for dims in dimensions -%}
{% if dims > 0 %}
{% set size = 'size(hostptr)*' %}
{% set rank = ',dimension(' + ':,'*(dims-1) + ':)' %}
{% else %}
{% set size = '' %}
{% set rank = '' %}
{% endif %}
{% set suffix = tuple[0] + "_" + dims|string %}                                                              
    recursive function {{routine}}_{{suffix}}(hostptr) result(deviceptr)
      use iso_c_binding
      implicit none
      {{tuple[2]}},target{{ rank }},intent(in) :: hostptr
      !
      type(c_ptr) :: deviceptr
      !
      deviceptr = {{routine}}_b(c_loc(hostptr))
    end function

{% endfor %} 
{% endfor %} 

{% for mapping in mappings -%}
{% set routine = "map_" + mapping[0] %}
    ! {{routine}}
    recursive function {{routine}}_b(hostptr,num_bytes) result(retval)
      use iso_c_binding
      use openacc_gomp_base, only: mapping, {{mapping[1]}}
      implicit none
      !
      type(c_ptr),intent(in)       :: hostptr
      integer(c_size_t),intent(in) :: num_bytes
      !
      type(mapping) :: retval
      !
      call retval%init(hostptr,num_bytes,{{mapping[1]}})
    end function

{% for tuple in datatypes -%}
{%- for dims in dimensions -%}
{% if dims > 0 %}
{% set size = 'size(hostptr)*' %}
{% set rank = ',dimension(' + ':,'*(dims-1) + ':)' %}
{% else %}
{% set size = '' %}
{% set rank = '' %}
{% endif %}
{% set suffix = tuple[0] + "_" + dims|string %}                                                              
    recursive function {{routine}}_{{suffix}}(hostptr) result(retval)
      use iso_c_binding
      use openacc_gomp_base, only: mapping
      implicit none
      {{tuple[2]}},target{{ rank }},intent(in) :: hostptr
      !
      type(mapping) :: retval
      !
      retval = {{routine}}_b(c_loc(hostptr),1_c_size_t*{{size}}{{tuple[1]}})
    end function

{% endfor %} 
{% endfor %} 
{% endfor -%} 

end module