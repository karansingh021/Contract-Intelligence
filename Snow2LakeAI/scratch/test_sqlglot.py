import sqlglot

raw1 = "-- Just a comment"
raw2 = "  -- Another comment"

try:
    print(sqlglot.parse(raw1))
except Exception as e:
    print("Error 1:", e)

try:
    print(sqlglot.parse(raw2))
except Exception as e:
    print("Error 2:", e)
