"""旋钮实验第一步：用同一初始参数分别训练 A/B 条纹数据，并记录参数轨迹。

输出：
    output/alpha.json      参数名 -> A 训练终值
    output/beta.json       参数名 -> B 训练终值
    output/track_a.json    参数名 -> A 训练轨迹（epoch 0 为初始值）
    output/track_b.json    参数名 -> B 训练轨迹（epoch 0 为初始值）
"""

import json
import random
from pathlib import Path
from typing import Dict, List, Tuple

try:
    import torch
except ModuleNotFoundError as exc:
    raise SystemExit("缺少依赖 torch：请先执行 pip install torch（CPU 版即可）") from exc

SEED = 1
EPOCHS = 50
LEARNING_RATE = 0.01
WEIGHT_STD = 0.03
BIAS_STD = 0.5
IMAGE_SIZE = 8
INPUT_DIM = IMAGE_SIZE * IMAGE_SIZE
HIDDEN_DIM = 8
NUM_CLASSES = 2
TRAIN_PER_CLASS = 400
TEST_PER_CLASS = 100
TOP_K = 10
OUTPUT_DIR = Path(__file__).resolve().parent / "output"


class KnobMLP(torch.nn.Module):
    """极小 MLP：64 -> hidden... -> 2。架构由 hidden_dims 决定。"""

    def __init__(self, hidden_dims: List[int]) -> None:
        super().__init__()
        self.layers = torch.nn.ModuleList()
        in_dim = INPUT_DIM
        for hidden in hidden_dims:
            self.layers.append(torch.nn.Linear(in_dim, hidden))
            in_dim = hidden
        self.out = torch.nn.Linear(in_dim, NUM_CLASSES)
        self.relu = torch.nn.ReLU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """前向传播：逐层 ReLU 后输出 2 类 logits。"""
        for layer in self.layers:
            x = self.relu(layer(x))
        return self.out(x)


class KnobCNN(torch.nn.Module):
    """极小 CNN：两个卷积层（核 3x3，空间局部性）+ 全局池化 + 全连接。

    用于对比：卷积核有空间局部结构——参数指向性是否比 MLP 更结构化。
    """

    def __init__(self) -> None:
        super().__init__()
        self.conv1 = torch.nn.Conv2d(1, 4, kernel_size=3, padding=1)
        self.conv2 = torch.nn.Conv2d(4, 8, kernel_size=3, padding=1)
        self.fc = torch.nn.Linear(8, NUM_CLASSES)
        self.relu = torch.nn.ReLU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """前向传播：两层卷积 + ReLU + 全局平均池化 + 全连接。"""
        x = x.view(-1, 1, IMAGE_SIZE, IMAGE_SIZE)
        x = self.relu(self.conv1(x))
        x = self.relu(self.conv2(x))
        x = x.mean(dim=(2, 3))
        return self.fc(x)


# 架构注册表：名称 -> (构建函数, 描述)
ARCHITECTURES = {
    "mlp1": (lambda: KnobMLP([8]), "1 隐层 8 宽"),
    "mlp2": (lambda: KnobMLP([8, 8]), "2 隐层 8 宽（默认）"),
    "mlp3": (lambda: KnobMLP([8, 8, 8]), "3 隐层 8 宽"),
    "wide": (lambda: KnobMLP([16]), "1 隐层 16 宽"),
    "cnn": (lambda: KnobCNN(), "2 卷积层 3x3 + 池化"),
}


def _data_seed(kind: str, split: str) -> int:
    """为不同数据子集生成稳定、互不相同的随机种子。"""
    return SEED * 1000 + (0 if split == "train" else 100) + (0 if kind == "A" else 1)


def make_stripe_data(kind: str, count: int, seed: int) -> Tuple[torch.Tensor, torch.Tensor]:
    """生成横/竖条纹二值图数据集，A 标签 0、B 标签 1。

    每张图是 8x8 二值图；A 每隔一行全 1，B 每隔一列全 1，
    并随机翻转 1~3 个像素作为噪声。
    """
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


def make_datasets() -> Dict[str, Tuple[torch.Tensor, torch.Tensor]]:
    """构造 A/B 的训练集与测试集，每类 400 训练 + 100 测试。"""
    return {
        "train_a": make_stripe_data("A", TRAIN_PER_CLASS, _data_seed("A", "train")),
        "test_a": make_stripe_data("A", TEST_PER_CLASS, _data_seed("A", "test")),
        "train_b": make_stripe_data("B", TRAIN_PER_CLASS, _data_seed("B", "train")),
        "test_b": make_stripe_data("B", TEST_PER_CLASS, _data_seed("B", "test")),
    }


def init_model(seed: int, arch: str = "mlp2") -> torch.nn.Module:
    """以固定 seed 创建并初始化模型，保证 A/B 两次训练从同一初始点出发。"""
    if arch not in ARCHITECTURES:
        raise ValueError(f"未知架构: {arch}，可选: {sorted(ARCHITECTURES)}")
    torch.manual_seed(seed)
    model = ARCHITECTURES[arch][0]()
    with torch.no_grad():
        for module in model.modules():
            if isinstance(module, (torch.nn.Linear, torch.nn.Conv2d)):
                torch.nn.init.normal_(module.weight, mean=0.0, std=WEIGHT_STD)
                torch.nn.init.normal_(module.bias, mean=0.0, std=BIAS_STD)
    return model


def train_and_track(
    model: KnobMLP,
    x: torch.Tensor,
    y: torch.Tensor,
    epochs: int,
) -> Dict[str, List[List[float]]]:
    """训练模型并记录每轮后的全部参数值（索引 0 是训练前初始值）。"""
    optimizer = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE)
    criterion = torch.nn.CrossEntropyLoss()
    track: Dict[str, List[List[float]]] = {
        name: [] for name, _ in model.named_parameters()
    }

    def record() -> None:
        for name, param in model.named_parameters():
            track[name].append(param.detach().cpu().numpy().reshape(-1).tolist())

    record()
    for _ in range(epochs):
        optimizer.zero_grad()
        logits = model(x)
        loss = criterion(logits, y)
        loss.backward()
        optimizer.step()
        record()
    return track


def evaluate(model: KnobMLP, x: torch.Tensor, y: torch.Tensor) -> float:
    """计算模型在指定数据集上的测试准确率。"""
    model.eval()
    with torch.no_grad():
        predictions = torch.argmax(model(x), dim=1)
    return float((predictions == y).float().mean().item())


def final_values(track: Dict[str, List[List[float]]]) -> Dict[str, List[float]]:
    """从轨迹中取出最后一轮的参数终值。"""
    return {name: values[-1] for name, values in track.items()}


def top_parameter_changes(
    track: Dict[str, List[List[float]]],
    limit: int = TOP_K,
) -> List[Tuple[str, int, float]]:
    """按单个参数位置计算 |Δ|，返回变化最大的 TopK。"""
    changes: List[Tuple[str, int, float]] = []
    for name, trajectory in track.items():
        initial = trajectory[0]
        final = trajectory[-1]
        for index, (before, after) in enumerate(zip(initial, final, strict=True)):
            changes.append((name, index, abs(after - before)))
    return sorted(changes, key=lambda item: item[2], reverse=True)[:limit]


def write_json(path: Path, payload: object) -> None:
    """以 UTF-8 JSON 写入输出文件。"""
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    """训练 A/B 模型，导出参数终值与轨迹，并打印灵敏度 Top10。

    Args:
        arch: 架构名（mlp1/mlp2/mlp3/wide/cnn），输出文件带架构前缀。
    """
    import argparse

    parser = argparse.ArgumentParser(description="旋钮实验：A/B 训练参数轨迹")
    parser.add_argument("--arch", type=str, default="mlp2",
                        help=f"架构: {sorted(ARCHITECTURES)}（默认 mlp2）")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    datasets = make_datasets()
    prefix = args.arch

    model_a = init_model(SEED, args.arch)
    track_a = train_and_track(model_a, *datasets["train_a"], EPOCHS)
    alpha = final_values(track_a)

    model_b = init_model(SEED, args.arch)
    track_b = train_and_track(model_b, *datasets["train_b"], EPOCHS)
    beta = final_values(track_b)

    write_json(OUTPUT_DIR / f"alpha_{prefix}.json", alpha)
    write_json(OUTPUT_DIR / f"beta_{prefix}.json", beta)
    write_json(OUTPUT_DIR / f"track_a_{prefix}.json", track_a)
    write_json(OUTPUT_DIR / f"track_b_{prefix}.json", track_b)

    param_count = sum(len(values) for values in alpha.values())
    print(f"参数总数：{param_count}")
    print(f"A 训练模型：A 测试准确率 {evaluate(model_a, *datasets['test_a']):.2%}，"
          f"B 测试准确率 {evaluate(model_a, *datasets['test_b']):.2%}")
    print(f"B 训练模型：A 测试准确率 {evaluate(model_b, *datasets['test_a']):.2%}，"
          f"B 测试准确率 {evaluate(model_b, *datasets['test_b']):.2%}")

    for label, track in (("A", track_a), ("B", track_b)):
        print(f"{label} 训练灵敏度 Top{TOP_K}（参数名[下标] |Δ|）：")
        for name, index, delta in top_parameter_changes(track):
            print(f"  {name}[{index}] {delta:.4f}")


if __name__ == "__main__":
    main()
