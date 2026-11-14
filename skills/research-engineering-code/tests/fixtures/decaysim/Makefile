CC ?= cc
CFLAGS ?= -O2 -Wall -Wextra -std=c11

build: build/decay

build/decay: sim/main.c sim/euler.c sim/euler.h
	mkdir -p build
	$(CC) $(CFLAGS) -o $@ sim/main.c sim/euler.c -lm

build/test_euler: tests/test_euler.c sim/euler.c sim/euler.h
	mkdir -p build
	$(CC) $(CFLAGS) -Isim -o $@ tests/test_euler.c sim/euler.c -lm

test: build/test_euler
	build/test_euler
	python3 -m unittest discover -s tests -p 'test_*.py'

clean:
	rm -rf build

.PHONY: build test clean
