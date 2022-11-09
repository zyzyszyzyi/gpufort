# SPDX-License-Identifier: MIT
# Copyright (c) 2020-2022 Advanced Micro Devices, Inc. All rights reserved.
#from translator_base import *
import pyparsing
import ast

from gpufort import util

from .. import opts
from .. import conv
from .. import prepostprocess

from . import base
from . import traversals

import enum

class TTSimpleToken(base.TTNode):

    def _assign_fields(self, tokens):
        self._text = " ".join(tokens)

    def cstr(self):
        return "{};".format(self._text.lower())

    def fstr(self):
        return str(self._text)

class TTReturn(base.TTNode,base.FlowStatementMarker):

    def _assign_fields(self, tokens):
        self._result_name = ""

    def cstr(self):
        if self._result_name != None and len(self._result_name):
            return "return " + self._result_name + ";"
        else:
            return "return;"

    def fstr(self):
        return "return"

class TTLabel(base.TTNode,base.FlowStatementMarker):

    def _assign_fields(self, tokens):
        self._label = tokens[0]
        self.is_exit_marker = False
        self.is_standalone = False

    def cstr(self):
        result = "_"+self._label+":"
        if self.is_exit_marker:
            result = "_" + result
        if self.is_standalone:
            result += " ;"
        return result

class TTContinue(base.TTNode,base.FlowStatementMarker):
    def cstr(self):
        return ";"

    def fstr(self):
        return "continue"

class TTCycle(base.TTNode,base.FlowStatementMarker):

    def _assign_fields(self, tokens):
        self._result_name = ""
        self._in_loop = True

    def cstr(self):
        if self._label != None:
            # cycle label in loop is prefixed by single "_"
            return "goto _{};".format(self._label)    
        else:
            if self._in_loop:
                return "continue;"
            elif self._result_name != None and len(self._result_name):
                return "return " + self._result_name + ";"
            else:
                return "return;"

    def fstr(self):
        return "cycle {}".format(self.label)

class TTExit(base.TTNode,base.FlowStatementMarker):

    def _assign_fields(self, tokens):
        self._label = tokens[0]
        self._result_name = ""
        self._in_loop = True

    def cstr(self):
        if self._label != None:
            # exit label after loop is prefixed by "__"
            return "goto __{};".format(self._label)    
        else:
            if self._in_loop:
                return "break;"
            elif self._result_name != None and len(self._result_name):
                return "return " + self._result_name + ";"
            else:
                return "return;"

    def fstr(self):
        return "exit {}".format(self.label)

class TTUnconditionalGoTo(base.TTNode,base.FlowStatementMarker):
    #todo: More complex expressions possible with jump label list
    #todo: Target numeric label can be renamed to identifier (deleted Fortran feature)
    def _assign_fields(self, tokens):
        self._label = tokens[0]

    def cstr(self):
        return "goto _{};".format(self._label.rstrip("\n"))

class TTBlank(base.TTNode):
    
    def _assign_fields(self, tokens):
        self._text = tokens[0] 

    def cstr(self):
        return self._text 

    def fstr(self):
        return self._text 

class TTCommentedOut(base.TTNode):

    def _assign_fields(self, tokens):
        self._text = " ".join(tokens)

    def cstr(self):
        return "// {}".format(self._text)


class TTIgnore(base.TTNode):

    def cstr(self):
        return ""

class TTLiteral(base.TTNode):
    LOGICAL = "logical"
    CHARACTER = "character"
    INTEGER = "integer"
    REAL = "real"
            
    def _assign_fields(self, tokens):
        """
        Expected inputs for 
        """
        self._raw_value = tokens[0]
        self._value = self._raw_value
        self._kind = None
        if "_" in self._raw_value:
            parts = self._raw_value.rsplit("_",maxsplit=1)
            if not parts[1].endswith("'"):
                # '_' was not in the middle of character string
                self._value = parts[0]
                self._kind = parts[1] 
        self._size = None
    
    @property
    def value(self):
        return self._value
    
    @property
    def kind(self):
        return self._kind

    @property
    def resolved(self):
        return self._size != None

    @property
    def size(self):
        assert self._size != None
        return self._size

    @size.setter
    def set_size(self,size):
        self._size = size 
   
    @property
    def rank(self):
        return 0

    def fstr(self):
        return self._raw_value
 
class TTCharacter(TTLiteral):

    @property
    def type(self):
        return TTLiteral.CHARACTER 
    
    def cstr(self):
        raise util.error.LimitationError("not supported")

    def fstr(self):
        return self._value

class TTLogical(TTLiteral):

    @property
    def type(self):
        return TTLiteral.LOGICAL

    def cstr(self):
        if self.size == "1":
            return "true" if self._value.lower() == ".true." else "false"
        else:
            return "1" if self._value.lower() == ".true." else "0"

class TTNumber(TTLiteral):

    def _assign_fields(self, tokens):
        TTLiteral._assign_fields(tokens)
        if "." in self._value:
            self._type = TTLiteral.REAL 
        else:
            self._type = TTLiteral.INTEGER
    
    @property
    def type(self):
        return self._type

#    def is_real_of_kind(self,kind):
#        """:return: If the number is a real (of a certain kind)."""
#        if self._kind == None:
#            return kind == None
#        else:
#            if kind in opts.fortran_type_2_bytes_map["real"]:
#                has_exponent_e = "e" in self._value
#                has_exponent_d = "d" in self._value
#                has_exponent = has_exponent_e or has_exponent_d
#                default_real_bytes = opts.fortran_type_2_bytes_map["real"][
#                    ""].strip()
#                kind_bytes = opts.fortran_type_2_bytes_map["real"][kind].strip()
#                if self._kind == None: # no suffix
#                    cond = False
#                    cond = cond or (has_exponent_d and kind_bytes == "8")
#                    cond = cond or (has_exponent_e and
#                                    kind_bytes == default_real_bytes)
#                    cond = cond or (not has_exponent and
#                                    kind_bytes == default_real_bytes)
#                    return cond
#                else:
#                    if self._kind in opts.fortran_type_2_bytes_map["real"]:
#                        kind_bytes = opts.fortran_type_2_bytes_map["real"][
#                            self._kind].strip()
#                        return kind_bytes == self._kind_bytes
#                    else:
#                        raise util.error.LookupError(\
#                          "no number of bytes found for kind '{}' in 'translator.fortran_type_2_bytes_map[\"real\"]'".format(self._kind))
#                        sys.exit(2) # todo: error code
#            else:
#                raise util.error.LookupError(\
#                  "no number of bytes found for kind '{}' in 'translator.fortran_type_2_bytes_map[\"real\"]'".format(kind))
#                sys.exit(2) # todo: error code
#        else:
#            return False
#
#    def is_integer_of_kind(self,kind):
#        """:return: If the number is an integer (of a certain kind)."""
#        if not self.type ==  and kind != None:
#            if kind in opts.fortran_type_2_bytes_map["integer"]:
#                has_exponent_e = "e" in self._value
#                has_exponent_d = "d" in self._value
#                has_exponent = has_exponent_e or has_exponent_d
#                default_integer_bytes = opts.fortran_type_2_bytes_map[
#                    "integer"][""].strip()
#                kind_bytes = opts.fortran_type_2_bytes_map["integer"][
#                    kind].strip()
#                if self._kind == None: # no suffix
#                    return kind_bytes == default_integer_bytes
#                else: # suffix
#                    if suffix in opts.fortran_type_2_bytes_map["integer"]:
#                        suffix_bytes = opts.fortran_type_2_bytes_map[
#                            "integer"][suffix].strip()
#                        return kind_bytes == suffix_bytes
#                    else:
#                        raise util.error.LookupError("no number of bytes found for suffix '{}' in 'translator.opts.fortran_type_2_bytes_map[\"integer\"]'".format(suffix))
#            else:
#                raise util.error.LookupError(\
#                  "no number of bytes found for kind '{}' in 'translator.opts.fortran_type_2_bytes_map[\"integer\"]'".format(kind))
#        else:
#            return is_integer

    def cstr(self):
        # todo: check kind parameter in new semantics part
        if self._type = TTLiteral.REAL:
            if self.size == 4:
                return self._value + "f"
            elif self.size == 8:
                return self._value.replace("d", "e")
            else:
                raise util.error.LimitationError("only single & double precision floats supported")
        elif self._type == TTLiteral.INTEGER
            if self.size == 16:
                return self._value + "LL"
            elif self.size == 8:
                return self._value + "L"
            else:
                # short is typically promoted to int
                return self._value
    
    def __str__(self):
        return "TTNumber(val:"+str(self._value)+",kind:"+self._kind+")"
    __repr__ = __str__

class Typed(base.TTNode):

    def _assign_fields(self, tokens):
        self._index_record = None
        self._bytes_per_element = None 
    
    @property
    def partially_resolved(self):
        return self._index_record != None
   
    @property
    def resolved(self):
        return ( 
          self.partially_resolved
          and self._bytes_per_element != None
        )
 
    @property
    def index_record(self):
        assert self.partially_resolved
        return self._index_record 
    
    @index_record.setter
    def set_index_record(self,index_record):
        self._index_record = index_record 
   
    def _get_type_defining_record(self):
        """:return: An index record that describes the type
        of an expression. Per default it is the main record."""
        return self.index_record 

    @property 
    def type(self):
        return self._get_type_defining_record()["f_type"]
    
    @property 
    def kind(self):
        return self._get_type_defining_record()["kind"]

    @property
    def bytes_per_element(self):
        assert self.fully_resolved
        return self._bytes_per_element
    
    @bytes_per_element.setter
    def set_bytes_per_element(self,bytes_per_element):
        self._bytes_per_element = bytes_per_element 

    @property
    def ctype(self):
        assert self.fully_resolved
        return opts.bytes_2_c_type[
          self._type][self._bytes_per_element] 

    @property 
    def rank(self):
        assert self.partially_resolved
        return self.index_record["rank"] > 0

class TTIdentifier(Typed):
        
    def _assign_fields(self, tokens):
        self._name = tokens[0]
        Typed._assign_fields(self,tokens)

    def fstr(self):
        return str(self._name)

    def cstr(self):
        return self.fstr()

    def __str__(self):    
        return "TTIdentifier(name:"+str(self._name)+")"
    __repr__ = __str__


class TTTensorEval(Typed):
    
    def _assign_fields(self, tokens):
        self._name = tokens[0]
        if len(tokens) > 1:
            self._args = tokens[1]
        else:
            self._args = base.TTNone
        Typed._assign_fields(self,tokens)
    
    # override
    def _get_type_defining_record(self):
        record = self.index_record
        if "rank" in record
            return record
        else:
            assert record["kind"] == "function"
            result_name = record["result_name"]
            ivar = next((ivar
              for ivar in record["variables"] 
              if ivar["name"] == result_name),None)
            assert ivar != None
            return ivar

    def child_nodes(self):
        for arg in self._args:
            yield arg

    def slice_args(self):
        """Returns all range args in the order of their appeareance.
        """
        # todo: double check that this does not descend
        for arg in self._args:
            if isinstance(arg,TTSlice):
                yield arg
    
    def has_slice_args(self):
        """If any range args are present in the argument list.
        """
        return next(self.slice_args(),None) != None

    def args(self):
        """Returns all args in the order of their appeareance.
        """
        return self._args

    def has_args(self):
        """If any args are present.
        """
        return len(self._args) 

    def is_array_access(self):
        return if "rank" in self.index_record
 
    def is_func_call(self):
        return not self.is_array_access()
    
    def is_intrinsic_call(self):
        assert self.is_func_call()
        return "intrinsic" in self.index_record["attributes"])
   
    def is_elemental_func_call(self):
        assert self.is_func_call()
        return "elemental" in self.index_record["attributes"])

    def is_conversion_call(self):
        """:note: Conversions are always elemental."""
        assert self.is_elemental_call()
        return "conversion" in self.index_record["attributes"])
  
    @property 
    def rank(self):
        if self.is_array_access():
            return len([arg for arg in self.slice_args()])
        else: 
            return self._get_type_defining_record()["rank"] 

    def name_cstr(self):
        name = traversals.make_cstr(self._name).lower()
        if self.is_array_access():
            return name
        elif self.is_intrinsic_call():
            name = prepostprocess.modernize_fortran_function_name(name)
            if name in [
              "max",
              "min",
              ]:
                num_args = len(self._args)
                return "max" + str(num_args)
            else:
                return name
        else:
            return name

    def cstr(self):
        name = self.name_cstr()
        return "".join([
            name,
            self._args.cstr(name,
                             self.is_array_access(),
                             opts.fortran_style_tensor_eval)])
    
    def fstr(self):
        name = traversals.make_fstr(self._name)
        return "".join([
            name,
            self._args.fstr()
            ])
    
    def __str__(self):
        return "TTTensorEval(name:"+str(self._name)+",is_array_access:"+str(self.is_array_access())+")"
    __repr__ = __str__

class TTValue(base.TTNode):
    
    def _assign_fields(self, tokens):
        self._value = tokens[0]
        self._reduction_index = None
        self._fstr = None

    def get_type_defininig_node(self):
        if isinstance(self._value,(TTDerivedTypeMember)):
            return self._value.get_innermost_member()._element
        else:
            return self._value

    def get_rank_defining_node(self):
        if isinstance(self._value,(TTDerivedTypeMember)):
            return self._value.get_rank_defining_node()
        else:
            return self._value

    @property
    def type(self):
        return self.get_type_defining_node().type
    
    @property
    def kind(self):
        return self.get_type_defining_node().kind

    @property
    def rank(self):
        return self.get_rank_defining_node().rank

    @property
    def index_record(self):
        ttnode = self.get_type_defininig_node()
        if isinstance(ttnode,(TTIdentifier,TTFunctionCall)):
            return ttnode.index_record()
        else:
            return None

    def child_nodes(self):
        yield self._value
   
    def is_identifier(self):
        return isinstance(self._value, TTIdentifier)

    def identifier_part(self,converter=traversals.make_fstr):
        """
        :return: The identifier part of the expression. In case
                 of a function call/tensor access expression, 
                 excludes the argument list.
                 In case of a derived type, excludes the argument
                 list of the innermost member.
        """
        if type(self._value) is TTTensorEval:
            return converter(self._value._name)
        elif type(self._value) is TTDerivedTypeMember:
            return self._value.identifier_part(converter)
        else:
            return converter(self._value)
    
    def is_function_call(self):
        """:note: TTTensorEval instances must be flagged as tensor beforehand.
        """
        # todo: check if detect all arrays in indexer/scope
        # so that we do not need to know function names anymore.
        if type(self._value) is TTTensorEval:
            return not self._value.is_array_access()
        elif type(self._value) is TTDerivedTypeMember:
            # todo: support type bounds routines
            return False
        else:
            return False

    def get_value(self):
        return self._value 

    def name(self):
        return self._value.fstr()
    
    def has_slice_args(self):
        if type(self._value) is TTTensorEval:
            return self._value.has_slice_args()
        elif type(self._value) is TTDerivedTypeMember:
            return self._value.innermost_member_has_slice_args()
        else:
            return False

    def slice_args(self):
        if type(self._value) is TTTensorEval:
            return self._value.slice_args()
        elif type(self._value) is TTDerivedTypeMember:
            return self._value.innermost_member_slice_args()
        else:
            return []
    
    def has_args(self):
        """:return If the value type expression has an argument list. In
                   case of a derived type member, if the inner most derived
                   type member has an argument list.
        """
        if type(self._value) is TTTensorEval:
            return True
        elif type(self._value) is TTDerivedTypeMember:
            return self._value.innermost_member_has_args()
        else:
            return False
    
    def args(self):
        if type(self._value) is TTTensorEval:
            return self._value._args
        elif type(self._value) is TTDerivedTypeMember:
            return self._value.innermost_member_args()
        else:
            return []
    
    def fstr(self):
        if self._fstr != None:
            return self._fstr
        else:
            return traversals.make_fstr(self._value)

    def cstr(self):
        result = traversals.make_cstr(self._value)
        if self._reduction_index != None:
            if opts.fortran_style_tensor_eval:
                result += "({idx})".format(idx=self._reduction_index)
            else:
                result += "[{idx}]".format(idx=self._reduction_index)
        return result.lower()

class TTLvalue(TTValue):
    def __str__(self):
        return "TTLvalue(val:"+str(self._value)+")"
    __repr__ = __str__

class TTRvalue(TTValue):
    def __str__(self):
        return "TTRvalue(val:"+str(self._value)+")"
    __repr__ = __str__

#def _inquiry_str(prefix,ref,dim,kind=""):
#    result = prefix + "(" + ref
#    if len(dim):
#        result += "," + dim
#    if len(kind):
#        result += "," + kind
#    return result + ")"
#def _inquiry_cstr(prefix,ref,dim,kind,f_type="integer",c_type_expected="int"):
#    """Tries to determine a C type before calling _inquiry_str.
#    Wraps the result of the latter function into a typecast
#    if the C type does not equal the expected type.
#    """
#    c_type = conv.convert_to_c_type(f_type,
#                                    kind,
#                                    default=None)
#    result = _inquiry_str(prefix,ref,dim)
#    if c_type_expected != c_type:
#        return "static_cast<{}>({})".format(c_type,result)
#    else:
#        return result
#
#class TTSizeInquiry(base.TTNode):
#    """Translator tree node for size inquiry function.
#    """
#
#    def _assign_fields(self, tokens):
#        self._ref, self._dim, self._kind = tokens
#
#    def cstr(self):
#        """
#        :return: number of elements per array dimension, if the dimension
#                 is specified as argument.
#                 Utilizes the <array>_n<dim> and <array>_lb<dim> arguments that
#                 are passed as argument of the extracted kernels.
#        :note: only the case where <dim> is specified as integer literal is handled by this function.
#        """
#        if opts.fortran_style_tensor_eval:
#            return _inquiry_cstr("size",
#                                  traversals.make_cstr(self._ref),
#                                  traversals.make_cstr(self._dim),
#                                  traversals.make_cstr(self._kind))
#        else:
#            if type(self._dim) is TTNumber:
#                return traversals.make_cstr(self._ref) + "_n" + traversals.make_cstr(
#                    self._dim)
#            else:
#                prefix = "size"
#                return "/* " + prefix + "(" + traversals.make_fstr(self._ref) + ") */"
#    def fstr(self):
#        return _inquiry_str("size",
#                            traversals.make_fstr(self._ref),
#                            traversals.make_fstr(self._dim),
#                            traversals.make_fstr(self._kind))
#
#
#class TTLboundInquiry(base.TTNode):
#    """
#    Translator tree node for lbound inquiry function.
#    """
#
#    def _assign_fields(self, tokens):
#        self._ref, self._dim, self._kind = tokens
#
#    def cstr(self):
#        """
#        :return: lower bound per array dimension, if the dimension argument is specified as integer literal.
#                 Utilizes the <array>_n<dim> and <array>_lb<dim> arguments that
#                 are passed as argument of the extracted kernels.
#        :note:   only the case where <dim> is specified as integer literal is handled by this function.
#        """
#        if opts.fortran_style_tensor_eval:
#            return _inquiry_cstr("lbound",
#                                  traversals.make_cstr(self._ref),
#                                  traversals.make_cstr(self._dim),
#                                  traversals.make_cstr(self._kind))
#        else:
#            if type(self._dim) is TTNumber:
#                return traversals.make_cstr(self._ref) + "_lb" + traversals.make_cstr(
#                    self._dim)
#            else:
#                prefix = "lbound"
#                return "/* " + prefix + "(" + traversals.make_fstr(self._ref) + ") */"
#
#    def fstr(self):
#        return _inquiry_str("lbound",
#                            traversals.make_fstr(self._ref),
#                            traversals.make_fstr(self._dim),
#                            traversals.make_fstr(self._kind))
#
#
#class TTUboundInquiry(base.TTNode):
#    """
#    Translator tree node for ubound inquiry function.
#    """
#
#    def _assign_fields(self, tokens):
#        self._ref, self._dim, self._kind = tokens
#
#    def cstr(self):
#        """
#        :return: upper bound per array dimension, if the dimension argument is specified as integer literal.
#                 Utilizes the <array>_n<dim> and <array>_lb<dim> arguments that
#                 are passed as argument of the extracted kernels.
#        :note:   only the case where <dim> is specified as integer literal is handled by this function.
#        """
#        if opts.fortran_style_tensor_eval:
#            return _inquiry_cstr("ubound",
#                                  traversals.make_cstr(self._ref),
#                                  traversals.make_cstr(self._dim),
#                                  traversals.make_cstr(self._kind))
#        else:
#            if type(self._dim) is TTNumber:
#                return "({0}_lb{1} + {0}_n{1} - 1)".format(
#                    traversals.make_cstr(self._ref), traversals.make_cstr(self._dim))
#            else:
#                prefix = "ubound"
#                return "/* " + prefix + "(" + traversals.make_fstr(self._ref) + ") */"
#    def fstr(self):
#        return _inquiry_str("ubound",
#                            traversals.make_fstr(self._ref),
#                            traversals.make_fstr(self._dim),
#                            traversals.make_fstr(self._kind))
#
#
#class TTConvertToExtractReal(base.TTNode):
#
#    def _assign_fields(self, tokens):
#        self._ref, self._kind = tokens
#
#    def cstr(self):
#        c_type = conv.convert_to_c_type("real", self._kind).replace(
#            " ", "_") # todo: check if his anything else than double or float
#        return "make_{1}({0})".format(
#            traversals.make_cstr(self._ref),
#            c_type) # rely on C++ compiler to make the correct type conversion
#
#    def fstr(self):
#        result = "REAL({0}".format(traversals.make_fstr(self._ref))
#        if not self._kind is None:
#            result += ",kind={0}".format(traversals.make_fstr(self._kind))
#        return result + ")"
#
#
#class TTConvertToDouble(base.TTNode):
#
#    def _assign_fields(self, tokens):
#        self._ref, self._kind = tokens
#
#    def cstr(self):
#        return "make_double({0})".format(
#            traversals.make_cstr(self._ref)
#        ) # rely on C++ compiler to make the correct type conversion
#
#    def fstr(self):
#        return "DBLE({0})".format(
#            traversals.make_fstr(self._ref)
#        ) # rely on C++ compiler to make the correct type conversion
#
#
#class TTConvertToComplex(base.TTNode):
#
#    def _assign_fields(self, tokens):
#        self._x, self._y, self._kind = tokens
#
#    def cstr(self):
#        c_type = conv.convert_to_c_type("complex",
#                                        self._kind,
#                                        default=None,
#                                        float_complex="hipFloatComplex",
#                                        double_complex="hipDoubleComplex")
#        return "make_{2}({0}, {1})".format(traversals.make_cstr(self._x),
#                                           traversals.make_cstr(self._y), c_type)
#
#    def fstr(self):
#        result = "CMPLX({0},{1}".format(traversals.make_fstr(self._x),
#                                        traversals.make_fstr(self._y))
#        if not self._kind is None:
#            result += ",kind={0}".format(traversals.make_fstr(self._kind))
#        return result + ")"
#
#
#class TTConvertToDoubleComplex(base.TTNode):
#
#    def _assign_fields(self, tokens):
#        self._x, self._y, self._kind = tokens
#
#    def cstr(self):
#        c_type = "double_complex"
#        return "make_{2}({0}, {1})".format(traversals.make_cstr(self._x),
#                                           traversals.make_cstr(self._y), c_type)
#
#    def fstr(self):
#        result = "DCMPLX({0},{1}".format(traversals.make_fstr(self._x),
#                                         traversals.make_fstr(self._y))
#        return result + ")"
#
#
#class TTExtractImag(base.TTNode):
#
#    def _assign_fields(self, tokens):
#        self._ref, self._kind = tokens
#
#    def cstr(self):
#        return "{0}._y".format(traversals.make_cstr(self._ref))
#
#
#class TTConjugate(base.TTNode):
#
#    def _assign_fields(self, tokens):
#        self._ref, self._kind = tokens
#
#    def cstr(self):
#        return "conj({0})".format(traversals.make_cstr(self._ref))


class TTDerivedTypeMember(base.TTNode):

    def _assign_fields(self, tokens):
        self._type, self._element = tokens
        #print(self._type)
        self._cstr = None
    
    @property
    def index_record(self):
        return self._value.index_record

    def get_children(self):
        yield self._type
        yield self._element

    def walk_derived_type_members_preorder(self):
        """Yields all TTDerivedTypeMember instances.
        """
        yield self
        if isinstance(self._element,TTDerivedTypeMember):
            yield from self._element.walk_derived_type_members_preorder()
    
    def walk_derived_type_members_postorder(self):
        """Yields all TTDerivedTypeMember instances.
        """
        if isinstance(self._element,TTDerivedTypeMember):
            yield from self._element.walk_derived_type_members_postorder()
        yield self

    def get_innermost_member(self):
        """:return: inner most derived type member.
        """
        for current in walk_derived_type_members_preorder():
            pass
        return current

    def get_type_defininig_node(self):
        return self.get_innermost_member()._element

    def get_rank_defining_node(self):
        r""":return: The subexpression part that contains the information on 
        the rank of this derived type member access expression.
        :note: Assumes semantics check has been performed beforehand
        so that we can assume that not more than one part of the derived
        type member access expression has a rank greater than 0.

        **Examples:**

        arr1(:)%scal1 -> returns arr1
        arr1(i)%scal1 -> returns scal2
        arr1(i)%arr2 -> returns arr2
        arr1%arr2(i) -> returns arr1
        """
        for current in self.walk_derived_type_members_preorder():
            if current._type.rank > 0:
                return current._type
        return current._element 

    @property
    def rank(self):
        return self.get_rank_defining_node().rank

    def slice_args(self):
        """Returns all range args in the order of their appeareance.
        """
        # todo: double check that this does not descend
        for arg in self._args:
            if isinstance(arg,TTSlice):
                yield arg

    def has_slice_args(self):
        """If any range args are present in the argument list.
        """
        return next(self.slice_args(),None) != None


    def identifier_part(self,converter=traversals.make_fstr):
        # todo: adopt walk_members generator
        result = converter(self._type)
        current = self._element
        while isinstance(current,TTDerivedTypeMember):
            current = current._element
            result += "%"+converter(self._type)
        if isinstance(current,TTTensorEval):
            result += "%"+converter(current._name)
        else: # TTIdentifier
            result += "%"+converter(current)
        return result             

    def overwrite_cstr(self,expr):
        self._cstr = expr

    def cstr(self):
        if self._cstr == None:
            return traversals.make_cstr(self._type) + "." + traversals.make_cstr(
                self._element)
        else:
            return self._cstr

    def fstr(self):
        return traversals.make_fstr(self._type) + "%" + traversals.make_fstr(
            self._element)
    
    def __str__(self):
        return "TTDerivedTypeMember(name:"+str(self._type)+"member:"+str(self._element)+")"
    __repr__ = __str__


class TTSubroutineCall(base.TTNode):

    def _assign_fields(self, tokens):
        self._subroutine = tokens[0]

    def cstr(self):
        return self._subroutine.cstr() + ";"
 
def _need_to_add_brackets(op,other_opd):
    return isinstance(other_opd,(TTUnaryOp,TTBinaryOpChain))

class TTUnaryOp(base.TTNode):
    f2c = {
      ".not.": "!{r}",
      "+": "{r}",
      "-": "-{r}",
    }
    
    def _assign_fields(self, tokens):
        self.op, self.opd = tokens[0]
        #self.type = None
        #self.kind = None
        #self.rank = None
    
    def child_nodes(self):
        yield self.opd
   
    @property
    def rank(self):
        assert isinstance(self.opd,TTRvalue)
        return self.opd.rank
    
    @property
    def index_record(self):
        assert isinstance(self.opd,TTRvalue)
        return self.opd.index_record
 
    def _op_c_template(self):
        return TTUnaryOp.f2c.get(self.op.lower())
    def cstr(self):
        if _need_to_add_brackets(self,opd):
            return self._op_c_template().format(
              r="(" + self.opd.cstr() + ")"
            )
        else:
            return self._op_c_template().format(
              r=self.opd.cstr()
            )
    
    def fstr(self):
        if _need_to_add_brackets(self,opd):
            return self.op + "(" + self.opd.fstr() + ")"
        else:
            return self.op + self.opd.fstr()

class TTBinaryOpChain(base.TTNode):
    """pyparsing's infixNotation flattens
    repeated applications of binary
    operator expressions that have the same precedence 
    into a single list of tokens.
    This class models such lists of grouped operator
    and operand tokens.

    Example:
    
    As '+' and '-' have the same precendence, 
    parsing the expression
    `a + b + c - d`
    will have pyparsing's infixNotation group the
    tokens as follows: 
    ['a','+','b','+','c','-','d'].
    While it parses the expression `a + b - c*d`
    as below:
    ['a','+','b','-',['c','*','d']]
    """

    class OperatorType(enum.Enum):
        UNKNOWN = 0
        POW = 1 # only applicable to number types (integer,real,complex)
        ADD = 2 # only applicable to number types (integer,real,complex)
        MUL = 3 # only applicable to number types (integer,real,complex)
        COMP = 4 # only applicable to number types (integer,real,complex)
        LOGIC = 5 # only applicable to logical types
    
    f2c = {
      "**":"__pow({l},{r})",
      "*": "{l} * {r}",
      "/": "{l} / {r}",
      "+": "{l} + {r}",
      "-": "{l} - {r}",
      "<": "{l} < {r}",
      "<=": "{l} <= {r}",
      ">": "{l} > {r}",
      ">=": "{l} >= {r}",
      ".lt.": "{l} < {r}",
      ".le.": "{l} <= {r}",
      ".gt.": "{l} > {r}",
      ".ge.": "{l} >= {r}",
      "==": "{l} == {r}",
      "/=": "{l} != {r}",
      ".and.": "{l} && {r}",
      ".or.":  "{l} || {r}",
      ".eq.": "{l} == {r}",
      ".eqv.": "{l} == {r}",
      ".ne.": "{l} != {r}",
      ".neqv.": "{l} != {r}",
      ".xor.": "{l} ^ {r}",
    }
    
    def _assign_fields(self, tokens):
        #print([type(tk) for tk in tokens[0]])
        self.exprs = tokens[0]
        #self.type = None
        #self.kind = None
        #self.rank = None
        self._op_type = None

    @property
    def operator_type(self):
        """:return: a characteristic operator for 
        the binary operators aggregated in this chain
        of binary operations.
        
        Returns '&&' for all logical comparisons,
        '==' for all number comparisons, '*' for [*/]
        and '+' for [+-].
        """
        if self._op_type == None:
            op = self.operators[0].lower()
            if op == "**":
                self._op_type = OperatorType.POW
            elif op in ["*","/"]:
                self._op_type = OperatorType.MUL
            elif op in ["+","-"]:
                self._op_type = OperatorType.ADD
            elif op in [
              "<",
              "<=",
              ">",
              ">=",
              ".lt.",
              ".le.",
              ".gt.",
              ".ge.",
              "==",
              "/=",
            ]:
                self._op_type =  OperatorType.COMP
            elif op in [
              ".and.",
              ".or.",
              ".eq.",
              ".eqv.",
              ".ne.",
              ".neqv.",
              ".xor.",
            ]:
                self._op_type =  OperatorType.LOGIC
        return self._op_type 
    
    @property
    def operands(self):
        return self.exprs[::2]

    @property
    def operators(self):
        return self.exprs[1::2]

  
    @property
    def operators(self):
        pass


    def child_nodes(self):
        for opd in self.operands:
            yield opd
    
    def _op_c_template(self,op):
        return TTBinaryOpChain.f2c.get(op.lower())
    
    def cstr(self):
        # a + b + c
        # + + 
        # a b c
        # add(add(a,b),c)
        opds = self.operands
        lopd = opds[0]
        result = lopd.cstr()
        if _need_to_add_brackets(self,lopd): 
            result="(" + result + ")"
        for i,op in enumerate(self.operators):
            op_template = self._op_c_template(op)
            l = result
            ropd = opds[i+1]
            r = ropd.cstr()
            if _need_to_add_brackets(self,ropd): 
                r="(" + r + ")"
            result = op_template.format(
              l = result,
              r = r
            )
        return result
    
    def fstr(self):
        opds = self.operands
        result = opds[0].fstr()
        if _need_to_add_brackets(self,opds[0]): 
            result="(" + result + ")"
        for i,op in enumerate(self.operators):
            op_template = "{l} {op} {r}"
            l = result
            r = opds[i+1].fstr()
            if _need_to_add_brackets(self,opds[i+1]): 
                r="(" + r + ")"
            result = op_template.format(
              l = l,
              r = r,
              op = self.op
            )
        return result

class TTArithExpr(base.TTNode):

    def _assign_fields(self, tokens):
        self._expr = tokens[0] # either: rvalue,unary op,binary op

    def child_nodes(self):
        yield self._expr

    
    
    def walk_rvalues_preorder(self):
        """Yields all TTDerivedTypeMember instances.
        """
        yield self
        if isinstance(self._element,TTDerivedTypeMember):
            yield from self._element.walk_derived_type_members_preorder()
    
    def walk_rvalues_postorder(self):
        """Yields all TTDerivedTypeMember instances.
        """
        if isinstance(self._expr,TTRvalue):
            yield self._expr
        
 
    def cstr(self):
        return self._expr.cstr()
    def fstr(self):
        return self._expr.fstr()


class TTComplexArithExpr(base.TTNode):

    def _assign_fields(self, tokens):
        self._real, self._imag = tokens[0]

    def child_nodes(self):
        yield self._real; yield self._imag
    def cstr(self):
        return "make_hip_complex({real},{imag})".format(\
                real=traversals.make_cstr(self._real),\
                imag=traversals.make_cstr(self._imag))

    def fstr(self):
        return "({real},{imag})".format(\
                real=traversals.make_fstr(self._real),\
                imag=traversals.make_fstr(self._imag))


class TTPower(base.TTNode):

    def _assign_fields(self, tokens):
        self.base, self.exp = tokens

    def child_nodes(self):
        yield self.base; yield self.exp
    def gpufort_fstr(self, scope=None):
        return "__pow({base},{exp})".format(base=traversals.make_fstr(self.base),
            exp=traversals.make_fstr(self.exp))
    def __str__(self):
        return self.gpufort_fstr()

    def fstr(self):
        return "({base})**({exp})".format(\
            base=traversals.make_cstr(self.base),exp=traversals.make_cstr(self.exp))

class TTAssignment(base.TTNode):

    def _assign_fields(self, tokens):
        self._lhs, self._rhs = tokens

    def child_nodes(self):
        yield self._lhs; yield self._rhs
    def cstr(self):
        return self._lhs.cstr() + "=" + self._rhs.cstr() + ";\n"
    def fstr(self):
        return self._lhs.fstr() + "=" + self._rhs.fstr() + ";\n"

class TTArgument(base.TTNode):
    def _assign_fields(self, tokens):
        self.value = tokens[0]
    def child_nodes(self):
        yield self.value
    def cstr(self):
        return self.value.cstr()
    def fstr(self):
        return self.value.fstr()
     
class TTKeywordArgument(base.TTNode):
    def _assign_fields(self, tokens):
        self.key, self.value = tokens
    def child_nodes(self):
        yield self.key; yield self.value
    def cstr(self):
        return self._lhs.cstr() + "=" + self._rhs.cstr() + ";\n"
    def fstr(self):
        return self._lhs.fstr() + "=" + self._rhs.fstr() + ";\n"
class TTComplexAssignment(base.TTNode):

    def _assign_fields(self, tokens):
        self._lhs, self._rhs = tokens

    def child_nodes(self):
        yield self._lhs; yield self._rhs
    def cstr(self):
        """
        Expand the complex assignment.
        """
        result = ""
        result += "{}.x = {};\n".format(traversals.make_cstr(self._lhs),
                                        traversals.make_cstr(self._rhs._real))
        result += "{}.y = {};\n".format(traversals.make_cstr(self._lhs),
                                        traversals.make_cstr(self._rhs._imag))
        return result


class TTMatrixAssignment(base.TTNode):

    def _assign_fields(self, tokens):
        self._lhs, self._rhs = tokens

    def child_nodes(self):
        yield self._lhs; yield self._rhs
    def cstr(self):
        """
        Expand the matrix assignment.
        User still has to fix the ranges manually. 
        """
        result = "// TODO: fix ranges"
        for expression in self._rhs:
            result += traversals.make_cstr(
                self._lhs) + argument + "=" + flatten_arith_expr(
                    expression) + ";\n"
        return result

class TTSlice(base.TTNode):

    def _assign_fields(self, tokens):
        self._lbound, self._ubound, self._stride =\
          None, None, None 
        if len(tokens) == 1:
            self._ubound = tokens[0]
        elif len(tokens) == 2:
            self._lbound = tokens[0]
            self._ubound = tokens[1]
        elif len(tokens) == 3:
            self._lbound = tokens[0]
            self._ubound = tokens[1]
            self._stride = tokens[2]

    def set_loop_var(self, name):
        self._loop_var = name

    def l_bound(self, converter=traversals.make_cstr):
        return converter(self._lbound)

    def u_bound(self, converter=traversals.make_cstr):
        return converter(self._ubound)

    def unspecified_l_bound(self):
        return not len(self.l_bound())

    def unspecified_u_bound(self):
        return not len(self.u_bound())

    def stride(self, converter=traversals.make_cstr):
        return converter(self._stride)

    def size(self, converter=traversals.make_cstr):
        result = "{1} - ({0}) + 1".format(converter(self._lbound),
                                          converter(self._ubound))
        try:
            result = str(ast.literal_eval(result))
        except:
            try:
                result = " - ({0}) + 1".format(converter(self._lbound))
                result = str(ast.literal_eval(result))
                if result == "0":
                    result = converter(self._ubound)
                else:
                    result = "{1}{0}".format(result, converter(self._ubound))
            except:
                pass
        return result

    def cstr(self):
        #return self.size(traversals.make_cstr)
        return "/*TODO fix this BEGIN*/{0}/*fix END*/".format(self.fstr())

    def overwrite_fstr(self,fstr):
        self._fstr = fstr
    
    def fstr(self):
        if self._fstr != None:
            return self._fstr
        else:
            result = ""
            if not self._lbound is None:
                result += traversals.make_fstr(self._lbound)
            result += ":"
            if not self._ubound is None:
                result += traversals.make_fstr(self._ubound)
            if not self._stride is None:
                result += ":" + traversals.make_fstr(self._stride)
            return result

class TTArgumentList(base.TTNode):
    def _assign_fields(self, tokens):
        self.items = []
        self.max_rank = -1
        self.items = tokens.asList()
        self.max_rank = len(self.items)
        self.__next_idx = 0
    def __len__(self):
        return len(self.items)
    def __iter__(self):
        return iter(self.items)

    def cstr(self):
        return "".join(
            ["[{0}]".format(traversals.make_cstr(el)) for el in self.items])

    def __max_rank_adjusted_items(self):
        if self.max_rank > 0:
            assert self.max_rank <= len(self.items)
            result = self.items[0:self.max_rank]
        else:
            result = []
        return result

    def cstr(self,name,is_tensor=False,fortran_style_tensor_eval=True):
        args = self.__max_rank_adjusted_items()
        if len(args):
            if (not fortran_style_tensor_eval and is_tensor):
                return "[_idx_{0}({1})]".format(name, ",".join([
                    traversals.make_cstr(s) for s in args
                ])) # Fortran identifiers cannot start with "_"
            else:
                return "({})".format(
                    ",".join([traversals.make_cstr(s) for s in args]))
        else:
            return ""

    def fstr(self):
        args = self.__max_rank_adjusted_items()
        if len(args):
            return "({0})".format(",".join(
                traversals.make_fstr(el) for el in args))
        else:
            return ""

class TTDo(base.TTContainer):

    def _assign_fields(self, tokens):
        self._begin, self._end, self._step, self.body = tokens
        self.numeric_do_label = None
    @property
    def index(self):
        return self._begin._lhs
    @property
    def first(self):
        return self._begin._rhs
    @property
    def last(self):
        return self._end
    @property
    def step(self):
        return self._step
    def has_step(self):
        return self._step != None
    def child_nodes(self):
        yield self.body; yield self._begin; yield self._end; yield self._step
class TTUnconditionalDo(base.TTContainer):
    def _assign_fields(self, tokens):
        self.body = tokens[0]
        self.numeric_do_label = None
    def child_nodes(self):
        return []
    def header_cstr(self):
        return "while (true) {{\n"
    def footer_cstr(self):
        return "}\n" 
class TTBlock(base.TTContainer):
    def _assign_fields(self, tokens):
        self.indent = "" # container of if/elseif/else branches, so no indent
    def header_cstr(self):
        return "{{\n"
    def footer_cstr(self):
        return "}\n" 

class TTIfElseBlock(base.TTContainer):
    def _assign_fields(self, tokens):
        self.indent = "" # container of if/elseif/else branches, so no indent

class TTIfElseIf(base.TTContainer):

    def _assign_fields(self, tokens):
        self._else, self._condition, self.body = tokens

    def child_nodes(self):
        yield self._condition; yield self.body
    
    def header_cstr(self):
        prefix = self._else+" " if self._else != None else ""
        return "{}if ({}) {{\n".format(prefix,traversals.make_cstr(self._condition))
    def footer_cstr(self):
        return "}\n" 

class TTElse(base.TTContainer):
    
    def header_cstr(self):
        return "else {\n"
    def footer_cstr(self):
        return "}\n" 

    def cstr(self):
        body_content = base.TTContainer.cstr(self)
        return "{}{}\n{}".format(
            self.header_cstr(),
            body_content,
            self.footer_cstr())

class TTSelectCase(base.TTContainer):
    def _assign_fields(self, tokens):
        self.selector = tokens[0]
        self.indent = "" # container of if/elseif/else branches, so no indent
    def header_cstr(self):
        return "switch ({}) {{\n".format(self.selector)
    def footer_cstr(self):
        return "}\n" 

class TTCase(base.TTContainer):

    def _assign_fields(self, tokens):
        self.cases, self.body = tokens

    def child_nodes(self):
        yield self.cases; yield self.body
    
    def header_cstr(self):
        result = ""
        for case in self.cases:
            result += "case ("+traversals.make_cstr(case)+"):\n"
        return result
    def footer_cstr(self):
        return "  break;\n" 

class TTCaseDefault(base.TTContainer):

    def _assign_fields(self, tokens):
        self.body = tokens[0]

    def child_nodes(self):
        yield self.body
    
    def header_cstr(self):
        return "default:\n"
    def footer_cstr(self):
        return "  break;\n" 

class TTDoWhile(base.TTContainer):

    def _assign_fields(self, tokens):
        self._condition, self.body = tokens
        self.numeric_do_label = None

    def child_nodes(self):
        yield self._condition; yield self.body
    
    def header_cstr(self):
        return "while ({0}) {{\n".format(
          traversals.make_cstr(self._condition)
        )
    def footer_cstr(self):
        return "  break;\n" 

def set_fortran_parse_actions(grammar):
    grammar.logical.setParseAction(TTLogical)
    grammar.character.setParseAction(TTCharacter)
    grammar.integer.setParseAction(TTNumber)
    grammar.number.setParseAction(TTNumber)
    grammar.identifier.setParseAction(TTIdentifier)
    grammar.rvalue.setParseAction(TTRvalue)
    grammar.lvalue.setParseAction(TTLvalue)
    grammar.derived_type_elem.setParseAction(TTDerivedTypeMember)
    grammar.tensor_eval.setParseAction(TTTensorEval)
    #grammar.convert_to_extract_real.setParseAction(TTConvertToExtractReal)
    #grammar.convert_to_double.setParseAction(TTConvertToDouble)
    #grammar.convert_to_complex.setParseAction(TTConvertToComplex)
    #grammar.convert_to_double_complex.setParseAction(TTConvertToDoubleComplex)
    #grammar.extract_imag.setParseAction(TTExtractImag)
    #grammar.conjugate.setParseAction(TTConjugate)
    #grammar.conjugate_double_complex.setParseAction(TTConjugate) # same action
    #grammar.size_inquiry.setParseAction(TTSizeInquiry)
    #grammar.lbound_inquiry.setParseAction(TTLboundInquiry)
    #grammar.ubound_inquiry.setParseAction(TTUboundInquiry)
    grammar.tensor_slice.setParseAction(TTSlice)
    grammar.tensor_eval_args.setParseAction(TTArgumentList)
    grammar.arith_expr.setParseAction(TTArithExpr)
    grammar.complex_arith_expr.setParseAction(
        TTComplexArithExpr)
    #grammar.power.setParseAction(TTPower)
    grammar.keyword_argument.setParseAction(TTKeywordArgument)
    grammar.assignment.setParseAction(TTAssignment)
    grammar.matrix_assignment.setParseAction(TTMatrixAssignment)
    grammar.complex_assignment.setParseAction(TTComplexAssignment)
    # statements
    grammar.fortran_subroutine_call.setParseAction(TTSubroutineCall)
