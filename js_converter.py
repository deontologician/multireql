'''Converts a python ast into ruby source code'''

import ast
import logging

from cStringIO import StringIO

from conversion_utils import dromedary

logger = logging.getLogger('ruby_converter')


class Visitor(ast.NodeVisitor):
    '''Converts python ast nodes into a ruby string'''

    def __init__(self,
                 reql_vars=frozenset("r"),
                 out=None):
        self.out = StringIO() if out is None else out
        self.reql_vars = reql_vars
        super(Visitor, self).__init__()
        self.write = self.out.write

    def skip(self, message, *args, **kwargs):
        raise Exception(message, *args, **kwargs)

    def convert(self, node):
        '''Convert a text line to another text line'''
        self.visit(node)
        return self.out.getvalue()

    def join(self, sep, items):
        first = True
        for item in items:
            if first:
                first = False
            else:
                self.write(sep)
            self.visit(item)

    def wrap(self, *args):
        for arg in args:
            if isinstance(arg, str):
                self.write(arg)
            elif isinstance(arg, ast.AST):
                self.visit(arg)
            else:
                raise Exception("Bad argument to wrap")

    def to_str(self, s):
        self.write(repr(s).strip('b'))

    def generic_visit(self, node):
        logger.error("While translating: %s", ast.dump(node))
        logger.error("Got as far as: %s", ''.join(self.out))
        raise Exception("Don't know what this thing is: " + str(type(node)))

    def visit_Assign(self, node):
        if len(node.targets) != 1:
            raise Exception("We only support assigning to one variable")
        self.write("var ")
        self.write(node.targets[0].id)
        self.write(" = ")
        self.visit(node.value)

    def visit_Str(self, node):
        self.to_str(node.s)

    def visit_Bytes(self, node):
        self.write("Buffer(")
        self.to_str(node.s)
        self.write(", 'binary')")

    def visit_Name(self, node):
        if node.is_reql:
            self.write(dromedary(node.id))
        else:
            self.write(dromedary(node.id))

    def visit_NameConstant(self, node):
        if node.value is None:
            self.write("null")
        elif node.value is True:
            self.write("true")
        elif node.value is False:
            self.write("false")
        else:
            raise Exception(
                "Don't know NameConstant with value %s" % node.value)

    def visit_Attribute(self, node):
        self.visit(node.value)
        self.write(".")
        if node.is_reql:
            self.write(dromedary(node.attr))
        else:
            self.write(node.attr)

    def visit_Num(self, node):
        self.write(repr(node.n))

    def visit_Index(self, node):
        self.visit(node.value)

    def visit_Call(self, node):
        self.visit(node.func)
        self.write("(")
        self.join(", ", node.args)
        if node.keywords:
            if node.args:
                self.write(", ")
            self.write("{")
            self.join(", ", node.keywords)
            self.write("}")
        self.write(")")

    def visit_arg(self, node):
        '''arg in a lambda declaration'''
        self.write(node.arg)

    def visit_keyword(self, node):
        if node.is_reql:
            self.write(dromedary(node.arg))
        else:
            self.write(node.arg)
        self.write(": ")
        self.visit(node.value)

    def visit_Dict(self, node):
        self.write("{")
        first = True
        for k, v in zip(node.keys, node.values):
            if first:
                first = False
            else:
                self.write(", ")
            self.write(k)
            self.write(": ")
            self.visit(v)
        self.write("}")

    def visit_List(self, node):
        self.write("[")
        self.join(", ", node.elts)
        self.write("]")

    def visit_Tuple(self, node):
        self.visit_List(node)

    def visit_Lambda(self, node):
        self.write("function(")
        self.join(", ", node.args.args)
        self.wrap(") { return ", node.body, " }")

    def visit_Subscript(self, node):
        self.visit(node.value)
        if type(node.slice) == ast.Index:
            if node.is_reql:
                self.wrap("(", node.slice.value, ")")
            else:
                self.wrap("[", node.slice.value, "]")
        elif type(node.slice) == ast.Slice:
            self.wrap(".slice(", node.slice.lower)
            if node.slice.upper is not None:
                self.wrap(", ", node.slice.upper)
            self.write(")")
        else:
            raise Exception("Not handling ExtSlice")

    def visit_ListComp(self, node):
        raise Exception("list comprehension not implemented yet")

    def visit_UnaryOp(self, node):
        opMap = {
            ast.USub: "-",
            ast.Not: "!",
            ast.UAdd: "+",
            ast.Invert: "~",
        }
        reqlMap = {
            ast.Not: "not"
        }
        if node.is_reql:
            self.wrap(node.operand, ".", reqlMap[type(node.op)], "()")
        else:
            self.wrap(opMap[type(node.op)], node.operand)

    def visit_BinOp(self, node):
        jsMap = {
            ast.Add: " + ",
            ast.Sub: " - ",
            ast.Mult: " * ",
            ast.Div: " / ",
            ast.Mod: " % ",
            ast.Pow: " ** ",
        }
        reqlMap = {
            ast.Add: "add",
            ast.Sub: "sub",
            ast.Mult: "mul",
            ast.Div: "div",
            ast.Mod: "mod",
        }
        if node.is_reql:
            if not node.left.is_reql:
                self.write("r.expr(")
            self.visit(node.left)
            if not node.left.is_reql:
                self.write(")")
            self.write(".")
            self.write(reqlMap[type(node.op)])
            self.write("(")
            self.visit(node.right)
            self.write(")")
        else:
            self.visit(node.left)
            self.write(jsMap[type(node.op)])
            self.visit(node.right)

    def visit_Compare(self, node):
        if len(node.comparators) > 1:
            raise RuntimeError("Chained comparison not supported")
        left = node.left
        op_type = type(node.ops[0])
        right = node.comparators[0]
        is_reql = left.is_reql or right.is_reql
        op_map = {
            ast.Lt: " < ",
            ast.Gt: " > ",
            ast.GtE: " >= ",
            ast.LtE: " <= ",
            ast.Eq: " == ",
            ast.NotEq: " != ",
        }
        reql_map = {
            ast.Lt: "lt",
            ast.Gt: "gt",
            ast.GtE: "ge",
            ast.LtE: "le",
            ast.Eq: "eq",
            ast.NotEq: "ne",
        }
        if is_reql:
            self.wrap('(', left, ').', reql_map[op_type], '(', right, ')')
        else:
            self.wrap(left, op_map[op_type], right)
