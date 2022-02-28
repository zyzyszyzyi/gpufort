# SPDX-License-Identifier: MIT
# Copyright (c) 2020-2022 Advanced Micro Devices, Inc. All rights reserved.
import os, sys
import re

import orjson

from gpufort import util
from . import grammar
from . import opts

_ERR_LINEMAPPER_MACRO_DEFINITION_NOT_FOUND = 11001


def _evaluate_defined(input_string, macro_names):
    # expand macro; one at a time
    result = input_string
    iterate = True
    while iterate:
        iterate = False
        for match, start, end in grammar.pp_defined.scanString(result):
            substring = result[start:end].strip(" \t\n")
            subst = "1" if match.name in macro_names else "0"
            result = result.replace(substring, subst)
            iterate = True
            break
    return result


def _expand_macros(input_string, macro_stack):
    # expand macro; one at a time
    macro_names = [macro["name"] for macro in macro_stack]
    # check if macro identifiers appear in string before scanning the result
    iterate = True
    for name in macro_names:
        if name in input_string:
            iterate = True
    if iterate or "defined" in input_string:
        result = _evaluate_defined(input_string, macro_names)
    else:
        result = input_string
    while iterate:
        # Requires N+1 iterations to perform N replacements
        iterate = False
        for macro in macro_stack:
            name = macro["name"]
            if name in result:
                if len(macro["args"]):
                    calls = util.parsing.extract_function_calls(result, name)
                    if len(calls):
                        substring = calls[-1][
                            0] # always start from right-most (=inner-most) call site
                        args = calls[-1][1]
                        subst = macro["subst"].strip(" \n\t")
                        for n, placeholder in enumerate(macro["args"]):
                            subst = re.sub(r"\b{}\b".format(placeholder),
                                           args[n], subst)
                        result = result.replace(substring,
                                                subst) # result has changed
                        iterate = True
                        break
                else:
                    old_result = result
                    subst = macro["subst"].strip(" \n\t")
                    result = re.sub(r"\b{}\b".format(name), subst, result)
                    if result != old_result:
                        iterate = True
                    break
    return result


def _linearize_statements(linemap):
    result = []
    for stmt in linemap["statements"]:
        result += stmt["prolog"]
        result.append(stmt["body"])
        result += stmt["epilog"]
    return result


def _convert_operators(input_string):
    """Converts Fortran and C logical operators to python ones.
    :note: Adds whitespace around the operators as they 
    """
    return input_string.replace(r".and."," and ").\
                        replace(r".or."," or ").\
                        replace(r".not.","not ").\
                        replace(r"&&"," and ").\
                        replace(r"||"," or ").\
                        replace(r"!","not ")


def evaluate_condition(input_string, macro_stack):
    """
    Evaluates preprocessor condition.
    :param str input_string: Expression as text.
    :note: Input validation performed according to:
           https://realpython.com/python-eval-function/#minimizing-the-security-issues-of-eval
    """
    transformed_input_string = _convert_operators(
        _expand_macros(input_string, macro_stack))
    code = compile(transformed_input_string, "<string>", "eval")
    return eval(code, {"__builtins__": {}}, {}) > 0


def _handle_preprocessor_directive(lines, fortran_file_path, macro_stack,
                                   region_stack1, region_stack2):
    """
    :param str fortran_file_path: needed to load included files where only relative path is specified
    :param list macro_stack: A stack for storing/removing macro definition based on preprocessor directives.
    :param list region_stack1: A stack that stores if the current code region is active or inactive.
    :param list region_stack2: A stack that stores if any if/elif branch in the current if-elif-else-then
                              construct was active. This info is needed to decide if an else region 
                              should be activated.
    """

    def region_stack_format(stack):
        return "-".join([str(int(el)) for el in stack])

    macro_names = ",".join([macro["name"] for macro in macro_stack])
    util.logging.log_enter_function(opts.log_prefix,"_handle_preprocessor_directive",\
      {"fortran-file-path": fortran_file_path,\
       "region-stack-1":    region_stack_format(region_stack1),\
       "region-stack-2":    region_stack_format(region_stack2),\
       "macro-names":       macro_names})

    included_linemaps = []

    handled = False
    # strip away whitespace chars
    try:
        stripped_first_line = lines[0].lstrip("# \t").lower()
        single_line_statement = _convert_lines_to_statements(lines)[
            0] # does not make sense for define
        if region_stack1[-1]:
            if stripped_first_line.startswith("define"):
                util.logging.log_debug3(
                    opts.log_prefix, "_handle_preprocessor_directive",
                    "found define in line '{}'".format(lines[0].rstrip("\n")))
                # TODO error handling
                result = grammar.pp_dir_define.parseString(lines[0],
                                                           parseAll=True)
                subst_lines = [
                    line.strip("\n") + "\n"
                    for line in [result.subst] + lines[1:]
                ]
                subst = "".join(subst_lines).replace(r"\\", "")
                if result.args:
                    args = result.args.replace(" ", "").split(",")
                else:
                    args = []
                new_macro = {"name": result.name, "args": args, "subst": subst}
                macro_stack.append(new_macro)
                handled = True
            elif stripped_first_line.startswith("undef"):
                util.logging.log_debug3(
                    opts.log_prefix, "_handle_preprocessor_directive",
                    "found undef in line '{}'".format(lines[0].rstrip("\n")))
                result = grammar.pp_dir_define.parseString(
                    single_line_statement, parseAll=True)
                for macro in list(macro_stack): # shallow copy
                    if macro["name"] == result.name:
                        macro_stack.remove(macro)
                handled = True
            elif stripped_first_line.startswith("include"):
                util.logging.log_debug3(
                    opts.log_prefix, "_handle_preprocessor_directive",
                    "found include in line '{}'".format(lines[0].rstrip("\n")))
                result = grammar.pp_dir_include.parseString(
                    single_line_statement, parseAll=True)
                filename = result.filename.strip(" \t")
                current_dir = os.path.dirname(fortran_file_path)
                if not filename.startswith("/") and len(current_dir):
                    filename = os.path.dirname(
                        fortran_file_path) + "/" + filename
                included_linemaps = _preprocess_and_normalize_fortran_file(
                    filename, macro_stack, region_stack1, region_stack2)
                handled = True
        # if cond. true, push new region to stack
        if stripped_first_line.startswith("if"):
            util.logging.log_debug3(
                opts.log_prefix, "_handle_preprocessor_directive",
                "found if/ifdef/ifndef in line '{}'".format(
                    lines[0].rstrip("\n")))
            if region_stack1[-1] and stripped_first_line.startswith("ifdef"):
                result = grammar.pp_dir_ifdef.parseString(
                    single_line_statement, parseAll=True)
                condition = "defined(" + result.name + ")"
            elif region_stack1[-1] and stripped_first_line.startswith(
                    "ifndef"):
                result = grammar.pp_dir_ifndef.parseString(
                    single_line_statement, parseAll=True)
                condition = "!defined(" + result.name + ")"
            elif region_stack1[-1]: # and stripped_first_line.startswith("if"):
                result = grammar.pp_dir_if.parseString(single_line_statement,
                                                       parseAll=True)
                condition = result.condition
            else:
                condition = "0"
            active = evaluate_condition(condition, macro_stack)
            region_stack1.append(active)
            any_if_elif_active = active
            region_stack2.append(any_if_elif_active)
            handled = True
        # elif
        elif stripped_first_line.startswith("elif"):
            util.logging.log_debug3(
                opts.log_prefix, "_handle_preprocessor_directive",
                "found elif in line '{}'".format(lines[0].rstrip("\n")))
            region_stack1.pop() # rm previous if/elif-branch
            if region_stack1[-1] and not region_stack2[
                    -1]: # TODO allow to have multiple options specified at once
                result = grammar.pp_dir_elif.parseString(single_line_statement,
                                                         parseAll=True)
                condition = result.condition
            else:
                condition = "0"
            active = evaluate_condition(condition, macro_stack)
            region_stack1.append(active)
            region_stack2[-1] = region_stack2[-1] or active
            handled = True
        # else
        elif stripped_first_line.startswith("else"):
            util.logging.log_debug3(
                opts.log_prefix, "_handle_preprocessor_directive",
                "found else in line '{}'".format(lines[0].rstrip("\n")))
            region_stack1.pop() # rm previous if/elif-branch
            active = region_stack1[-1] and not region_stack2[-1]
            region_stack1.append(active)
            handled = True
        # endif
        elif stripped_first_line.startswith("endif"):
            region_stack1.pop()
            region_stack2.pop()
            handled = True
    except Exception as e:
        raise e

    if not handled:
        # TODO add ignore filter
        util.logging.log_warning(opts.log_prefix,"_handle_preprocessor_directive",\
          "preprocessor directive '{}' was ignored".format(single_line_statement))

    return included_linemaps


def _convert_lines_to_statements(lines):
    """Fortran lines can contain multiple statements that
    are separated by a semicolon.
    This routine unrolls such lines into multiple single statements.
    Additionally, it converts single-line Fortran if statements
    into multi-line if-then-endif statements.
    """

    p_continuation = re.compile(r"\&\s*([!c\*]\$\w+)?|([!c\*]\$\w+\&)",
                                re.IGNORECASE)
    # we look for a sequence ") <word>" were word != "then".
    p_single_line_if = re.compile(
        r"^(?P<indent>[\s\t]*)(?P<head>if\s*\(.+\))\s*\b(?!then)(?P<body>\w.+)",
        re.IGNORECASE)
    # Try to determine indent char and width
    first_line = lines[0]
    num_indent_chars = len(first_line) - len(first_line.lstrip(' '))
    if num_indent_chars == 0 and opts.default_indent_char == '\t':
        indent_char = '\t'
        num_indent_chars = len(first_line) - len(first_line.lstrip('\t'))
        indent_increment = indent_char * opts.indent_width_tabs
    else:
        indent_char = ' '
        indent_increment = indent_char * opts.indent_width_whitespace
    indent_offset = num_indent_chars * indent_char

    # replace line continuation by whitespace, split at ";"
    statement_parts = []
    comment_parts = []
    for line in lines:
        indent,stmt_or_dir_part,comment,_ = \
           util.parsing.split_fortran_line(line)
        if len(stmt_or_dir_part):
            statement_parts.append(stmt_or_dir_part)
        if len(comment):
            comment_parts.append(comment)
    single_line_statements = []
    if len(statement_parts):
        combined_statements = "".join(statement_parts)
        single_line_statements +=\
          p_continuation.sub(" ",combined_statements).split(";")
    if len(comment_parts):
        if len(single_line_statements):
            single_line_statements[-1] = single_line_statements[-1].rstrip(
                "\n") + "\n"
        single_line_statements += comment_parts
    # unroll single-line if
    unrolled_statements = []
    for stmt in single_line_statements:
        match = p_single_line_if.search(stmt)
        if match:
            if match.group("head").startswith("if"):
                THEN = " then"
                ENDIF = "endif"
            else:
                THEN = " THEN"
                ENDIF = "ENDIF"
            unrolled_statements.append(
                match.group("indent") + match.group("head") + THEN + "\n")
            unrolled_statements.append(
                match.group("indent") + indent_increment
                + match.group("body").rstrip("\n")
                + "\n") # line break is part of body
            unrolled_statements.append(match.group("indent") + ENDIF + "\n")
        else:
            unrolled_statements.append(indent_offset
                                       + stmt.lstrip(indent_char))
    return unrolled_statements


def _detect_line_starts(lines):
    """Fortran statements can be broken into multiple lines 
    via the '&' characters. This routine detects in which line a statement
    (or multiple statements per line) begins.
    The difference between the line numbers of consecutive entries
    is the number of lines the first statement occupies.
    """
    p_directive_continuation = re.compile(r"[!c\*]\$\w+\&")

    # 1. save multi-line statements (&) in buffer
    buffering = False
    line_starts = []
    for lineno, line in enumerate(lines, start=0):
        # Continue buffering if multiline CUF/ACC/OMP statement
        _,stmt_or_dir,comment,_ = \
           util.parsing.split_fortran_line(line)
        buffering |= p_directive_continuation.match(stmt_or_dir) != None
        if not buffering:
            line_starts.append(lineno)
        if len(stmt_or_dir) and stmt_or_dir[-1] in ['&', '\\']:
            buffering = True
        else:
            buffering = False
    line_starts.append(len(lines))
    return line_starts


def _preprocess_and_normalize_fortran_file(fortran_file_path, macro_stack,
                                           region_stack1, region_stack2):
    """
    :throws: IOError if the specified file cannot be found/accessed.
    """
    util.logging.log_enter_function(opts.log_prefix,
                                    "_preprocess_and_normalize_fortran_file",
                                    {"fortran_file_path": fortran_file_path})

    try:
        with open(fortran_file_path, "r") as infile:
            linemaps = preprocess_and_normalize(infile.readlines(),
                                                fortran_file_path, macro_stack,
                                                region_stack1, region_stack2)
            util.logging.log_leave_function(
                opts.log_prefix, "_preprocess_and_normalize_fortran_file")
            return linemaps
    except Exception as e:
        raise e


@util.logging.log_entry_and_exit(opts.log_prefix)
def _group_modified_linemaps(linemaps, wrap_in_ifdef):
    """Find contiguous blocks of modified lines and blank lines between them."""

    EMPTY_BLOCK    = { "min_lineno": -1, "max_lineno": -1, "orig": "", "subst": "",\
                       "only_prolog": False, "only_epilog": False}
    blocks = []
    current_linemaps = []

    # auxiliary local functions
    def max_lineno_(linemap):
        return linemap["lineno"] + len(linemap["lines"]) - 1

    def borders_previous_linemap_(linemap):
        nonlocal current_linemaps
        if len(current_linemaps):
            return linemap["lineno"] == max_lineno_(current_linemaps[-1]) + 1
        else:
            return True

    def contains_blank_line_(linemap):
        return len(linemap["lines"]) == 1 and not len(
            linemap["lines"][0].lstrip(" \t\n"))

    def was_modified_(linemap):
        modified = linemap["modified"]
        for linemap in linemap["included_linemaps"]:
            modified = modified or was_modified_(linemap)
        return modified

    def has_prolog_(linemap):
        result = len(linemap["prolog"])
        for linemap in linemap["included_linemaps"]:
            result = result or has_prolog_(linemap)
        return result

    def has_epilog_(linemap):
        result = len(linemap["epilog"])
        for linemap in linemap["included_linemaps"]:
            result = result or has_epilog_(linemap)
        return result

    def to_string_(list_of_strings):
        return "\n".join([
            el.rstrip("\n") for el in list_of_strings if el is not None
        ]) + "\n"

    def collect_subst_(linemap):
        subst = []
        if len(linemap["prolog"]):
            subst += linemap["prolog"]
        if len(linemap["included_linemaps"]):
            for linemap in linemap["included_linemaps"]:
                subst += collect_subst_(linemap)
        elif linemap["modified"]:
            subst += _linearize_statements(linemap)
        else: # for included linemaps
            subst += linemap["lines"]
        if len(linemap["epilog"]):
            subst += linemap["epilog"]
        return subst

    def append_current_block_if_non_empty_():
        # append current block if it is not empty
        # or does only contain blank lines.
        nonlocal blocks
        nonlocal current_linemaps
        if len(current_linemaps): # remove blank lines
            while contains_blank_line_(current_linemaps[-1]):
                current_linemaps.pop()
        if len(current_linemaps): # len might have changed
            block = dict(EMPTY_BLOCK) # shallow copy
            block["min_lineno"] = current_linemaps[0]["lineno"]
            block["max_lineno"] = max_lineno_(current_linemaps[-1])
            subst = []
            for linemap in current_linemaps:
                block["orig"] += to_string_(linemap["lines"])
                subst += collect_subst_(linemap)
            # special treatment for single-linemap blocks which are not modified
            # and are no #include statements but have prolog or epilog
            if len(current_linemaps) == 1 and not current_linemaps[0]["modified"] and not\
               len(current_linemaps[0]["included_linemaps"]):
                linemap = current_linemaps[0]
                #assert has_prolog_(linemap) or has_prolog_(linemap)
                block["only_prolog"] = has_prolog_(linemap)
                block["only_epilog"] = has_epilog_(linemap)
                if block["only_epilog"]: # xor
                    block["only_epilog"] = not block["only_prolog"]
                    block["only_prolog"] = False
                block["subst"] = to_string_(linemap["prolog"]
                                            + linemap["epilog"])
            else:
                block["subst"] = to_string_(subst)
            blocks.append(block)

    # 1. find contiguous blocks of modified or blank lines
    # 2. blocks must start with modified lines
    # 3. blank lines must be removed from tail of block
    for i, linemap in enumerate(linemaps):
        lineno = linemap["lineno"]
        if was_modified_(linemap) or has_prolog_(linemap) or has_epilog_(
                linemap):
            if not wrap_in_ifdef or not borders_previous_linemap_(linemap):
                append_current_block_if_non_empty_()
                current_linemaps = []
            current_linemaps.append(linemap)
        elif opts.line_grouping_include_blank_lines and len(
                current_linemaps) and contains_blank_line_(
                    linemap) and borders_previous_linemap_(linemap):
            current_linemaps.append(linemap)
    # append last block
    append_current_block_if_non_empty_()
    return blocks


# API


def init_macros(options):
    """init macro stack from compiler options and user-prescribed config values."""

    macro_stack = []
    macro_stack += opts.user_defined_macros
    for result, _, __ in grammar.pp_compiler_option.scanString(options):
        value = result.value
        if value == None:
            value == "1"
        macro = {"name": result.name, "args": [], "subst": result.value}
        macro_stack.append(macro)
    return macro_stack


def preprocess_and_normalize(fortran_file_lines,
                             fortran_file_path,
                             macro_stack=[],
                             region_stack1=[True],
                             region_stack2=[True]):
    """:param list file_lines: Lines of a file, terminated with line break characters ('\n').
    :returns: a list of dicts with keys 'lineno', 'original_lines', 'statements'.
    """

    util.logging.log_enter_function(opts.log_prefix,
                                    "preprocess_and_normalize",
                                    {"fortran_file_path": fortran_file_path})
    assert opts.default_indent_char in [
        ' ', '\t'
    ], "Indent char must be whitespace ' ' or tab '\\t'"

    # 1. detect line starts
    line_starts = _detect_line_starts(fortran_file_lines)

    # 2. go through the blocks of buffered lines
    linemaps = []
    for i, _ in enumerate(line_starts[:-1]):
        line_start = line_starts[i]
        next_line_start = line_starts[i + 1]
        lines = fortran_file_lines[line_start:next_line_start]

        included_linemaps = []
        is_preprocessor_directive = lines[0].startswith("#")
        if is_preprocessor_directive and not opts.only_apply_user_defined_macros:
            try:
                included_linemaps = _handle_preprocessor_directive(
                    lines, fortran_file_path, macro_stack, region_stack1,
                    region_stack2)
                statements1 = []
                statements3 = []
            except Exception as e:
                raise e
        elif region_stack1[-1]: # in_active_region
            # Convert line to statememts
            statements1 = _convert_lines_to_statements(lines)
            # 2. Apply macros to statements
            statements2 = []
            for stmt1 in statements1:
                statements2.append(_expand_macros(stmt1, macro_stack))
            # 3. Above processing might introduce multiple statements per line againa.
            # Hence, convert each element of statements2 to single statements again
            statements3 = []
            for stmt2 in statements2:
                for stmt3 in _convert_lines_to_statements([stmt2]):
                    statement = {"epilog": [], "prolog": [], "body": stmt3}
                    statements3.append(statement)
        #if len(included_linemaps) or (not is_preprocessor_directive and region_stack1[-1]):
        linemap = {
            "file": fortran_file_path,
            "lineno": line_start + 1, # key
            "lines": lines,
            "raw_statements": statements1,
            "included_linemaps": included_linemaps,
            "is_preprocessor_directive": is_preprocessor_directive,
            "is_active": region_stack1[-1],
            # inout
            "statements": statements3,
            "modified": False,
            # out
            "prolog": [],
            "epilog": []
        }
        linemaps.append(linemap)
    util.logging.log_leave_function(opts.log_prefix,
                                    "preprocess_and_normalize")
    return linemaps


def read_lines(fortran_lines, options="", fortran_file_path="<none>"):
    """
    A C and Fortran preprocessor (cpp and fpp).

    Current limitations:

    * Only considers if/ifdef/ifndef/elif/else/define/undef/include 

    :return: The input data structure without the entries whose statements where not in active code region
             as determined by the preprocessor.
    :param str options: a sequence of compiler options such as '-D<key> -D<key>=<value>'.
    :param str fortran_file_path: File path to write into the linemaps.
    """
    # TODO check if order of read_file routines can be simplified using this method

    util.logging.log_enter_function(opts.log_prefix, "read_lines",
                                    {"options": options})

    macro_stack = init_macros(options)
    linemaps = preprocess_and_normalize(fortran_lines, fortran_file_path,
                                        macro_stack)
    util.logging.log_leave_function(opts.log_prefix, "read_lines")
    return linemaps


def read_file(fortran_file_path, options=""):
    """A C and Fortran preprocessor (cpp and fpp).

    Current limitations:

    * Only considers if/ifdef/ifndef/elif/else/define/undef/include 

    :return: The input data structure without the entries whose statements where not in active code region
             as determined by the preprocessor.
    :param str options: a sequence of compiler options such as '-D<key> -D<key>=<value>'.
    :throws: IOError if the specified file cannot be found/accessed.
    """

    util.logging.log_enter_function(opts.log_prefix, "read_file", {
        "fortran_file_path": fortran_file_path,
        "options": options
    })

    macro_stack = init_macros(options)
    try:
        linemaps = _preprocess_and_normalize_fortran_file(fortran_file_path,macro_stack,\
           region_stack1=[True],region_stack2=[True]) # init value of region_stack[0] can be arbitrary
        util.logging.log_leave_function(opts.log_prefix, "read_file")
        return linemaps
    except Exception as e:
        raise e


@util.logging.log_entry_and_exit(opts.log_prefix)
def modify_file(linemaps, **kwargs):
    """Modify a file's file_content based on 
    the changes encoded by the linemaps.
    :param \*\*kwargs: See below.
    :param list linemaps: A list of linemaps that encode changes to each line.
    :return: The modified file's file_content as str. 
    :Keyword Arguments:
    * *file_lines* (``str``):
        Lines of the file that should be parsed.
    * *file_content* (``str``):
        Content of the file that should be parsed.
    * *preamble* (``str``):
        A preamble to put at the top of the output.
    * *ifdef_macro* (``str``):
        Macro to use in the ifdef directive [default: .opts.line_grouping_ifdef_macro].
    """
    file_lines, have_lines = util.kwargs.get_value("file_lines", [], **kwargs)
    if not have_lines:
        file_content, have_content = util.kwargs.get_value(
            "file_content", None, **kwargs)
        if have_content:
            file_lines = file_content.splitlines(keepends=True)
        else:
            raise ValueError(
                "Missing keyword argument: One of 'file_content' (str) or 'file_lines' (list of str) must be present."
            )
    preamble, _ = util.kwargs.get_value("preamble", "", **kwargs)
    ifdef_macro, _ = util.kwargs.get_value("ifdef_macro",
                                           opts.line_grouping_ifdef_macro,
                                           **kwargs)

    # TODO also offer variant where linemaps are not grouped in order
    # to have direct mapping between original code lines and modified
    # lines. Relevant for compiler app in order to link compiler backend
    # errors to the lines in the original file.
    blocks = _group_modified_linemaps(linemaps, ifdef_macro != None)

    output = ""
    block_id = 0
    lines_to_skip = -1
    for lineno, line in enumerate(file_lines, start=1):
        if block_id < len(blocks) and\
           lineno == blocks[block_id]["min_lineno"]:
            block = blocks[block_id]
            lines_to_skip = block["max_lineno"] - block["min_lineno"]
            subst = block["subst"].rstrip("\n")
            original = block["orig"].rstrip("\n")
            if ifdef_macro != None:
                if block["only_epilog"]:
                    output += "{2}\n#ifdef {0}\n{1}\n#endif\n".format(\
                      ifdef_macro,subst,original)
                elif block["only_prolog"]:
                    output += "#ifdef {0}\n{1}\n#endif\n{2}\n".format(\
                      ifdef_macro,subst,original)
                else:
                    if len(block["subst"].strip(" \n\t")):
                        output += "#ifdef {0}\n{1}\n#else\n{2}\n#endif\n".format(\
                          ifdef_macro,subst,original)
                    else:
                        output += "#ifndef {0}\n{2}\n#endif\n".format(\
                          ifdef_macro,subst,original)
            else:
                if block["only_epilog"]:
                    output += original + "\n" + subst + "\n"
                elif block["only_prolog"]:
                    output += subst + "\n" + original + "\n"
                else:
                    output += subst + "\n"
            block_id += 1
        elif lines_to_skip > 0:
            lines_to_skip -= 1
        else:
            output += line
    if preamble != None and len(preamble):
        if opts.line_grouping_ifdef_macro != None:
            preamble2 = "#ifdef {}\n{}\n#endif".format(\
              opts.line_grouping_ifdef_macro,preamble.rstrip("\n"))
        else:
            preamble2 = preamble.rstrip("\n")
        output = preamble2 + "\n" + output
    return output


def write_modified_file(outfile_path, infile_path, linemaps, preamble=""):
    """Create a modified version of the input file from
    the modified linemaps and write it to the output file path.
    
    :param str outfile_path: Output file path.
    :param str infile_path: Input file path.
    :param list linemaps: A list of linemaps created via GPUFORT's linemapper component.
    :param str preamble: A preamble to put at the begin of the output file file.
    :see: gpufort.linemapper
    """
    util.logging.log_enter_function(opts.log_prefix,"write_modified_file",\
      {"infile_path": infile_path,"outfile_path": outfile_path})

    with open(infile_path,"r") as infile,\
         open(outfile_path,"w") as outfile:
        outfile.write(
            modify_file(linemaps,
                        file_lines=infile.readlines(),
                        preamble=preamble).rstrip())
    util.logging.log_leave_function(opts.log_prefix, "write_modified_file")


@util.logging.log_entry_and_exit(opts.log_prefix)
def render_file(linemaps, **kwargs):
    """Render a file according to the linemaps.
    :param \*\*kwargs: See below.

    :Keyword Arguments:
    
    *stage* (`str`) 
        Either 'lines', 'statements' or 'expanded_statements', i.e. the preprocessor stage.
    *include_inactive* (`bool`) 
        Unclude also code lines in inactive code regions.
    *keep_preprocessor_directives* (`bool`) 
        Include also preprocessor directives in the output (except include directives).
    """
    stage, _ = util.kwargs.get_value("stage", "statements", **kwargs)
    include_inactive, _ = util.kwargs.get_value("include_inactive", False,
                                                **kwargs)
    keep_preprocessor_directives, _ = util.kwargs.get_value(
        "keep_preprocessor_directives", False, **kwargs)

    def render_file_(linemaps):
        nonlocal stage
        nonlocal include_inactive
        nonlocal keep_preprocessor_directives

        result = ""
        for linemap in linemaps:
            condition1 = include_inactive or (linemap["is_active"])
            condition2 = keep_preprocessor_directives or (
                len(linemap["included_linemaps"]) or
                not linemap["is_preprocessor_directive"])
            if condition1 and condition2:
                if len(linemap["included_linemaps"]):
                    result += render_file_(linemap["included_linemaps"])
                elif stage == "statements":
                    result += "".join(_linearize_statements(linemap))
                else:
                    result += "".join(linemap[stage])
        return result

    return render_file_(linemaps).strip("\n")


@util.logging.log_entry_and_exit(opts.log_prefix)
def dump_linemaps(linemaps, file_path):
    with open(file_path, "wb") as outfile:
        if opts.pretty_print_linemaps_dump:
            outfile.write(orjson.dumps(linemaps, option=orjson.OPT_INDENT_2))
        else:
            outfile.write(orjson.dumps(linemaps))


def get_linemaps_content(linemaps,
                         key,
                         first_linemap_first_elem=0,
                         last_linemap_last_elem=-1):
    """Collects entries for the given key from the node's linemaps."""
    result = []
    for i, linemap in enumerate(linemaps):
        if len(linemaps) == 1:
            if last_linemap_last_elem == -1:
                result += linemap[key][first_linemap_first_elem:]
            else:
                result += linemap[key][
                    first_linemap_first_elem:last_linemap_last_elem + 1]
        elif i == 0:
            result += linemap[key][first_linemap_first_elem:]
        elif i == len(linemaps) - 1:
            if last_linemap_last_elem == -1:
                result += linemap[key]
            else:
                result += linemap[key][0:last_linemap_last_elem + 1]
        else:
            result += linemap[key]
    return result


def get_statement_bodies(linemaps,
                         first_linemap_first_elem=0,
                         last_linemap_last_elem=-1):
    return [
        stmt["body"] for stmt in get_linemaps_content(
            linemaps, "statements", first_linemap_first_elem,
            last_linemap_last_elem)
    ]


def init_macros(options):
    """init macro stack from compiler options and user-prescribed config values."""

    macro_stack = []
    macro_stack += opts.user_defined_macros
    for result, _, __ in grammar.pp_compiler_option.scanString(options):
        value = result.value
        if value == None:
            value == "1"
        macro = {"name": result.name, "args": [], "subst": result.value}
        macro_stack.append(macro)
    return macro_stack