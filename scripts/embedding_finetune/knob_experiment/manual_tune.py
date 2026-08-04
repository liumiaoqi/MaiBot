"""旋钮实验第三步：手动把“指向 A”的参数拉向初始值，观察 A/B 准确率 trade-off。

用法：python manual_tune.py [--top-n 5]
"""

import argparse
import json
import random
from pathlib import Path
from typing import Dict, List, Tuple

try:
    import torch
except ModuleNotFoundError as exc:
    raise SystemExit("缺少依赖 torch：请先执行 pip install torch（CPU 版即可）") from exc

SEED = 1
WEIGHT_STD = 0.03
BIAS_STD = 0.5
THRESHOLD = 0.05
DEFAULT_TOP_N = 5
DEFAULT_RATIOS = (0, 25, 50, 75, 100)
IMAGE_SIZE = 8
INPUT_DIM = IMAGE_SIZE * IMAGE_SIZE
HIDDEN_DIM = 8
NUM_CLASSES = 2
TEST_PER_CLASS = 100
OUTPUT_DIR = Path(__file__).resolve().parent / "output"


class KnobMLP(torch.nn.Module):
    """与 train_track.py 完全一致的极小 MLP。"""

    def __init__(self) -> None:
        super().__init__()
        self.fc1 = torch.nn.Linear(INPUT_DIM, HIDDEN_DIM)
        self.fc2 = torch.nn.Linear(HIDDEN_DIM, HIDDEN_DIM)
        self.fc3 = torch.nn.Linear(HIDDEN_DIM, NUM_CLASSES)
        self.relu = torch.nn.ReLU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """前向传播：两层 ReLU 后输出 2 类 logits。"""
        x = self.relu(self.fc1(x))
        x = self.relu(self.fc2(x))
        return self.fc3(x)


def _data_seed(kind: str, split: str) -> int:
    """与 train_track.py 保持一致的测试集种子。"""
    return SEED * 1000 + (0 if split == "train" else 100) + (0 if kind == "A" else 1)


def make_stripe_data(kind: str, count: int, seed: int) -> Tuple[torch.Tensor, torch.Tensor]:
    """生成横/竖条纹二值图测试集。"""
    rng = random.Random(seed)
    images: List[List[float]] = []
    labels: List[int] = []
    for _ in range(count):
        image = [[0.0] * IMAGE_SIZE for _ in range(IMAGE_SIZE)]
        if kind == "A":
            for row in range(0, IMAGE_SIZE, 2):
                image[row] = [1.0] * IMAGE_SIZE
        else:
            for col in range(0, IMAGE_SIZE, 2):
                for row in range(IMAGE_SIZE):
                    image[row][col] = 1.0
        for _ in range(rng.randint(1, 3)):
            row, col = rng.randrange(IMAGE_SIZE), rng.randrange(IMAGE_SIZE)
            image[row][col] = 1.0 - image[row][col]
        images.append([value for row in image for value in row])
        labels.append(0 if kind == "A" else 1)
    return torch.tensor(images, dtype=torch.float32), torch.tensor(labels, dtype=torch.long)


def init_model(seed: int) -> KnobMLP:
    """以固定 seed 创建模型（随后会被 α 覆盖）。"""
    torch.manual_seed(seed)
    model = KnobMLP()
    with torch.no_grad():
        for module in model.modules():
            if isinstance(module, torch.nn.Linear):
                torch.nn.init.normal_(module.weight, mean=0.0, std=WEIGHT_STD)
                torch.nn.init.normal_(module.bias, mean=0.0, std=BIAS_STD)
    return model


def load_json(name: str) -> Dict[str, list]:
    """读取 output 下的 JSON 文件。"""
    return json.loads((OUTPUT_DIR / name).read_text(encoding="utf-8"))


def select_pointing_a(
    alpha: Dict[str, list],
    beta: Dict[str, list],
    track_a: Dict[str, list],
    top_n: int,
) -> List[Tuple[str, int, float, float]]:
    """选出“指向 A”的 Top N 参数（按 A 指向度降序）。

    A 指向度 = |α-初始| - |β-初始|；严格“指向 A”候选不足时回退到全参数。
    返回 (参数名, 下标, A 指向度, |α-初始|)。
    """
    strict: List[Tuple[str, int, float, float]] = []
    fallback: List[Tuple[str, int, float, float]] = []
    for name in alpha:
        initial = track_a[name][0]
        for index, (alpha_value, beta_value, init_value) in enumerate(
            zip(alpha[name], beta[name], initial, strict=True)
        ):
            delta_a = abs(alpha_value - init_value)
            delta_b = abs(beta_value - init_value)
            score = delta_a - delta_b
            item = (name, index, score, delta_a)
            fallback.append(item)
            if delta_a > THRESHOLD and delta_b < THRESHOLD:
                strict.append(item)
    candidates = strict if len(strict) >= top_n else fallback
    return sorted(candidates, key=lambda item: item[2], reverse=True)[:top_n]


def apply_ratio(
    state: Dict[str, list],
    selected: List[Tuple[str, int, float, float]],
    init_state: Dict[str, list],
    ratio: float,
) -> Dict[str, list]:
    """把选中参数从 α 向初始值插值：new = α + ratio × (初始 - α)。"""
    new_state = {name: list(values) for name, values in state.items()}
    for name, index, _, _ in selected:
        alpha_value = state[name][index]
        init_value = init_state[name][index]
        new_state[name][index] = alpha_value + ratio * (init_value - alpha_value)
    return new_state


def evaluate(model: KnobMLP, x: torch.Tensor, y: torch.Tensor) -> float:
    """计算模型在指定数据集上的测试准确率。"""
    model.eval()
    with torch.no_grad():
        predictions = torch.argmax(model(x), dim=1)
    return float((predictions == y).float().mean().item())


def build_model(state: Dict[str, list]) -> KnobMLP:
    """把 JSON 参数状态写回模型。"""
    model = init_model(SEED)
    with torch.no_grad():
        for name, param in model.named_parameters():
            param.copy_(torch.tensor(state[name]).reshape(param.shape))
    return model


def main() -> None:
    """载入 α/β，测试 Top N 旋钮拉向初始值的 A/B 准确率 trade-off。"""
    parser = argparse.ArgumentParser(description="手动旋钮实验")
    parser.add_argument("--top-n", type=int, default=DEFAULT_TOP_N, help="选择指向 A 的参数个数")
    args = parser.parse_args()
    top_n = max(1, args.top_n)

    missing = [name for name in ("alpha.json", "beta.json", "track_a.json")
               if not (OUTPUT_DIR / name).exists()]
    if missing:
        raise SystemExit(f"缺少输出文件 {missing}，请先运行 train_track.py")

    alpha = load_json("alpha.json")
    beta = load_json("beta.json")
    track_a = load_json("track_a.json")
    init_state = {name: values[0] for name, values in track_a.items()}
    test_a = make_stripe_data("A", TEST_PER_CLASS, _data_seed("A", "test"))
    test_b = make_stripe_data("B", TEST_PER_CLASS, _data_seed("B", "test"))

    selected = select_pointing_a(alpha, beta, track_a, top_n)
    print(f"选中的 Top {top_n} 指向 A 参数：")
    for name, index, score, delta_a in selected:
        print(f"  {name}[{index}] 指向度={score:.4f} |Δα|={delta_a:.4f}")

    print("\n修改比例 | A 测试准确率 | B 测试准确率")
    print("----------|---------------|---------------")
    rows: List[Tuple[int, float, float]] = []
    for percent in DEFAULT_RATIOS:
        ratio = percent / 100.0
        state = apply_ratio(alpha, selected, init_state, ratio)
        model = build_model(state)
        acc_a = evaluate(model, *test_a)
        acc_b = evaluate(model, *test_b)
        rows.append((percent, acc_a, acc_b))
        print(f"{percent:>6}%   | {acc_a:>12.2%} | {acc_b:>12.2%}")

    initial_acc_a = rows[0][1]
    initial_acc_b = rows[0][2]
    final_acc_a = rows[-1][1]
    final_acc_b = rows[-1][2]
    a_drop = initial_acc_a - final_acc_a
    b_rise = final_acc_b - initial_acc_b
    print(f"\nA 准确率变化：{a_drop:+.2%}，B 准确率变化：{b_rise:+.2%}")
    if a_drop > 0 and b_rise > 0:
        print("结论：出现了“A 降 B 升”的旋钮——把指向 A 的参数拉向初始值会同时降低 A、提升 B。")
    else:
        print("结论：Top N 内未出现“A 降 B 升”的旋钮，指向性可能分布在整个参数空间。")


if __name__ == "__main__":
    main()
