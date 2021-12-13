#!/usr/bin/env python3
import os,sys
import re
import pyparsing as pyp

MACRO_FILES = [
  "hip_implementation.macros.hip.cpp",
  "gpufort_array.macros.h",
  "interface_module.macros.f03",
  "gpufort_array.macros.f03"
]
MACRO_FILTERS = [
  re.compile("|".join(\
"""render_derived_type_copy_array_member_routines
render_derived_type_copy_scalars_routines
render_derived_types
render_derived_type_size_bytes_routines
render_cpu_kernel_launcher
render_hip_kernel
render_hip_kernel_comment
render_hip_kernel_launcher""".split("\n"))),
  re.compile("|".join(\
"""render_gpufort_array_c_bindings
render_gpufort_array_data_access_interfaces
render_gpufort_array_data_access_routines
render_gpufort_array_init_routines
render_gpufort_array_copy_to_buffer_routines
render_gpufort_array_wrap_routines
render_gpufort_array_interfaces""".split("\n")))
]

pyp.ParserElement.setDefaultWhitespaceChars("\r\n\t &;")

def iterate_macro_files(template_dir,action):
    ident       = pyp.pyparsing_common.identifier
    macro_open  = pyp.Regex(r"\{%-?\s+macro").suppress()
    macro_close = pyp.Regex(r"\s-#\}").suppress()
    LPAR,RPAR   = map(pyp.Suppress,"()")
    EQ          = pyp.Suppress("=")
    RHS         = pyp.Regex(r"\[\]|\"\w*\"|[0-9]+")
    arg         = pyp.Group(ident + pyp.Optional(EQ + RHS, default=""))
    arglist     = pyp.delimitedList(arg)
    macro       = macro_open + ident + LPAR + arglist + RPAR 

    for macrofile_name in MACRO_FILES:
        macrofile_ext = macrofile_name.split(".macros.")[-1]
        with open(os.path.join(template_dir,macrofile_name), "r") as infile:
            content = infile.read()
            for parse_result in macro.searchString(content):
                for regex in MACRO_FILTERS:
                    if regex.match(parse_result[0]):
                       #print(parse_result)
                       macro_name = parse_result[0]
                       macro_args = parse_result[1:]
                       macro_signature = "".join([macro_name,"(",\
                                                  ",".join([arg[0] for arg in macro_args]),")"])
                       template_content = \
                         "".join(["{% import \"",macrofile_name, "\" as macros %}\n",\
                                 "{{ macros.",macro_signature," }}"])
                       template_name = ".".join([parse_result[0],"template",macrofile_ext])
                       action(template_name,\
                              template_content,\
                              macro_name,macro_args)

def create_autogenerated_templates(template_dir):
    python_funcs = []
    def create_autogenerated_templates_action_(template_name,template_content,\
                                               macro_name,macro_args):
        with open(os.path.join(template_dir,template_name),"w") as outfile:
            outfile.write(template_content)
        templatefile_ext = template_name.split(".template.")[-1]
        func_name = macro_name+"_"+templatefile_ext.replace(".","_")
        python_funcs.append((func_name,macro_args,template_name))
    iterate_macro_files(template_dir,create_autogenerated_templates_action_)
    
    with open(os.path.join(template_dir,"model.py.in"),"w") as outfile: 
        rendered_funcs = []
        if len(python_funcs):
            rendered_funcs.append("# autogenerated file")
        for func in python_funcs:
            python_func_arg_list = []
            for arg in func[1]:
                if len(arg[1]):
                    python_func_arg_list.append("=".join(arg))
                else:
                    python_func_arg_list.append(arg[0])
            context = ",\n    ".join(["\"{0}\":{0}".format(arg[0]) for arg in func[1]])
            rendered_funcs.append("""def {0}({1}):
  context = {{
    {2} 
  }}
  return BaseModel("{3}").generate_code(context)
""".format(func[0],",".join(python_func_arg_list),context,func[2]))
        outfile.write("\n".join(rendered_funcs))

def delete_autogenerated_templates(template_dir):
    def delete_autogenerated_templates_action_(template_path,template_content,\
                                               macro_name,macro_args):
        if os.path.exists(template_path):
            os.remove(template_path)
    iterate_macro_files(template_dir,delete_autogenerated_templates_action_)
    
    with open(os.path.join(template_dir,"model.py.in"),"w") as outfile:
        outfile.write("")

def convert_macros_to_templates(template_dir):
    """coverts selected macros to templates"""
    delete_autogenerated_templates(template_dir)    
    create_autogenerated_templates(template_dir)

if __name__ == "__main__":
    convert_macros_to_templates(\
      os.path.abspath(os.path.join(__file__,"..")))