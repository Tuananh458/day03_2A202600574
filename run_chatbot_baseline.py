import os
import sys
from dotenv import load_dotenv

# Thêm thư mục hiện tại vào sys.path để import các module
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.core.openai_provider import OpenAIProvider
from src.telemetry.metrics import tracker

def main():
    # Cấu hình stdout hỗ trợ ký tự UTF-8 trên Windows console
    if sys.stdout.encoding != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    # Load environment variables
    load_dotenv()
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "your_openai_api_key_here":
        print("❌ Lỗi: Bạn chưa cấu hình OPENAI_API_KEY trong file .env!")
        return

    model_name = os.getenv("DEFAULT_MODEL", "gpt-4o")

    print("=========================================================================")
    print("💬 CHATBOT BASELINE (MÔ HÌNH HỘI THOẠI TRUYỀN THỐNG - KHÔNG REACT) 💬")
    print(f"Model: {model_name}")
    print("=========================================================================\n")

    # Khởi tạo OpenAI Provider
    llm = OpenAIProvider(model_name=model_name, api_key=api_key)

    # Hỗ trợ nhập yêu cầu động từ bàn phím
    default_query = (
        "Hãy thiết kế một đề kiểm tra Toán lớp 12 gồm 3 câu hỏi trắc nghiệm chủ đề 'Hàm số lũy thừa' "
        "(1 câu Dễ, 2 câu Trung bình). Yêu cầu: Ưu tiên lấy câu hỏi có sẵn từ ngân hàng câu hỏi trước. "
        "Nếu thiếu câu nào, hãy tự thiết kế câu mới chuẩn kiến thức lớp 12 và BẮT BUỘC lưu câu hỏi mới đó "
        "vào ngân hàng câu hỏi. Trình bày đề kiểm tra hoàn chỉnh kèm bảng đáp án và lời giải chi tiết."
    )
    
    print("Nhập yêu cầu của bạn (hoặc nhấn Enter để dùng yêu cầu mặc định):")
    try:
        user_query = input("> ").strip()
        if not user_query:
            user_query = default_query
    except (EOFError, OSError):
        user_query = default_query

    print("\n-------------------------------------------------------------------------")
    print(f"👉 Yêu cầu thực thi:\n{user_query}\n")
    print("⏳ Chatbot đang phản hồi trực tiếp (System 1 - Phản xạ nhanh)...")
    print("-------------------------------------------------------------------------")

    try:
        # Gọi trực tiếp LLM không có System Prompt mô tả Tools hay ReAct Loop
        system_prompt = "Bạn là một AI Trợ lý giáo dục thông thường giúp giáo viên soạn đề thi."
        response_dict = llm.generate(user_query, system_prompt=system_prompt)
        content = response_dict.get("content", "").strip()
        
        # Track metrics
        tracker.track_request(
            provider=response_dict.get("provider", "unknown"),
            model=llm.model_name,
            usage=response_dict.get("usage", {}),
            latency_ms=response_dict.get("latency_ms", 0)
        )

        print("\n=========================================================================")
        print("🎉 KẾT QUẢ PHẢN HỒI TỪ CHATBOT BASELINE:")
        print("=========================================================================\n")
        print(content)
        print("\n=========================================================================")
        print("📊 SỐ LIỆU ĐO LƯỜNG HIỆU NĂNG & TELEMETRY:")
        print("=========================================================================")
        
        for metric in tracker.session_metrics:
            print(f"  - Model: {metric['model']}")
            print(f"  - Total Tokens: {metric['total_tokens']}")
            print(f"  - Latency: {metric['latency_ms']} ms")
            print(f"  - Cost Estimate: ${metric['cost_estimate']:.5f}")
        print("=========================================================================\n")
        print("⚠️  NHẬN XÉT QUAN TRỌNG:")
        print("  1. Chatbot tự bịa ra (hallucinate) các câu hỏi chứ không thể lấy từ file question_bank.json thực tế.")
        print("  2. Chatbot KHÔNG thể tự động gọi công cụ save_question_to_bank để lưu câu hỏi mới vào ngân hàng.")
        print("=========================================================================\n")
        
    except Exception as e:
        print(f"\n❌ Lỗi trong quá trình chạy Chatbot: {e}")

if __name__ == "__main__":
    main()
