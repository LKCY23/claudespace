#ifndef EULER_H
#define EULER_H

/* One explicit Euler step of dy/dt = -k y. */
double euler_step(double y, double k, double dt);

/* Integrate from y0 for n_steps steps; writes n_steps + 1 values into out. */
void integrate(double y0, double k, double dt, int n_steps, double *out);

#endif
