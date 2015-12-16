Transpiler from python to JavaScript, Ruby, and Java for reql queries

Right now requires python3, but it's not critical

## Example:

```bash
$ python3 ./multireql.py 'r.table("foo").get_all("foo", index="crabs").filter(lambda x: x > (3+2)).map(r.range(), lambda x,y: x + y)'
```

Python:

```py
r.table("foo").get_all("foo", index="crabs").filter(lambda x: x > (3+2)).map(r.range(), lambda x,y: x + y)
```

Ruby:

```rb
r.table('foo').get_all('foo', index: 'crabs').filter{|x| x > (3 + 2)}.map(r.range){|x, y| (x + y)}
```

JavaScript:

```js
r.table('foo').getAll('foo', {index: 'crabs'}).filter(function(x) { return (x).gt(3 + 2) }).map(r.range(), function(x, y) { return x.add(y) })
```

Java:

```java
r.table("foo").getAll("foo").optArg("index", "crabs").filter(x -> (x).gt(3L + 2L)).map(r.range(), (x, y) -> x.add(y))
```

### Limitations:

1. Doesn't currently do assignment statements
2. Works only in python3
3. Emits perhaps more parens than necessary to ensure precedence is correct
4. Doesn't handle exotic stuff like list comprehensions, binary output etc.

### To do:

Right now, the transpilers support being passed a set of variable names that are considered to be 'reql'. This is so we can detect when a binary operator is being used on a reql expression, or whether it represents a native binary operation. For example, if we have the expression `tbl.filter(lambda x: x + 2)`, without giving it the context `{'r', 'tbl'}` it will assume `tbl` is a normal python value, and that the lambda passed to filter is operating on normal python values, and will not convert `x + 2` into `x.add(2)` in the java and js outputs (it will accidentally be right for the ruby output).

In order to support this, the context needs to be collected as a test file is transpiled, accumulating variable definitions that are known to be reql queries. This is done in the Java python test transpiler in the official rethinkdb repo, but for simplicity was left out here.

### Files

- `./multireql.py`: command line wrapper. Has some (currently) unexposed functions for seeing how well the transpiler does against hand-written polyglot tests
- `./conversion_utils.py`: Utility functions
- `./{java,js,ruby}_converter.py` transpilers for each language
- `./astdump.py` a useful script to see how python parses a statement
- `./parsePolyglot.py` copied from rethinkdb source, parses polyglot yaml files. Used by analysis functions in `multireql.py`
