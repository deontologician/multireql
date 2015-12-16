'''Converts a python ast into ruby source code'''

import re
import ast
import logging

try:
    from io import StringIO
except ImportError:
    from cStringIO import StringIO


logger = logging.getLogger('ruby_converter')

SYMBOL_REGEX = re.compile(r'[A-Za-z@$_]+[_A-Za-z0-9]*[!_=?A-Za-z0-9]?')


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

    def to_str(self, s):
        self.write(repr(s).strip('b'))

    def to_args(self, args, optargs=[]):
        if not args and not optargs:
            # idiomatic ruby skips empty braces
            return
        self.write("(")
        self.join(", ", args + optargs)
        self.write(")")

    def visit_keyword(self, node):
        self.write(node.arg)
        self.write(": ")
        self.visit(node.value)

    def visit_arg(self, node):
        self.write(node.arg)

    def generic_visit(self, node):
        logger.error("While translating: %s", ast.dump(node))
        logger.error("Got as far as: %s", ''.join(self.out))
        raise Exception("Don't know what this thing is: " + str(type(node)))

    def visit_Assign(self, node):
        if len(node.targets) != 1:
            raise Exception("We only support assigning to one variable")
        self.write(node.targets[0].id)
        self.write(" = ")
        self.visit(node.value)

    def visit_Str(self, node):
        self.to_str(node.s)

    def visit_Bytes(self, node):
        self.to_str(node.s)
        self.write(".force_encoding('BINARY')")

    def visit_Name(self, node):
        name = node.id
        if name == 'frozenset':
            self.skip("can't convert frozensets")
        self.write({
            'True': 'true',
            'False': 'false',
            'None': 'nil',
            }.get(name, name))

    def visit_NameConstant(self, node):
        if node.value is None:
            self.write("nil")
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
        self.write(node.attr)

    def visit_Num(self, node):
        self.write(repr(node.n))

    def visit_Index(self, node):
        self.visit(node.value)

    def convert_if_string_encode(self, node):
        '''Finds strings like 'foo'.encode("utf-8") and turns them into the
        java version: "foo".getBytes(StandardCharsets.UTF_8)'''
        try:
            assert node.func.attr == 'encode'
            node.func.value.s
            encoding = node.args[0].s
        except Exception:
            return False
        java_encoding = {
            "ascii": "US_ASCII",
            "utf-16": "UTF_16",
            "utf-8": "UTF_8",
        }[encoding]
        self.visit(node.func.value)
        self.write(".getBytes(StandardCharsets.")
        self.write(java_encoding)
        self.write(")")
        return True

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute) and \
           node.func.attr == 'expr' and \
           isinstance(node.func.value, ast.Name) and \
           node.func.value.id == 'r':
            # Translates r.expr(foo) into r(foo)
            self.visit(node.func.value)
        else:
            self.visit(node.func)
        if node.args and type(node.args[-1]) == ast.Lambda:
            self.to_args(node.args[:-1], node.keywords)
            self.visit(node.args[-1])
        else:
            self.to_args(node.args, node.keywords)

    def visit_Dict(self, node):
        self.write("{")
        first = True
        for k, v in zip(node.keys, node.values):
            if first:
                first = False
            else:
                self.write(", ")
            self.visit(k)
            self.write(" => ")
            self.visit(v)
        self.write("}")

    def visit_List(self, node):
        self.write("[")
        self.join(", ", node.elts)
        self.write("]")

    def visit_Tuple(self, node):
        self.visit_List(node)

    def visit_Lambda(self, node):
        self.write("{|")
        self.join(", ", node.args.args)
        self.write("| ")
        self.visit(node.body)
        self.write("}")

    def visit_Subscript(self, node):
        self.visit(node.value)
        if type(node.slice) == ast.Index:
            self.write("[")
            self.visit(node.slice.value)
            self.write("]")
        elif type(node.slice) == ast.Slice:
            self.write("[(")
            self.visit(node.slice.lower)
            if node.slice.upper is not None:
                self.write("...")
                self.visit(node.slice.upper)
            else:
                self.write("..-1")
            self.write(")]")
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
        self.write(opMap[type(node.op)])
        self.visit(node.operand)

    def visit_BinOp(self, node):
        opMap = {
            ast.Add: " + ",
            ast.Sub: " - ",
            ast.Mult: " * ",
            ast.Div: " / ",
            ast.Mod: " % ",
            ast.Pow: " ** ",
            ast.BitAnd: " & ",
            ast.BitOr: " | ",
        }
        self.write('(')
        self.visit(node.left)
        self.write(opMap[type(node.op)])
        self.visit(node.right)
        self.write(')')

    def visit_Compare(self, node):
        opMap = {
            ast.Lt: " < ",
            ast.Gt: " > ",
            ast.GtE: " >= ",
            ast.LtE: " <= ",
            ast.Eq: " == ",
            ast.NotEq: " != ",
        }
        left = node.left
        right = None
        for op, comparator in zip(node.ops, node.comparators):
            if right is not None:
                self.write(" && ")
            right = comparator
            op_name = opMap[type(op)]
            self.visit(left)
            self.write(op_name)
            self.visit(right)
            left = right
