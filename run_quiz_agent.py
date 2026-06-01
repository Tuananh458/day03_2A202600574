import os
import sys
from dotenv import load_dotenv

# Thêm thư mục hiện tại vào sys.path để import các module
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.core.openai_provider import OpenAIProvider
from src.agent.agent import ReActAgent
from src.tools.quiz_tools import TOOLS_METADATA
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
        print("Vui lòng mở file .env và nhập OpenAI API Key của bạn để chạy Agent.")
        return

    provider_name = os.getenv("DEFAULT_PROVIDER", "openai")
    model_name = os.getenv("DEFAULT_MODEL", "gpt-4o")

    print("=========================================================================")
    print("🎓 AI TRỢ LÝ RA ĐỀ KIỂM TRA & QUẢN LÝ NGÂN HÀNG CÂU HỎI GIÁO DỤC 🎓")
    print(f"Provider: {provider_name.upper()} | Model: {model_name}")
    print("=========================================================================\n")

    # Khởi tạo OpenAI Provider
    llm = OpenAIProvider(model_name=model_name, api_key=api_key)
    
    # Khởi tạo ReAct Agent với bộ tools giáo dục
    agent = ReActAgent(llm=llm, tools=TOOLS_METADATA, max_steps=7)

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
    print("⏳ Agent đang suy luận và thực thi các bước ReAct (Thought-Action-Observation)...")
    print("-------------------------------------------------------------------------")

    try:
        # Chạy Agent
        final_response = agent.run(user_query)
        
        print("\n=========================================================================")
        print("🎉 KẾT QUẢ ĐỀ THI HOÀN CHỈNH TỪ AGENT:")
        print("=========================================================================\n")
        print(final_response)
        print("\n=========================================================================")
        print("📊 SỐ LIỆU ĐO LƯỜNG HIỆU NĂNG & TELEMETRY (SESSION METRICS):")
        print("=========================================================================")
        
        total_tokens = 0
        total_latency = 0
        total_cost = 0.0
        
        for idx, metric in enumerate(tracker.session_metrics):
            print(f"\nStep {idx + 1}:")
            print(f"  - Model: {metric['model']}")
            print(f"  - Prompt Tokens: {metric['prompt_tokens']}")
            print(f"  - Completion Tokens: {metric['completion_tokens']}")
            print(f"  - Total Tokens: {metric['total_tokens']}")
            print(f"  - Latency: {metric['latency_ms']} ms")
            print(f"  - Cost Estimate: ${metric['cost_estimate']:.5f}")
            
            total_tokens += metric['total_tokens']
            total_latency += metric['latency_ms']
            total_cost += metric['cost_estimate']
            
        print("\n-------------------------------------------------------------------------")
        print(f"📈 TỔNG CỘNG TOÀN BỘ PHIÊN LÀM VIỆC (SUMMARY):")
        print(f"  - Tổng số bước gọi LLM: {len(tracker.session_metrics)}")
        print(f"  - Tổng số Token tiêu hao: {total_tokens}")
        print(f"  - Tổng thời gian phản hồi: {total_latency} ms ({total_latency/1000:.2f} giây)")
        print(f"  - Tổng chi phí ước tính: ${total_cost:.5f}")
        print("=========================================================================\n")
        
    except Exception as e:
        print(f"\n❌ Lỗi trong quá trình chạy Agent: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
