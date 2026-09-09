#!/usr/bin/env python3
"""
Load the trained MLP checkpoint and test it on MNIST.

This reuses the exact model definition and data pipeline from the training
script, so the reloaded model behaves identically to training time.

Usage
-----
    python load_and_test.py                                   # test whole test set
    python load_and_test.py --ckpt fpga_export/mnist_mlp.pt   # explicit path
    python load_and_test.py --show 8                          # print 8 example predictions
"""

import argparse

import torch

# Reuse the network definition + binarization from the training script
from train_mnist_fpga import MLP, load_binarized_mnist, export_int_model, integer_inference


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ckpt", default="fpga_export/mnist_mlp.pt", help="path to mnist_mlp.pt")
    p.add_argument("--data-dir", default="./data")
    p.add_argument("--show", type=int, default=5, help="how many example predictions to print")
    p.add_argument("--cpu", action="store_true")
    args = p.parse_args()

    device = torch.device("cuda" if (torch.cuda.is_available() and not args.cpu) else "cpu")

    # 1) Load the checkpoint and rebuild the network with the saved hyperparameters
    ckpt = torch.load(args.ckpt, map_location=device, weights_only=False)
    model = MLP(hidden=ckpt["hidden"], bits=ckpt["bits"]).to(device)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    print(f"Loaded {args.ckpt}  |  arch {ckpt['arch']}  |  threshold {ckpt['threshold']}")

    # 2) Load the test set, binarized the SAME way as during training
    _, _, xte, yte = load_binarized_mnist(args.data_dir, ckpt["threshold"])
    xte_d, yte_d = xte.to(device), yte.to(device)

    # 3) Accuracy with the PyTorch (float, fake-quant) model
    with torch.no_grad():
        logits = model(xte_d)
        preds = logits.argmax(1)
        acc = (preds == yte_d).float().mean().item()
    print(f"Test accuracy (PyTorch model): {acc*100:.2f}%  on {yte.numel()} images")

    # 4) Accuracy with the pure-integer path (what the FPGA computes)
    params = export_int_model(model, ckpt["bits"])
    int_preds, _, _ = integer_inference(params, xte.numpy())
    int_acc = (int_preds == yte.numpy()).mean()
    print(f"Test accuracy (integer/FPGA path): {int_acc*100:.2f}%")

    # 5) Show a few example predictions
    if args.show > 0:
        print(f"\nFirst {args.show} predictions (pred vs. true):")
        for i in range(args.show):
            mark = "ok " if int(preds[i]) == int(yte[i]) else "MISS"
            print(f"  #{i:<3d} pred={int(preds[i])}  true={int(yte[i])}  [{mark}]")


if __name__ == "__main__":
    main()
