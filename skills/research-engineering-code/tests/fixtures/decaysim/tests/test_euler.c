#include <math.h>
#include <stdio.h>

#include "euler.h"

static int failures = 0;

static void check_close(const char *name, double actual, double expected) {
    if (fabs(actual - expected) > 1e-12) {
        printf("FAIL %s: got %.17g, expected %.17g\n", name, actual, expected);
        failures++;
    }
}

static void test_one_step_shrinks_by_k_dt(void) {
    check_close("one_step_shrinks_by_k_dt", euler_step(2.0, 0.5, 0.1), 1.9);
}

static void test_zero_rate_keeps_value(void) {
    double y[4];
    integrate(3.0, 0.0, 0.1, 3, y);
    check_close("zero_rate_keeps_value", y[3], 3.0);
}

int main(void) {
    test_one_step_shrinks_by_k_dt();
    test_zero_rate_keeps_value();
    if (failures == 0) {
        printf("C tests OK\n");
    }
    return failures == 0 ? 0 : 1;
}
