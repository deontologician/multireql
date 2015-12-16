import re
import ast


def camel(varname):
    'CamelCase'
    if re.match(r'[A-Z][A-Z0-9_]*$|[a-z][a-z0-9_]*$', varname):
        # if snake-case (upper or lower) camelize it
        suffix = "_" if varname.endswith('_') else ""
        return ''.join(x.title() for x in varname.split('_')) + suffix
    else:
        # if already mixed case, just capitalize the first letter
        return varname[0].upper() + varname[1:]


def dromedary(varname):
    'dromedaryCase'
    if re.match(r'[A-Z][A-Z0-9_]*$|[a-z][a-z0-9_]*$', varname):
        chunks = varname.split('_')
        suffix = "_" if varname.endswith('_') else ""
        return (chunks[0].lower() +
                ''.join(x.title() for x in chunks[1:]) +
                suffix)
    else:
        return varname[0].lower() + varname[1:]


def add_is_reql_flags(node, reql_vars=None, passed_to_reql=False):
    IsReql(reql_vars, passed_to_reql).visit(node)


class IsReql(ast.NodeVisitor):
    '''Adds a flag to every node in the tree indicating if it's a reql
    term or not'''
    def __init__(self, reql_vars=None, passed_to_reql=False):
        self.reql_vars = reql_vars or {'r'}
        self.passed_to_reql = passed_to_reql

    def generic_visit(self, node):
        node.is_reql = False

    def visit_Name(self, node):
        node.is_reql = node.id in self.reql_vars

    def visit_Attribute(self, node):
        self.visit(node.value)
        node.is_reql = node.value.is_reql

    def visit_Lambda(self, node):
        node.is_reql = self.passed_to_reql
        if self.passed_to_reql:
            lambda_vars = {n.arg for n in node.args.args}
            IsReql(reql_vars=self.reql_vars | lambda_vars).visit(node.body)
        else:
            IsReql(reql_vars=self.reql_vars).visit(node.body)

    def visit_Call(self, node):
        self.visit(node.func)
        node.is_reql = node.func.is_reql
        if node.is_reql:
            pp = IsReql(self.reql_vars, passed_to_reql=True)
        else:
            pp = self
        for arg in node.args:
            pp.visit(arg)
        for keyword in node.keywords:
            keyword.is_reql = node.is_reql
            pp.visit(keyword.value)

    def visit_Subscript(self, node):
        self.visit(node.value)
        node.is_reql = node.value.is_reql
        if node.is_reql:
            pp = IsReql(self.reql_vars, passed_to_reql=True)
        else:
            pp = self
        pp.visit(node.slice)

    def visit_Index(self, node):
        pp = IsReql(self.reql_vars, passed_to_reql=False)
        pp.visit(node.value)
        node.is_reql = self.passed_to_reql

    def visit_Slice(self, node):
        pp = IsReql(self.reql_vars, passed_to_reql=False)
        if node.lower is not None:
            pp.visit(node.lower)
        if node.step is not None:
            pp.visit(node.step)
        if node.upper is not None:
            pp.visit(node.upper)
        node.is_reql = self.passed_to_reql

    def visit_BinOp(self, node):
        self.visit(node.left)
        self.visit(node.right)
        node.is_reql = (
            type(node.op) != ast.Pow and
            (node.left.is_reql or node.right.is_reql))

    def visit_Compare(self, node):
        self.visit(node.left)
        is_reql = node.left.is_reql
        for comp in node.comparators:
            self.visit(comp)
            is_reql = is_reql or comp.is_reql
        node.is_reql = is_reql

    def visit_UnaryOp(self, node):
        self.visit(node.operand)
        node.is_reql = node.operand.is_reql

    def visit_List(self, node):
        node.is_reql = False
        for elt in node.elts:
            self.visit(elt)

    def visit_Tuple(self, node):
        self.visit_List(node)

    def visit_Dict(self, node):
        node.is_reql = False
        for key, value in zip(node.keys, node.values):
            self.visit(key)
            self.visit(value)
