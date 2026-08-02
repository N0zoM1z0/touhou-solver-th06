# Physical counterexample corpus

Each JSON file is one minimized-enough runtime state that reproduces an
understood integrated solver failure. The generic test loader replays every
file; adding another physical failure should normally add data here rather
than another long snapshot fixture to a Python test.

Algorithm unit tests still belong in Python. This corpus is only for concrete
runtime states whose regression contract is understood and stable.
