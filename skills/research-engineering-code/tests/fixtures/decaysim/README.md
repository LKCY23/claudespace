# decaysim

Integrates the decay equation dy/dt = -k y, y(0) = 1, with the explicit Euler
method in C, then compares the final value with the exact solution exp(-k t)
in Python.

    make test                                  # C and Python unit tests
    ./run.sh out --k 1.0 --dt 0.1 --steps 10   # writes out/trajectory.csv and out/summary.json

`summary.json` holds `final_t`, `final_y`, `exact_y` and `abs_error`.
