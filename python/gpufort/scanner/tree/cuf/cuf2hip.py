# SPDX-License-Identifier: MIT
# Copyright (c) 2020-2022 Advanced Micro Devices, Inc. All rights reserved.
from gpufort import translator
from gpufort import util
from . import backends


class CufLoopNest2Hip(backends.CufBackendBase):

    def transform(self,
                  joined_lines,
                  joined_statements,
                  statements_fully_cover_lines,
                  index=[]):
        return nodes.STLoopNest.transform(self._stnode, joined_lines,
                                          joined_statements,
                                          statements_fully_cover_lines, index)


backends.register_cuf_backend("hip", CufLoopNest2Hip, None)
