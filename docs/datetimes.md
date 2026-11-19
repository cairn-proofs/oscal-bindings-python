# Datetimes

Each OSCAL date-time field (`metadata.last_modified`, `result.start`, ...) is an `OscalDateTime`: a `datetime` subclass, so `isinstance(value, datetime)` holds and code that reads it as a `datetime` keeps working. OSCAL allows any number of fraction digits, and Python's `datetime` keeps six, so `OscalDateTime` also keeps the digits of the text and writes them again:

```python
from oscal_bindings import OscalDateTime, parse_oscal

doc = parse_oscal(text)                    # last-modified: "2024-01-02T03:04:05.1234567Z"
last = doc.root.catalog.metadata.last_modified
last.microsecond                           # 123456, as a datetime has it
last.fraction                              # "1234567", every digit of the text
last.to_string()                           # "2024-01-02T03:04:05.1234567Z"
```

Equality, order, and hash count every digit: `.1234567` and `.1234568` are different instants, and `.120` equals `.12`. Arithmetic is where the extra digits can fall away:

- `value + timedelta` and `value - timedelta` keep them, and so do `replace` and `astimezone`.
- `value - other` is a `timedelta`, which holds microseconds, so two values that differ only after the sixth digit have a difference of zero. Compare them with `==`, `<`, and `>`.
- `timestamp()`, `strftime()`, and `isoformat(timespec=...)` use the microsecond value only.

The class docstring lists each method, and the API documentation shows it.
