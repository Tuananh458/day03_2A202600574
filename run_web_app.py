import http.server
import socketserver
import json
import os
import urllib.parse
import traceback
import sys
from dotenv import load_dotenv

# Add src to system path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.core.openai_provider import OpenAIProvider
from src.agent.agent import ReActAgent
from src.tools.quiz_tools import TOOLS_METADATA, DB_FILE
from src.telemetry.metrics import tracker

# Load environment variables
load_dotenv()

PORT = 8000
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

class WebAppRequestHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path):
        # Override to serve files from the "web" subdirectory
        parsed_url = urllib.parse.urlparse(path)
        clean_path = parsed_url.path
        
        if clean_path == "/" or clean_path == "":
            return os.path.join(WEB_DIR, "index.html")
            
        # Security check: prevent directory traversal
        filename = os.path.basename(clean_path)
        if clean_path.endswith(".css"):
            return os.path.join(WEB_DIR, "style.css")
        elif clean_path.endswith(".js"):
            return os.path.join(WEB_DIR, "app.js")
            
        return os.path.join(WEB_DIR, filename)

    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        
        # API: get list of questions in bank
        if parsed_url.path == "/api/questions":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            
            questions = []
            if os.path.exists(DB_FILE):
                try:
                    with open(DB_FILE, "r", encoding="utf-8") as f:
                        questions = json.load(f)
                except Exception as e:
                    print(f"Error reading DB: {e}")
                    questions = []
                    
            self.wfile.write(json.dumps(questions, ensure_ascii=False).encode("utf-8"))
            return
            
        # Fallback to serving static files
        super().do_GET()

    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        
        if parsed_url.path == "/api/chat":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length).decode('utf-8')
            
            try:
                request_data = json.loads(post_data)
                user_message = request_data.get("message", "").strip()
                mode = request_data.get("mode", "react")
                provider_name = request_data.get("provider", "openai")
                model_name = request_data.get("model", "deepseek-v4-flash")
                
                # Check api key
                api_key = os.getenv("OPENAI_API_KEY")
                if not api_key:
                    raise ValueError("Không tìm thấy OPENAI_API_KEY trong file .env!")
                
                # Clear session metrics before starting a run
                tracker.session_metrics = []
                
                # Initialize Provider
                llm = OpenAIProvider(model_name=model_name, api_key=api_key)
                
                if mode == "react":
                    # Initialize Agent without strict step limit to allow saving multiple questions
                    agent = ReActAgent(llm=llm, tools=TOOLS_METADATA, max_steps=30)
                    stream_generator = agent.run_stream(user_message)
                else:
                    # Chatbot Baseline
                    def baseline_stream_generator():
                        yield {"type": "step_start", "step": 1}
                        yield {"type": "thought_chunk", "step": 1, "content": "Xử lý phản hồi chatbot thông thường...\n"}
                        
                        system_prompt = "Bạn là một AI Trợ lý giáo dục thông thường giúp giáo viên soạn đề thi."
                        llm_stream = llm.generate_stream(user_message, system_prompt=system_prompt)
                        
                        last_done = None
                        for chunk in llm_stream:
                            if chunk["type"] == "chunk":
                                delta = chunk.get("content", "")
                                if delta:
                                    yield {"type": "final_answer_chunk", "step": 1, "content": delta}
                            elif chunk["type"] == "done":
                                last_done = chunk
                                
                        tracker.track_request(
                            provider=last_done.get("provider", "unknown") if last_done else "openai",
                            model=llm.model_name,
                            usage=last_done.get("usage", {}) if last_done else {},
                            latency_ms=last_done.get("latency_ms", 0) if last_done else 0
                        )
                        
                        steps_list = [{
                            "step": 1,
                            "thought": "Xử lý phản hồi chatbot thông thường.",
                            "action": "Không gọi công cụ (Chatbot Baseline)",
                            "observation": "",
                            "metrics": tracker.session_metrics[-1] if tracker.session_metrics else None
                        }]
                        
                        yield {
                            "type": "done",
                            "response": last_done.get("content", "").strip() if last_done else "",
                            "steps": steps_list,
                            "telemetry": {
                                "latency_ms": last_done.get("latency_ms", 0) if last_done else 0,
                                "prompt_tokens": last_done.get("usage", {}).get("prompt_tokens", 0) if last_done else 0,
                                "completion_tokens": last_done.get("usage", {}).get("completion_tokens", 0) if last_done else 0,
                                "total_tokens": last_done.get("usage", {}).get("total_tokens", 0) if last_done else 0,
                                "cost_estimate": tracker.session_metrics[-1].get("cost_estimate", 0.0) if tracker.session_metrics else 0.0,
                                "steps": 1
                            }
                        }
                    
                    stream_generator = baseline_stream_generator()
                
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.send_header("X-Accel-Buffering", "no")
                self.end_headers()
                
                for event in stream_generator:
                    payload = f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    self.wfile.write(payload.encode("utf-8"))
                    self.wfile.flush()
                
            except Exception as e:
                traceback.print_exc()
                try:
                    try:
                        self.send_response(200)
                        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                        self.send_header("Cache-Control", "no-cache")
                        self.send_header("Connection", "keep-alive")
                        self.end_headers()
                    except Exception:
                        pass
                    
                    error_payload = {"type": "error", "message": str(e)}
                    self.wfile.write(f"data: {json.dumps(error_payload, ensure_ascii=False)}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except Exception as ex:
                    print(f"Error sending error event: {ex}")
            return
            
        self.send_response(404)
        self.end_headers()

class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

def run_server():
    # Configure console encoding to UTF-8 on Windows
    if sys.stdout.encoding != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    Handler = WebAppRequestHandler
    ThreadingTCPServer.allow_reuse_address = True
    
    with ThreadingTCPServer(("", PORT), Handler) as httpd:
        print("=========================================================================")
        print(f"🚀 SERVER CHATBOT ĐÃ ĐƯỢC KHỞI CHẠY THÀNH CÔNG!")
        print(f"👉 Địa chỉ truy cập: http://localhost:{PORT}")
        print(f"👉 Thư mục giao diện: {WEB_DIR}")
        print("=========================================================================")
        print("Nhấn Ctrl+C trong Terminal để tắt Server.\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")
            httpd.server_close()

if __name__ == "__main__":
    run_server()
