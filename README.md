## Flip7helper

Real-time helper for the card game **Flip 7**:

- Watches a screenshot folder
- Detects visible cards using OpenCV template matching (templates in `assets/`)
- Prints **Bust Probability** and **Expected Value (EV)** using the official 94-card deck composition

### Install (WSL/Linux)

From this folder:

```bash
python -m pip install -e .
```

### Run

Watch a folder that Windows writes screenshots into (example WSL mount):

```bash
flip7-watch --watch "/mnt/c/Users/<YOU>/Pictures/Screenshots"
```

If detections are too noisy, raise/lower the threshold:

```bash
flip7-watch --watch "/mnt/c/Users/<YOU>/Pictures/Screenshots" --threshold 0.85
```

