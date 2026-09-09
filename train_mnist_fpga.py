#!/usr/bin/env python3
"""
Train a 3-layer MLP (784 -> hidden -> 10) on BLACK & WHITE (binarized) MNIST
with INT8 weights, for deployment on an FPGA.

Pipeline
--------
1. Load MNIST, binarize every pixel to {0, 1} using a threshold (black=0, white=1).
2. Train the MLP with Quantization-Aware Training (QAT): in every forward pass the
   weights are fake-quantized to signed 8-bit integers (-127..127) using a
   straight-through estimator, so the network learns weights that still work once
   they are real int8.
3. Export int8 weights and int32 biases.
4. Verify with a PURE-INTEGER inference path (no floats anywhere):
        h      = ReLU(W1_int @ x + b1_int)      # x is 0/1, so this is exact integer
        logits = W2_int @ h + b2_int
        pred   = argmax(logits)
   Because the inputs are integers (0/1) and the weights are integers, every value
   here is an exact integer accumulation. This is EXACTLY what the FPGA computes,
   so the "integer" accuracy printed at the end is your real hardware accuracy.

Why this is FPGA-friendly
-------------------------
* Weights: signed int8  -> tiny BRAM/LUT footprint, cheap multipliers.
* Inputs : 1-bit (0/1)  -> the first layer is just a conditional add of weights.
* No floating point, no re-quantization between layers is required for the class
  decision: argmax is invariant to the positive per-layer scale factors, so you
  only need integer multiply-accumulate + ReLU + argmax on the FPGA.

Usage
-----
    python train_mnist_fpga.py                    # sensible defaults, ~97% test acc
    python train_mnist_fpga.py --hidden 32        # smaller hidden layer
    python train_mnist_fpga.py --epochs 30 --lr 5e-4 --threshold 0.5

Everything you might want to tune is an argparse flag (see --help).
"""

import argparse
import json
import os

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, TensorDataset
from torchvision import datasets, transforms


# --------------------------------------------------------------------------- #
#  Quantization-aware training building blocks
# --------------------------------------------------------------------------- #
class _FakeQuantWeight(torch.autograd.Function):
    """Symmetric per-tensor int weight quantization with a straight-through
    estimator. Forward: round weights onto the int grid then scale back to float
    so training 'sees' the quantization error. Backward: gradient passes through
    unchanged (STE)."""

    @staticmethod
    def forward(ctx, w, qmax):
        scale = w.abs().max() / qmax
        scale = torch.clamp(scale, min=1e-8)
        q = torch.round(w / scale).clamp(-qmax, qmax)
        return q * scale  # dequantized -> back in float range

    @staticmethod
    def backward(ctx, grad_output):
        return grad_output, None  # STE: pass gradient straight through


class QuantLinear(nn.Module):
    """A Linear layer whose weights are fake-quantized to signed `bits`-bit
    integers during the forward pass. Bias stays float during training and is
    quantized to int32 only at export time."""

    def __init__(self, in_features, out_features, bits=8):
        super().__init__()
        self.qmax = 2 ** (bits - 1) - 1  # e.g. 127 for 8-bit
        self.weight = nn.Parameter(torch.empty(out_features, in_features))
        self.bias = nn.Parameter(torch.zeros(out_features))
        nn.init.kaiming_uniform_(self.weight, a=5 ** 0.5)

    def forward(self, x):
        w_q = _FakeQuantWeight.apply(self.weight, self.qmax)
        return F.linear(x, w_q, self.bias)


class MLP(nn.Module):
    """784 -> hidden -> 10, ReLU hidden activation, int8 weights."""

    def __init__(self, hidden, bits=8):
        super().__init__()
        self.fc1 = QuantLinear(784, hidden, bits)
        self.fc2 = QuantLinear(hidden, 10, bits)

    def forward(self, x):
        h = F.relu(self.fc1(x))
        return self.fc2(h)


# --------------------------------------------------------------------------- #
#  Data: load MNIST and binarize to black/white {0, 1}
# --------------------------------------------------------------------------- #
def load_binarized_mnist(data_dir, threshold):
    tf = transforms.ToTensor()  # gives float pixels in [0, 1]
    train = datasets.MNIST(data_dir, train=True, download=True, transform=tf)
    test = datasets.MNIST(data_dir, train=False, download=True, transform=tf)

    def to_bw(ds):
        x = ds.data.float() / 255.0            # [N, 28, 28] in [0,1]
        x = (x > threshold).float()            # BINARIZE: black=0, white=1
        x = x.view(x.size(0), 784)             # flatten to [N, 784]
        y = ds.targets.clone()
        return x, y

    xtr, ytr = to_bw(train)
    xte, yte = to_bw(test)
    return xtr, ytr, xte, yte


# --------------------------------------------------------------------------- #
#  Export the trained model to integer arrays
# --------------------------------------------------------------------------- #
def export_int_model(model, bits):
    """Convert the float (fake-quantized) weights to real integer arrays.

    Returns a dict of numpy integer arrays:
        W1_int (int8), b1_int (int32), W2_int (int8), b2_int (int32)
    plus the per-layer float scales (only needed if you ever want to recover
    real-valued logits; NOT needed for argmax on the FPGA).
    """
    qmax = 2 ** (bits - 1) - 1
    W1 = model.fc1.weight.detach().cpu().numpy()
    b1 = model.fc1.bias.detach().cpu().numpy()
    W2 = model.fc2.weight.detach().cpu().numpy()
    b2 = model.fc2.bias.detach().cpu().numpy()

    s1 = np.abs(W1).max() / qmax
    s2 = np.abs(W2).max() / qmax

    W1_int = np.round(W1 / s1).clip(-qmax, qmax).astype(np.int32)
    W2_int = np.round(W2 / s2).clip(-qmax, qmax).astype(np.int32)
    # Bias lives in the same integer domain as its layer's accumulator:
    #   layer1 accumulator ~ (1/s1) * float,  layer2 accumulator ~ 1/(s1*s2) * float
    b1_int = np.round(b1 / s1).astype(np.int32)
    b2_int = np.round(b2 / (s1 * s2)).astype(np.int32)

    return {
        "W1_int": W1_int.astype(np.int8),
        "b1_int": b1_int,
        "W2_int": W2_int.astype(np.int8),
        "b2_int": b2_int,
        "s1": np.float64(s1),
        "s2": np.float64(s2),
    }


def integer_inference(params, X_bin):
    """Pure-integer forward pass, exactly what the FPGA does.
    X_bin: [N, 784] array of 0/1. Returns predicted labels [N]."""
    W1 = params["W1_int"].astype(np.int64)     # [H, 784]
    b1 = params["b1_int"].astype(np.int64)     # [H]
    W2 = params["W2_int"].astype(np.int64)     # [10, H]
    b2 = params["b2_int"].astype(np.int64)     # [10]
    X = X_bin.astype(np.int64)                 # [N, 784], values 0/1

    h = X @ W1.T + b1                          # [N, H]   integer accumulate
    h = np.maximum(h, 0)                       # ReLU
    logits = h @ W2.T + b2                     # [N, 10]  integer accumulate
    preds = logits.argmax(axis=1)
    return preds, h, logits


# --------------------------------------------------------------------------- #
#  Write FPGA-ready hex memory files ($readmemh format)
# --------------------------------------------------------------------------- #
def _twos_complement_hex(value, nbits):
    return format(int(value) & ((1 << nbits) - 1), "0{}x".format(nbits // 4))


def write_mem_files(params, out_dir):
    def dump(name, arr, nbits):
        flat = np.asarray(arr).reshape(-1)
        with open(os.path.join(out_dir, name), "w") as f:
            for v in flat:
                f.write(_twos_complement_hex(v, nbits) + "\n")

    # Weights are stored row-major: for W1 [H,784] the file is neuron0's 784
    # weights, then neuron1's, ...  Adjust the reshape above if your HDL wants
    # a different ordering.
    dump("w1.mem", params["W1_int"], 8)   # int8  -> 2 hex digits
    dump("b1.mem", params["b1_int"], 32)  # int32 -> 8 hex digits
    dump("w2.mem", params["W2_int"], 8)
    dump("b2.mem", params["b2_int"], 32)


# --------------------------------------------------------------------------- #
#  Main
# --------------------------------------------------------------------------- #
def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--hidden", type=int, default=64, help="hidden-layer neurons (hyperparameter)")
    p.add_argument("--bits", type=int, default=8, help="weight bit-width (signed)")
    p.add_argument("--epochs", type=int, default=20)
    p.add_argument("--batch-size", type=int, default=128)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--threshold", type=float, default=0.5,
                   help="binarization threshold in [0,1]; pixel>threshold -> 1 (white)")
    p.add_argument("--data-dir", type=str, default="./data")
    p.add_argument("--out-dir", type=str, default="./fpga_export")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--cpu", action="store_true", help="force CPU even if a GPU is present")
    args = p.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    device = torch.device("cuda" if (torch.cuda.is_available() and not args.cpu) else "cpu")
    os.makedirs(args.out_dir, exist_ok=True)

    print(f"Device: {device}")
    print(f"Config: hidden={args.hidden}  bits={args.bits}  epochs={args.epochs} "
          f"lr={args.lr}  batch={args.batch_size}  threshold={args.threshold}\n")

    # ---- data ----
    xtr, ytr, xte, yte = load_binarized_mnist(args.data_dir, args.threshold)
    print(f"Train: {xtr.shape[0]} images   Test: {xte.shape[0]} images "
          f"(binarized to 0/1)\n")
    train_loader = DataLoader(TensorDataset(xtr, ytr), batch_size=args.batch_size,
                              shuffle=True, num_workers=2, pin_memory=(device.type == "cuda"))

    # ---- model / optim ----
    model = MLP(args.hidden, args.bits).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"Model: 784 -> {args.hidden} -> 10   ({n_params:,} weights+biases)\n")

    xte_d, yte_d = xte.to(device), yte.to(device)

    # ---- train ----
    for epoch in range(1, args.epochs + 1):
        model.train()
        for xb, yb in train_loader:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad()
            loss = F.cross_entropy(model(xb), yb)
            loss.backward()
            opt.step()

        # float (fake-quant) test accuracy after each epoch
        model.eval()
        with torch.no_grad():
            acc = (model(xte_d).argmax(1) == yte_d).float().mean().item()
        print(f"epoch {epoch:2d}/{args.epochs}   test acc (float QAT): {acc*100:5.2f}%")

    # ---- export to integers ----
    params = export_int_model(model, args.bits)

    # ---- authoritative check: PURE-INTEGER inference (this == the FPGA) ----
    preds_tr, _, _ = integer_inference(params, xtr.numpy())
    preds_te, h_te, logits_te = integer_inference(params, xte.numpy())
    int_acc_tr = (preds_tr == ytr.numpy()).mean()
    int_acc_te = (preds_te == yte.numpy()).mean()

    print("\n================= INTEGER (FPGA) RESULTS =================")
    print(f"  Train accuracy (int inference): {int_acc_tr*100:.2f}%")
    print(f"  Test  accuracy (int inference): {int_acc_te*100:.2f}%   <-- FPGA number")
    print(f"  {'PASS >= 90%' if int_acc_te >= 0.90 else 'BELOW 90% - tune hyperparameters'}")

    # ---- hardware sizing info: accumulator bit-widths you need in HDL ----
    h_absmax = int(np.abs(h_te).max())
    logit_absmax = int(np.abs(logits_te).max())
    w1_range = (int(params["W1_int"].min()), int(params["W1_int"].max()))
    w2_range = (int(params["W2_int"].min()), int(params["W2_int"].max()))
    print("\n----------------- FPGA sizing -----------------")
    print(f"  W1 int8 range: {w1_range}   W2 int8 range: {w2_range}")
    print(f"  Max |hidden accumulator|: {h_absmax}  -> needs "
          f"{h_absmax.bit_length()+1}-bit signed")
    print(f"  Max |logit accumulator| : {logit_absmax}  -> needs "
          f"{logit_absmax.bit_length()+1}-bit signed")

    # ---- save everything ----
    npz_path = os.path.join(args.out_dir, "mnist_int8_model.npz")
    np.savez(npz_path, **params)
    write_mem_files(params, args.out_dir)

    # ---- save the PyTorch model itself (so it can be reloaded on a PC) ----
    ckpt_path = os.path.join(args.out_dir, "mnist_mlp.pt")
    torch.save({
        "state_dict": model.state_dict(),   # fc1/fc2 weights + biases
        "hidden": args.hidden,              # needed to rebuild the network
        "bits": args.bits,
        "threshold": args.threshold,        # needed to binarize inputs the same way
        "arch": "784->{}->10".format(args.hidden),
        "test_acc_int": float(int_acc_te),
    }, ckpt_path)
    meta = {
        "hidden": args.hidden, "bits": args.bits, "threshold": args.threshold,
        "epochs": args.epochs, "lr": args.lr, "batch_size": args.batch_size,
        "test_acc_int": float(int_acc_te), "train_acc_int": float(int_acc_tr),
        "hidden_accum_bits": h_absmax.bit_length() + 1,
        "logit_accum_bits": logit_absmax.bit_length() + 1,
    }
    with open(os.path.join(args.out_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    print("\nSaved to", os.path.abspath(args.out_dir))
    print("  mnist_mlp.pt           (PyTorch checkpoint: state_dict + hidden/threshold)")
    print("  mnist_int8_model.npz   (W1_int int8, b1_int int32, W2_int int8, b2_int int32)")
    print("  w1.mem b1.mem w2.mem b2.mem   ($readmemh hex, two's complement)")
    print("  meta.json")


if __name__ == "__main__":
    main()
