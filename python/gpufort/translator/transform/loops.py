# SPDX-License-Identifier: MIT
# Copyright (c) 2020-2022 Advanced Micro Devices, Inc. All rights reserved.
"""
:note: This module has intentionally no
       dependencies on other GPUFORT modules
       and packages.
"""

import copy
import re
import textwrap

single_level_indent = " "*2

_counters = {}

unique_label_template = "_{label}{num}"

def reset():
  """Resets the counters for labelling the helper variables.
  :note: Must be done explicitly to allow nesting of loops and loopnests."""
  _counters.clear()


def remove_unnecessary_helper_variables(code_to_modify,other_code_to_read=[]):
    """Remove unnecessary helper variables from `code_to_modify`,
    unless they are present in one of the optional
    `other_code_to_read` inputs. 

    Loop transformations and mapping to GPU resources
    can introduce unnecessary constants and can let 
    other constants become unused.
    This routine removes those variables iteratively.
   
    :parma str code_to_modify: The code to modify, as generated by
                               the Loopnest.map_to_hip_cpp and Loop.map_to_hip_cpp
                               routines
    :param str other_code_to_read: Other code that should be read in 
                               oder to determine if a variable is unused. 
    :return: The modified HIP C++ code.
    """
    statements = code_to_modify.split(";")
    condition = True
    while condition:
        condition = False
        joined_statements = ";".join(statements)
        # 1. Remove declaration of unused (never read) and unnecessary constants (const int _aXYZ = _bIJK;)
        replacements = {}
        for label,num_labels in _counters.items():
            for num in range(0,num_labels):
                varname = unique_label_template.format(
                  label=label,
                  num=num
                )
                p_const_int_decl = re.compile(r"^\s*const\s*int\s*\b"+varname+r"\b\s*=\s*(?P<rhs>\w+)\s*($|[\/])")
                count = joined_statements.count(varname)
                for code in other_code_to_read:
                    if code != None:
                        other_count = code.count(varname)
                for statement in list(statements):
                    if varname in statement:
                        if count == 1 and other_count == 0: # unused variable
                            statements.remove(statement)
                            condition = True
                        elif other_count == 0: # name not used in other files
                            match = p_const_int_decl.search(statement)
                            if match:
                                statements.remove(statement)
                                replacements[varname] = match.group("rhs")
                                condition = True
                                  
        # 2. Replace occurrence of helper variables that have been deemed unnecessary by their RHS value
        for i,statement in enumerate(statements):
            modified_statement = statement
            for pattern,subst in replacements.items():
                if pattern in modified_statement:
                    modified_statement = re.sub(r"\b"+pattern+r"\b",subst,modified_statement)
            if modified_statement != statement:
                statements[i] = modified_statement
                condition = True
    return joined_statements

hip_includes = \
"""
#include "gpufort_loop.h"
"""

_hip_kernel_prolog_acc =\
""""\
const gpufort::acc_grid _res(gridDim.x,gpufort::div_round_up(blockDim.x,warpSize),{vector_length});
const gpufort::acc_coords _coords(blockIdx.x,threadIdx.x/warpSize,threadIdx.x%warpSize);
"""

def render_hip_kernel_prolog(vector_length="warpSize"):
    return _hip_kernel_prolog.format(
        vector_length = vector_length)
 
def unique_label(label):
    """Returns a unique label for a loop variable that describes
    a loop entity. The result is prefixed with "_" to
    prevent collisions with Fortran variables.
    """
    if label not in _counters:
        _counters[label] = 0
    num = _counters[label]
    _counters[label] += 1
    return "_"+label+str(num)
    return unique_label_template.format(
      label=label,
      num=num
    )

def render_int_decl(lhs,rhs=None):
    if rhs == None or rhs == "":
        return "int {};\n".format(lhs,rhs)
    else:
        return "int {} = {};\n".format(lhs,rhs)

def render_const_int_decl(lhs,rhs):
    return "const int {} = {};\n".format(lhs,rhs)

def _render_tile_size_var_decl(tile_size_var,loop_len,num_tiles):
    """:return: C++ expression (str) that introduces a tile size var based
    on a loop length and a number of tiles.
    """
    rhs = "{fun}({loop_len},{num_tiles})".format(
              fun="gpufort::div_round_up",
              loop_len=loop_len,
              num_tiles=num_tiles)
    return render_const_int_decl(tile_size_var,rhs)

def _render_for_loop_open(index,incl_lbound,excl_ubound,step=None):
  if step == None:
      template = """\
for ({0} = {1}; 
     {0} < {2}; {0}++) {{
"""
  else:
      template = """\
for ({0} = {1};
     {0} < {2}; {0} += {3}) {{
"""
  return template.format(index,incl_lbound,excl_ubound,step)

class AccResourceFilter:
    def __init__(self,num_gangs=[],
                      num_workers=[],
                      vector_length=[],
                      resource_triple_name="_coords"):
        # note: the mutable (default) arguments cannot simply
        # be assigned, as all instances might modify
        # the same (default) instance.
        self.num_gangs = list(num_gangs)
        self.num_workers = list(num_workers)
        self.vector_length = list(vector_length)
        self.resource_triple_name = resource_triple_name
    def set_from(self,other):
        self.__init__(
          other.num_gangs,
          other.num_workers,
          other.vector_length,
          other.resource_triple_name
        )
    def __add__(self,other):
        return AccResourceFilter(
          self.num_gangs + other.num_gangs,
          self.num_workers + other.num_workers,
          self.vector_length + other.vector_length
        )
    def __iadd__(self,other):
        new = self.__add__(other)
        self.set_from(new)
        return self
    def __sub__(self,other):
        return AccResourceFilter(
          [e for e in self.num_gangs 
             if e not in other.num_gangs],
          [e for e in self.num_workers 
             if e not in other.num_workers],
          [e for e in self.vector_length 
             if e not in other.vector_length]
        )
    def __isub__(self,other):
        new = self.__sub__(other)
        self.set_from(new)
        return self
    def __eq__(self,other):
        return ( self.num_gangs == other.num_gangs
                 and self.num_workers == other.num_workers
                 and self.vector_length == other.vector_length )
    def __ne__(self,other):
        return not self.__eq__(other)
    def __len__(self):
        return (len(self.num_gangs) 
                + len(self.num_workers)
                + len(self.vector_length))
    def assert_is_well_defined(self):
        assert (not len(self.num_gangs) 
                or len(self.num_gangs) == 1)
        assert (not len(self.num_workers)
                or len(self.num_workers) == 1)
        assert (not len(self.vector_length)
                or len(self.vector_length) == 1)
    def loop_entry_condition(self):
        """:return a filter condition for masking
        in statements only for the certain resources.
        :note: If the entry in a list is None, no specific condition
               is added. None serves as a wildcard.
        """
        self.assert_is_well_defined()
        conditions = []

        def append_condition_if_not_none_(
              resource_triple_member,
              values):
            nonlocal conditions
            if len(values) and values[0] != None:
                conditions.append("{}.{} < {}".format(
                  self.resource_triple_name,
                  resource_triple_member,
                  values[0]
                ))
        append_condition_if_not_none_(
          "gang",self.num_gangs
        )
        append_condition_if_not_none_(
          "worker",self.num_workers
        )
        append_condition_if_not_none_(
          "vector_lane",self.vector_length
        )
        if len(conditions):
            return " && ".join(conditions)
        else:
            return "true" 
    def statement_selection_condition(self):
        self.assert_is_well_defined()
        conditions = []
        if not len(self.num_workers):
            conditions.append(
              "{}.worker == {}".format(
                self.resource_triple_name,
                "0" 
              )
            )
        if not len(self.vector_length):
            conditions.append(
              "{}.vector_lane == {}".format(
                self.resource_triple_name,
                "0" 
              )
            )
        if len(conditions):
            return " && ".join(conditions)
        else:
            return "true" 
    def index(self):
        return "_coords.get_vector_lane_id({res})".format(
          res=self.resource_triple_name       
        )
    def gang_partitioned_mode(self):
        return len(self.num_gangs)
    def worker_partitioned_mode(self):
        return len(self.num_workers)
    def vector_partitioned_mode(self):
        return len(self.vector_length)
    def worker_and_vector_partitioned_mode(self):
        return (self.worker_partitioned_mode()
                and self.vector_partitioned_mode())

class Loop:

    def assert_is_well_defined(self):
        assert self.grid_dim == None or self.grid_dim in ["x","y","z"],\
               "self.grid_dim must be chosen 'x','y', or 'z' or None"
        assert self.grid_dim == None or ( 
            not self.vector_partitioned
            and not self.worker_partitioned
            and not self.gang_partitioned) 
        assert (self._length != None 
               or self._last != None
               or self._excl_ubound != None), "one of self._length, self._last, self._excl_ubound must not be None"
    
    def __init__(self,
          index,
          first,
          last = None,
          length = None,
          excl_ubound = None,
          step = None,
          gang_partitioned = False,
          worker_partitioned = False,
          vector_partitioned = False,
          num_gangs = None,
          num_workers = None,
          vector_length = None,
          grid_dim = None, # one of ["x","y","z",None]
          prolog = None,
          body_prolog = None,
          body_epilog = None,
          body_extra_indent = ""):
        self.index = index.strip()
        self.first = first.strip()
        self._last = last
        self._length = length
        self._excl_ubound = excl_ubound
        self.step = step
        self.gang_partitioned = gang_partitioned
        self.worker_partitioned = worker_partitioned
        self.vector_partitioned = vector_partitioned
        self.grid_dim = grid_dim
        self.num_workers = num_workers
        self.num_gangs = num_gangs
        self.vector_length = vector_length
        self.prolog = prolog
        self.body_prolog = body_prolog
        self.body_epilog = body_epilog
        self.body_extra_indent = body_extra_indent
        self.assert_is_well_defined()

    def last(self):
        self.assert_is_well_defined()
        if self._last != None:
            return self._last
        elif self._excl_ubound != None:
            return "({} - 1)".format(self._excl_ubound)
        else:
            return "({} + {} - 1)".format(self.first,self._length)
        
    def excl_ubound(self):
        self.assert_is_well_defined()
        if self._excl_ubound != None:
            return self._excl_ubound
        elif self._last != None:
            return "({} + 1)".format(self._last)
        else:
            if self.step != None and self.step.strip() != "1":
                step_str = "("+self.step+")*"
            else:
                step_str = ""
            if self.first == "0":
                return step_str + self._length
            else:
                return "({} + {}{})".format(self.first,step_str,self._length)

    def length(self):
        self.assert_is_well_defined()
        if self._length != None:
            return self._length
        else:
            gpufort_fun = "gpufort::loop_len"
            if self.step == None:
                return "{}({},{})".format(
                  gpufort_fun,
                  self.first,self.last())
            else:
                return "{}({},{},{})".format(
                  gpufort_fun,
                  self.first,self.last(),self.step)


    def _is_normalized_loop(self):
        return (
                 self.first == "0" 
                 and (
                       self.step == None
                       or self.step.strip() == "1"
                     )
                )

    def _render_index_recovery(self,first,step,normalized_index):
        """:return: Expression that computes an original loop index
        from the normalized index, which runs from 0 to the length
        of the original loop, and the `first` index and `step` size
        of the original loop. 
        """
        if first != "0":
            result = first+" + "
        else:
            result = ""
        if step != None:
            result += "({})*{}".format(
              step,
              normalized_index
            )
        else: 
            result += normalized_index
        return result
    
    def tile(self,tile_size,
                  tile_loop_index_var=None):
        """
        :param tile_loop_index_var: Index to use for the loop over the tiles,
                                chosen automatically if None is passed.
        """
        # tile loop
        indent = ""
        orig_len_var = unique_label("len")
        tile_loop_prolog = render_const_int_decl( 
            orig_len_var,
            self.length()
        )
        num_tiles = "gpufort::div_round_up({loop_len},{tile_size})".format(
          loop_len=orig_len_var,
          tile_size=tile_size
        )
        num_tiles_var = unique_label("num_tiles")
        tile_loop_prolog += render_const_int_decl( 
            num_tiles_var,
            num_tiles
        )
        if tile_loop_index_var == None:
            tile_loop_index_var = unique_label("tile")
            tile_loop_prolog += render_int_decl(tile_loop_index_var)
        tile_loop = Loop(
            index = tile_loop_index_var,
            first = "0",
            length = num_tiles_var,
            excl_ubound = num_tiles_var,
            step = None,
            gang_partitioned = self.gang_partitioned,
            worker_partitioned = self.worker_partitioned if self.vector_partitioned else False,
            vector_partitioned = False,
            num_gangs = self.num_gangs,
            num_workers = self.num_workers if self.vector_partitioned else None,
            vector_length = self.vector_length,
            prolog=tile_loop_prolog)
        # element_loop
        element_loop_index_var = unique_label("elem")
        # element loop prolog
        element_loop_prolog = render_int_decl(element_loop_index_var)
        # element loop body prolog
        normalized_index_var = unique_label("idx")
        element_loop_body_prolog = render_const_int_decl( 
          normalized_index_var,
          "{} + ({})*{}".format(
            element_loop_index_var,
            tile_size,
            tile_loop_index_var
          )
        )
        element_loop_body_prolog += "if ( {normalized_index} < {orig_len} ) {{\n".format(
          normalized_index=normalized_index_var,
          orig_len=orig_len_var
        )
        element_loop_body_epilog = "}\n"
        indent += single_level_indent
        # recover original index
        element_loop_body_prolog += "{}{} = {};\n".format( 
          indent,
          self.index,
          self._render_index_recovery(
            self.first,self.step,normalized_index_var
          )
        )
        element_loop = Loop(
          index = element_loop_index_var,
          first = "0",
          length = tile_size,
          excl_ubound = tile_size,
          step = self.step,
          gang_partitioned = False,
          worker_partitioned = False if self.vector_partitioned else self.worker_partitioned,
          vector_partitioned = self.vector_partitioned,
          num_gangs = self.num_gangs,
          num_workers = None if self.vector_partitioned else self.num_workers,
          vector_length = self.vector_length,
          prolog = element_loop_prolog,
          body_prolog = element_loop_body_prolog,
          body_epilog = element_loop_body_epilog,
          body_extra_indent = single_level_indent)
        return (tile_loop,element_loop)

    def _render_hip_prolog_and_epilog_acc(self,local_res_var):
        hip_loop_prolog =\
"""
const gpufort::acc_grid {local_res}(
  {num_gangs},
  {num_workers},
  {vector_length});
if ( {loop_entry_condition} ) {{
"""

        hip_loop_epilog = """\
}} // {comment}
"""
        resource_filter = AccResourceFilter()
        if self.vector_partitioned:
            if self.vector_length == None:
                vector_length = "gpufort::acc_resource_all"  
                resource_filter.vector_length.append(None)
            else:
                vector_length = self.vector_length
                resource_filter.vector_length.append(
                  local_res_var+".vector_lanes"
                )
        else:
            vector_length = "1"
        if self.worker_partitioned:
            if self.num_workers == None:
                num_workers = "gpufort::acc_resource_all"  
                resource_filter.num_workers.append(None)
            else:
                num_workers = self.num_workers
                resource_filter.num_workers.append(
                  local_res_var+".workers"
                )
        else:
            num_workers = "1"
        num_gangs = "gpufort::acc_resource_all"
        resource_filter.num_gangs.append(None)
        if self.gang_partitioned:
            if self.num_gangs != None:
                num_gangs = self.num_gangs
                resource_filter.num_gangs[0] = local_res_var+".gangs"
            
        loop_open = hip_loop_prolog.format(
          local_res=local_res_var,
          num_gangs=num_gangs,
          num_workers=num_workers,
          vector_length=vector_length,
          loop_entry_condition=resource_filter.loop_entry_condition()
        )
        loop_close = hip_loop_epilog.format(
          comment=local_res_var
        )
        return (loop_open,loop_close,resource_filter)

    def map_to_hip_cpp(self,
          remove_unnecessary=True):
        """:return: HIP C++ device code.
        :note: Maps to blocks and threads if self.grid_dim is chosen
               as 'x','y','z'.
        """
        self.assert_is_well_defined()
        indent = "" 
        loop_open = ""
        loop_close = ""
        resource_filter = AccResourceFilter()
        vector_partitioned = (
          self.grid_dim in ["x","y","z"]
          or self.vector_partitioned
        )
        partitioned = (
          vector_partitioned
          or self.worker_partitioned
          or self.gang_partitioned
        )
        if partitioned: 
            if self.grid_dim == None: # only for acc
                local_res_var = unique_label("local_res")
                hip_prolog, hip_epilog, resource_filter =\
                  self._render_hip_prolog_and_epilog_acc(local_res_var) 
                loop_open += hip_prolog
                indent += single_level_indent
            # prepend the original prolog
            if self.prolog != None:
                loop_open += textwrap.indent(self.prolog,indent)
            #
            orig_len_var = unique_label("len")
            worker_tile_size_var = unique_label("worker_tile_size")
            if self.grid_dim == None:
                num_worker_tiles = "{}.total_num_workers()".format(local_res_var)
                worker_id_var = unique_label("worker_id")
            else:
                num_worker_tiles = "gridDim.{0}".format(self.grid_dim)
                worker_id_var = "blockIdx.{0}".format(self.grid_dim)
            #
            loop_open += textwrap.indent(
              render_const_int_decl(
                orig_len_var,
                self.length()
              ) 
              +
              _render_tile_size_var_decl(
                worker_tile_size_var,
                orig_len_var,
                num_worker_tiles
              ),
              indent
            )
            if self.grid_dim == None:
                loop_open += textwrap.indent(
                  render_const_int_decl(
                    worker_id_var,
                    "_coords.worker_id({})".format(local_res_var)
                  ),
                  indent
                )
            if vector_partitioned: # vector, worker-vector, gang-worker-vector
                # loop over vector lanes
                if self._is_normalized_loop():
                    index_var = self.index
                else:
                    index_var = unique_label("idx")
                if self.grid_dim == None: # acc
                    first = "_coords.vector_lane + {}*{}".format(
                      worker_id_var,
                      worker_tile_size_var
                    )
                    vector_tile_size = local_res_var+".vector_lanes"
                else:
                    first = "threadIdx.{0} + blockIdx.{0}*{1}".format(
                      self.grid_dim,
                      worker_tile_size_var
                    )
                    vector_tile_size = "blockDim.{0}".format(self.grid_dim)
                excl_ubound_var = unique_label("excl_ubound")
                loop_open += textwrap.indent(
                  render_const_int_decl( 
                    excl_ubound_var,
                    "min({},({}+1)*{})".format(
                      orig_len_var,
                      worker_id_var,
                      worker_tile_size_var
                    )
                  )
                  +
                  _render_for_loop_open(
                    index_var,
                    first,
                    excl_ubound_var,
                    vector_tile_size
                  ),
                  indent
                )
                loop_close = indent+"}} // {}\n".format(index_var) + loop_close
                indent += single_level_indent
                # recover the original index
                if not self._is_normalized_loop():
                    loop_open += "{}{} = {};\n".format(
                      indent,
                      self.index,
                      self._render_index_recovery(
                        self.first,self.step,index_var
                      )
                    )
            else:
                # keep the element loop, map tile loop to resources
                tile_loop, element_loop = self.tile(
                    worker_tile_size_var,
                    tile_loop_index_var=worker_id_var
                )
                if tile_loop.prolog != None:
                    tile_loop_prolog = tile_loop.prolog
                else:
                    tile_loop_prolog = ""
                if element_loop.prolog != None:
                    element_loop_prolog = element_loop.prolog
                else:
                    element_loop_prolog = ""
                loop_open += textwrap.indent(
                  tile_loop_prolog
                  +
                  element_loop_prolog
                  +
                  _render_for_loop_open(
                    element_loop.index,
                    element_loop.first,
                    element_loop.excl_ubound(),
                    element_loop.step
                  ),
                  indent
                )
                loop_close = indent+"}} // {}\n".format(element_loop.index) + loop_close
                #
                indent += single_level_indent
                loop_open += textwrap.indent(
                  element_loop.body_prolog.replace("$idx$",worker_id_var),
                  indent
                )
                loop_close = textwrap.indent(
                  element_loop.body_epilog.replace("$idx$",worker_id_var),
                  indent
                ) + loop_close
                indent += element_loop.body_extra_indent
            if self.grid_dim == None: 
                loop_close += hip_epilog
        else: # unpartitioned loop
            # prepend the original prolog
            if self.prolog != None:
                loop_open += self.prolog
            loop_open += _render_for_loop_open(
              self.index,
              self.first,
              self.excl_ubound(),
              self.step
            )
            loop_close = "}} // {}\n".format(
              self.index
            )
            indent += single_level_indent

        # add the body prolog & epilog of this loop, outcome of previous loop transformations
        if self.body_prolog != None:
            loop_open += textwrap.indent(
              self.body_prolog.replace("$idx$",self.index),
              indent
            )
        if self.body_epilog != None:
          loop_close = textwrap.indent(
            self.body_epilog.replace("$idx$",self.index),
            indent
          ) + loop_close
        if remove_unnecessary:
            loop_open = remove_unnecessary_helper_variables(
              loop_open,[loop_close]
            )
        return (loop_open,
                loop_close,
                resource_filter,
                indent+self.body_extra_indent)

class Loopnest:
    """ Transforms tightly-nested loopnests where only the first loop
    stores information about loop transformations and mapping the loop to a HIP
    device. Possible transformations are collapsing and tiling of the loopnest.
    In the latter case, the loopnest must contain as many loops as tiles.
    Mapping to a HIP device is performed based on the
    offload information stored in the first loop of the loopnest.
    """
    def __init__(self,loops=[]):
        self._loops = []
        for loop in loops:
            self.append(loop)
        self._is_tiled = False
    def __len__(self):
        return len(self.loops)
    def __getitem__(self, key):
        return self._loops[key]
    def append(self,loop):
        self._loops.append(loop) 
    def collapse(self):
        """Collapse all loops in the loopnest."""
        assert len(self._loops)
        loop_lengths_vars = []
        first_loop = self._loops[0]
        # Preamble before loop
        prolog = ""
        for i,loop in enumerate(self._loops):
            if loop.prolog != None:
                prolog += loop.prolog
            loop_lengths_vars.append(unique_label("len"))
            prolog += render_const_int_decl(
              loop_lengths_vars[-1],
              loop.length()
            )
        total_len_var = unique_label("total_len")
        prolog += render_const_int_decl(
          total_len_var,
          "*".join(loop_lengths_vars)
        )
        collapsed_index_var = unique_label("idx")
        prolog += "int {};\n".format(collapsed_index_var)
        # Preamble within loop body
        body_prolog = ""
        remainder_var = unique_label("rem");
        denominator_var= unique_label("denom")
        # template, idx remains as placeholder
        # we use $idx$ and simple str.replace as the
        # { and } of C/C++ scopes could cause issues
        # with str.format
        body_prolog += "int {rem} = $idx$;\n".format(rem=remainder_var)
        body_prolog += "int {denom} = {total_len};\n".format(
          denom=denominator_var,total_len=total_len_var
        )
        # index recovery
        for i,loop in enumerate(self._loops):
            if loop.step != None:
                body_prolog += "{} = {};\n".format(
                  loop.index,
                  "gpufort::outermost_index({}/*inout*/,{}/*inout*/,{},{},{})".format(
                    remainder_var,
                    denominator_var,
                    loop.first,
                    loop_lengths_vars[i],
                    loop.step
                  )
                )
            else:
                body_prolog += "{} = {};\n".format(
                  loop.index,
                  "gpufort::outermost_index({}/*inout*/,{}/*inout*/,{},{})".format(
                    remainder_var,
                    denominator_var,
                    loop.first,
                    loop_lengths_vars[i]
                  )
                )
        # add body prolog & epilog of individual loops
        body_epilog = ""
        indent = ""
        for loop in self._loops:
            if loop.body_prolog != None:
                body_prolog += textwrap.indent(loop.body_prolog,indent)
            if loop.body_epilog != None:
                body_epilog = textwrap.indent(loop.body_epilog,indent) + body_epilog
            indent += loop.body_extra_indent
        collapsed_loop = Loop(
          index = collapsed_index_var,
          first = "0",
          length = total_len_var,
          excl_ubound = total_len_var,
          step = None,
          gang_partitioned = first_loop.gang_partitioned,
          worker_partitioned = first_loop.worker_partitioned,
          vector_partitioned = first_loop.vector_partitioned,
          num_gangs = first_loop.num_gangs,
          num_workers = first_loop.num_workers,
          vector_length = first_loop.vector_length,
          prolog = prolog, 
          body_prolog = body_prolog,
          body_epilog = body_epilog,
          body_extra_indent = indent)
        return collapsed_loop

    def tile(self,tile_sizes,
             collapse_tile_loops=True,
             collapse_element_loops=True):
        """Tile the loops in the loopnest with respect to the `tile_sizes` argument.
      
        :param bool collapse_tile_loops:
        :param bool collapse_elements_loops:
        """
        if isinstance(tile_sizes,str):
            tile_sizes = [tile_sizes]
        assert len(tile_sizes) == len(self._loops)
        tile_loops = Loopnest()
        element_loops = Loopnest()
        for i,loop in enumerate(self._loops):
            tile_loop, element_loop = loop.tile(tile_sizes[i])
            tile_loops.append(tile_loop)
            element_loops.append(element_loop)
        # Only first tile loop and element loop inherit 
        # partitioning attributes
        for loop in tile_loops[1:]+element_loops[1:]:
            loop.gang_partitioned = False
            loop.worker_partitioned = False
            loop.vector_partitioned = False
        if collapse_tile_loops:
            tile_loops = [tile_loops.collapse()]
        if collapse_element_loops:
            element_loops = [element_loops.collapse()]
        result = Loopnest(tile_loops[:] + element_loops[:])
        return result

    def map_to_hip_cpp(self,remove_unnecessary=True):
        loopnest_open  = ""
        loopnest_close  = ""
        indent = ""
        resource_filter = AccResourceFilter()
        map_to_hip_grid = False
        map_to_acc_grid = False
        for loop in self._loops:
            loop.assert_is_well_defined()
            if loop.grid_dim != None:
                map_to_hip_grid = True
            if ( loop.vector_partitioned
                 or loop.worker_partitioned
                 or loop.gang_partitioned ):
                map_to_acc_grid = True
        assert not map_to_hip_grid or not map_to_acc_grid,\
            "cannot mix OpenACC gang/worker/vector partitioning with "+\
            "HIP grid partitioning" 
        for loop in self._loops:
            loop_open,loop_close,loop_resource_filter,max_indent =\
                loop.map_to_hip_cpp(
                  remove_unnecessary = False
                )
            loopnest_open += textwrap.indent(
              loop_open,
              indent
            )
            loopnest_close = textwrap.indent(
              loop_close,
              indent
            ) + loopnest_close
            resource_filter += loop_resource_filter
            indent += max_indent
        if remove_unnecessary:
            loopnest_open = remove_unnecessary_helper_variables(
              loopnest_open,[loopnest_close]
            )
        return (loopnest_open,
               loopnest_close,
               resource_filter,
               indent)

# todo: implement
# todo: workaround, for now expand all simple workshares
# Workshares are interesting because the loop
# bounds might actually coincide with the array
# dimensions of a variable
#class Workshare:
#    pass
## Workshare that reduces some array to a scalar, e.g. MIN/MAX/...
#class ReducingWorkshare:
#    pass 
