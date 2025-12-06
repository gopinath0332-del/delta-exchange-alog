# Log File Format Comparison

## Before Fix (with ANSI color codes)

```
[2025-12-06 17:51:31.261] [INFO    ] [__main__                      ] [2m2025-12-06T12:21:31.261122Z[0m [[32m[1minfo     [0m] [1mDelta Exchange Trading Platform[0m [[0m[1m[34m__main__[0m][0m [36menvironment[0m=[35mtestnet[0m [36mversion[0m=[35m0.1.0[0m
[2025-12-06 17:51:31.381] [INFO    ] [__main__                      ] [2m2025-12-06T12:21:31.381351Z[0m [[32m[1minfo     [0m] [1mFetching historical data      [0m [[0m[1m[34m__main__[0m][0m [36mdays[0m=[35m30[0m [36msymbol[0m=[35mBTCUSD[0m [36mtimeframe[0m=[35m1h[0m
```

**Issues:**

- ANSI escape sequences (`[2m`, `[32m`, `[0m`, etc.) make logs unreadable
- Difficult to parse or search through logs
- Cannot be properly displayed in most text editors or log viewers

## After Fix (clean, human-readable)

```
[2025-12-06 17:58:25.273] [INFO    ] [__main__                      ] 2025-12-06T12:28:25.272980Z [info     ] Delta Exchange Trading Platform [__main__] environment=testnet version=0.1.0
[2025-12-06 17:58:25.280] [ERROR   ] [__main__                      ] 2025-12-06T12:28:25.278373Z [error    ] Unexpected error               [__main__] error="No module named 'delta_rest_client'"
```

**Benefits:**

- Clean, readable text without escape sequences
- Easy to search and parse
- Works perfectly in any text editor or log viewer
- Maintains all important information (timestamp, level, logger, message, context)

## Log Format Structure

Each log line contains:

1. **File Timestamp**: `[2025-12-06 17:58:25.273]` - When the log was written to file
2. **Log Level**: `[INFO    ]` - Severity level (aligned to 8 characters)
3. **Logger Name**: `[__main__                      ]` - Module/component name (aligned to 30 characters)
4. **Structlog Output**: The formatted message from structlog with:
   - ISO timestamp
   - Log level
   - Event message
   - Logger name
   - Context key-value pairs

## Example Log Entries

### Info Message

```
[2025-12-06 17:57:19.644] [INFO    ] [trading.strategy              ] 2025-12-06T12:27:19.644616Z [info     ] Starting: Place Order          [trading.strategy] price=45000 quantity=0.5 symbol=BTCUSD
```

### Warning Message

```
[2025-12-06 17:57:19.644] [WARNING ] [__main__                      ] 2025-12-06T12:27:19.644223Z [warning  ] Warning message                [__main__] alert='check this' threshold=90
```

### Error with Exception

```
[2025-12-06 17:57:19.646] [ERROR   ] [__main__                      ] 2025-12-06T12:27:19.645333Z [error    ] Division error occurred        [__main__] dividend=10 divisor=0 operation=calculate
Traceback (most recent call last):
  File "/Users/admin/Projects/delta-exchange-alog/core/logger.py", line 303, in <module>
    result = 10 / 0
             ~~~^~~
ZeroDivisionError: division by zero
```

## Technical Implementation

The fix was implemented in the `HumanReadableFormatter` class:

```python
# ANSI escape sequence pattern for stripping colors
import re
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

def format(self, record: logging.LogRecord) -> str:
    # Get the message and strip ANSI color codes
    message = record.getMessage()
    if not self.use_colors:
        message = self.ANSI_ESCAPE.sub('', message)
    # ... rest of formatting
```

This ensures that:

- Console output can still have colors (when outputting to a terminal)
- File output is always clean text without color codes
- The same formatter handles both cases efficiently
