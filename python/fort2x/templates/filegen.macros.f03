{#- SPDX-License-Identifier: MIT                                        -#}
{#- Copyright (c) 2021 Advanced Micro Devices, Inc. All rights reserved.-#}
{########################################################################################}
{% import "common.macros.f03" as cm %}
{########################################################################################}
{%- macro render_interface_module(name,
                                  used_modules=[],
                                  rendered_types=[],
                                  rendered_interfaces=[],
                                  rendered_routines=[],
                                  prolog="! This file was autogenerated by GPUFORT") -%}
{{prolog}}
module {{name}}
{% if used_modules|length %}
{{cm.render_used_modules(used_modules)|indent(2,True)-}}
{% endif %}
  implicit none
{% if rendered_types|length %}

{% for rendered_type in rendered_types %}
{{rendered_type|indent(2,True)}}
{% endfor %}
{% endif %}
{% if rendered_interfaces|length %}

{% for rendered_interface in rendered_interfaces %}
{{rendered_interface|indent(2,True)}}
{% endfor %}
{% endif %}
{% if rendered_routines|length %}

contains
{% for rendered_routine in rendered_routines %}
{{rendered_routine | indent(2,true)}}
{% endfor %}
{% endif %}
end module {{name}}
{%- endmacro -%}
