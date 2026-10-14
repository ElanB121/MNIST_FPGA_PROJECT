#!/usr/bin/env python3
"""
Split w1.mem / b1.mem (and w2.mem / b2.mem) into P banks, one per processing
element (PE), so P neurons can each read one weight per clock cycle.

Bank p holds the neurons p, p+P, p+2P, ...  Inside a bank the rows are stored
back to back:  address = (neuron // P) * row_length + input_index.
Banks are padded with zero rows so they all have the same depth.

    python scripts/split_weights.py --repo MNIST_FPGA --p 4 --out banks

Writes w1_bank{p}.mem, b1_bank{p}.mem, w2_bank{p}.mem, b2_bank{p}.mem.
Pure Python, no packages needed.
"""

import argparse
import math
import os

LAYERS = [  # (name, weight file, bias file, neurons, inputs)
    ("1", "w1.mem", "b1.mem", 64, 784),
    ("2", "w2.mem", "b2.mem", 10, 64),
]


def read_lines(path):
    with open(path) as f:
        return [l.strip() for l in f if l.strip()]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", required=True, help="path to the cloned MNIST_FPGA repository")
    ap.add_argument("--p", type=int, required=True, help="number of parallel neurons (PEs)")
    ap.add_argument("--out", default="banks")
    args = ap.parse_args()

    exp = os.path.join(args.repo, "fpga_export")
    os.makedirs(args.out, exist_ok=True)
    for name, wfile, bfile, neurons, inputs in LAYERS:
        w = read_lines(os.path.join(exp, wfile))
        b = read_lines(os.path.join(exp, bfile))
        rows = math.ceil(neurons / args.p)
        for p in range(args.p):
            with open(os.path.join(args.out, f"w{name}_bank{p}.mem"), "w") as fw, \
                 open(os.path.join(args.out, f"b{name}_bank{p}.mem"), "w") as fb:
                for r in range(rows):
                    n = r * args.p + p
                    if n < neurons:
                        fw.write("\n".join(w[n * inputs:(n + 1) * inputs]) + "\n")
                        fb.write(b[n] + "\n")
                    else:                       # padding row: unused neuron
                        fw.write("00\n" * inputs)
                        fb.write("00000000\n")
        print(f"Layer {name}: {neurons} neurons -> {args.p} banks x {rows} rows "
              f"(depth {rows * inputs} weights per bank)")


if __name__ == "__main__":
    main()
