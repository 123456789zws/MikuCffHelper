from typing import List, Dict, Any
from binaryninja import (
    Function,
    Variable,
    MediumLevelILFunction,
    MediumLevelILSetVar,
    MediumLevelILVar,
    MediumLevelILOperation,
    MediumLevelILIf,
    MediumLevelILConst,
    MediumLevelILInstruction
)

from .mikuPlugin import suggest_stateVar, log_error

def collect_stateVar_info(func: Function, ret_int: bool = True):
    """收集函数中的状态变量信息
    Args:
        func (Function): 目标函数
        ret_int (bool): 是否返回整数值
    Returns:
        Tuple[Dict, Dict]: 包含if表和定义表的元组
    """
    args = func.parameter_vars
    args_name = [var.name for var in args]
    mlil = func.medium_level_il
    if not mlil:
        return {}, {}
    ifTable: Dict[
        MediumLevelILVar|Any, List[MediumLevelILInstruction]|List[int]|Any
    ] = {}
    defineTable: Dict[
        MediumLevelILVar|Any, List[MediumLevelILInstruction]|List[int]|Any
    ] = {}
    
    def travse_if_const_compare(expr):
        if not isinstance(expr, MediumLevelILIf):
            return
        condition = expr.condition
        if isinstance(condition, MediumLevelILVar):
            log_error(f"if(cond) should not appear in {expr}")
            return
        if not hasattr(condition, "right"):
            return
        if isinstance(condition.right, MediumLevelILConst):
            left = condition.left
            for token in left.tokens:
                if token in args_name:
                    return
            if not isinstance(left, MediumLevelILVar):
                return
            if left.src not in ifTable:
                ifTable[left.src] = []
            if ret_int:
                ifTable[left.src].append(condition.right.value.value)
            else:
                ifTable[left.src].append(expr)

    def travse_define(expr):
        if not isinstance(expr, MediumLevelILSetVar):
            return
        if not isinstance(expr.src, MediumLevelILConst):
            return
        for token in expr.tokens:
            if token in args_name:
                return
        if expr.dest not in defineTable:
            defineTable[expr.dest] = []
        if ret_int:
            defineTable[expr.dest].append(expr.src.value.value)
        else:
            defineTable[expr.dest].append(expr)

    list(mlil.traverse(travse_if_const_compare))
    list(mlil.traverse(travse_define))
    
    if not ret_int:
        for x in ifTable:
            ifTable[x] = [instr for instr in ifTable[x] if instr.instr_index < len(mlil)]
        for x in defineTable:
            defineTable[x] = [
                instr for instr in defineTable[x] if instr.instr_index < len(mlil)
            ]
    return ifTable, defineTable

class StateMachine:
    """状态机分析器，负责状态机分析和状态变量检测"""
    
    @staticmethod
    def find_state_var(func: Function):
        """查找函数中的状态变量
        Args:
            func (Function): 目标函数
        Returns:
            List[Variable]: 找到的状态变量列表
        """
        vars = func.vars
        vars_name = [var.name for var in vars]
        if all([not var.startswith("state-") for var in vars_name]):
            from .mikuPlugin import suggest_stateVar
            suggest_stateVar(func.view, func)
        state_vars = [var for var in vars if var.name.startswith("state-")]
        return state_vars

    @staticmethod
    def find_paired_state_var(state_var: Variable, mlil: MediumLevelILFunction):
        """查找与给定状态变量配对的另一个状态变量
        Args:
            state_var (Variable): 目标状态变量
            mlil (MediumLevelILFunction): 中间语言函数
        Returns:
            Variable: 找到的配对状态变量，如果不存在返回None
        """
        if not state_var.name.startswith("state-"):
            return None
        defines = mlil.get_var_definitions(state_var)
        if all([defi.src.operation == MediumLevelILOperation.MLIL_CONST for defi in defines]):
            return None
        for define in defines:
            if not isinstance(define, MediumLevelILSetVar):
                continue
            var = define.src
            if (isinstance(var, MediumLevelILVar)
                    and var.src != state_var):
                if not var.src.name.startswith("state-"):
                    from ..utils import make_stateVar
                    make_stateVar(mlil.source_function.view,mlil.source_function,var.src)
                return var.src
