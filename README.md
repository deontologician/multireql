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

Limitations:

1. Doesn't currently do assignment statements
2. Works only in python3
3. Emits perhaps more parens than necessary to ensure precedence is correct
