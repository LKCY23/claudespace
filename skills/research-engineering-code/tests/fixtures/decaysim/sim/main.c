/* decay: integrate dy/dt = -k y from y(0) = 1 and write t,y rows as CSV. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "euler.h"

static int parse_double(const char *text, double *value) {
    char *end;
    *value = strtod(text, &end);
    return end != text && *end == '\0';
}

int main(int argc, char **argv) {
    double k = 1.0, dt = 0.1;
    int steps = 10;
    const char *out_path = NULL;

    for (int i = 1; i < argc; i++) {
        if (i + 1 >= argc) {
            fprintf(stderr, "missing value for %s\n", argv[i]);
            return 2;
        }
        const char *flag = argv[i], *value = argv[++i];
        double number;
        if (strcmp(flag, "--out") == 0) {
            out_path = value;
        } else if (!parse_double(value, &number)) {
            fprintf(stderr, "not a number for %s: %s\n", flag, value);
            return 2;
        } else if (strcmp(flag, "--k") == 0) {
            k = number;
        } else if (strcmp(flag, "--dt") == 0) {
            dt = number;
        } else if (strcmp(flag, "--steps") == 0) {
            steps = (int)number;
        } else {
            fprintf(stderr, "unknown option: %s\n", flag);
            return 2;
        }
    }
    if (out_path == NULL || dt <= 0.0 || steps < 1) {
        fprintf(stderr, "usage: decay --out PATH [--k K] [--dt DT>0] [--steps N>=1]\n");
        return 2;
    }

    double *y = malloc(sizeof(double) * (size_t)(steps + 1));
    if (y == NULL) {
        fprintf(stderr, "out of memory\n");
        return 1;
    }
    integrate(1.0, k, dt, steps, y);

    FILE *file = fopen(out_path, "w");
    if (file == NULL) {
        fprintf(stderr, "cannot open %s\n", out_path);
        free(y);
        return 1;
    }
    fprintf(file, "t,y\n");
    for (int i = 0; i <= steps; i++) {
        fprintf(file, "%.17g,%.17g\n", i * dt, y[i]);
    }
    fclose(file);
    free(y);
    return 0;
}
