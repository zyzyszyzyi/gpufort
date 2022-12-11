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

class TTReturn(base.TTStatement):

    def _assign_fields(self, tokens):
        self._result_name = ""

    def cstr(self):
        if self._result_name != None and len(self._result_name):
            return "return " + self._result_name + ";"
        else:
            return "return;"

    def fstr(self):
        return "return"

class TTLabel(base.TTStatement):

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

class TTContinue(base.TTStatement):
    def cstr(self):
        return ";"

    def fstr(self):
        return "continue"

class TTCycle(base.TTStatement):

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

class TTExit(base.TTStatement):

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

class TTUnconditionalGoTo(base.TTStatement):
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

class TTDo(base.TTContainer):

    def _assign_fields(self, tokens):
        self._begin, self._end, self._step, self.body = tokens
        self.numeric_do_label = None
    @property
    def index(self):
        return self._begin.lhs
    @property
    def first(self):
        return self._begin.rhs
    @property
    def last(self):
        return self._end
    @property
    def step(self):
        return self._step
    def has_step(self):
        return self._step != None
    def child_nodes(self):
        yield self._begin
        yield self._end 
        if self._step != None:
            yield self._step
        yield from self.body 

class TTUnconditionalDo(base.TTContainer):
    def _assign_fields(self, tokens):
        self.body = tokens[0]
        self.numeric_do_label = None
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
        yield self._condition
        yield from self.body
    
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
    def child_nodes(self):
        yield self.selector
        yield from self.body
    def header_cstr(self):
        return "switch ({}) {{\n".format(self.selector)
    def footer_cstr(self):
        return "}\n" 

class TTCase(base.TTContainer):

    def _assign_fields(self, tokens):
        self.cases, self.body = tokens

    def child_nodes(self):
        yield from self.cases
        yield from self.body
    
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
        yield from self.body
    
    def header_cstr(self):
        return "default:\n"
    def footer_cstr(self):
        return "  break;\n" 

class TTDoWhile(base.TTContainer):

    def _assign_fields(self, tokens):
        self._condition, self.body = tokens
        self.numeric_do_label = None

    def child_nodes(self):
        yield self._condition
        yield from self.body
    
    def header_cstr(self):
        return "while ({0}) {{\n".format(
          traversals.make_cstr(self._condition)
        )
    def footer_cstr(self):
        return "  break;\n" 
