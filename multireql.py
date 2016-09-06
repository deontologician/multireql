#!/usr/bin/env python
from __future__ import print_function

import sys
import ast
import os
from collections import Counter

import conversion_utils
import ruby_converter
import java_converter
import js_converter
from parsePolyglot import parse_yaml

DEFAULT_TEST_DIR = '../../test/rql_test/src'


def main():
    if len(sys.argv) > 1:
        snippet = sys.argv[1]
    else:
        snippet = sys.stdin.read()
    parsed_snippet = parse_snippet(snippet, exit_on_fail=True)

    print("Python:")
    print(" - ", snippet)

    print("Ruby:")
    ruby_snippet = transpile(parsed_snippet, 'rb')
    print(" - ", ruby_snippet)

    print()
    print("JavaScript:")
    js_snippet = transpile(parsed_snippet, 'js')
    print(" - ", js_snippet)

    print()
    print("Java:")
    java_snippet = transpile(parsed_snippet, 'java')
    print(" - ", java_snippet)


def transpile(snippet, lang):
    try:
        if lang == 'rb':
            return transpile_snippet(snippet, ruby_converter)
        elif lang == 'js':
            return transpile_snippet(snippet, js_converter)
        elif lang == 'java':
            return transpile_snippet(snippet, java_converter)
    except Exception as e:
        print(e)
        return None


def transpile_snippet(parsed_snippet, converter):
    return converter.Visitor().convert(parsed_snippet)


def parse_snippet(snippet, exit_on_fail=False):
    try:
        parsed = ast.parse(snippet, mode='eval').body
        conversion_utils.add_is_reql_flags(parsed)
        return parsed
    except Exception as e:
        print(e)
        if exit_on_fail:
            exit(0)
        else:
            return None


def all_yaml_tests(test_dir=DEFAULT_TEST_DIR):
    '''Generator for the full paths of all non-excluded yaml tests'''
    for root, dirs, files in os.walk(test_dir):
        for f in files:
            path = os.path.relpath(os.path.join(root, f), os.getcwd())
            if os.path.splitext(path)[1] == '.yaml':
                yield parse_yaml(open(path).read())


def tests_in_file(test_file):
    for test in test_file['tests']:
        yield test


def every_test(test_dir=DEFAULT_TEST_DIR):
    for testfile in all_yaml_tests(test_dir):
        for test in tests_in_file(testfile):
            yield test


def add_signature(counter, test):
    counter[frozenset(test.keys())] += 1
    return counter


def equal_or_contained_in(first, second):
    if first == second:
        return True
    if isinstance(second, list):
        return first in second
    else:
        return False


def check_ruby(results, test):
    if 'rb' in test and 'cd' in test:
        parsed = parse_snippet(test['cd'])
        if parsed is None:
            results['syntax_error'].append(test['cd'])
            return results
        transpiled = transpile(parsed, 'rb')
        if transpiled is None:
            results['failed_transpile'].append(test['cd'])
            return results
        if equal_or_contained_in(transpiled, test['rb']):
            results['correct'].append({
                'generic': test['cd'],
                'transpiled': transpiled,
                'custom': test['rb'],
            })
        elif 'r.row' in transpiled:
            results['r.row'].append({
                'generic': test['cd'],
                'transpiled': transpiled,
                'custom': test['rb']
            })
        else:
            results['incorrect'].append({
                'custom': test['rb'],
                'transpiled': transpiled,
                'generic': test['cd'],
            })
    return results


def check_if_python_works(results, test):
    if 'rb' in test and 'py' in test and 'cd' not in test:
        parsed = parse_snippet(test['py'])
        if parsed is None:
            results['syntax_error'].append({
                'python': test['py'],
                'ruby': test['rb'],
            })
            return results
        transpiled = transpile(parsed, 'rb')
        if transpiled is None:
            results['failed_transpile'].append({
                'python': test['py'],
                'ruby': test['rb'],
            })
            return results
        if transpiled == test['rb']:
            results['correct'].append({
                'python': test['py'],
                'ruby': test['rb'],
            })
        elif 'r.row' in transpiled:
            results['r.row'].append({
                'python': test['py'],
                'handcrafted_ruby': test['rb'],
                'transpiled_ruby': transpiled,
            })
        else:
            results['incorrect'].append({
                'python': test['py'],
                'handcrafted_ruby': test['rb'],
                'transpiled_ruby': transpiled,
            })
    return results


def count_key_signatures():
    return reduce_tests(add_signature, Counter())


def count_bad_ruby_transpiles():
    return reduce_tests(check_ruby, {
        'correct': [],
        'incorrect': [],
        'syntax_error': [],
        'failed_transpile': [],
        'r.row': [],
    })


def count_python_replacements():
    return reduce_tests(check_if_python_works, {
        'correct': [],
        'incorrect': [],
        'syntax_error': [],
        'failed_transpile': [],
        'r.row': [],
    })


def reduce_tests(func, initial):
    return reduce(func, every_test(), initial)


if __name__ == "__main__":
    main()
