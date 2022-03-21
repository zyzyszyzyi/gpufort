#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2020-2022 Advanced Micro Devices, Inc. All rights reserved.
import time
import unittest
import cProfile,pstats,io
import json

import addtoplevelpath
from gpufort import util

LOG_FORMAT = "[%(levelname)s]\tgpufort:%(message)s"
util.logging.opts.verbose    = False
util.logging.init_logging("log.log",LOG_FORMAT,"warning")

PROFILING_ENABLE = False

testdata1 = \
"""
! comment
  ! comment
stmt_or_dir ! comment
!$acc stmt_or_dir
*$acc stmt_or_dir
c$acc stmt_or_dir
C$acc stmt_or_dir
!$ acc stmt_or_dir
! $acc comment
  !a$acc comment
"""

# whitespace at begin is important to
# as [cC] in first column indicates a comment
# line in Fortran 77.
testdata2 = \
"""  call myroutine( & ! comment 1
        arg1,&
        ! comment 2


        arg2) ! comment 3
"""

testdata2_result = \
"""  call myroutine( &
        arg1,&


        arg2)
  ! comment 1
        ! comment 2
        ! comment 3
"""

testdata3="k () + a ( b, c(d)+e(f)) + g(h(i,j+a(k(),2)))"""

testdata3_result= {
    "a" :  [('a ( b, c(d)+e(f))', [' b', ' c(d)+e(f)']), ('a(k(),2)', ['k()', '2'])],
    "b" :  [],
    "c" :  [('c(d)', ['d'])],
    "d" :  [],
    "f" :  [],
    "g" :  [('g(h(i,j+a(k(),2)))', ['h(i,j+a(k(),2))'])],
    "h" :  [('h(i,j+a(k(),2))', ['i', 'j+a(k(),2)'])],
    "i" :  [],
    "j" :  [],
    "k" :  [('k ()', []), ('k()', [])],
    }


class TestParsingUtils(unittest.TestCase):
    def prepare(self,text):
        return text.strip().splitlines()
    def clean(self,text):
        return text.replace(" ","").replace("\t","").replace("\n","").replace("\r","")
    def setUp(self):
        global PROFILING_ENABLE
        if PROFILING_ENABLE:
            self.profiler = cProfile.Profile()
            self.profiler.enable()
        self.started_at = time.time()
    def tearDown(self):
        global PROFILING_ENABLE
        if PROFILING_ENABLE:
            self.profiler.disable() 
            s = io.StringIO()
            sortby = 'cumulative'
            stats = pstats.Stats(self.profiler, stream=s).sort_stats(sortby)
            stats.print_stats(10)
            print(s.getvalue())
        elapsed = time.time() - self.started_at
        print('{} ({}s)'.format(self.id(), round(elapsed, 6)))
    def test_01_split_fortran_line(self):
        for line in self.prepare(testdata1):
            indent,stmt_or_dir,comment,trailing_ws =\
              util.parsing.split_fortran_line(line)
            if "stmt_or_dir" in line:
                self.assertTrue(len(stmt_or_dir))
            else:
                self.assertFalse(len(stmt_or_dir))
            if "comment" in line:
                self.assertTrue(len(comment))
            else:
                self.assertFalse(len(comment))
        # 
    def test_02_relocate_inline_comments(self):
        result = util.parsing.relocate_inline_comments(\
                   testdata2.splitlines())
        self.assertEqual(self.clean("\n".join(result)),self.clean(testdata2_result))
    def test_03_extract_function_calls(self):
        for c in ["a","b","c","d","f","g","h","i","j","k"]:
            result = util.parsing.extract_function_calls(testdata3,c)
            #print(result)
            self.assertEqual(result,testdata3_result[c])
    def test_04_parse_use_statement(self):
        statements = [
          "use mymod",
          "use mymod, only: var1",
          "use mymod, only: var1, var2",
          "use mymod, only: var1, var2=>var3",
        ]
        results = [
          ('mymod', []),
          ('mymod', [('var1', 'var1')]),
          ('mymod', [('var1', 'var1'),('var2', 'var2')]),
          ('mymod', [('var1', 'var1'),('var2', 'var3')]),
        ]
        for i,stmt in enumerate(statements):
            #print(util.parsing.parse_use_statement(stmt))
            self.assertEqual(util.parsing.parse_use_statement(stmt),results[i])
    def test_05_parse_declaration(self):
        statements = [
          "integer,parameter :: a(1) = (/1/), b = 5*2**3",
          "integer(kind(hipSuccess)),parameter :: ierr = hipSuccess",
          "integer(kind=4),parameter :: mykind = 3",
          "integer*4,pointer :: a(:) => null(), b => null()",
          "integer*4,allocatable :: b(:,:,n,-1:5)",
          "integer,dimension(:,:) :: int_array2d",
        ]
        results = [
          # type, kind, qualifiers without dimensions, dimension bounds, variables: list of (name, bounds, rhs)
          ('integer', None, ['parameter'], [], [('a', ['1'], '(/1/)'), ('b', [], '5*2**3')], 'integer', ['parameter']),
          ('integer', 'kind(hipSuccess)', ['parameter'], [], [('ierr', [], 'hipSuccess')], 'integer(kind(hipSuccess))', ['parameter']),
          ('integer', '4', ['parameter'], [], [('parameter', [], None)], 'integer(kind=4),', ['parameter']),
          ('integer', '4', ['pointer'], [], [('a', [':'], 'null()'), ('b', [], 'null()')], 'integer*4', ['pointer']),
          ('integer', '4', ['allocatable'], [], [('b', [':', ':', 'n', '-1:5'], None)], 'integer*4', ['allocatable']),
          ('integer', None, [], [':', ':'], [('int_array2d', [], None)], 'integer', ['dimension(:,:)']) ,
        ]
        for i,stmt in enumerate(statements):
            #print(util.parsing.parse_declaration(stmt))
            self.assertEqual(util.parsing.parse_declaration(stmt),results[i])
    def test_06_parse_attributes_statement(self):
        statements = [
          "attributes(device,constant) :: a_d, b_d"
        ]
        results = [
          (['device','constant'], ['a_d','b_d'])
        ]
        for i,stmt in enumerate(statements):
            #print(util.parsing.parse_attributes_statement(stmt))
            self.assertEqual(util.parsing.parse_attributes_statement(stmt),results[i])
    def test_07_strip_array_indexing(self):
        expressions = [
          "a",
          "a(1)",
          "a(:,5)",
          "a(:,5)%b",
          "A(:,5)%b(c(5,2))%c",
        ]
        results = [
          "a",
          "a",
          "a",
          "a%b",
          "A%b%c",
        ]
        for i,expr in enumerate(expressions):
            #print(util.parsing.strip_array_indexing(expr))
            self.assertEqual(util.parsing.strip_array_indexing(expr),results[i])
    def test_08_derived_type_parents(self):
        expressions = [
          "a",
          "a(1)",
          "a(:,5)",
          "a(:,5)%b",
          "A(:,5)%b(c(5,2))%c",
        ]
        results = [
          [],
          [],
          [],
          ['a'],
          ['A', 'A%b'],
        ]
        for i,expr in enumerate(expressions):
            #print(util.parsing.derived_type_parents(expr))
            self.assertEqual(util.parsing.derived_type_parents(expr),results[i])
    def test_09_tokenize(self):
        expressions = [
          "!$acc enter data copyin(a) copyout(b(-1:))",
        ]
        results = [
          ['!$', 'acc', 'enter', 'data', 'copyin', '(', 'a', ')', 'copyout', '(', 'b', '(', '-', '1', ':', ')', ')'],
        ]
        for i,expr in enumerate(expressions):
            #print(util.parsing.tokenize(expr))
            self.assertEqual(util.parsing.tokenize(expr),results[i])
    def test_10_parse_directive(self):
        expressions = [
          "!$acc enter data copyin(a,b,c(:)) copyout(b(-1:))",
        ]
        results = [
          ['!$', 'acc', 'enter', 'data', 'copyin(a,b,c(:))', 'copyout(b(-1:))'],
        ]
        for i,expr in enumerate(expressions):
            #print(util.parsing.parse_directive(expr))
            self.assertEqual(util.parsing.parse_directive(expr),results[i])
    
    def test_11_parse_acc_clauses(self):
        expressions = [
          ["copyin(a,b,c(:))","copyout(b(-1:))","async"],
          ["copyin(a,b,c(:))","copyout(b(-1:))","reduction(+:a)","async"],
          ["map(to:x,y(:),tofrom:a%z(1:n,2:m))"], # actually OMP clauses
        ]
        results = [
          [('copyin', ['a', 'b', 'c(:)']), ('copyout', ['b(-1:)']), ('async', [])],
          [('copyin', ['a', 'b', 'c(:)']), ('copyout', ['b(-1:)']), ('reduction', [('+', ['a'])]), ('async', [])],
          [('map', [('to', ['x', 'y(:)']), ('tofrom', ['a%z(1:n,2:m)'])])],
        ]
        for i,expr in enumerate(expressions):
            #print(util.parsing.parse_acc_clauses(expr))
            self.assertEqual(util.parsing.parse_acc_clauses(expr),results[i])
    
    def test_12_parse_acc_directive(self):
        expressions = [
          "!$acc enter data copyin(a,b,c(:)) copyout(b(-1:))",
          "!$acc wait(i,j) async(c)",
          "!$acc kernels loop reduction(+:x)"
        ]
        results = [
          ('!$', ['acc', 'enter', 'data'], [], ['copyin(a,b,c(:))', 'copyout(b(-1:))']),
          ('!$', ['acc', 'wait'], ['i', 'j'], ['async(c)']),
          ('!$', ['acc', 'kernels', 'loop'], [], ['reduction(+:x)']),
        ]
        for i,expr in enumerate(expressions):
            #print(util.parsing.parse_acc_directive(expr))
            self.assertEqual(util.parsing.parse_acc_directive(expr),results[i])
    def test_13_parse_cuf_kernel_call(self):
        expressions = [
          "call mykernel<<<grid,block>>>(arg1,arg2,arg3(1:n))",
          "call mykernel<<<grid,block,0,stream>>>(arg1,arg2,arg3(1:n))",
        ]
        results = [
          ('mykernel',['grid','block'],['arg1','arg2','arg3(1:n)']),
          ('mykernel',['grid','block','0','stream'],['arg1','arg2','arg3(1:n)']),
        ]
        for i,expr in enumerate(expressions):
            #print(util.parsing.parse_cuf_kernel_call(expr))
            self.assertEqual(util.parsing.parse_cuf_kernel_call(expr),results[i])
    def test_14_mangle_fortran_var_expr(self):
        expressions = [
          "a(i,j)%b%arg3(1:n)",
        ]
        results = [
          "aLijR_b_arg3L1TnR",
        ]
        for i,expr in enumerate(expressions):
            #print(util.parsing.mangle_fortran_var_expr(expr))
            self.assertEqual(util.parsing.mangle_fortran_var_expr(expr),results[i])
    def test_15_parse_derived_type_statement(self):
        expressions = [
          'type mytype',
          'type :: mytype',
          'type, bind(c) :: mytype',
          'type :: mytype(k,l)',
        ]
        results = [
          ('mytype', [], []),
          ('mytype', [], []),
          ('mytype', ['bind(c)'], []),
          ('mytype', [], ['k,l)']),
        ]
        for i,expr in enumerate(expressions):
            #print(util.parsing.parse_derived_type_statement(expr))
            self.assertEqual(util.parsing.parse_derived_type_statement(expr),results[i])

if __name__ == '__main__':
    unittest.main() 
