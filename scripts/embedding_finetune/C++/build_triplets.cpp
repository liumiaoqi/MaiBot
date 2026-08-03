/**
 * build_triplets.cpp — C++23 现代实现
 * 余弦相似度硬算 + 三元组索引构造
 *
 * 展示的 C++20/23 特性：
 *   std::expected<T,E>   — 类型安全的错误处理（替代异常/错误码）
 *   std::print/println   — 类型安全格式化输出（替代 printf）
 *   std::span            — 非拥有式连续序列视图（替代裸指针+长度）
 *   std::views::zip      — 并行迭代多个序列
 *   std::ranges::to      — 从范围视图直接构造容器
 *   std::jthread         — 析构时自动 join 的线程（RAII）
 *   deducing this        — 显式对象参数（简化 const/非const 重载）
 *   结构化绑定           — auto [x, y] = pair
 *   [[nodiscard]]        — 忽略返回值时编译器警告
 *   std::string_view     — 非拥有式字符串视图
 *   std::atomic          — 无锁原子操作（线程安全计数器）
 *
 * 编译：make
 * 用法：build_triplets embeddings.bin 2 2 > triplets.tsv
 *       参数：文件路径 top_k bottom_k
 */

#include <algorithm>    // std::ranges::sort, std::min
#include <atomic>       // std::atomic, std::memory_order_relaxed
#include <cmath>        // std::sqrt
#include <expected>     // std::expected, std::unexpected（C++23）
#include <format>       // std::format（C++20）
#include <mutex>        // std::mutex, std::lock_guard
#include <print>        // std::print, std::println（C++23）
#include <ranges>       // std::views::iota/zip/filter/transform, std::ranges::sort/to
#include <span>         // std::span（C++20）
#include <string_view>  // std::string_view（C++17）
#include <thread>       // std::jthread（C++20）
#include <tuple>        // std::tuple, 结构化绑定
#include <vector>       // std::vector
#include <cstdio>       // std::fopen/fread/fclose（二进制 I/O 无现代替代）

// ─── 数据结构 ───────────────────────────────────────────────

/// Embedding 数据集：N 条 D 维向量，连续存储在一维数组中
struct EmbeddingData {
    int32_t N;                  // 向量条数
    int32_t D;                  // 每条向量的维度（如 1024）
    std::vector<float> data;    // 连续存储，第 i 条向量起始位置 = i * D

    /// 获取第 i 条向量的只读视图
    /// deducing this（C++23）：显式对象参数，自动推导 const/非 const
    [[nodiscard]] auto operator[](this const EmbeddingData& self, int i)
        -> std::span<const float>
    {
        return {&self.data[static_cast<size_t>(i) * self.D],
                static_cast<size_t>(self.D)};
    }
};

/// 相似度条目：记录某个向量的索引和它与 anchor 的余弦相似度
struct SimEntry {
    int idx;      // 向量在原始数据中的下标（0 到 N-1）
    float sim;    // 与 anchor 的余弦相似度，范围 [-1, 1]
};

/// 三元组索引：(anchor, positive, negative)
using Triplet = std::tuple<int, int, int>;

// ─── 核心算法 ───────────────────────────────────────────────

/**
 * 从二进制文件读取 embedding 数据
 * 文件格式：int32 N | int32 D | N*D 个 float32（行主序）
 *
 * 使用 std::expected（C++23）做类型安全的错误处理：
 *   成功 → 含 EmbeddingData 的 expected
 *   失败 → 含错误描述字符串的 unexpected
 */
auto read_embeddings(std::string_view path)
    -> std::expected<EmbeddingData, std::string>
{
    // C++23: if 初始化语句，fp 非空则进入分支
    if (auto* fp = std::fopen(path.data(), "rb"); fp) {
        int32_t N, D;
        if (std::fread(&N, sizeof(int32_t), 1, fp) != 1 ||
            std::fread(&D, sizeof(int32_t), 1, fp) != 1) {
            std::fclose(fp);
            return std::unexpected("文件头读取失败");
        }

        auto total = static_cast<size_t>(N) * D;
        auto data = std::vector<float>(total);
        if (std::fread(data.data(), sizeof(float), total, fp) != total) {
            std::fclose(fp);
            return std::unexpected("向量数据读取不完整");
        }
        std::fclose(fp);
        return EmbeddingData{N, D, std::move(data)};
    }
    // std::format（C++20）：类型安全的格式化字符串
    return std::unexpected(std::format("无法打开: {}", path));
}

/**
 * 计算两个向量的余弦相似度
 * cos(θ) = (a·b) / (|a| × |b|)
 *
 * @param a 向量 a（std::span 视图，零拷贝）
 * @param b 向量 b
 * @return 余弦相似度 [-1, 1]；零向量返回 0
 */
auto cosine_sim(std::span<const float> a, std::span<const float> b) -> float {
    float dot = 0.0f;   // 点积 a·b = Σ a[i]*b[i]
    float na  = 0.0f;   // |a|² 的累加器
    float nb  = 0.0f;   // |b|² 的累加器

    // C++23: std::views::zip 并行迭代两个序列
    // 结构化绑定 auto [x, y] 同时解包每对元素
    for (auto [x, y] : std::views::zip(a, b)) {
        dot += x * y;
        na  += x * x;
        nb  += y * y;
    }

    na = std::sqrt(na);     // |a|
    nb = std::sqrt(nb);     // |b|
    return (na < 1e-9f || nb < 1e-9f) ? 0.0f : dot / (na * nb);
}

/**
 * 为第 i 条向量（anchor）构造三元组
 * 找 top-k 个最相似的为 positive，bottom-k 个最不相似的为 negative
 * 笛卡尔积组合：每个 positive × 每个 negative → 一个三元组
 */
auto build_triplets_for(int i, const EmbeddingData& emb,
                        int top_k, int bottom_k) -> std::vector<Triplet>
{
    auto ai = emb[i];  // anchor 向量的 span 视图，零拷贝

    // C++23: 范围管道组合
    //   iota(0, N)     → 生成 0,1,...,N-1
    //   filter(...)    → 过滤掉自身索引 i
    //   transform(...) → 计算每个的余弦相似度，生成 SimEntry
    //   to<vector>()   → 从视图收集到 std::vector（C++23）
    auto sims = std::views::iota(0, emb.N)
        | std::views::filter([i](int j) { return j != i; })
        | std::views::transform([&](int j) -> SimEntry {
              return {j, cosine_sim(ai, emb[j])};
          })
        | std::ranges::to<std::vector>();

    // C++20: ranges 排序
    //   std::greater{} → 降序（相似度高的在前）
    //   &SimEntry::sim → 投影：只取 sim 字段做比较键
    std::ranges::sort(sims, std::greater{}, &SimEntry::sim);

    auto npos = std::min(top_k, static_cast<int>(sims.size()));
    auto nneg = std::min(bottom_k, static_cast<int>(sims.size()));

    // 笛卡尔积组合：positive × negative
    auto result = std::vector<Triplet>{};
    result.reserve(npos * nneg);
    for (int p = 0; p < npos; ++p) {
        for (int n = 0; n < nneg; ++n) {
            int neg_idx = static_cast<int>(sims.size()) - 1 - n;  // 从末尾取最不相似的
            result.emplace_back(i, sims[p].idx, sims[neg_idx].idx);
        }
    }
    return result;
}

// ─── 主函数 ─────────────────────────────────────────────────

int main(int argc, char* argv[]) {
    if (argc < 4) {
        // C++23: std::println — 类型安全，编译期检查格式串
        std::println(stderr, "用法: {} embeddings.bin top_k bottom_k", argv[0]);
        return 1;
    }

    auto path     = std::string_view{argv[1]};    // 非拥有式字符串视图
    auto top_k    = std::atoi(argv[2]);            // 每个 anchor 取 top-k 近邻为 positive
    auto bottom_k = std::atoi(argv[3]);            // 每个 anchor 取 bottom-k 远邻为 negative

    // 读取 embedding 数据（std::expected 错误处理，无异常）
    auto emb_result = read_embeddings(path);
    if (!emb_result) {
        std::println(stderr, "错误: {}", emb_result.error());
        return 1;
    }
    const auto& emb = *emb_result;  // 解引用获取数据
    std::println(stderr, "读取 {} 条向量，维度 {}", emb.N, emb.D);

    // ─── 多线程并行构造 ──────────────────────────────────────

    // std::jthread（C++20）：析构时自动 join，无需手动等待
    auto num_threads = std::max(1u, std::jthread::hardware_concurrency());
    std::println(stderr, "使用 {} 个线程", num_threads);

    std::atomic<int> progress{0};   // 原子计数器，线程安全
    std::mutex output_mutex;        // 输出互斥锁，防止多线程行交错

    // 工作函数：处理 [start, end) 范围内的 anchor
    auto worker = [&](int start, int end) {
        for (int i = start; i < end; ++i) {
            auto triplets = build_triplets_for(i, emb, top_k, bottom_k);

            // RAII 锁守卫：离开花括号作用域自动释放
            {
                std::lock_guard lock{output_mutex};  // CTAD 推导类型，无需 <std::mutex>
                for (auto [anchor, pos, neg] : triplets) {  // 结构化绑定解包 tuple
                    std::println("{}\t{}\t{}", anchor, pos, neg);
                }
            }

            // 原子递增 + 宽松内存序（无需严格顺序，只用于进度显示）
            int done = progress.fetch_add(1, std::memory_order_relaxed) + 1;
            if (done % 500 == 0 || done == emb.N) {
                std::println(stderr, "  已处理 {}/{}", done, emb.N);
            }
        }
    };

    // 按线程数均分 anchor 范围，启动 jthread
    {
        auto threads = std::vector<std::jthread>{};
        auto chunk = (emb.N + static_cast<int>(num_threads) - 1)
                     / static_cast<int>(num_threads);
        for (int t = 0; t < static_cast<int>(num_threads); ++t) {
            int start = t * chunk;
            int end = std::min(start + chunk, emb.N);
            if (start >= end) break;
            threads.emplace_back(worker, start, end);  // jthread 构造即启动
        }
        // 离开此作用域 → threads 析构 → 各 jthread 析构 → 自动 join
    }

    std::println(stderr, "完成");
    return 0;
}
