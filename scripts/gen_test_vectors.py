#!/usr/bin/env python3
"""
Generate test images and golden reference values for the CDA 4253 final project.

The golden model is computed in pure integer Python directly from the provided
.mem files (w1.mem, b1.mem, w2.mem, b2.mem), i.e. exactly the data your FPGA
loads. Your hardware must reproduce these numbers bit for bit.

Images come from the MNIST test set, binarized with the same loader the model
was trained with (threshold 0.5), so this script needs the course repository and
its Python environment (torch + torchvision):

    git clone https://github.com/KasraAhmadi/MNIST_FPGA
    python scripts/gen_test_vectors.py --repo MNIST_FPGA --n 256 --out sim_data

Outputs (in --out):
    images_784.mem            one line per image, 784 binary digits ($readmemb into
                              reg [783:0] rom [0:N-1]); pixel i is bit i
    images_1bit.mem           one pixel per line, address = 784*img + i
    labels.mem                true digit per image (hex)
    golden.csv                image, label, golden prediction, logits z0..z9
    golden_img0_hidden.mem    64 hidden values h_j of image 0 (32-bit hex)
    golden_img0_logits.mem    10 logits z_k of image 0 (32-bit hex, two's complement)
"""

import argparse
import os
import sys

HIDDEN, INPUTS, OUTPUTS = 64, 784, 10


def read_mem(path, nbits):
    """Read a $readmemh file of two's-complement values into Python ints."""
    vals = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            v = int(line, 16)
            if v >= 1 << (nbits - 1):
                v -= 1 << nbits
            vals.append(v)
    return vals


def hex32(v):
    return format(v & 0xFFFFFFFF, "08x")


def golden(x, W1, b1, W2, b2):
    """Pure-integer inference, identical to what the FPGA computes."""
    h = []
    for j in range(HIDDEN):
        row = W1[j * INPUTS:(j + 1) * INPUTS]
        acc = b1[j] + sum(w for w, px in zip(row, x) if px)   # conditional add
        h.append(max(acc, 0))                                  # ReLU
    z = []
    for k in range(OUTPUTS):
        row = W2[k * HIDDEN:(k + 1) * HIDDEN]
        z.append(b2[k] + sum(w * hj for w, hj in zip(row, h)))
    pred = max(range(OUTPUTS), key=lambda k: (z[k], -k))       # first max wins ties
    return h, z, pred


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--repo", required=True, help="path to the cloned MNIST_FPGA repository")
    p.add_argument("--n", type=int, default=256, help="number of test images to export")
    p.add_argument("--start", type=int, default=0, help="first MNIST test image index")
    p.add_argument("--out", default="sim_data", help="output directory")
    p.add_argument("--data-dir", default="./data", help="where MNIST is downloaded")
    args = p.parse_args()

    exp = os.path.join(args.repo, "fpga_export")
    W1 = read_mem(os.path.join(exp, "w1.mem"), 8)
    b1 = read_mem(os.path.join(exp, "b1.mem"), 32)
    W2 = read_mem(os.path.join(exp, "w2.mem"), 8)
    b2 = read_mem(os.path.join(exp, "b2.mem"), 32)
    assert len(W1) == HIDDEN * INPUTS and len(W2) == OUTPUTS * HIDDEN, "unexpected .mem sizes"

    sys.path.insert(0, os.path.abspath(args.repo))
    try:
        from train_mnist_fpga import load_binarized_mnist
    except ImportError as e:
        sys.exit(f"Could not import the repository's data loader ({e}).\n"
                 "Install its requirements first:  pip install torch torchvision")

    _, _, xte, yte = load_binarized_mnist(args.data_dir, 0.5)
    xs = xte[args.start:args.start + args.n].int().tolist()
    ys = yte[args.start:args.start + args.n].tolist()

    os.makedirs(args.out, exist_ok=True)
    correct = 0
    with open(os.path.join(args.out, "images_784.mem"), "w") as f784, \
         open(os.path.join(args.out, "images_1bit.mem"), "w") as f1, \
         open(os.path.join(args.out, "labels.mem"), "w") as flab, \
         open(os.path.join(args.out, "golden.csv"), "w") as fcsv:
        fcsv.write("image,label,pred," + ",".join(f"z{k}" for k in range(OUTPUTS)) + "\n")
        for n, (x, y) in enumerate(zip(xs, ys)):
            # Leftmost character is the MSB, so reverse to make pixel i == bit i.
            f784.write("".join(str(px) for px in reversed(x)) + "\n")
            f1.write("".join(f"{px}\n" for px in x))
            flab.write(f"{y:x}\n")
            h, z, pred = golden(x, W1, b1, W2, b2)
            correct += pred == y
            fcsv.write(f"{n},{y},{pred}," + ",".join(map(str, z)) + "\n")
            if n == 0:
                with open(os.path.join(args.out, "golden_img0_hidden.mem"), "w") as fh:
                    fh.write("".join(hex32(v) + "\n" for v in h))
                with open(os.path.join(args.out, "golden_img0_logits.mem"), "w") as fz:
                    fz.write("".join(hex32(v) + "\n" for v in z))

    print(f"Wrote {len(xs)} images to {os.path.abspath(args.out)}")
    print(f"Golden-model accuracy on these images: {correct}/{len(xs)} "
          f"= {100.0 * correct / len(xs):.2f}%")
    print("Your hardware must produce the same prediction as golden.csv for every image.")


if __name__ == "__main__":
    main()
