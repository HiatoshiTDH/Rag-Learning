"""Sinh demo/ux_demo.html từ src/static/index.html + shim backend giả lập.

Chạy:  python scripts/build_demo.py
Demo mở thẳng trong trình duyệt là chạy — UI thật 100%, chỉ backend là giả:
paper mẫu, câu trả lời soạn sẵn, streaming mô phỏng, settings/upload giả lập.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKER = "<!-- DEMO-SHIM-SLOT -->"

SHIM = r'''<script>
/* ===== DEMO SHIM — backend giả lập ngay trong trình duyệt ===== */
(() => {
const PAPERS = [
  { paper_id: "2304.03442", year: 2023,
    title: "Generative Agents: Interactive Simulacra of Human Behavior" },
  { paper_id: "2308.11432", year: 2023,
    title: "A Survey on Large Language Model based Autonomous Agents" },
  { paper_id: "local-semg-exo-review", year: 2024,
    title: "sEMG-driven Control of Assistive Exoskeletons: A Review" },
];

const SETTINGS = {
  LLM_BACKEND: "anthropic", ANSWER_MODEL: "claude-opus-5",
  ANTHROPIC_API_KEY: "sk-ant…9xk2",
  OPENAI_COMPAT_BASE_URL: "http://localhost:11434/v1",
  OPENAI_COMPAT_MODEL: "qwen2.5:14b", OPENAI_COMPAT_API_KEY: "",
  EMBED_BACKEND: "local", VOYAGE_API_KEY: "", RERANK_BACKEND: "local",
  ANSWER_LANGUAGE: "auto",
};

const ANSWERS = {
  memory: {
    text: "Generative agents chọn ký ức để retrieve bằng một hàm chấm điểm tổng hợp ba thành phần: recency (độ mới, suy giảm mũ theo thời gian truy cập gần nhất), importance (độ quan trọng do chính language model chấm từ 1-10 khi ký ức được ghi) và relevance (độ tương đồng cosine giữa embedding của ký ức và ngữ cảnh hiện tại). [1] Ba điểm này được chuẩn hóa rồi cộng có trọng số — phiên bản trong paper dùng trọng số bằng nhau — và các ký ức điểm cao nhất được đưa vào prompt. [1] Khảo sát của Wang và cộng sự xếp cơ chế này vào nhóm \"hybrid memory\", kết hợp bộ nhớ ngắn hạn trong context với kho dài hạn truy hồi được, và ghi nhận đây là thiết kế được trích dẫn nhiều nhất trong các agent framework về sau. [2]",
    citations: [
      { n: 1, title: "Generative Agents — 4. Architecture: Memory and Retrieval" },
      { n: 2, title: "A Survey on LLM-based Autonomous Agents — 3.1 Memory" },
    ],
    usage: { input_tokens: 14230, output_tokens: 412, cache_read_input_tokens: 0, cost_usd: 0.0815 },
  },
  limitation: {
    text: "Về hạn chế của cơ chế memory retrieval này, chính các tác giả thừa nhận ba điểm. Thứ nhất, điểm importance do model tự chấm không ổn định — cùng một sự kiện có thể nhận điểm khác nhau giữa các lần chạy. [1] Thứ hai, chi phí tăng tuyến tính theo độ dài memory stream vì mỗi lần retrieve phải chấm lại recency trên toàn bộ ứng viên. [1] Thứ ba, reflection phụ thuộc vào chất lượng câu hỏi tự sinh — nếu model đặt câu hỏi kém, nhận định rút ra sẽ nông. [1] Khảo sát bổ sung rằng hầu hết hệ thống kế thừa kiến trúc này chưa giải quyết được việc quên có chọn lọc (selective forgetting). [2]",
    citations: [
      { n: 1, title: "Generative Agents — 7. Discussion: Limitations" },
      { n: 2, title: "A Survey on LLM-based Autonomous Agents — 6. Challenges" },
    ],
    usage: { input_tokens: 15890, output_tokens: 388, cache_read_input_tokens: 11200, cost_usd: 0.0929 },
  },
  exo: {
    text: "Theo bài review, pipeline điều khiển exoskeleton bằng sEMG gồm bốn tầng: thu tín hiệu bề mặt da (thường 8-16 kênh quanh nhóm cơ chủ vận), tiền xử lý (lọc dải 20-450 Hz, khử nhiễu điện lưới), trích đặc trưng (RMS, MAV, và gần đây là học biểu diễn bằng CNN/TCN), rồi ánh xạ sang lệnh điều khiển — hoặc phân loại rời rạc cử chỉ, hoặc hồi quy liên tục mô-men khớp. [1] Thách thức lớn nhất được nhấn mạnh là electrode shift và mỏi cơ làm phân bố tín hiệu trôi theo thời gian, khiến model huấn luyện một phiên suy giảm mạnh ở phiên sau. [1]",
    citations: [
      { n: 1, title: "sEMG-driven Control of Assistive Exoskeletons — 3. Control Pipeline" },
    ],
    usage: { input_tokens: 9840, output_tokens: 356, cache_read_input_tokens: 0, cost_usd: 0.0581 },
  },
  fallback: {
    text: "Trong kho hiện có các paper sau. Generative Agents đề xuất kiến trúc agent có trí nhớ dài hạn với memory stream, retrieval ba trục và reflection. [1] Bài khảo sát của Wang và cộng sự hệ thống hóa các thành phần của LLM agent — profiling, memory, planning, action — trên hơn 100 công trình. [2] Bài review về exoskeleton tổng hợp pipeline điều khiển bằng tín hiệu sEMG và các thách thức khi triển khai thực tế. [3] Bạn có thể hỏi sâu vào bất kỳ paper nào, hoặc tick 2-3 paper để so sánh.",
    citations: [
      { n: 1, title: "Generative Agents — Abstract" },
      { n: 2, title: "A Survey on LLM-based Autonomous Agents — Abstract" },
      { n: 3, title: "sEMG-driven Control of Assistive Exoskeletons — Abstract" },
    ],
    usage: { input_tokens: 11020, output_tokens: 340, cache_read_input_tokens: 0, cost_usd: 0.0636 },
  },
};

const COMPARE_TEXT = "So sánh cách đánh giá của hai paper:\n\nĐiểm giống — cả hai đều không dùng benchmark định lượng chuẩn: Generative Agents đánh giá bằng phỏng vấn các agent (believability do người chấm), còn bài khảo sát tổng hợp thay vì tự thí nghiệm.\n\nĐiểm khác — Generative Agents thiết kế evaluation riêng gồm 5 nhóm câu hỏi phỏng vấn (self-knowledge, memory, plans, reactions, reflections) và ablation từng thành phần bộ nhớ, cho thấy bỏ retrieval làm believability giảm mạnh nhất. Bài khảo sát tiếp cận theo trục phân loại: gom các phương pháp đánh giá của hơn 100 công trình thành đánh giá chủ quan (human annotation, Turing-style) và khách quan (task success rate, benchmark), đồng thời chỉ ra thiếu chuẩn chung là khoảng trống của cả lĩnh vực.\n\nĐiều kiện áp dụng — cách của Generative Agents phù hợp khi hành vi giống người là mục tiêu chính; khung của bài khảo sát phù hợp làm checklist khi tự thiết kế evaluation cho agent mới.";

function pick(question, history) {
  const q = question.toLowerCase();
  if ((q.includes("hạn chế") || q.includes("limitation") || q.includes("nhược")) && history.length)
    return ANSWERS.limitation;
  if (q.includes("memory") || q.includes("ký ức") || q.includes("nhớ") || q.includes("retriev"))
    return ANSWERS.memory;
  if (q.includes("exo") || q.includes("emg") || q.includes("cơ") || q.includes("khung xương"))
    return ANSWERS.exo;
  return ANSWERS.fallback;
}

const sleep = ms => new Promise(r => setTimeout(r, ms));
const json = obj => new Response(JSON.stringify(obj), { status: 200,
  headers: { "Content-Type": "application/json" } });

function sseResponse(answer) {
  const enc = new TextEncoder();
  const words = answer.text.split(" ");
  const stream = new ReadableStream({
    async start(c) {
      const send = obj => c.enqueue(enc.encode("data: " + JSON.stringify(obj) + "\n\n"));
      await sleep(650);
      for (let i = 0; i < words.length; i += 3) {
        send({ type: "delta", text: words.slice(i, i + 3).join(" ") + " " });
        await sleep(38);
      }
      send({ type: "done", ...answer });
      c.close();
    },
  });
  return new Response(stream, { status: 200,
    headers: { "Content-Type": "text/event-stream" } });
}

const mask = v => !v ? "" : (v.length <= 10 ? "•".repeat(v.length) : v.slice(0, 6) + "…" + v.slice(-4));

window.fetch = async (url, opts = {}) => {
  const u = typeof url === "string" ? url : url.url;

  if (u.endsWith("/api/papers")) { await sleep(250); return json(PAPERS); }

  if (u.endsWith("/api/status")) return json({
    llm_backend: SETTINGS.LLM_BACKEND,
    answer_model: SETTINGS.LLM_BACKEND === "openai_compat"
      ? SETTINGS.OPENAI_COMPAT_MODEL : SETTINGS.ANSWER_MODEL,
    embed_backend: SETTINGS.EMBED_BACKEND === "local" ? "local (bge-m3)" : SETTINGS.EMBED_BACKEND,
    rerank_backend: SETTINGS.RERANK_BACKEND,
    papers: PAPERS.length, demo: true });

  if (u.endsWith("/api/ask_stream")) {
    const body = JSON.parse(opts.body);
    return sseResponse(pick(body.question, body.history || []));
  }

  if (u.endsWith("/api/compare")) { await sleep(1600); return json({ text: COMPARE_TEXT }); }

  if (u.endsWith("/api/settings/test")) {
    await sleep(500);
    return json(SETTINGS.LLM_BACKEND === "openai_compat"
      ? { ok: true, message: `Endpoint local OK (${SETTINGS.OPENAI_COMPAT_MODEL}) — demo` }
      : { ok: true, message: `Đã có Anthropic API key (${SETTINGS.ANSWER_MODEL}) — demo` });
  }

  if (u.endsWith("/api/settings")) {
    if ((opts.method || "GET") === "GET") return json(SETTINGS);
    await sleep(400);
    const body = JSON.parse(opts.body);
    const warnings = [];
    if (body.EMBED_BACKEND && body.EMBED_BACKEND !== SETTINGS.EMBED_BACKEND)
      warnings.push("Đổi embedding backend: cần xóa index và ingest lại (bản thật).");
    if (body.LLM_BACKEND === "openai_compat")
      warnings.push("Local LLM: nhớ chạy Ollama trước khi hỏi (bản thật).");
    for (const [k, v] of Object.entries(body)) {
      if (!(k in SETTINGS) || typeof v !== "string") continue;
      if (["ANTHROPIC_API_KEY", "VOYAGE_API_KEY", "OPENAI_COMPAT_API_KEY"].includes(k)) {
        if (v && !v.includes("…") && ![...v].every(c => c === "•")) SETTINGS[k] = mask(v);
      } else if (v) SETTINGS[k] = v;
    }
    return json({ ok: true, warnings, changed: Object.keys(body) });
  }

  if (u.endsWith("/api/upload")) {
    const f = opts.body.get("file");
    await sleep(2400);   // mô phỏng GROBID parse + embed
    const id = "local-" + f.name.toLowerCase().replace(/\.pdf$/, "")
      .replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40);
    PAPERS.push({ paper_id: id, year: 2024,
      title: f.name.replace(/\.pdf$/i, "") + " (bạn vừa upload — demo)" });
    return json({ paper_id: id, chunks: 37 });
  }

  return json({ error: "demo không có endpoint này" });
};
})();
</script>'''


def main() -> None:
    src = (ROOT / "src" / "static" / "index.html").read_text()
    assert MARKER in src, f"index.html thiếu marker {MARKER}"
    demo = src.replace(MARKER, SHIM)
    demo = demo.replace("<title>Paper Assistant</title>",
                        "<title>Paper Assistant — UX Demo</title>")
    out = ROOT / "demo" / "ux_demo.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(demo)
    print(f"Đã sinh {out} ({len(demo):,} byte)")


if __name__ == "__main__":
    main()
