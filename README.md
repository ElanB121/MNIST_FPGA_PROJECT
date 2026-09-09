# Binary-MNIST INT8 MLP → FPGA

A deliberately simple **3-layer perceptron** (`784 → hidden → 10`) trained on
**black-and-white MNIST** with **signed 8-bit integer weights**, so it can be
loaded straight onto an FPGA. Training uses quantization-aware training (QAT) in
PyTorch; inference on the FPGA is **pure integer arithmetic** — no floating point.

| Metric | Value |
|---|---|
| Test accuracy (PyTorch, float QAT) | **96.87%** |
| Test accuracy (integer / FPGA path) | **96.86%** |
| Topology | `784 → 64 → 10` |
| Total parameters | 50,890 |
| Weight type | signed `int8` (−127…127) |
| Bias type | `int32` |
| Hidden accumulator width | 12-bit signed |
| Output (logit) accumulator width | 20-bit signed |

> The **integer/FPGA** accuracy is the number that matters for hardware: it runs the
> exported int8 weights through exact integer multiply-accumulate, exactly what the
> FPGA computes. It matches the PyTorch model to within rounding.

---

## 1. Model Architecture

A fully-connected feed-forward network with one hidden layer. Each image enters as
a 784-element binary vector and leaves as 10 class scores; the prediction is the
`argmax` of those scores.

```
        INPUT                    HIDDEN (ReLU)                 OUTPUT
   ┌─────────────┐    W1, b1     ┌─────────────┐   W2, b2    ┌─────────────┐
   │     784     │ ───────────▶  │     64      │ ──────────▶ │     10      │
   │  bits {0,1} │   [64 × 784]  │   neurons   │  [10 × 64]  │ classes 0-9 │
   │   28 × 28   │               │ (hyperparam)│             │   argmax    │
   └─────────────┘               └─────────────┘             └─────────────┘

     h = ReLU(W1 · x + b1)        logits = W2 · h + b2        pred = argmax(logits)
```

Because the input `x` holds only 0/1 values and both weight matrices are signed
integers, every product and sum is an exact integer multiply-accumulate. The
`argmax` decision is invariant to the per-layer scale factors, so **no
re-quantization between layers is required** on the FPGA.

### Weights & biases — where each parameter lives

Each layer owns one weight matrix and one bias vector. The table maps every
parameter to its PyTorch attribute, its exported array, and the FPGA memory file
(`$readmemh`, two's-complement hex).

| Layer | Parameter | Shape | Type | PyTorch → Export → Mem file |
|---|---|---|---|---|
| Layer 1 (784→64) | Weights **W1** | `[64, 784]` (50,176) | `int8`  | `fc1.weight` → `W1_int` → `w1.mem` |
| Layer 1 (784→64) | Bias **b1**    | `[64]`               | `int32` | `fc1.bias`   → `b1_int` → `b1.mem` |
| Layer 2 (64→10)  | Weights **W2** | `[10, 64]` (640)     | `int8`  | `fc2.weight` → `W2_int` → `w2.mem` |
| Layer 2 (64→10)  | Bias **b2**    | `[10]`               | `int32` | `fc2.bias`   → `b2_int` → `b2.mem` |

---

## 2. Data Taxonomy

The model trains and is evaluated on the **MNIST** handwritten-digit dataset,
converted to pure black-and-white before it ever reaches the network.

| Split | Size | Notes |
|---|---|---|
| Training set | 60,000 images | labels 0–9 |
| Test set     | 10,000 images | held out, never seen in training |

**Source.** MNIST is fetched through `torchvision.datasets.MNIST` with
`download=True`, which mirrors the original dataset into a local `./data` folder.
The train/test splits are the dataset's own canonical partitions.

**From a 28×28 image to a 784-element binary vector:**

1. **Normalize** — divide the 0–255 pixel values by 255 → floats in `[0, 1]`.
2. **Binarize** — apply a threshold (default `0.5`): a pixel becomes `1` (white)
   if above the threshold, else `0` (black).
3. **Flatten** — reshape the `28 × 28` grid row-by-row into a single `784`-vector.

```python
from torchvision import datasets, transforms

def load_binarized_mnist(data_dir, threshold=0.5):
    tf = transforms.ToTensor()                     # pixels -> float in [0, 1]
    train = datasets.MNIST(data_dir, train=True,  download=True, transform=tf)
    test  = datasets.MNIST(data_dir, train=False, download=True, transform=tf)

    def to_bw(ds):
        x = ds.data.float() / 255.0                # [N, 28, 28] grayscale, 0..1
        x = (x > threshold).float()                # BINARIZE: black=0, white=1
        x = x.view(x.size(0), 784)                 # flatten 28x28 -> 784-vector
        return x, ds.targets.clone()

    return to_bw(train), to_bw(test)               # (x_train,y_train),(x_test,y_test)
```

Because the input is 1-bit per pixel, the first layer on the FPGA reduces to a
conditional add of weights: each pixel that is `1` contributes its weight to the
accumulator, each `0` contributes nothing.

---

## 3. Installation

Requires an NVIDIA GPU for fast training (CPU also works, just slower).

```bash
# 1. Create an isolated environment
conda create -n mnist_fpga python=3.11 -y
conda activate mnist_fpga

# 2a. Install PyTorch WITH CUDA (recommended, GPU)
pip install --index-url https://download.pytorch.org/whl/cu124 torch torchvision

# 2b. OR install the CPU-only build
pip install torch torchvision
```

No conda? Any Python 3.10–3.12 virtualenv works — install the same packages with
`pip`. The only dependencies are `torch`, `torchvision`, and `numpy`
(pulled in automatically). See `requirements.txt`.

---

## 4. Training

```bash
python train_mnist_fpga.py                 # defaults: hidden=64, 20 epochs -> ~96.9%
python train_mnist_fpga.py --help          # all tunable flags
```

Useful flags (tune these to trade accuracy vs. hardware cost):

| Flag | Default | Meaning |
|---|---|---|
| `--hidden`     | 64   | hidden-layer neurons (the main hyperparameter) |
| `--bits`       | 8    | weight bit-width (signed) |
| `--epochs`     | 20   | training epochs |
| `--threshold`  | 0.5  | binarization threshold, pixel > threshold → white |
| `--lr`         | 1e-3 | learning rate |
| `--batch-size` | 128  | mini-batch size |

Training writes everything to `fpga_export/`:

| File | Contents |
|---|---|
| `mnist_mlp.pt` | PyTorch checkpoint: `state_dict` + `hidden` + `threshold` |
| `mnist_int8_model.npz` | `W1_int` (int8), `b1_int` (int32), `W2_int` (int8), `b2_int` (int32) |
| `w1.mem` `b1.mem` `w2.mem` `b2.mem` | `$readmemh` hex, two's complement (int8=2 digits, int32=8) |
| `meta.json` | config, accuracy, accumulator bit-widths |

---

## 5. Loading & Testing the Model on a PC

The trained network is a standard PyTorch checkpoint and can be reloaded and
evaluated on any machine with PyTorch — no FPGA required.

```bash
python load_and_test.py --show 5
```

Expected output:

```
Loaded fpga_export/mnist_mlp.pt  |  arch 784->64->10  |  threshold 0.5
Test accuracy (PyTorch model):     96.87%  on 10000 images
Test accuracy (integer/FPGA path): 96.86%
  #0   pred=7  true=7  [ok]
  #1   pred=2  true=2  [ok]
  #2   pred=1  true=1  [ok]
```

The essential steps, if you want to load it yourself:

```python
import torch
from train_mnist_fpga import MLP, load_binarized_mnist

# 1. Load checkpoint and rebuild the exact network
ckpt  = torch.load("fpga_export/mnist_mlp.pt", weights_only=False)
model = MLP(hidden=ckpt["hidden"], bits=ckpt["bits"])   # 784 -> 64 -> 10
model.load_state_dict(ckpt["state_dict"])               # restore trained weights
model.eval()

# 2. Load the test set, binarized with the SAME threshold as training
_, _, x_test, y_test = load_binarized_mnist("./data", ckpt["threshold"])

# 3. Predict and score
pred = model(x_test).argmax(1)
acc  = (pred == y_test).float().mean()
print(f"test accuracy: {acc*100:.2f}%")                 # -> ~96.9%
```

Use `weights_only=False` because the checkpoint stores the hyperparameters
alongside the weights.

---

## Repository layout

```
train_mnist_fpga.py   Train + quantize + export (defines MLP and the data pipeline)
load_and_test.py      Reload the checkpoint and report test accuracy
requirements.txt      Python dependencies
fpga_export/          Trained model + int8 arrays + .mem files for the FPGA
```

*Course project — the MNIST dataset (`data/`) is downloaded on first run and is not
tracked here.*
