import ast
import logging
import re
from cStringIO import StringIO

from conversion_utils import camel, dromedary

logger = logging.getLogger('java_converter')


# Java reserved keywords. If we add a term that collides with one
# of theses, the method names will have a trailing _ added
JAVA_KEYWORDS = {
    'abstract', 'continue', 'for', 'new', 'switch', 'assert',
    'default', 'goto', 'package', 'synchronized', 'boolean', 'do',
    'if', 'private', 'this', 'break', 'double', 'implements',
    'protected', 'throw', 'byte', 'else', 'import', 'public',
    'throws', 'case', 'enum', 'instanceof', 'return', 'transient',
    'catch', 'extends', 'int', 'short', 'try', 'char', 'final',
    'interface', 'static', 'void', 'class', 'finally', 'long',
    'strictfp', 'volatile', 'const', 'float', 'native', 'super',
    'while'
}

# Methods defined on Object that we don't want to inadvertantly override
OBJECT_METHODS = {
    'clone', 'equals', 'finalize', 'hashCode', 'getClass',
    'notify', 'notifyAll', 'wait', 'toString'
}

# Renames for methods
METHOD_ALIASES = {
    'GET_FIELD': 'g'  # getField is too long for such a common operation
}


TOPLEVEL_CONSTANTS = {
    'monday', 'tuesday', 'wednesday', 'thursday', 'friday',
    'saturday', 'sunday', 'january', 'february', 'march', 'april',
    'may', 'june', 'july', 'august', 'september', 'october',
    'november', 'december', 'minval', 'maxval', 'error'
}


def attr_matches(path, node):
    '''Helper function. Several places need to know if they are an
    attribute of some root object'''
    root, name = path.split('.')
    ret = is_name(root, node.value) and node.attr == name
    return ret


def is_name(name, node):
    '''Determine if the current attribute node is a Name with the
    given name'''
    return type(node) == ast.Name and node.id == name


def escape_string(s, out):
    out.write('"')
    for codepoint in s:
        rpr = repr(codepoint)[1:-1]
        if rpr.startswith('\\x'):
            # Python will shorten unicode escapes that are less than a
            # byte to use \x instead of \u . Java doesn't accept \x so
            # we have to expand it back out.
            rpr = '\\u00' + rpr[2:]
        elif rpr == '"':
            rpr = r'\"'
        out.write(rpr)
    out.write('"')


def py_to_java_type(py_type):
    '''Converts python types to their Java equivalents'''
    if py_type is None:
        return None
    elif isinstance(py_type, str):
        # This can be called on something already converted
        return py_type
    elif py_type.__name__ == 'function':
        return 'ReqlFunction1'
    elif (py_type.__module__ == 'datetime' and
          py_type.__name__ == 'datetime'):
        return 'OffsetDateTime'
    elif py_type.__module__ == 'builtins':
        return {
            bool: 'Boolean',
            bytes: 'byte[]',
            int: 'Long',
            float: 'Double',
            str: 'String',
            dict: 'Map',
            list: 'List',
            object: 'Object',
            type(None): 'Object',
        }[py_type]
    elif py_type.__module__ == 'rethinkdb.ast':
        # Anomalous non-rule based capitalization in the python driver
        return {
            'DB': 'Db'
        }.get(py_type.__name__, py_type.__name__)
    elif py_type.__module__ == 'rethinkdb.errors':
        return py_type.__name__
    elif py_type.__module__ == '?test?':
        return {
            'uuid': 'UUIDMatch',  # clashes with ast.Uuid
        }.get(py_type.__name__, camel(py_type.__name__))
    elif py_type.__module__ == 'rethinkdb.query':
        # All of the constants like minval maxval etc are defined in
        # query.py, but no type name is provided to `type`, so we have
        # to pull it out of a class variable
        return camel(py_type.st)
    else:
        raise RuntimeError(
            "Don't know how to convert python type {}.{} to java"
            .format(py_type.__module__, py_type.__name__))


class Visitor(ast.NodeVisitor):
    '''Converts python ast nodes into a java string'''

    def __init__(self,
                 reql_vars=frozenset("r"),
                 out=None,
                 type_=None,
                 is_def=False,
                 smart_bracket=True,
    ):
        self.out = StringIO() if out is None else out
        self.reql_vars = reql_vars
        self.type = py_to_java_type(type_)
        self._type = type_
        self.is_def = is_def
        self.smart_bracket = smart_bracket
        super(Visitor, self).__init__()
        self.write = self.out.write

    def skip(self, message, *args, **kwargs):
        raise RuntimeError(message, *args, **kwargs)

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
        escape_string(s, self.out)

    def cast_null(self, arg, cast='ReqlExpr'):
        '''Emits a cast to (ReqlExpr) if the node represents null'''
        if (type(arg) == ast.Name and arg.id == 'null') or \
           (type(arg) == ast.NameConstant and arg.value == "None"):
            self.write("(")
            self.write(cast)
            self.write(") ")
        self.visit(arg)

    def wrap(self, *args):
        for arg in args:
            if isinstance(arg, str):
                self.write(arg)
            elif isinstance(arg, ast.AST):
                self.visit(arg)
            else:
                raise Exception("Bad argument to wrap")

    def to_args(self, args, optargs=[]):
        self.write("(")
        if args:
            self.cast_null(args[0])
        for arg in args[1:]:
            self.write(', ')
            self.cast_null(arg)
        self.write(")")
        for optarg in optargs:
            self.write(".optArg(")
            self.to_str(optarg.arg)
            self.write(", ")
            self.visit(optarg.value)
            self.write(")")

    def generic_visit(self, node):
        logger.error("While translating: %s", ast.dump(node))
        logger.error("Got as far as: %s", ''.join(self.out))
        raise RuntimeError("Don't know what this thing is: " + str(type(node)))

    def visit_Assign(self, node):
        if len(node.targets) != 1:
            RuntimeError("We only support assigning to one variable")
        self.write(self.type + " ")
        self.write(node.targets[0].id)
        self.write(" = (")
        self.write(self.type)
        self.write(") (")
        if node.is_reql:
            ReQLVisitor(self.reql_vars,
                        out=self.out,
                        type_=self.type,
                        is_def=True,
                        ).visit(node.value)
        else:
            self.visit(node.value)

        self.write(");")

    def visit_Str(self, node):
        self.to_str(node.s)

    def visit_Bytes(self, node, skip_prefix=False, skip_suffix=False):
        if not skip_prefix:
            self.write("new byte[]{")
        for i, byte in enumerate(node.s):
            if i > 0:
                self.write(", ")
            # Java bytes are signed :(
            if byte > 127:
                self.write(str(-(256 - byte)))
            else:
                self.write(str(byte))
        if not skip_suffix:
            self.write("}")
        else:
            self.write(", ")

    def visit_Name(self, node):
        name = node.id
        if name == 'frozenset':
            self.skip("can't convert frozensets to GroupedData yet")
        if name in JAVA_KEYWORDS or \
           name in OBJECT_METHODS:
            name += '_'
        self.write({
            'True': 'true',
            'False': 'false',
            'None': 'null',
            'nil': 'null',
            }.get(name, name))

    def visit_arg(self, node):
        self.write(node.arg)

    def visit_NameConstant(self, node):
        if node.value is None:
            self.write("null")
        elif node.value is True:
            self.write("true")
        elif node.value is False:
            self.write("false")
        else:
            raise RuntimeError(
                "Don't know NameConstant with value %s" % node.value)

    def visit_Attribute(self, node, emit_parens=True):
        skip_parent = False
        if attr_matches("r.ast", node):
            # The java driver doesn't have that namespace, so we skip
            # the `r.` prefix and create an ast class member in the
            # test file. So stuff like `r.ast.rqlTzinfo(...)` converts
            # to `ast.rqlTzinfo(...)`
            skip_parent = True

        if not skip_parent:
            self.visit(node.value)
            self.write(".")
        self.write(dromedary(node.attr))

    def visit_Num(self, node):
        self.write(repr(node.n))
        if not isinstance(node.n, float):
            if node.n > 9223372036854775807 or node.n < -9223372036854775808:
                self.write(".0")
            else:
                self.write("L")

    def visit_Index(self, node):
        self.visit(node.value)

    def skip_if_arity_check(self, node):
        '''Throws out tests for arity'''
        rgx = re.compile('.*([Ee]xpect(ed|s)|Got) .* argument')
        try:
            if node.func.id == 'err' and rgx.match(node.args[1].s):
                self.skip("arity checks done by java type system")
        except (AttributeError, TypeError):
            pass

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
        self.skip_if_arity_check(node)
        if self.convert_if_string_encode(node):
            return
        if type(node.func) == ast.Attribute and node.func.attr == 'error':
            # This weird special case is because sometimes the tests
            # use r.error and sometimes they use r.error(). The java
            # driver only supports r.error(). Since we're coming in
            # from a call here, we have to prevent visit_Attribute
            # from emitting the parents on an r.error for us.
            self.visit_Attribute(node.func, emit_parens=False)
        else:
            self.visit(node.func)
        self.to_args(node.args, node.keywords)

    def visit_Dict(self, node):
        self.write("r.hashMap(")
        if len(node.keys) > 0:
            self.visit(node.keys[0])
            self.write(", ")
            self.visit(node.values[0])
        for k, v in zip(node.keys[1:], node.values[1:]):
            self.write(").with(")
            self.visit(k)
            self.write(", ")
            self.visit(v)
        self.write(")")

    def visit_List(self, node):
        self.write("r.array(")
        self.join(", ", node.elts)
        self.write(")")

    def visit_Tuple(self, node):
        self.visit_List(node)

    def visit_Lambda(self, node):
        if len(node.args.args) == 1:
            self.visit(node.args.args[0])
        else:
            self.to_args(node.args.args)
        self.write(" -> ")
        self.visit(node.body)

    def visit_Subscript(self, node):
        if node.slice is None or type(node.slice.value) != ast.Num:
            logger.error("While doing: %s", ast.dump(node))
            raise RuntimeError("Only integers subscript can be converted."
                               " Got %s" % node.slice.value.s)
        self.visit(node.value)
        self.write(".get(")
        self.write(str(node.slice.value.n))
        self.write(")")

    def visit_ListComp(self, node):
        gen = node.generators[0]

        if type(gen.iter) == ast.Call and gen.iter.func.id.endswith('range'):
            # This is really a special-case hacking of [... for i in
            # range(i)] comprehensions that are used in the polyglot
            # tests sometimes. It won't handle translating arbitrary
            # comprehensions to Java streams.
            self.write("LongStream.range(")
            if len(gen.iter.args) == 1:
                self.write("0, ")
                self.visit(gen.iter.args[0])
            elif len(gen.iter.args) == 2:
                self.visit(gen.iter.args[0])
                self.write(", ")
                self.visit(gen.iter.args[1])
            self.write(").boxed()")
        else:
            # Somebody came up with a creative new use for
            # comprehensions in the test suite...
            raise RuntimeError(
                "ListComp hack couldn't handle: ", ast.dump(node))
        self.write(".map(")
        self.visit(gen.target)
        self.write(" -> ")
        self.visit(node.elt)
        self.write(").collect(Collectors.toList())")

    def visit_UnaryOp(self, node):
        opMap = {
            ast.USub: "-",
            ast.Not: "!",
            ast.UAdd: "+",
            ast.Invert: "~",
        }
        self.write(opMap[type(node.op)])
        self.visit(node.operand)

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


class ReQLVisitor(Visitor):
    '''Mostly the same as the Visitor, but converts some
    reql-specific stuff. This should only be invoked on an expression
    if it's already known to return true from is_reql'''


    def prefix(self, func_name, left, right):
        self.write("r.")
        self.write(func_name)
        self.write("(")
        self.visit(left)
        self.write(", ")
        self.visit(right)
        self.write(")")

    def infix(self, func_name, left, right):
        self.visit(left)
        self.write(".")
        self.write(func_name)
        self.write("(")
        self.visit(right)
        self.write(")")

    def is_not_reql(self, node):
        if type(node) in (ast.Name, ast.NameConstant,
                          ast.Num, ast.Str, ast.Dict, ast.List):
            return True
        else:
            return False

    def visit_Subscript(self, node):
        self.visit(node.value)
        if type(node.slice) == ast.Index:
            # Syntax like a[2] or a["b"]
            if self.smart_bracket and type(node.slice.value) == ast.Str:
                self.write(".g(")
            elif self.smart_bracket and type(node.slice.value) == ast.Num:
                self.write(".nth(")
            else:
                self.write(".bracket(")
            self.visit(node.slice.value)
            self.write(")")
        elif type(node.slice) == ast.Slice:
            # Syntax like a[1:2] or a[:2]
            self.write(".slice(")
            lower, upper, rclosed = self.get_slice_bounds(node.slice)
            self.write(str(lower))
            self.write(", ")
            self.write(str(upper))
            self.write(")")
            if rclosed:
                self.write('.optArg("right_bound", "closed")')
        else:
            raise RuntimeError("No translation for ExtSlice")

    def get_slice_bounds(self, slc):
        '''Used to extract bounds when using bracket slice
        syntax. This is more complicated since Python3 parses -1 as
        UnaryOp(op=USub, operand=Num(1)) instead of Num(-1) like
        Python2 does'''
        if not slc:
            return 0, -1, True

        def get_bound(bound, default):
            if bound is None:
                return default
            elif type(bound) == ast.UnaryOp and type(bound.op) == ast.USub:
                return -bound.operand.n
            elif type(bound) == ast.Num:
                return bound.n
            else:
                raise RuntimeError(
                    "Not handling bound: %s" % ast.dump(bound))

        right_closed = slc.upper is None

        return get_bound(slc.lower, 0), get_bound(slc.upper, -1), right_closed

    def visit_Attribute(self, node, emit_parens=True):
        is_toplevel_constant = False
        if attr_matches("r.row", node):
            self.skip("Java driver doesn't support r.row")
        elif is_name("r", node.value) and node.attr in self.TOPLEVEL_CONSTANTS:
            # Python has r.minval, r.saturday etc. We need to emit
            # r.minval() and r.saturday()
            is_toplevel_constant = True
        python_clashes = {
            # These are underscored in the python driver to avoid
            # keywords, but they aren't java keywords so we convert
            # them back.
            'or_': 'or',
            'and_': 'and',
            'not_': 'not',
        }
        method_aliases = {dromedary(k): v for k, v in METHOD_ALIASES.items()}
        self.visit(node.value)
        self.write(".")
        initial = python_clashes.get(
            node.attr, dromedary(node.attr))
        initial = method_aliases.get(initial, initial)
        self.write(initial)
        if initial in JAVA_KEYWORDS | OBJECT_METHODS:
            self.write('_')
        if emit_parens and is_toplevel_constant:
            self.write('()')

    def visit_UnaryOp(self, node):
        if type(node.op) == ast.Invert:
            self.visit(node.operand)
            self.write(".not()")
        else:
            super(ReQLVisitor, self).visit_UnaryOp(node)

    def visit_Call(self, node):
        # We call the superclass first, so if it's going to fail
        # because of r.row or other things it fails first, rather than
        # hitting the checks in this method. Since everything is
        # written to a stringIO object not directly to a file, if we
        # bail out afterwards it's still ok
        super_result = super(ReQLVisitor, self).visit_Call(node)

        # r.for_each(1) etc should be skipped
        if (attr_equals(node.func, "attr", "for_each") and
           type(node.args[0]) != ast.Lambda):
            self.skip("the java driver doesn't allow "
                      "non-function arguments to forEach")
        # map(1) should be skipped
        elif attr_equals(node.func, "attr", "map"):
            def check(node):
                if type(node) == ast.Lambda:
                    return True
                elif hasattr(node, "func") and attr_matches("r.js", node.func):
                    return True
                elif type(node) == ast.Dict:
                    return True
                elif type(node) == ast.Name:
                    # The assumption is that if you're passing a
                    # variable to map, it's at least potentially a
                    # function. This may be misguided
                    return True
                else:
                    return False
            if not check(node.args[-1]):
                self.skip("the java driver statically checks that "
                          "map contains a function argument")
        else:
            return super_result


def attr_equals(node, attr, value):
    '''Helper for digging into ast nodes'''
    return hasattr(node, attr) and getattr(node, attr) == value
