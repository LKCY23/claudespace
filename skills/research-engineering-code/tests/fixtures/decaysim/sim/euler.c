#include "euler.h"

double euler_step(double y, double k, double dt) {
    return y - k * y * dt;
}

void integrate(double y0, double k, double dt, int n_steps, double *out) {
    out[0] = y0;
    for (int i = 0; i < n_steps; i++) {
        out[i + 1] = euler_step(out[i], k, dt);
    }
}
